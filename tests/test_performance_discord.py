import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from datetime import timedelta
import pytest
import discord
from sqlalchemy import select, func
from app.db import PerformanceNotice, PerformanceEvent
from app import performances as service
from bot import performances as commands
from test_performances import store, act, prepare, state, START


def test_unauthorized_discord_stage_button_cannot_start(store, act, monkeypatch):
    prepare(act)
    monkeypatch.setattr(commands,'Session',store)
    monkeypatch.setattr(commands,'member_access',lambda _:True)
    monkeypatch.setattr(commands,'ADMIN_IDS',{99})
    monkeypatch.setattr(commands,'VERIFIED_ROLE_ID',5)
    s=state(store)
    interaction=SimpleNamespace(user=SimpleNamespace(id=10,roles=[SimpleNamespace(id=5)]),
        channel_id=123,id=1234,response=SimpleNamespace(defer=AsyncMock(),send_message=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()))
    asyncio.run(commands.run_action(interaction,1,'start',s['config'].revision,s['next']['id']))
    assert 'Organizer access required' in interaction.followup.send.call_args.args[0]
    assert state(store)['current'] is None


def test_wrong_channel_rejected(store, monkeypatch):
    monkeypatch.setattr(commands,'Session',store)
    monkeypatch.setattr(commands,'member_access',lambda _:True)
    interaction=SimpleNamespace(channel_id=999,response=SimpleNamespace(send_message=AsyncMock()))
    asyncio.run(commands.run_action(interaction,1,'register'))
    assert 'assigned performance channel' in interaction.response.send_message.call_args.args[0]


class Channel:
    guild=SimpleNamespace(id=77)
    def __init__(self): self.messages=[]; self.fail=False
    async def history(self,limit):
        for message in reversed(self.messages[-limit:]): yield message
    async def send(self,content,**kwargs):
        if self.fail: raise discord.HTTPException(SimpleNamespace(status=503,reason='offline'),'offline')
        message=SimpleNamespace(id=len(self.messages)+100, content=content, author=SimpleNamespace(id=7))
        self.messages.append(message)
        return message


def test_notice_send_retry_dedup_and_restart_recovery(store, act, monkeypatch):
    prepare(act)
    s=state(store)
    act('start',99,at=START,target=s['next']['id'])
    with store() as db:
        service.lock(db);service.queue_notices(db,1,START+timedelta(minutes=5));db.commit()
    channel=Channel(); bot=SimpleNamespace(user=SimpleNamespace(id=7),get_channel=lambda _:channel)
    monkeypatch.setattr(commands,'Session',store)
    monkeypatch.setattr(commands.discord,'TextChannel',Channel)
    monkeypatch.setattr(commands,'GUILD_ID',77)
    channel.fail=True
    with pytest.raises(discord.HTTPException): asyncio.run(commands.deliver_notices(bot,1))
    with store() as db: assert db.scalar(select(func.count()).select_from(PerformanceNotice).where(PerformanceNotice.sent_at.is_not(None))) == 0
    channel.fail=False
    asyncio.run(commands.deliver_notices(bot,1))
    assert len(channel.messages)==2
    asyncio.run(commands.deliver_notices(bot,1))
    assert len(channel.messages)==2
    # Simulate a crash after sending but before saving the delivery receipt.
    with store.begin() as db:
        row=db.scalar(select(PerformanceNotice).where(PerformanceNotice.sent_at.is_not(None)))
        row.sent_at=None;row.message_id=None
    asyncio.run(commands.deliver_notices(bot,1))
    assert len(channel.messages)==2


def test_stage_text_preserves_manual_start_and_original_reference(store, act):
    prepare(act)
    text=commands.stage_text(state(store))
    assert 'Transition / house music' in text
    assert '**NEXT:** <@10>' in text and '**ON DECK:** <@11>' in text
    assert 'Only the organizer starts' in text


