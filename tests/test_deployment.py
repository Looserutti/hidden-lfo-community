import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import sqlite3

import pytest
from scripts.check_config import validate_config
from scripts.verify_backup import restore_copy


def settings():
    return dict(SESSION_SECRET='x' * 48, DISCORD_CLIENT_ID='123', DISCORD_CLIENT_SECRET='test-only-secret',
        ADMIN_DISCORD_IDS='111,222', SITE_DOMAIN='preview.community.test',
        PUBLIC_BASE_URL='https://preview.community.test',
        DISCORD_REDIRECT_URI='https://preview.community.test/auth/callback')


def test_staging_origin_and_admin_configuration():
    assert validate_config(settings(), production=True) == []
    invalid = {**settings(), 'DISCORD_REDIRECT_URI': 'http://localhost:8000/auth/callback'}
    assert any('DISCORD_REDIRECT_URI' in issue for issue in validate_config(invalid, production=True))
    invalid = {**settings(), 'PUBLIC_BASE_URL': 'http://preview.community.test', 'ADMIN_DISCORD_IDS': 'not-an-id'}
    issues = validate_config(invalid, production=True)
    assert any('HTTPS' in issue for issue in issues)
    assert any('ADMIN_DISCORD_IDS' in issue for issue in issues)
    assert not any('test-only-secret' in issue for issue in issues)
    assert validate_config(settings(), production=True, bot=True)


def test_backup_restore_never_overwrites_existing_data(tmp_path):
    source, restored = tmp_path / 'backup.db', tmp_path / 'restored.db'
    with sqlite3.connect(source) as db:
        db.executescript('CREATE TABLE members(id INTEGER); CREATE TABLE events(id INTEGER); CREATE TABLE registrations(id INTEGER); INSERT INTO members VALUES (42);')
    restore_copy(source, restored)
    with sqlite3.connect(restored) as db:
        assert db.execute('SELECT id FROM members').fetchone()[0] == 42
    with pytest.raises(FileExistsError):
        restore_copy(source, restored)
    with pytest.raises(ValueError):
        restore_copy(source, source)
    malformed = tmp_path / 'not-a-backup.db'
    with sqlite3.connect(malformed) as db:
        db.execute('CREATE TABLE unrelated(id INTEGER)')
    with pytest.raises(ValueError):
        restore_copy(malformed, tmp_path / 'invalid-restored.db')
    assert not (tmp_path / 'invalid-restored.db').exists()


@pytest.mark.parametrize('enabled', [False, True])
def test_outbound_bot_jobs_require_explicit_opt_in(monkeypatch, enabled):
    from bot import main
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    session = MagicMock()
    session.__enter__.return_value = db
    monkeypatch.setattr(main, 'Session', lambda: session)
    monkeypatch.setattr(main, 'EVENT_PUBLISHING_ENABLED', enabled)
    monkeypatch.setattr(main, 'STAFF_REPORTS_ENABLED', enabled)
    jobs = [MagicMock(), MagicMock()]
    for job in jobs:
        job.is_running.return_value = False
    monkeypatch.setattr(main, 'publish_events', jobs[0])
    monkeypatch.setattr(main, 'weekly_report', jobs[1])
    fake_bot = SimpleNamespace(add_view=MagicMock(), tree=SimpleNamespace(sync=AsyncMock()))
    asyncio.run(main.CommunityBot.setup_hook(fake_bot))
    for job in jobs:
        assert job.start.call_count == int(enabled)
