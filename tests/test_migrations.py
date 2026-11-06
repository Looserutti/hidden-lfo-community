import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest


@pytest.mark.parametrize('legacy', [False, True])
def test_upgrade_fresh_and_existing_database(tmp_path, legacy):
    database = tmp_path / 'migration.db'
    if legacy:
        with sqlite3.connect(database) as db:
            db.executescript("""
                CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY);
                INSERT INTO alembic_version VALUES ('0001');
                CREATE TABLE members (discord_id INTEGER PRIMARY KEY, joined_at DATETIME,
                    verified_at DATETIME, last_server_activity DATETIME,
                    last_observed_online DATETIME, exempt BOOLEAN NOT NULL);
                INSERT INTO members(discord_id, exempt) VALUES (123456789, 1);
            """)
    env = {**os.environ, 'DATABASE_URL': f'sqlite:///{database}'}
    result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'],
        cwd=Path(__file__).resolve().parent.parent, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT version_num FROM alembic_version').fetchone()[0] == '0007'
        columns = {r[1] for r in db.execute('PRAGMA table_info(members)')}
        assert {'discord_username', 'server_display_name'} <= columns
        assert 'suppressed' in {r[1] for r in db.execute('PRAGMA table_info(imported_events)')}
        assert 'submitted_by' in {r[1] for r in db.execute('PRAGMA table_info(event_submissions)')}
        assert 'filename' in {r[1] for r in db.execute('PRAGMA table_info(gallery_tracks)')}
        if legacy:
            assert db.execute('SELECT exempt, discord_username FROM members WHERE discord_id=123456789').fetchone() == (1, None)
