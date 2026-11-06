import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app import feeds
from app.db import Base, ImportedEvent, Setting

SOURCE = {'id': 'example', 'name': 'Example Venue', 'adapter': 'ticketweb_calendar',
          'url': 'https://example.com/calendar/', 'timezone': 'America/Los_Angeles'}


def test_calendar_parser_timezone_exclusions_and_safe_literals():
    html = """events: [{id: '12', start: '2026-11-06 21:00:00', title: 'Artist &amp; Friends'},
       {id: '13', start: '2026-11-07 18:00:00', title: 'CLOSED FOR PRIVATE EVENT'}]"""
    rows = feeds.parse_ticketweb_calendar(html, SOURCE)
    assert len(rows) == 1
    assert rows[0]['title'] == 'Artist & Friends'
    assert rows[0]['starts_at'] == datetime(2026, 11, 7, 5, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        feeds.parse_ticketweb_calendar('<p>Format changed</p>', SOURCE)


def test_discord_normalization_and_guild_guard():
    item = {'id': '456', 'guild_id': '123', 'name': 'Community Jam',
            'scheduled_start_time': '2026-11-14T20:00:00Z', 'status': 4}
    rows = feeds.parse_discord_events([item], 123)
    assert rows[0]['cancelled']
    assert rows[0]['source_url'] == 'https://discord.com/events/123/456'
    with pytest.raises(ValueError):
        feeds.parse_discord_events([item], 999)


@pytest.fixture
def store(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'feeds.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine)
    monkeypatch.setattr(feeds, 'Session', sessions)
    monkeypatch.setattr(feeds, 'SOURCES', [SOURCE])
    yield sessions
    engine.dispose()


def sample_event():
    return dict(external_id='12', title='Sample', starts_at=datetime(2026, 11, 7, 5, tzinfo=timezone.utc),
                location='Example Venue', source_url='https://example.com/event/12', cancelled=False)


def test_collection_pause_dedupe_and_failure_preserves_data(store, monkeypatch):
    calls = []
    async def fetch(source):
        calls.append(source['id'])
        return [sample_event()]
    monkeypatch.setattr(feeds, 'fetch_source', fetch)
    assert not asyncio.run(feeds.collect_source('example')) and not calls
    with store.begin() as db:
        feeds.set_enabled(db, 'collection', True)
        feeds.set_enabled(db, 'example.collect', True)
    assert asyncio.run(feeds.collect_source('example'))
    assert asyncio.run(feeds.collect_source('example'))
    with store.begin() as db:
        rows = db.scalars(select(ImportedEvent)).all()
        assert len(rows) == 1
        rows[0].suppressed = True
    assert asyncio.run(feeds.collect_source('example'))
    with store() as db:
        assert db.get(ImportedEvent, ('example', '12')).suppressed
    async def failed(source):
        raise httpx.HTTPStatusError('blocked', request=httpx.Request('GET', source['url']), response=httpx.Response(403))
    monkeypatch.setattr(feeds, 'fetch_source', failed)
    assert not asyncio.run(feeds.collect_source('example'))
    with store() as db:
        assert db.get(ImportedEvent, ('example', '12')).title == 'Sample'
        assert '403' in db.get(Setting, 'feeds.result.example').value


def test_pause_during_fetch_discards_results(store, monkeypatch):
    with store.begin() as db:
        feeds.set_enabled(db, 'collection', True)
        feeds.set_enabled(db, 'example.collect', True)
    async def fetch(source):
        with store.begin() as db:
            feeds.set_enabled(db, 'collection', False)
        return [sample_event()]
    monkeypatch.setattr(feeds, 'fetch_source', fetch)
    assert not asyncio.run(feeds.collect_source('example'))
    with store() as db:
        assert not db.scalars(select(ImportedEvent)).all()


def test_discord_snapshot_retires_deleted_events(store):
    source = {**SOURCE, 'adapter': 'discord'}
    with store.begin() as db:
        feeds.save_events(db, source, [sample_event()])
    with store.begin() as db:
        feeds.save_events(db, source, [])
    with store() as db:
        assert db.get(ImportedEvent, ('example', '12')).cancelled


def test_weekly_source_schedule_timezone_restart_failure_and_manual_pull(store, monkeypatch):
    import json
    monkeypatch.setattr(feeds, 'SITE', {'calendar_timezone': 'America/Los_Angeles',
                                      'calendar_collection': {'weekday': 1, 'hour': 9}})
    with store.begin() as db:
        feeds.set_enabled(db, 'collection', True)
        feeds.set_enabled(db, 'example.collect', True)
    with store() as db:
        assert not feeds.automatic_pull_due(db, SOURCE, datetime(2026, 11, 10, 16, 59, tzinfo=timezone.utc))
        assert feeds.automatic_pull_due(db, SOURCE, datetime(2026, 11, 10, 17, tzinfo=timezone.utc))
        assert not feeds.automatic_pull_due(db, SOURCE, datetime(2026, 11, 11, 17, tzinfo=timezone.utc))
        # Summer Tuesday at 09:00 Pacific is 16:00 UTC.
        assert feeds.automatic_pull_due(db, SOURCE, datetime(2027, 7, 6, 16, tzinfo=timezone.utc))
    with store.begin() as db:
        db.add(Setting(key='feeds.result.example', value=json.dumps({
            'attempted_at': '2026-11-10T17:00:00+00:00', 'error': 'HTTP 503'})))
    with store() as db:
        assert not feeds.automatic_pull_due(db, SOURCE, datetime(2026, 11, 11, 2, tzinfo=timezone.utc))
        assert feeds.automatic_pull_due(db, SOURCE, datetime(2026, 11, 17, 17, tzinfo=timezone.utc))
        assert not feeds.automatic_pull_due(db, {**SOURCE, 'adapter': 'discord'}, datetime(2026, 11, 11, 2, tzinfo=timezone.utc))
    async def fetch(source):
        return [sample_event()]
    monkeypatch.setattr(feeds, 'fetch_source', fetch)
    # Manual pulls bypass automatic weekday restrictions.
    assert asyncio.run(feeds.collect_source('example'))
    with store.begin() as db:
        feeds.set_enabled(db, 'collection', False)
    with store() as db:
        assert not feeds.automatic_pull_due(db, SOURCE, datetime(2026, 11, 17, 17, tzinfo=timezone.utc))


def test_retention_removes_only_expired_venues_and_prevents_reimport(store, monkeypatch):
    from datetime import timedelta
    fixed = datetime(2026, 11, 5, 20, tzinfo=timezone.utc)
    monkeypatch.setattr(feeds, 'now', lambda: fixed)
    monkeypatch.setattr(feeds, 'SITE', {'venue_retention_days': 30})
    discord = {**SOURCE, 'id': 'discord', 'adapter': 'discord'}
    monkeypatch.setattr(feeds, 'SOURCES', [SOURCE, discord])
    old = {**sample_event(), 'starts_at': fixed - timedelta(days=31)}
    boundary = {**sample_event(), 'external_id': 'boundary', 'starts_at': fixed - timedelta(days=30)}
    future = {**sample_event(), 'external_id': 'future', 'starts_at': fixed + timedelta(days=1)}
    with store.begin() as db:
        db.add(ImportedEvent(source_id=SOURCE['id'], **old))
        feeds.save_events(db, discord, [old])
        feeds.save_events(db, SOURCE, [boundary, future])
    with store.begin() as db:
        assert feeds.prune_venue_events(db) == 1
        feeds.save_events(db, SOURCE, [old])
    with store() as db:
        assert db.get(ImportedEvent, (SOURCE['id'], old['external_id'])) is None
        assert db.get(ImportedEvent, ('discord', old['external_id'])) is not None
        assert db.get(ImportedEvent, (SOURCE['id'], 'boundary')) is not None
        assert db.get(ImportedEvent, (SOURCE['id'], 'future')) is not None
