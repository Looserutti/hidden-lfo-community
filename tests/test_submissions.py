import asyncio
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from app.db import Base, Event, EventSubmission
from app.submissions import submit_event, review_submission
from app.shows import upcoming_shows
from bot import events


@pytest.fixture
def store(tmp_path):
    engine=create_engine(f"sqlite:///{tmp_path / 'proposals.db'}")
    Base.metadata.create_all(engine)
    sessions=sessionmaker(engine,expire_on_commit=False)
    yield sessions
    engine.dispose()


def proposal(db,key='1',user=123):
    return submit_event(db,interaction_id=key,submitted_by=user,submitted_name='Stage Name',
        title='Community Show',description='Live music', starts_at=datetime.now(timezone.utc)+timedelta(days=2),location='Venue')


def test_pending_hidden_approved_once_and_rejection(store):
    with store.begin() as db:
        item=proposal(db)
        item_id=item.id
        assert proposal(db).id==item_id
    with store() as db:
        assert upcoming_shows(db,datetime.now(timezone.utc))==[]
    with store.begin() as db:
        review_submission(db,item_id,999,True)
    with store() as db:
        item=db.get(EventSubmission,item_id)
        assert item.status=='approved' and item.reviewed_by==999 and item.reviewed_at
        assert db.get(Event,item.event_id).published
        assert len(upcoming_shows(db,datetime.now(timezone.utc)))==1
    with pytest.raises(ValueError,match='already reviewed'):
        with store.begin() as db:
            review_submission(db,item_id,999,True)
    with store.begin() as db:
        assert db.scalar(select(func.count()).select_from(Event))==1
        rejected=proposal(db,'2')
        review_submission(db,rejected.id,999,False)
        assert rejected.event_id is None and rejected.status=='rejected'


def test_submission_limits_and_future_date(store):
    with store.begin() as db:
        for i in range(5): proposal(db,str(i))
        with pytest.raises(ValueError,match='five events'):
            proposal(db,'6')
        with pytest.raises(ValueError,match='future'):
            submit_event(db,interaction_id='past',submitted_by=456,submitted_name='Name',title='Past',
                         description='',starts_at=datetime.now(timezone.utc)-timedelta(days=1),location='Venue')


def test_discord_command_guard_and_modal_submission(store,monkeypatch):
    class Tree:
        def command(self,**kwargs): return lambda f:f
    command=events.register_events(SimpleNamespace(tree=Tree()))
    interaction=SimpleNamespace(id=555,user=SimpleNamespace(id=123,display_name='Stage Name'),
        response=SimpleNamespace(send_message=AsyncMock(),send_modal=AsyncMock(),defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()))
    monkeypatch.setattr(events,'verified_member',lambda i:False)
    asyncio.run(command(interaction))
    interaction.response.send_modal.assert_not_called()
    assert interaction.response.send_message.call_args.kwargs['ephemeral']
    monkeypatch.setattr(events,'verified_member',lambda i:True)
    monkeypatch.setattr(events,'Session',store)
    monkeypatch.setattr(events,'SITE',{'name':'Community','calendar_timezone':'UTC'})
    asyncio.run(command(interaction))
    modal=interaction.response.send_modal.call_args.args[0]
    assert len(modal.children)==5
    future=datetime.now(timezone.utc)+timedelta(days=2)
    for key,value in {'event_title':'Member Show','description':'Music', 'date':future.strftime('%Y-%m-%d'),
                      'time':'20:00','location':'Venue'}.items():
        setattr(modal,key,SimpleNamespace(value=value))
    asyncio.run(modal.on_submit(interaction))
    assert interaction.followup.send.call_args.kwargs['ephemeral']
    with store() as db:
        assert db.scalar(select(EventSubmission)).status=='pending'
        assert db.scalar(select(func.count()).select_from(Event))==0


def test_retry_preserves_form_values(monkeypatch):
 monkeypatch.setattr(events,'verified_member',lambda i:True)
 interaction=SimpleNamespace(user=SimpleNamespace(id=123),response=SimpleNamespace(send_modal=AsyncMock()))
 async def run():
  retry=events.RetryEvent(123,{'event_title':'My show','date':'tomorrow','time':'7pm','description':'Keep this'})
  await retry.edit.callback(interaction)
  modal=interaction.response.send_modal.call_args.args[0]
  assert modal.event_title.default=='My show' and modal.date.default=='tomorrow'
  assert modal.time.default=='7pm' and modal.description.default=='Keep this'
 asyncio.run(run())
