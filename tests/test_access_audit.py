"""Route-wide negative authorization checks; never mutates a live database."""
import base64
import json
import re
import time
import os
os.environ.setdefault("SESSION_SECRET", "isolated-access-audit-test-secret")
from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner
from app import web


def cookie(identity, signer=None):
    payload=base64.b64encode(json.dumps({'discord_id':identity,'csrf':'valid-test-csrf'}).encode())
    return (signer or TimestampSigner(web.secret)).sign(payload).decode()


def admin_routes(method):
    # OpenAPI expands included routers as well as directly registered routes.
    from types import SimpleNamespace
    for path, operations in web.app.openapi()['paths'].items():
        if path.startswith('/admin') and method.lower() in operations:
            yield SimpleNamespace(dependant=SimpleNamespace(body_params=[])), re.sub(r'\{[^}]+\}', '1', path)


def form(route):
    values={'page':'1','csrf':'invalid','title':'Test','description':'Test','starts_at':'2030-01-01T20:00:00+00:00',
            'start_date':'2030-01-01','start_time':'20:00','location':'Venue','capacity':'',
            'collection':'false','website':'false','publish':'false','collect':'false','source_id':'example','source_url':'https://venue.example/show','enabled':'false','hidden':'true'}
    for param in getattr(route.dependant,'body_params',[]):
        values.setdefault(param.name,'test')
    return values


def test_every_admin_route_rejects_anonymous_and_non_allowlisted_user(monkeypatch):
    monkeypatch.setattr(web,'ADMIN_IDS',{123})
    with TestClient(web.app) as client:
        for signed in [None,cookie(999)]:
            client.cookies.clear()
            if signed:client.cookies.set('session',signed,domain='testserver.local',path='/')
            for route,path in admin_routes('GET'):
                assert client.get(path).status_code==403,path
            for route,path in admin_routes('POST'):
                assert client.post(path,data=form(route),follow_redirects=False).status_code==403,path


def test_every_admin_mutation_rejects_invalid_csrf(monkeypatch):
    monkeypatch.setattr(web,'ADMIN_IDS',{123})
    with TestClient(web.app) as client:
        client.cookies.set('session',cookie(123),domain='testserver.local',path='/')
        for route,path in admin_routes('POST'):
            if path.endswith('/upload'):
                response=client.post(path,data={'csrf':'invalid'},files={'audio':('test.mp3',b'ID3test','audio/mpeg')},follow_redirects=False)
            else:
                response=client.post(path,data=form(route),follow_redirects=False)
            assert response.status_code==403,path


def test_tampered_and_expired_sessions_are_denied(monkeypatch):
    monkeypatch.setattr(web,'ADMIN_IDS',{123})
    class OldSigner(TimestampSigner):
        def get_timestamp(self):return int(time.time())-9*3600
    with TestClient(web.app) as client:
        for value in [cookie(123)+'tampered',cookie(123,OldSigner(web.secret))]:
            client.cookies.clear();client.cookies.set('session',value,domain='testserver.local',path='/')
            assert client.get('/admin').status_code==403


def test_oauth_state_is_consumed_after_failed_exchange(monkeypatch):
    import httpx
    class Offline:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,*args,**kwargs):raise httpx.ConnectError('test unavailable')
    monkeypatch.setattr(web.httpx,'AsyncClient',lambda **kwargs:Offline())
    with TestClient(web.app) as client:
        payload=base64.b64encode(json.dumps({'oauth_state':'one-use-state'}).encode())
        client.cookies.set('session',TimestampSigner(web.secret).sign(payload).decode(),domain='testserver.local',path='/')
        response=client.get('/auth/callback?code=test&state=one-use-state')
        assert response.status_code==502
        assert client.get('/auth/callback?code=test&state=one-use-state').status_code==403
