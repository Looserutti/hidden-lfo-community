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
