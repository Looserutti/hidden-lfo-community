"""Select native events eligible for Discord announcements; imports are never selected."""
from datetime import datetime, timezone
from sqlalchemy import select
from app.db import EventSubmission
from app.services import event_announcement
from app.config import BASE_URL


def approved_member_event(db, event_id, since=''):
    query=select(EventSubmission.id).where(EventSubmission.event_id==event_id, EventSubmission.status=='approved')
    if since:
        cutoff=datetime.fromisoformat(since.replace('Z','+00:00'))
        if cutoff.tzinfo is None:
            raise ValueError('Announcement cutoff requires an explicit timezone')
        query=query.where(EventSubmission.reviewed_at>=cutoff.astimezone(timezone.utc))
    return db.scalar(query.limit(1)) is not None


def announcement_content(event, count, member_event=False):
    prefix='**New member event posted to the Community Calendar**\nAdmin-approved community submission.\n\n' if member_event else ''
    link=f'\nView event: {BASE_URL}/events/{event.id}' if member_event else ''
    return prefix+event_announcement(event,count)[:1950-len(prefix)-len(link)]+link
