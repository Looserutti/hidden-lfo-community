import base64
import json
import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault('SESSION_SECRET', 'local-test-secret')
from app import web
from app.db import Base, Member, Event
from app.services import sync_member_identity
from types import SimpleNamespace


@pytest.fixture
def dashboard(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'dashboard.db'}", connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine)
    monkeypatch.setattr(web, 'Session', sessions)
    monkeypatch.setattr(web, 'ADMIN_IDS', {123})
    with TestClient(web.app) as client:
        payload = base64.b64encode(json.dumps({'discord_id': 123, 'csrf': 'test-csrf'}).encode())
        client.cookies.set('session', TimestampSigner(web.secret).sign(payload).decode())
        yield client, sessions
    engine.dispose()


def test_overview_and_member_search(dashboard):
    client, sessions = dashboard
    with sessions.begin() as db:
        db.add(Member(discord_id=999, discord_username='artist', server_display_name='<Stage Name>', joined_at=datetime.now(timezone.utc)-timedelta(days=150)))
        db.add(Event(title='Upcoming', published=True, starts_at=datetime.now(timezone.utc)+timedelta(days=1)))
    response = client.get('/admin')
    assert response.status_code == 200
    assert 'Community overview' in response.text and 'Upcoming events' in response.text
    assert response.headers['cache-control'] == 'no-store'
    for search in ('STAGE', 'artist', '999'):
        response = client.get('/admin/activity', params={'search': search})
        assert '1 matching members' in response.text
        assert '&lt;Stage Name&gt;' in response.text
        assert '<Stage Name>' not in response.text
    assert 'No members match' in client.get('/admin/activity?search=absent').text
    assert client.get('/admin/activity?status=invalid').status_code == 400
    assert client.get('/admin/activity?page=0').status_code == 422


def test_pagination_and_exemption_csrf(dashboard):
    client, sessions = dashboard
    with sessions.begin() as db:
        db.add_all(Member(discord_id=i, discord_username='artist') for i in range(1000, 1051))
    response = client.get('/admin/activity?search=artist&page=2')
    assert 'Showing 51–51' in response.text and 'Page 2 of 2' in response.text
    assert 'search=artist' in response.text
    path = '/admin/members/1000/exemption'
    assert client.post(path, data={'csrf': 'invalid', 'enabled': 'true'}).status_code == 403
    assert client.post(path, data={'csrf': 'test-csrf', 'enabled': 'true'}, follow_redirects=False).status_code == 303
    with sessions() as db:
        assert db.get(Member, 1000).exempt
    client.cookies.clear()
    assert client.get('/admin/activity').status_code == 403
    assert client.post(path, data={'csrf': 'test-csrf', 'enabled': 'false'}).status_code == 403


def test_name_sync_keeps_identity_and_activity(dashboard):
    _, sessions = dashboard
    with sessions.begin() as db:
        m = sync_member_identity(db, SimpleNamespace(id=999, name='original', display_name='Stage Name'))
        m.exempt = True
        sync_member_identity(db, SimpleNamespace(id=999, name='renamed', display_name='New Stage Name'))
    with sessions() as db:
        m = db.get(Member, 999)
        assert m.discord_username == 'renamed' and m.server_display_name == 'New Stage Name'
        assert m.exempt and m.last_server_activity is None and m.last_observed_online is None


def test_calendar_settings_require_staff_access(dashboard):
    client, _ = dashboard
    response = client.get('/admin/settings')
    assert response.status_code == 200
    assert 'Calendar controls' in response.text and 'Save calendar controls' in response.text
    assert response.headers['cache-control'] == 'no-store'
    client.cookies.clear()
    assert client.get('/admin/settings').status_code == 403


def test_calendar_control_switches_and_manual_show(dashboard):
    from app import feeds
    from app.db import ImportedEvent
    client, sessions = dashboard
    response = client.post('/admin/settings/feeds', data={'csrf': 'invalid', 'website': 'true'})
    assert response.status_code == 403
    assert client.post('/admin/settings/sources/casbah/pull', data={'csrf': 'test-csrf'}).status_code == 409
    form = {'csrf': 'test-csrf', 'source_id': 'casbah', 'title': 'Example Soda Bar Show',
            'starts_at': '2026-11-14T20:00:00-08:00', 'source_url': 'https://example.com/show', 'location': 'Soda Bar'}
    assert client.post('/admin/settings/listings', data=form, follow_redirects=False).status_code == 303
    assert 'Example Soda Bar Show' not in client.get('/calendar?year=2026&month=11').text
    client.post('/admin/settings/feeds', data={'csrf': 'test-csrf', 'website': 'true'})
    client.post('/admin/settings/sources/casbah', data={'csrf': 'test-csrf', 'publish': 'true'})
    html = client.get('/calendar?year=2026&month=11').text
    assert 'Example Soda Bar Show' in html and 'Casbah Presents / Soda Bar' in html
    with sessions() as db:
        event = db.query(ImportedEvent).one()
        path = f'/admin/settings/listings/casbah/{event.external_id}/visibility'
        assert not feeds.enabled(db, 'collection')
    client.post(path, data={'csrf': 'test-csrf', 'hidden': 'true'})
    assert 'Example Soda Bar Show' not in client.get('/calendar?year=2026&month=11').text
    assert client.post('/admin/settings/listings', data={**form, 'source_url': 'javascript:alert(1)'}).status_code == 400
    assert client.post('/admin/settings/listings', data={**form, 'starts_at': '2026-11-14T20:00:00'}).status_code == 400
    client.cookies.clear()
    assert client.post('/admin/settings/feeds', data={'csrf': 'test-csrf'}).status_code == 403
