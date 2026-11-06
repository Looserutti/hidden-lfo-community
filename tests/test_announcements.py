from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import pytest
from app.db import Base,Event,EventSubmission
from app.announcements import approved_member_event,announcement_content


def test_approval_required_and_rollout_cutoff_prevents_backlog():
    engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    with Session(engine) as db:
        event=Event(title='Member concert',description='Music',starts_at=datetime.now(timezone.utc)+timedelta(days=2),location='Venue',published=True)
        db.add(event);db.flush()
        assert not approved_member_event(db,event.id)
        submission=EventSubmission(interaction_id='123',submitted_by=1,submitted_name='Member',title='Member concert',description='',starts_at=event.starts_at,location='Venue',status='pending',event_id=event.id)
        db.add(submission);db.flush()
        assert not approved_member_event(db,event.id)
        submission.status='approved';submission.reviewed_at=datetime(2026,11,6,tzinfo=timezone.utc);db.flush()
        assert approved_member_event(db,event.id)
        assert not approved_member_event(db,event.id,'2026-11-07T00:00:00Z')
        assert approved_member_event(db,event.id,'2026-11-05T00:00:00Z')
        with pytest.raises(ValueError):approved_member_event(db,event.id,'2026-11-05')
        text=announcement_content(event,0,True)
        assert 'New member event' in text and 'Member concert' in text and 'Starts:' in text
        assert 'New member event' not in announcement_content(event,0)
        event.description='x'*4000
        assert len(announcement_content(event,0,True))<=1950


def test_publisher_posts_approved_member_once_and_skips_other_events(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from sqlalchemy.orm import sessionmaker
    from bot import main
    engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    sessions=sessionmaker(engine)
    with sessions.begin() as db:
        for title in ['Approved','Dashboard only','Pending']:
            db.add(Event(title=title,starts_at=datetime.now(timezone.utc)+timedelta(days=2),location='Venue',published=True))
        db.flush()
        db.add(EventSubmission(interaction_id='approved',submitted_by=1,submitted_name='Member',title='Approved',description='',starts_at=datetime.now(timezone.utc)+timedelta(days=2),location='Venue',status='approved',event_id=1,reviewed_at=datetime.now(timezone.utc)))
    class Channel:
        id=42
        def __init__(self):self.sent=[]
        async def send(self,content,**kwargs):
            self.sent.append(content)
            assert not kwargs['allowed_mentions'].everyone
            return SimpleNamespace(id=99)
    channel=Channel()
    monkeypatch.setattr(main,'Session',sessions)
    monkeypatch.setattr(main.discord,'TextChannel',Channel)
    monkeypatch.setattr(main.bot,'get_channel',lambda _:channel)
    monkeypatch.setattr(main,'EVENT_PUBLISHING_ENABLED',False)
    monkeypatch.setattr(main,'MEMBER_EVENT_ANNOUNCEMENTS_ENABLED',True)
    monkeypatch.setattr(main,'MEMBER_EVENT_ANNOUNCEMENTS_SINCE','2026-01-01T00:00:00Z')
    async def refresh(_):pass
    monkeypatch.setattr(main,'refresh_event_message',refresh)
    asyncio.run(main.publish_events.coro())
    asyncio.run(main.publish_events.coro())
    assert len(channel.sent)==1 and 'New member event' in channel.sent[0]
    with sessions() as db:assert db.get(Event,1).discord_message_id==99
