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
                CREATE TABLE events (id INTEGER PRIMARY KEY);
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
        assert db.execute('SELECT version_num FROM alembic_version').fetchone()[0] == '0010'
        columns = {r[1] for r in db.execute('PRAGMA table_info(members)')}
        assert {'discord_username', 'server_display_name'} <= columns
        assert 'suppressed' in {r[1] for r in db.execute('PRAGMA table_info(imported_events)')}
        assert 'submitted_by' in {r[1] for r in db.execute('PRAGMA table_info(event_submissions)')}
        assert 'filename' in {r[1] for r in db.execute('PRAGMA table_info(gallery_tracks)')}
        if legacy:
            assert db.execute('SELECT exempt, discord_username FROM members WHERE discord_id=123456789').fetchone() == (1, None)


def test_current_0007_upgrade_preserves_rsvp_and_matches_fresh_schema(tmp_path):
    from datetime import datetime, timezone
    from sqlalchemy import create_engine, inspect
    from app.db import Base, Event, Registration
    from sqlalchemy.orm import Session
    database = tmp_path / 'current.db'
    engine = create_engine(f'sqlite:///{database}')
    old_tables = [table for table in Base.metadata.sorted_tables if not table.name.startswith(('performance_', 'performer_'))]
    Base.metadata.create_all(engine, tables=old_tables)
    with Session(engine) as db:
        db.add(Event(id=1,title='Existing event',starts_at=datetime(2035,1,1,tzinfo=timezone.utc),published=True))
        db.add(Registration(id=1,event_id=1,discord_id=123,status='going',created_at=datetime(2034,1,1,tzinfo=timezone.utc)))
        db.commit()
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)')
        db.execute("INSERT INTO alembic_version VALUES ('0007')")
        db.execute('ALTER TABLE events DROP COLUMN deleted_at')
        event_before = db.execute('SELECT * FROM events').fetchall()
        rsvp_before = db.execute('SELECT * FROM registrations').fetchall()
    env = {**os.environ, 'DATABASE_URL': f'sqlite:///{database}'}
    for _ in range(2):
        result = subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=Path(__file__).resolve().parent.parent,env=env,capture_output=True,text=True)
        assert result.returncode == 0, result.stderr
    with sqlite3.connect(database) as db:
        assert [row[:-1] for row in db.execute('SELECT * FROM events')] == event_before
        assert db.execute('SELECT deleted_at FROM events').fetchone() == (None,)
        assert db.execute('SELECT * FROM registrations').fetchall() == rsvp_before
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
    fresh = create_engine('sqlite:///:memory:'); Base.metadata.create_all(fresh)
    upgraded, clean = inspect(engine), inspect(fresh)
    for table in Base.metadata.tables:
        if not table.startswith(('performance_', 'performer_')): continue
        assert upgraded.has_table(table)
        assert [(c['name'],str(c['type']),c['nullable']) for c in upgraded.get_columns(table)] == [(c['name'],str(c['type']),c['nullable']) for c in clean.get_columns(table)]
        assert {i['name'] for i in upgraded.get_indexes(table)} == {i['name'] for i in clean.get_indexes(table)}
        assert {tuple(c['column_names']) for c in upgraded.get_unique_constraints(table)} == {tuple(c['column_names']) for c in clean.get_unique_constraints(table)}
