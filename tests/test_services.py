from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base, Event, Member
from app.services import rsvp, inactive_members

def test_rsvp_and_inactivity():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine)
    with Session() as db:
        db.add(Event(id=1, title='Test', starts_at=datetime.now(timezone.utc), published=True, capacity=1))
        db.add(Member(discord_id=5, joined_at=datetime.now(timezone.utc)-timedelta(days=120), last_server_activity=datetime.now(timezone.utc)-timedelta(days=80)))
        db.commit()
        assert rsvp(db, 1, 5, True, True) == 'You are registered!'
        assert rsvp(db, 1, 6, True, True) == 'This event is full.'
        assert len(inactive_members(db)) == 1


def test_event_announcement_format():
    from app.services import event_announcement
    e = Event(id=2, title='Movie Night', description='Bring snacks',
              starts_at=datetime(2026, 11, 14, 19, tzinfo=timezone.utc),
              location='Voice Chat', capacity=20)
    announcement = event_announcement(e, 7)
    assert 'Movie Night' in announcement
    assert 'Registered: 7 / 20' in announcement
    assert 'Voice Chat' in announcement
    assert '<t:' in announcement


def test_event_field_validation():
    import os
    os.environ.setdefault('SESSION_SECRET', 'test-secret-only-do-not-use-in-production')
    from fastapi import HTTPException
    from app.web import parse_event_fields
    fields = parse_event_fields(' Test ', 'Description', '2026-11-14T19:00:00-08:00', 'Discord', '30')
    assert fields['title'] == 'Test'
    assert fields['capacity'] == 30
    try:
        parse_event_fields('Test', '', '2026-11-14T19:00:00', 'Discord', '')
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError('Timezone-naive start must be rejected')
