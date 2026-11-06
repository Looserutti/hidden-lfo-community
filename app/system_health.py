"""Read-only staff health summaries; never exposes backup credentials or raw errors."""
import json
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from app import feeds
from app.branding import SITE
from app.db import Setting


def stamp(value):
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).replace(tzinfo=timezone.utc) if '+' not in value and not value.endswith('Z') else datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError):
        return None


def check(name, success, failure, age, current):
    good, bad = stamp(success), stamp(failure)
    state, label = ('neutral', 'Not yet verified')
    if bad and (not good or bad > good):
        state, label = 'error', 'Failed — needs attention'
    elif good:
        state, label = ('error', 'Overdue — needs attention') if current-good > age else ('ok', 'Healthy')
    return dict(name=name, state=state, label=label, last_success=good.isoformat() if good else None)


def summary(db, current=None):
    current = current or datetime.now(timezone.utc)
    cards=[]
    try:
        backup=json.loads(Path(os.getenv('SYSTEM_HEALTH_FILE', '/run/community-health/backup.json')).read_text())
    except (OSError, ValueError):
        backup={}
    for name, key, age in [('Complete backup', 'last-success', timedelta(hours=36)), ('Off-server copy', 'last-offsite-success', timedelta(hours=36)), ('Recovery verification', 'last-verified', timedelta(days=35))]:
        cards.append(check(name, backup.get(key), backup.get('last-failure') if key!='last-verified' else backup.get('last-verify-failure'), age, current))
    preview=os.getenv('SITE_ENVIRONMENT')=='preview'
    for name,key,age in [('Discord bot','bot.worker_seen',timedelta(minutes=5)),('Calendar collector','feeds.worker_seen',timedelta(minutes=35))]:
        row=db.get(Setting,key)
        card=check(name,row.value if row else None,None,age,current)
        if preview: card.update(state='neutral',label='Not running in preview',last_success=None)
        cards.append(card)
    zone=ZoneInfo(SITE.get('calendar_timezone','UTC'))
    local=current.astimezone(zone)
    schedule=SITE.get('calendar_collection',{'weekday':1,'hour':9})
    due=(local-timedelta(days=(local.weekday()-schedule['weekday'])%7)).replace(hour=schedule['hour'],minute=0,second=0,microsecond=0)
    if due>local: due-=timedelta(days=7)
    for source in feeds.SOURCES:
        row=db.get(Setting,'feeds.result.'+source['id'])
        try: result=json.loads(row.value) if row else {}
        except ValueError: result={}
        card=check(source['name'],result.get('last_success'),result.get('attempted_at') if result.get('error') else None,timedelta(days=8),current)
        if not feeds.collection_enabled(db,source['id']): card.update(state='neutral',label='Paused')
        elif not result.get('error') and current>due+timedelta(hours=2) and (not stamp(result.get('last_success')) or stamp(result.get('last_success'))<due): card.update(state='error',label='Scheduled pull overdue')
        card['detail']='Weekly collection · '+('Published' if feeds.enabled(db,source['id']+'.publish') else 'Publication paused')
        cards.append(card)
    return cards
