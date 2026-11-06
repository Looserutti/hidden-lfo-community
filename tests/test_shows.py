from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import asyncio
import discord
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app import feeds
from app.db import Base, Event, ImportedEvent
from app.shows import upcoming_shows
from bot import shows


def test_shows_matches_published_calendar_and_seven_day_boundary(monkeypatch):
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    start = datetime(2026, 11, 5, 20, tzinfo=timezone.utc)
    monkeypatch.setattr(feeds, 'SOURCES', [{'id': 'venue', 'name': 'Venue'}])
    with sessionmaker(engine)() as db:
        feeds.set_enabled(db, 'website', True)
        feeds.set_enabled(db, 'venue.publish', True)
        db.add_all([Event(title='Community', starts_at=start, published=True),
                    Event(title='Draft', starts_at=start, published=False)])
        for key, offset, hidden, cancelled in [('show',1,False,False), ('hidden',1,True,False),
                ('cancelled',1,False,True), ('past',-1,False,False), ('boundary',7,False,False)]:
            db.add(ImportedEvent(source_id='venue', external_id=key, title=key,
                starts_at=start + timedelta(days=offset), suppressed=hidden, cancelled=cancelled,
                source_url='https://example.com/show'))
        db.commit()
        assert [r.title for r in upcoming_shows(db,start)] == ['Community','show']
        feeds.set_enabled(db,'venue.publish',False)
        db.commit()
        assert [r.title for r in upcoming_shows(db,start)] == ['Community']
    engine.dispose()


def test_private_shows_reply_role_guard_and_pagination(monkeypatch):
    monkeypatch.setattr(shows,'SITE',{'calendar_timezone':'America/Los_Angeles'})
    rows=[SimpleNamespace(title=f'Show {i}', starts_at=datetime(2026,11,7,2),
                          source_name='Venue',external_url='https://example.com/show') for i in range(17)]
    embed=shows.shows_embed(rows,2)
    assert len(embed.fields)==8 and embed.fields[0].name=='Show 8'
    assert '06:00 PM PST' in embed.fields[0].value
    assert len(shows.shows_embed(rows,3).fields)==1
    assert 'No published concerts' in shows.shows_embed([],1).description
    assert 'Try /shows page:1' in shows.shows_embed(rows,99).description
    monkeypatch.setattr(discord,'Member',SimpleNamespace)
    monkeypatch.setattr(shows,'GUILD_ID',123)
    monkeypatch.setattr(shows,'VERIFIED_ROLE_ID',456)
    interaction=SimpleNamespace(guild=SimpleNamespace(id=123),user=SimpleNamespace(roles=[SimpleNamespace(id=456)]))
    assert shows.verified_member(interaction)
    interaction.user.roles=[]
    assert not shows.verified_member(interaction)
    interaction.guild=None
    assert not shows.verified_member(interaction)


def test_command_denies_unverified_and_sends_private_reply(monkeypatch):
    from contextlib import nullcontext
    from unittest.mock import AsyncMock
    class Tree:
        def command(self, **kwargs):
            return lambda handler: handler
    command=shows.register_shows(SimpleNamespace(tree=Tree()))
    interaction=SimpleNamespace(response=SimpleNamespace(send_message=AsyncMock(),defer=AsyncMock()),
                                followup=SimpleNamespace(send=AsyncMock()))
    monkeypatch.setattr(shows,'verified_member',lambda i: False)
    asyncio.run(command(interaction))
    assert interaction.response.send_message.call_args.kwargs['ephemeral'] is True
    interaction.response.defer.assert_not_called()
    monkeypatch.setattr(shows,'verified_member',lambda i: True)
    monkeypatch.setattr(shows,'Session',lambda: nullcontext(None))
    monkeypatch.setattr(shows,'upcoming_shows',lambda db,stamp: [])
    asyncio.run(command(interaction))
    assert interaction.response.defer.call_args.kwargs['ephemeral'] is True
    assert interaction.followup.send.call_args.kwargs['ephemeral'] is True
    assert interaction.followup.send.call_args.kwargs['allowed_mentions'].everyone is False
