"""Independent calendar collection. No messages are sent to Discord."""
import ast
import asyncio
from datetime import datetime, timezone, timedelta
from html import unescape
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select, func, delete
from sqlalchemy.dialects.sqlite import insert
from app.config import GUILD_ID
from app.branding import SITE
from app.db import Session, Setting, ImportedEvent, now


def load_sources(path=None):
    path = Path(path) if path else Path(__file__).resolve().parent.parent / 'config/sources.json'
    sources = json.loads(path.read_text())
    ids = set()
    for source in sources:
        key = source['id']
        if not re.fullmatch(r'[a-z0-9-]{1,80}', key) or key in ids:
            raise ValueError('Source IDs must be unique lowercase identifiers')
        ids.add(key)
        if source['adapter'] not in ('discord', 'ticketweb_calendar'):
            raise ValueError('Unsupported calendar adapter')
        if urlsplit(source['url']).scheme != 'https' or not urlsplit(source['url']).netloc:
            raise ValueError('Sources require HTTPS URLs')
        ZoneInfo(source['timezone'])
    return sources


SOURCES = load_sources()


def enabled(db, key):
    setting = db.get(Setting, 'feeds.' + key)
    return bool(setting and setting.value == 'true')


def set_enabled(db, key, value):
    db.merge(Setting(key='feeds.' + key, value='true' if value else 'false'))


def source_state(db, source):
    status = db.get(Setting, 'feeds.result.' + source['id'])
    result = json.loads(status.value) if status else {}
    count = db.scalar(select(func.count()).select_from(ImportedEvent).where(ImportedEvent.source_id == source['id'], ImportedEvent.cancelled == False))
    return {**source, 'collect': enabled(db, source['id'] + '.collect'),
            'publish': enabled(db, source['id'] + '.publish'), 'stored_count': count,
            'result': result}


def collection_enabled(db, source_id):
    return enabled(db, 'collection') and enabled(db, source_id + '.collect')


def parse_ticketweb_calendar(html, source):
    # Read literal data only: never execute scripts from a source page.
    literal = r"'((?:\\.|[^'\\])*)'"
    pattern = r"\bid\s*:\s*" + literal + r"\s*,\s*start\s*:\s*" + literal + r"\s*,\s*title\s*:\s*" + literal
    matches = list(re.finditer(pattern, html))
    if not matches:
        raise ValueError('No supported calendar data found; existing listings kept')
    events = []
    for match in matches:
        event_id, start, title = [unescape(ast.literal_eval("'" + raw + "'")) for raw in match.groups()]
        if not event_id.isdigit():
            raise ValueError('Unexpected event identifier')
        if 'private event' in title.casefold():
            continue
        stamp = datetime.fromisoformat(start)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=ZoneInfo(source['timezone']))
        events.append({'external_id': event_id, 'title': title[:250],
            'starts_at': stamp.astimezone(timezone.utc), 'location': source['name'],
            'source_url': source['url'] + '#tw-event-dialog-' + event_id, 'cancelled': False})
    return events


