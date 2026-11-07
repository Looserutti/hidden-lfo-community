from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session as DBSession
from app.db import Member, Event, PerformanceEvent, Registration, now

def member(db: DBSession, discord_id: int) -> Member:
    m = db.get(Member, discord_id)
    if m is None:
        m = Member(discord_id=discord_id)
        db.add(m)
        db.flush()
    return m

def sync_member_identity(db: DBSession, discord_member) -> Member:
    """Names are labels, never identity keys or evidence of activity."""
    record = member(db, discord_member.id)
    record.discord_username = discord_member.name
    record.server_display_name = discord_member.display_name
    return record


def touch(db: DBSession, discord_id: int, field='last_server_activity'):
    m = member(db, discord_id)
    setattr(m, field, now())
    db.commit()

def rsvp(db: DBSession, event_id: int, discord_id: int, verified: bool, attending: bool) -> str:
    if not verified:
        return 'Please acknowledge the server rules before registering.'
    # SQLite has no SELECT FOR UPDATE. Acquire the write lock before checking capacity.
    # This serializes RSVP writes across the bot's SQLite connections/processes.
    try:
        if db.bind.dialect.name == 'sqlite':
            db.connection().exec_driver_sql('BEGIN IMMEDIATE')
        event = db.get(Event, event_id)
        if not event or not event.published:
            db.rollback()
            return 'This event is not available.'
        if attending and db.get(PerformanceEvent, event_id):
            db.rollback()
            return 'You can attend without an RSVP. To play, register on the performer stage board.'
        reg = db.scalar(select(Registration).where(Registration.event_id == event_id, Registration.discord_id == discord_id))
        if attending:
            if reg and reg.status == 'going':
                db.rollback()
                return 'You are already registered.'
            count = db.scalar(select(func.count()).select_from(Registration).where(Registration.event_id == event_id, Registration.status == 'going')) or 0
            if event.capacity is not None and count >= event.capacity:
                db.rollback()
                return 'This event is full.'
            if reg:
                reg.status = 'going'
            else:
                db.add(Registration(event_id=event_id, discord_id=discord_id, status='going'))
            db.commit()
            return 'You are registered!'
        if not reg or reg.status != 'going':
            db.rollback()
            return 'You do not have an active registration.'
        reg.status = 'cancelled'
        db.commit()
        return 'Your registration has been cancelled.'
    except (IntegrityError, OperationalError):
        db.rollback()
        return 'Registration is busy. Please try again.'

def inactive_members(db: DBSession, grace_days=90, inactive_days=60):
    cutoff = now() - timedelta(days=inactive_days)
    grace = now() - timedelta(days=grace_days)
    results = []
    for m in db.scalars(select(Member).where(Member.exempt == False)):
        if not m.joined_at or m.joined_at.replace(tzinfo=timezone.utc) > grace:
            continue
        observations = [t.replace(tzinfo=timezone.utc) for t in (m.last_server_activity, m.last_observed_online) if t]
        # Unknown historical activity must not be classified as inactivity.
        if observations and max(observations) < cutoff:
            results.append(m)
    return results


def event_announcement(e: Event, count: int | None) -> str:
    start = e.starts_at
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    stamp = int(start.timestamp())
    details = (f'**{e.title}**\n{e.description}\n'
               f'Starts: <t:{stamp}:F> (<t:{stamp}:R>)\nLocation: {e.location}')
    if count is None:
        return (details[:1850] + '\nAttendance is open without an RSVP.')[:1950]
    cap = str(e.capacity) if e.capacity is not None else 'unlimited'
    return (f'**{e.title}**\n{e.description}\n'
            f'Starts: <t:{stamp}:F> (<t:{stamp}:R>)\n'
            f'Location: {e.location}\nRegistered: {count} / {cap}\n'
            'Use the buttons below to register or cancel your RSVP.')[:1950]
