import base64
import json
import os
os.environ.setdefault('SESSION_SECRET', 'isolated-performance-route-secret')
from datetime import timedelta
from itsdangerous import TimestampSigner
from fastapi.testclient import TestClient
import pytest
from app import web
from app import performances as p
from app.db import PerformanceEvent
from test_performances import store, START, BEFORE


def cookie():
    payload = base64.b64encode(json.dumps({'discord_id':99, 'csrf':'valid'}).encode())
    return TimestampSigner(web.secret).sign(payload).decode()


@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setattr(web, 'Session', store)
    monkeypatch.setattr(web, 'ADMIN_IDS', {99})
    with TestClient(web.app) as client:
        client.cookies.set('session',cookie(), domain='testserver.local', path='/')
        yield client


def test_private_organizer_page_and_action(client, store):
    response = client.get('/admin/events/1/performances')
    assert response.status_code == 200
    assert 'Awaiting event activation' in response.text
    assert 'No performers registered' in response.text
    assert response.headers['cache-control'] == 'no-store'
    response = client.post('/admin/events/1/performances/action', data=dict(
        csrf='valid', action='activate', revision='0', request_id='activate'), follow_redirects=False)
    assert response.status_code == 303
    with store() as db:
        assert db.get(PerformanceEvent,1).lifecycle == 'live'
    # Same action is idempotent even though its revision is now old.
    assert client.post('/admin/events/1/performances/action', data=dict(
        csrf='valid', action='activate', revision='0', request_id='activate'), follow_redirects=False).status_code == 303
    assert client.post('/admin/events/1/performances/action', data=dict(
        csrf='valid', action='close', revision='0', request_id='stale'), follow_redirects=False).status_code == 409


def test_configure_page_and_validation(client, store):
    assert 'Enable performer registration' in client.get('/admin/events/2/performances').text
    assert client.post('/admin/events/2/performances/configure', data=dict(csrf='valid',channel_id='456',
        end_date='2035-01-01',end_time='23:00'), follow_redirects=False).status_code == 303
    assert client.post('/admin/events/2/performances/configure', data=dict(csrf='valid',channel_id='456',
        end_date='2035-01-01',end_time='23:00'), follow_redirects=False).status_code == 400
    assert client.post('/admin/events/1/performances/action',data={'csrf':'wrong'}).status_code == 403


def test_ready_organizer_controls_and_no_public_roster(client, store):
    with store() as db:
        p.execute(db,1,10,'register','route:register',verified=True,at=BEFORE)
    response=client.get('/admin/events/1/performances')
    assert 'Record arrival' in response.text and 'Mark ready' in response.text
    response=client.get('/events/1')
    # Public native event route is /event/{id}; no new public performer route.
    response=client.get('/event/1')
    if response.status_code == 200:
        assert 'Performer set sheet' not in response.text


def test_timer_exposes_only_clock_for_published_meetup(client, store):
    from app.db import Event

    client.cookies.clear()
    assert client.get('/meetups/1/timer').status_code == 200
    response = client.get('/meetups/1/timer/state')
    assert response.json() == {'remaining': None, 'paused': False}
    assert response.headers['cache-control'] == 'no-store'
    with store.begin() as db:
        db.get(Event, 1).published = False
    assert client.get('/meetups/1/timer/state').status_code == 404
