import os
os.environ.setdefault('SESSION_SECRET', 'test-secret-only-do-not-use-in-production')
from fastapi.testclient import TestClient
from app.web import app


def test_public_health_and_security_headers():
    with TestClient(app) as client:
        response = client.get('/healthz')
        assert response.status_code == 200
        assert response.json() == {'status': 'ok'}
        assert response.headers['x-content-type-options'] == 'nosniff'
        assert response.headers['x-frame-options'] == 'DENY'


def test_admin_requires_authorization():
    with TestClient(app) as client:
        response = client.get('/admin')
        assert response.status_code == 403
        assert response.headers['cache-control'] == 'no-store'
        response = client.get('/admin/activity')
        assert response.status_code == 403


def test_admin_mutations_require_authorization():
    with TestClient(app) as client:
        response = client.post('/admin/events/1/cancel', data={'csrf': 'invalid'}, follow_redirects=False)
        assert response.status_code == 403


def test_oauth_callback_rejects_invalid_state():
    with TestClient(app) as client:
        response = client.get('/auth/callback?code=fake&state=fake')
        assert response.status_code == 403
        assert response.headers['cache-control'] == 'no-store'
def test_oauth_callback_success(monkeypatch):
    from app import web

    class FakeResponse:
        def __init__(self, data):
            self.data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self.data

    class FakeDiscordClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, **kwargs):
            return FakeResponse({'access_token': 'fake-test-token'})

        async def get(self, url, **kwargs):
            return FakeResponse({'id': '123456789'})

    monkeypatch.setattr(web.httpx, 'AsyncClient', lambda **kwargs: FakeDiscordClient())
    monkeypatch.setattr(web, 'ADMIN_IDS', {123456789})
    monkeypatch.setenv('DISCORD_CLIENT_ID', 'test-client-id')
    monkeypatch.setenv('DISCORD_CLIENT_SECRET', 'test-client-secret')
    monkeypatch.setenv('DISCORD_REDIRECT_URI', 'http://testserver/auth/callback')

    with TestClient(app) as client:
        login_response = client.get('/login', follow_redirects=False)
        assert login_response.status_code == 307

        from urllib.parse import urlparse, parse_qs

        authorization_url = login_response.headers['location']
        state = parse_qs(urlparse(authorization_url).query)['state'][0]

        callback_response = client.get(
            '/auth/callback',
            params={'code': 'fake-code', 'state': state},
            follow_redirects=False,
        )

        assert callback_response.status_code == 303
        assert callback_response.headers['location'] == '/admin'

        admin_response = client.get('/admin')
        assert admin_response.status_code == 200


def test_public_homepage_without_login():
    with TestClient(app) as client:
        response = client.get('/')
        assert response.status_code == 200
