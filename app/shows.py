"""Published website calendar listings for the member-facing shows command."""
from datetime import timedelta, timezone
from types import SimpleNamespace
from sqlalchemy import select
from app.db import Event
from app import feeds
from app.config import BASE_URL


def upcoming_shows(db, start):
    end = start + timedelta(days=7)
    community = db.scalars(select(Event).where(
        Event.published == True, Event.starts_at >= start, Event.starts_at < end)).all()
    rows = [SimpleNamespace(title=e.title, starts_at=e.starts_at, source_name=e.location,
                            external_url=f'{BASE_URL}/events/{e.id}') for e in community]
    rows.extend(feeds.calendar_events(db, start, end))
    return sorted(rows, key=lambda e: e.starts_at.replace(tzinfo=timezone.utc))
