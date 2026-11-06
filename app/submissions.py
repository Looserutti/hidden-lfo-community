"""Member submissions and atomic administrator approval."""
from datetime import timezone
from sqlalchemy import select, func, update
from app.db import EventSubmission, Event, now


def submit_event(db, *, interaction_id, submitted_by, submitted_name, title, description, starts_at, location):
    existing = db.scalar(select(EventSubmission).where(EventSubmission.interaction_id == str(interaction_id)))
    if existing:
        return existing
    if not title.strip() or len(title) > 200 or not location.strip() or len(location) > 250 or len(description) > 4000:
        raise ValueError('Use a title, venue or location, and a description of at most 4,000 characters.')
    if starts_at.tzinfo is None or starts_at <= now():
        raise ValueError('Choose a future date and time.')
    pending = db.scalar(select(func.count()).select_from(EventSubmission).where(
        EventSubmission.submitted_by == submitted_by, EventSubmission.status == 'pending'))
    if pending >= 5:
        raise ValueError('You already have five events awaiting review. Please wait for an admin to review them.')
    submission = EventSubmission(interaction_id=str(interaction_id), submitted_by=submitted_by,
        submitted_name=submitted_name[:128], title=title.strip(), description=description,
        starts_at=starts_at.astimezone(timezone.utc), location=location.strip())
    db.add(submission)
    db.flush()
    return submission


def review_submission(db, submission_id, reviewer, approve, fields=None):
    # Claim the pending row before creating an event, so repeat/concurrent clicks cannot publish twice.
    result = db.execute(update(EventSubmission).where(EventSubmission.id == submission_id,
        EventSubmission.status == 'pending').values(status='approved' if approve else 'rejected',
        reviewed_by=reviewer, reviewed_at=now()))
    if result.rowcount != 1:
        raise ValueError('This submission was already reviewed or no longer exists.')
    submission = db.get(EventSubmission, submission_id)
    if approve:
        values = fields or dict(title=submission.title, description=submission.description,
            starts_at=submission.starts_at, location=submission.location, capacity=None)
        start = values['starts_at'].replace(tzinfo=timezone.utc)
        if start <= now():
            raise ValueError('Choose a future date and time before approving this event.')
        event = Event(**values, published=True)
        db.add(event)
        db.flush()
        submission.event_id = event.id
    return submission
