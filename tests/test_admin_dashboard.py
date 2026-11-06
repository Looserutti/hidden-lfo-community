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
    assert 'Exclude from publishing' in client.get('/admin/settings').text
    # An unchecked checkbox is omitted from form data and must restore eligibility.
    assert client.post(path, data={'csrf': 'test-csrf'}, follow_redirects=False).status_code == 303
    assert 'Example Soda Bar Show' in client.get('/calendar?year=2026&month=11').text
    assert client.post(path, data={'csrf': 'invalid', 'hidden': 'true'}).status_code == 403
    assert client.post('/admin/settings/listings', data={**form, 'source_url': 'javascript:alert(1)'}).status_code == 400
    assert client.post('/admin/settings/listings', data={**form, 'starts_at': '2026-11-14T20:00:00'}).status_code == 400
    client.cookies.clear()
    assert client.post('/admin/settings/feeds', data={'csrf': 'test-csrf'}).status_code == 403


def test_draft_date_picker_and_edit_store_utc(dashboard, monkeypatch):
    from app import web
    monkeypatch.setattr(web,'CALENDAR_ZONE','America/Los_Angeles')
    client,sessions=dashboard
    form={'csrf':'test-csrf','title':'Date picker draft','start_date':'2026-11-06','start_time':'18:00'}
    assert client.post('/admin/events',data=form,follow_redirects=False).status_code==303
    with sessions() as db:
        event=db.query(Event).one()
        event_id=event.id
        assert event.starts_at == datetime(2026,11,7,2) and not event.published
    assert client.post(f'/admin/events/{event_id}/edit',data={**form,'start_date':'2027-07-06'},follow_redirects=False).status_code==303
    with sessions() as db:
        assert db.get(Event,event_id).starts_at == datetime(2027,7,7,1)
    assert client.post('/admin/events',data={**form,'start_time':'bad'}).status_code==400
    assert client.post('/admin/events',data={**form,'csrf':'invalid'}).status_code==403
    html=client.get('/admin').text
    assert 'type="date"' in html and 'type="time"' in html


def test_submission_review_admin_csrf_and_publication(dashboard):
    from app.submissions import submit_event
    from app.db import EventSubmission
    client,sessions=dashboard
    start=datetime.now(timezone.utc)+timedelta(days=2)
    with sessions.begin() as db:
        submission=submit_event(db,interaction_id='admin-review-test',submitted_by=987,submitted_name='Member Artist',
            title='Proposed Show',description='Music',starts_at=start,location='Venue')
        key=submission.id
    assert 'Proposed Show' in client.get('/admin').text
    assert 'Proposed Show' not in client.get('/calendar').text
    path=f'/admin/submissions/{key}/approve'
    form={'csrf':'test-csrf','title':'Reviewed Show','description':'Reviewed details',
          'start_date':start.strftime('%Y-%m-%d'),'start_time':'18:00','location':'Reviewed venue'}
    assert client.post(path,data={**form,'csrf':'invalid'}).status_code==403
    assert client.post(path,data=form,follow_redirects=False).status_code==303
    assert client.post(path,data=form).status_code==409
    with sessions() as db:
        record=db.get(EventSubmission,key)
        assert record.reviewed_by==123 and record.status=='approved'
        assert db.get(Event,record.event_id).title=='Reviewed Show'
        assert db.query(Event).count()==1
    client.cookies.clear()
    assert client.post(f'/admin/submissions/{key}/reject',data={'csrf':'test-csrf'}).status_code==403


def test_preview_banner_and_search_exclusion_are_environment_specific(dashboard,monkeypatch):
    client,_=dashboard
    monkeypatch.setenv('SITE_ENVIRONMENT','preview')
    response=client.get('/admin')
    assert 'PREVIEW · Test site' in response.text
    assert response.headers['x-robots-tag']=='noindex, nofollow, noarchive'
    monkeypatch.delenv('SITE_ENVIRONMENT')
    response=client.get('/admin')
    assert 'PREVIEW · Test site' not in response.text
    assert 'x-robots-tag' not in response.headers


def test_home_merges_visible_imports_and_native_events(dashboard, monkeypatch):
    from app import feeds
    from app.db import ImportedEvent, Setting
    client,sessions=dashboard
    monkeypatch.setattr(feeds,'SOURCES',[{'id':'venue','name':'Venue'}])
    start=datetime.now(timezone.utc)+timedelta(days=1)
    with sessions.begin() as db:
        for key in ('website','venue.publish'):db.add(Setting(key='feeds.'+key,value='true'))
        db.add(Event(title='Native show',published=True,starts_at=start+timedelta(hours=1)))
        for i in range(5):
            db.add(ImportedEvent(source_id='venue',external_id=str(i),title=f'Imported show {i}',
                starts_at=start+timedelta(hours=i),location='Venue',source_url=f'https://example.org/{i}',
                cancelled=False,suppressed=i==0))
    html=client.get('/').text
    assert 'Imported show 0' not in html and 'Imported show 1' in html and 'Imported show 2' in html
    assert 'Imported show 3' not in html and 'Native show' in html
    assert 'href="https://example.org/1"' in html
    assert 'No upcoming events' not in html
    assert '<strong>5</strong>' in client.get('/admin').text
    with sessions.begin() as db:db.get(Setting,'feeds.website').value='false'
    assert 'Imported show' not in client.get('/').text


def test_native_event_discord_destination_includes_guild(dashboard, monkeypatch):
    client,sessions=dashboard
    monkeypatch.setattr(web,'GUILD_ID',111)
    with sessions.begin() as db:
        event=Event(title='Posted',published=True,starts_at=datetime.now(timezone.utc),
                    discord_channel_id=222,discord_message_id=333)
        db.add(event);db.flush();event_id=event.id
    html=client.get(f'/events/{event_id}').text
    assert 'https://discord.com/channels/111/222/333' in html
    import re
    assert re.search(r'datetime="[^"]+[+-]\d{2}:\d{2}"',html)
    monkeypatch.setattr(web,'GUILD_ID',0)
    assert 'Register in Discord</a>' not in client.get(f'/events/{event_id}').text
