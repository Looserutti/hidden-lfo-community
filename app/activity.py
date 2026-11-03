"""Observation-based activity review; no claims about unobserved history."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.db import Member

def utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def classify(m: Member, at: datetime | None = None, grace_days=90, inactive_days=60):
    at = utc(at) or datetime.now(timezone.utc)
    joined = utc(m.joined_at)
    seen = max((utc(x) for x in (m.last_server_activity, m.last_observed_online) if x), default=None)
    if m.exempt:
        status = 'exempt'
    elif joined is None:
        status = 'unknown'
    elif joined > at - timedelta(days=grace_days):
        status = 'grace'
    elif seen is None:
        status = 'unknown'
    elif seen < at - timedelta(days=inactive_days):
        status = 'review'
    else:
        status = 'active'
    return {'discord_id': m.discord_id, 'status': status, 'joined_at': joined,
            'last_server_activity': utc(m.last_server_activity),
            'last_observed_online': utc(m.last_observed_online), 'last_seen': seen,
            'exempt': bool(m.exempt)}

def report(db, at=None):
    rows = [classify(m, at=at) for m in db.scalars(select(Member).order_by(Member.discord_id)).all()]
    totals = {s: sum(r['status'] == s for r in rows) for s in ('active','review','grace','unknown','exempt')}
    return rows, totals

def report_text(totals):
    return ('Weekly activity review (observations only; no automatic removals)\n'
            f"Active: {totals['active']} | Review: {totals['review']} | "
            f"Grace: {totals['grace']} | Unknown: {totals['unknown']} | Exempt: {totals['exempt']}\n"
            'Presence is not server-specific; invisible/offline activity may be missed.')