def parse_discord_events(data, guild_id):
    if not isinstance(data, list):
        raise ValueError('Unexpected Discord response')
    events = []
    for item in data:
        if str(item['guild_id']) != str(guild_id):
            raise ValueError('Discord response belongs to another server')
        event_id = str(item['id'])
        if not event_id.isdigit():
            raise ValueError('Unexpected Discord event ID')
        stamp = datetime.fromisoformat(item['scheduled_start_time'].replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            raise ValueError('Discord event timestamp requires a timezone')
        events.append({'external_id': event_id, 'title': item['name'][:250],
            'starts_at': stamp.astimezone(timezone.utc),
            'location': (item.get('entity_metadata') or {}).get('location', 'Discord')[:250],
            'source_url': f'https://discord.com/events/{guild_id}/{event_id}',
            'cancelled': item['status'] in (3, 4)})
    return events


async def fetch_source(source):
    headers = {'User-Agent': 'CommunityPlatform/0.1 (calendar collector)'}
    url = source['url']
    if source['adapter'] == 'discord':
        token = os.getenv('DISCORD_BOT_TOKEN', '')
        if not token or not GUILD_ID:
            raise ValueError('Discord bot token and guild ID must be configured')
        url = f'https://discord.com/api/v10/guilds/{GUILD_ID}/scheduled-events'
        headers['Authorization'] = 'Bot ' + token
    async with httpx.AsyncClient(timeout=25, follow_redirects=False) as client:
        async with client.stream('GET', url, headers=headers) as response:
            response.raise_for_status()
            chunks = bytearray()
            async for chunk in response.aiter_bytes():
                chunks.extend(chunk)
                if len(chunks) > 4_000_000:
                    raise ValueError('Source response exceeds 4 MB limit')
    if source['adapter'] == 'discord':
        return parse_discord_events(json.loads(chunks), GUILD_ID)
    return parse_ticketweb_calendar(chunks.decode('utf-8'), source)


def venue_cutoff(stamp=None):
    return (stamp or now()) - timedelta(days=SITE.get('venue_retention_days', 30))


def prune_venue_events(db, stamp=None):
    """Remove expired venue imports only; Discord and community records are separate."""
    venue_ids = [s['id'] for s in SOURCES if s['adapter'] != 'discord']
    return db.execute(delete(ImportedEvent).where(
        ImportedEvent.source_id.in_(venue_ids), ImportedEvent.starts_at < venue_cutoff(stamp))).rowcount


def save_events(db, source, events):
    cutoff = venue_cutoff()
    for event in events:
        stamp = event['starts_at']
        stamp = stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp
        if source['adapter'] != 'discord' and stamp < cutoff:
            continue
        values = {**event, 'source_id': source['id'], 'updated_at': now()}
        statement = insert(ImportedEvent).values(**values)
        db.execute(statement.on_conflict_do_update(
            index_elements=['source_id', 'external_id'],
            set_={k: v for k, v in values.items() if k not in ('source_id', 'external_id')}))
    # Discord returns a complete snapshot: retire removed scheduled Events.
    # Venue pages may be partial, so absence from a venue page never deletes data.
    if source['adapter'] == 'discord':
        seen = {e['external_id'] for e in events}
        for old in db.scalars(select(ImportedEvent).where(ImportedEvent.source_id == source['id'])):
            if old.external_id not in seen and not old.external_id.startswith('manual-'):
                old.cancelled = True


async def collect_source(source_id):
    source = next((s for s in SOURCES if s['id'] == source_id), None)
    if source is None:
        raise ValueError('Unknown source')
    with Session() as db:
        if not collection_enabled(db, source_id):
            return False
    try:
        events = await fetch_source(source)
        error = ''
    except httpx.HTTPStatusError as exc:
        events, error = [], f'HTTP {exc.response.status_code}; existing listings kept'
    except httpx.RequestError:
        events, error = [], 'Network request failed; existing listings kept'
    except (ValueError, KeyError, TypeError, SyntaxError) as exc:
        events, error = [], 'Could not read source: ' + str(exc)[:180]
    with Session.begin() as db:
        # Respect a pause pressed while the request was in flight.
        if not collection_enabled(db, source_id):
            return False
        if not error:
            save_events(db, source, events)
        previous = db.get(Setting, 'feeds.result.' + source_id)
        last = json.loads(previous.value) if previous else {}
        result = {'attempted_at': now().isoformat(), 'error': error,
                  'last_success': last.get('last_success') if error else now().isoformat(),
                  'received': len(events) if not error else 0}
        db.merge(Setting(key='feeds.result.' + source_id, value=json.dumps(result)))
    return not error


def automatic_pull_due(db, source, stamp):
    """Source pulls run once each configured weekday; manual pulls bypass this gate."""
    if not collection_enabled(db, source['id']):
        return False
    local = stamp.astimezone(ZoneInfo(SITE.get('calendar_timezone', 'UTC')))
    schedule = SITE.get('calendar_collection', {'weekday': 1, 'hour': 9})
    if local.weekday() != schedule['weekday'] or local.hour < schedule['hour']:
        return False
    previous = db.get(Setting, 'feeds.result.' + source['id'])
    attempted = json.loads(previous.value).get('attempted_at') if previous else None
    return not attempted or datetime.fromisoformat(attempted).astimezone(local.tzinfo).date() != local.date()


async def collect_enabled_sources():
    with Session.begin() as db:
        prune_venue_events(db)
    for source in SOURCES:
        with Session() as db:
            due = automatic_pull_due(db, source, now())
        if due:
            await collect_source(source['id'])


def calendar_events(db, start, end=None, limit=None):
    if not enabled(db, 'website'):
        return []
    sources = {s['id']: s for s in SOURCES if enabled(db, s['id'] + '.publish')}
    query = select(ImportedEvent).where(ImportedEvent.cancelled == False, ImportedEvent.suppressed == False,
        ImportedEvent.starts_at >= start, ImportedEvent.source_id.in_(sources))
    if end is not None:
        query = query.where(ImportedEvent.starts_at < end)
    query = query.order_by(ImportedEvent.starts_at, ImportedEvent.source_id, ImportedEvent.external_id)
    if limit is not None:
        query = query.limit(limit)
    records = db.scalars(query).all()
    return [SimpleNamespace(id=None, title=e.title, starts_at=e.starts_at,
            external_url=e.source_url, source_name=sources[e.source_id]['name'], source_id=e.source_id, is_community=sources[e.source_id]['adapter'] == 'discord', location=e.location)
            for e in records]


async def run_worker():
    while True:
        with Session.begin() as db:
            db.merge(Setting(key='feeds.worker_seen', value=now().isoformat()))
        await collect_enabled_sources()
        await asyncio.sleep(900)


if __name__ == '__main__':
    asyncio.run(run_worker())
