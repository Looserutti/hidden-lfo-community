import base64
import json
import os
import pytest
from itsdangerous import TimestampSigner
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
os.environ.setdefault('SESSION_SECRET', 'local-audio-test-secret')
from app import web, audio
from app.db import Base, GalleryTrack


@pytest.fixture
def library(tmp_path, monkeypatch):
    engine = create_engine(f'sqlite:///{tmp_path / "library.db"}', connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine)
    monkeypatch.setattr(web,'Session',sessions)
    monkeypatch.setattr(web,'ADMIN_IDS',{123})
    monkeypatch.setattr(audio,'AUDIO_ROOT',tmp_path/'audio')
    with TestClient(web.app) as client:
        payload=base64.b64encode(json.dumps({'discord_id':123,'csrf':'test-csrf'}).encode())
        client.cookies.set('session',TimestampSigner(web.secret).sign(payload).decode())
        yield client,sessions
    engine.dispose()


def upload(client,name='track.mp3',data=b'ID3'+b'0'*100,csrf='test-csrf'):
    return client.post('/admin/music/upload',data={'csrf':csrf,'title':'Test track','artist':'Test artist'},
        files={'audio':(name,data,'audio/mpeg')},follow_redirects=False)


def test_audio_admin_auth_and_csrf(library):
    c,db=library
    assert c.get('/admin/music').status_code==200
    assert upload(c,csrf='bad').status_code==403
    c.cookies.clear()
    assert c.get('/admin/music').status_code==403
    assert upload(c).status_code==403
    with db() as session:assert not session.scalars(select(GalleryTrack)).all()


def test_draft_publish_range_and_unpublish(library):
    c,sessions=library
    assert upload(c).status_code==303
    with sessions() as db:track=db.scalars(select(GalleryTrack)).one();track_id=track.id
    assert c.get(f'/media/audio/{track_id}').status_code==404
    assert 'gallery-playlist' not in c.get('/').text
    data={'csrf':'test-csrf','title':'Published title','artist':'Artist','published':'true'}
    assert c.post(f'/admin/music/{track_id}',data=data,follow_redirects=False).status_code==303
    assert 'Published title' in c.get('/').text and 'has-player' in c.get('/').text
    r=c.get(f'/media/audio/{track_id}',headers={'Range':'bytes=0-9'})
    assert r.status_code==206 and r.content==b'ID3'+b'0'*7
    assert r.headers['content-type']=='audio/mpeg'
    data.pop('published')
    c.post(f'/admin/music/{track_id}',data=data)
    assert c.get(f'/media/audio/{track_id}').status_code==404


def test_upload_validation_quota_and_cleanup(library,monkeypatch):
    c,sessions=library
    assert upload(c,name='../analysis.mp3.asd').status_code==400
    assert upload(c,data=b'not music').status_code==400
    monkeypatch.setattr(audio,'MAX_UPLOAD',20)
    assert upload(c).status_code==413
    monkeypatch.setattr(audio,'MAX_UPLOAD',1000)
    monkeypatch.setattr(audio,'MAX_STORAGE',150)
    assert upload(c,name='../../track.mp3').status_code==303
    assert upload(c).status_code==413
    assert len(list(audio.AUDIO_ROOT.iterdir()))==1
    with sessions() as db:assert db.scalars(select(GalleryTrack)).one().filename.endswith('.mp3')


def test_reorder_and_delete(library):
    c,sessions=library
    upload(c);upload(c)
    with sessions() as db:ids=[t.id for t in db.scalars(select(GalleryTrack).order_by(GalleryTrack.id))]
    fields={'csrf':'test-csrf','title':'Second','artist':'Artist','move':'up','published':'true'}
    assert c.post(f'/admin/music/{ids[1]}',data=fields,follow_redirects=False).status_code==303
    with sessions() as db:
        assert [t.id for t in db.scalars(select(GalleryTrack).order_by(GalleryTrack.position))]==list(reversed(ids))
        filename=db.get(GalleryTrack,ids[1]).filename
    assert c.post(f'/admin/music/{ids[1]}/delete',data={'csrf':'wrong'}).status_code==403
    assert c.post(f'/admin/music/{ids[1]}/delete',data={'csrf':'test-csrf'},follow_redirects=False).status_code==303
    assert not audio.track_path(filename).exists()
    assert c.get(f'/media/audio/{ids[1]}').status_code==404
