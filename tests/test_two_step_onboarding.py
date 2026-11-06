import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
import discord
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base, Setting
from app.onboarding_permissions import plan_overwrites,VIEW,SEND,HISTORY
from bot import onboarding


def test_member_gate_removes_other_role_bypass_and_preserves_staff():
    channel={'permission_overwrites':[dict(id='3',type=0,allow=str(VIEW),deny='0'),dict(id='99',type=1,allow='0',deny=str(VIEW))]}
    rows={r['id']:r for r in plan_overwrites(channel,1,2,3,[4],[5],'community')}
    assert int(rows['1']['deny']) & VIEW
    assert int(rows['2']['allow']) & VIEW
    assert not int(rows['3']['allow']) & VIEW
    assert int(rows['99']['deny']) & VIEW
    rows={r['id']:r for r in plan_overwrites(channel,1,2,3,[4],[5],'banter')}
    assert int(rows['1']['allow']) & VIEW and int(rows['1']['allow']) & HISTORY
    assert int(rows['1']['deny']) & SEND and int(rows['3']['allow']) & SEND


def test_intro_requires_verified_real_message_and_grants_member(tmp_path,monkeypatch):
    engine=create_engine(f"sqlite:///{tmp_path / 'onboarding.db'}")
    Base.metadata.create_all(engine)
    sessions=sessionmaker(engine)
    monkeypatch.setattr(onboarding,'Session',sessions)
    monkeypatch.setattr(onboarding,'ONBOARDING_ENABLED',True)
    monkeypatch.setattr(onboarding,'GUILD_ID',1)
    monkeypatch.setattr(onboarding,'VERIFIED_ROLE_ID',2)
    monkeypatch.setattr(onboarding,'MEMBER_ROLE_ID',3)
    monkeypatch.setattr(onboarding,'INTRO_CHANNEL_ID',4)
    role=SimpleNamespace(id=3)
    guild=SimpleNamespace(id=1,get_role=lambda _:role)
    user=SimpleNamespace(id=10,bot=False,roles=[],add_roles=AsyncMock())
    message=SimpleNamespace(guild=guild,channel=SimpleNamespace(id=4),author=user,type=discord.MessageType.default)
    assert not asyncio.run(onboarding.introduction(message))
    user.roles=[SimpleNamespace(id=2)]
    message.type=discord.MessageType.chat_input_command
    assert not asyncio.run(onboarding.introduction(message))
    message.type=discord.MessageType.default
    assert asyncio.run(onboarding.introduction(message))
    user.add_roles.assert_awaited_once()
    with sessions() as db: assert db.get(Setting,'onboarding.introduction.10')
    user.roles.append(role)
    assert not asyncio.run(onboarding.introduction(message))
    engine.dispose()