def test_draft_event_does_not_create_board(store, monkeypatch):
    from app.db import Event
    with store.begin() as db: db.get(Event,1).published=False
    monkeypatch.setattr(commands,'Session',store)
    bot=SimpleNamespace(get_channel=lambda _:pytest.fail('Draft must not access Discord'))
    asyncio.run(commands.refresh_board(bot,1))


def test_existing_board_is_edited_and_send_before_save_is_recovered(store, act, monkeypatch):
    prepare(act)
    monkeypatch.setattr(commands,'Session',store)
    monkeypatch.setattr(commands.discord,'TextChannel',Channel)
    monkeypatch.setattr(commands,'GUILD_ID',77)
    channel=Channel()
    class Message:
        def __init__(self, identifier, content, view):
            self.id=identifier;self.content=content;self.author=SimpleNamespace(id=7)
            self.components=[SimpleNamespace(to_dict=lambda row=row:row) for row in view.to_components()]
            self.edits=0
        async def edit(self,content,view,**kwargs):
            self.content=content;self.edits+=1
            self.components=[SimpleNamespace(to_dict=lambda row=row:row) for row in view.to_components()]
    async def send(content,view,**kwargs):
        message=Message(100,content,view);channel.messages.append(message);return message
    async def fetch(identifier):
        return next(m for m in channel.messages if m.id==identifier)
    channel.send=send;channel.fetch_message=fetch
    bot=SimpleNamespace(user=SimpleNamespace(id=7),get_channel=lambda _:channel)
    asyncio.run(commands.refresh_board(bot,1))
    assert len(channel.messages)==1
    with store.begin() as db: db.get(PerformanceEvent,1).board_message_id=None
    asyncio.run(commands.refresh_board(bot,1))
    assert len(channel.messages)==1
    with store() as db: assert db.get(PerformanceEvent,1).board_message_id==100
    # New state updates the saved board instead of posting another.
    act('notready',10)
    asyncio.run(commands.refresh_board(bot,1))
    assert len(channel.messages)==1 and 'not ready' in channel.messages[0].content


@pytest.mark.parametrize('enabled',[False,True])
def test_performance_worker_requires_explicit_opt_in(monkeypatch, enabled):
    from unittest.mock import MagicMock
    from bot import main
    db=MagicMock();db.scalars.return_value.all.return_value=[]
    session=MagicMock();session.__enter__.return_value=db
    monkeypatch.setattr(main,'Session',lambda:session)
    monkeypatch.setattr(main,'PERFORMANCE_MANAGEMENT_ENABLED',enabled)
    monkeypatch.setattr(main,'EVENT_PUBLISHING_ENABLED',False)
    monkeypatch.setattr(main,'MEMBER_EVENT_ANNOUNCEMENTS_ENABLED',False)
    monkeypatch.setattr(main,'STAFF_REPORTS_ENABLED',False)
    monkeypatch.setattr(main,'PROJECT_ANNOUNCEMENTS_CHANNEL_ID',0)
    worker=MagicMock();worker.is_running.return_value=False
    monkeypatch.setattr(main,'performance_worker',worker,raising=False)
    bot=SimpleNamespace(add_view=MagicMock(),tree=SimpleNamespace(sync=AsyncMock()))
    asyncio.run(main.CommunityBot.setup_hook(bot))
    assert worker.start.call_count == int(enabled)


def test_unpublish_during_discord_history_lookup_suppresses_notice(store, act, monkeypatch):
    from app.db import Event
    prepare(act)
    act('start',99,at=START,target=state(store)['next']['id'])
    with store() as db:
        service.lock(db);service.queue_notices(db,1,START+timedelta(minutes=5));db.commit()
    channel=Channel()
    async def history(limit):
        with store.begin() as db: db.get(Event,1).published=False
        if False: yield None
    channel.history=history
    monkeypatch.setattr(commands,'Session',store)
    monkeypatch.setattr(commands.discord,'TextChannel',Channel)
    monkeypatch.setattr(commands,'GUILD_ID',77)
    bot=SimpleNamespace(user=SimpleNamespace(id=7),get_channel=lambda _:channel)
    asyncio.run(commands.deliver_notices(bot,1))
    assert channel.messages==[]
    with store() as db:
        assert db.scalar(select(func.count()).select_from(PerformanceNotice).where(PerformanceNotice.sent_at.is_not(None)))==0


def test_one_event_database_failure_does_not_starve_other_boards(store, monkeypatch):
    from sqlalchemy.exc import OperationalError
    with store() as db:
        service.configure(db,2,99,authorized=True,channel_id=456,ends_at=START+timedelta(hours=4))
    original=service.queue_notices
    def queue(db,event_id,at):
        if event_id==1: raise OperationalError('synthetic lock failure',{},Exception('test'))
        return original(db,event_id,at)
    monkeypatch.setattr(commands,'Session',store)
    monkeypatch.setattr(service,'queue_notices',queue)
    refresh=AsyncMock();deliver=AsyncMock()
    monkeypatch.setattr(commands,'refresh_board',refresh)
    monkeypatch.setattr(commands,'deliver_notices',deliver)
    asyncio.run(commands.reconcile(SimpleNamespace()))
    refresh.assert_awaited_once()
    assert refresh.call_args.args[1]==2
    deliver.assert_awaited_once()


def test_member_buttons_use_own_identity_and_fresh_database_state(store, act, monkeypatch):
    monkeypatch.setattr(commands,'Session',store)
    monkeypatch.setattr(commands,'member_access',lambda _:True)
    monkeypatch.setattr(commands,'ADMIN_IDS',{99})
    monkeypatch.setattr(commands,'VERIFIED_ROLE_ID',5)
    async def tap(view,action,identifier):
        interaction=SimpleNamespace(user=SimpleNamespace(id=10,roles=[SimpleNamespace(id=5)]),
            channel_id=123,id=identifier,response=SimpleNamespace(defer=AsyncMock(),send_message=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()))
        button=next(b for b in view.children if b.custom_id==f'performance:member:1:{action}')
        await button.callback(interaction)
        return interaction
    async def flow():
        first_view=commands.StageView.from_state(state(store))
        assert first_view.is_persistent()
        act('register', 10)
        # Recreate the view as setup_hook does after restarting the bot.
        restored=commands.StageView.from_state(state(store))
        assert {b.custom_id for b in first_view.children if ':member:' in b.custom_id}=={b.custom_id for b in restored.children if ':member:' in b.custom_id}
        await tap(restored,'checkin',20002)
        assert not state(store)['next']['ready']
        await tap(restored,'ready',20003)
        assert state(store)['next']['ready']
        await tap(restored,'notready',20004)
        assert not state(store)['next']['ready']
        assert len(state(store)['queue'])==1
    asyncio.run(flow())


def test_paused_set_board_restores_resume_control(store, act):
    prepare(act)
    first=state(store)['next']['id']
    act('start',99,at=START,target=first)
    act('pause_set',99,at=START+timedelta(minutes=5),target=first)
    paused=state(store,START+timedelta(minutes=12))
    view=commands.StageView.from_state(paused)
    assert 'PAUSED' in commands.stage_text(paused)
    assert any(':resume_set:' in b.custom_id and not b.disabled for b in view.children)
    assert next(b for b in view.children if ':start:' in b.custom_id).disabled


def test_performer_buttons_remain_available_after_registration_closes(store, act):
    act('close', 99)
    view = commands.StageView.from_state(state(store))
    member_buttons = [b for b in view.children if ':member:' in b.custom_id]
    assert [b.label for b in member_buttons] == ['I’ve arrived', 'I’m ready', 'I’m not ready']
    assert all(not b.disabled for b in member_buttons)
    act('end_event', 99)
    view = commands.StageView.from_state(state(store))
    assert all(b.disabled for b in view.children if ':member:' in b.custom_id)
