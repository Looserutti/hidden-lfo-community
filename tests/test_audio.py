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


def test_loudness_measurement_and_peak_safe_gain():
    from app.normalization import read_loudness,initial_gain
    assert read_loudness('log\n{"input_i":"-20.0","input_tp":"-4.0"}')==(-20.,-4.)
    assert initial_gain(-10.,-0.1,-14.)==-4.
    assert initial_gain(-22.,-2.,-14.)==0.5  # protect peaks rather than compressing
    with pytest.raises(ValueError):read_loudness('{"input_i":"-inf","input_tp":"-inf"}')


def test_admin_can_queue_adjustable_normalization(library,monkeypatch):
    from app import normalization
    c,sessions=library
    jobs=[]
    monkeypatch.setattr(normalization,'available',lambda:True)
    monkeypatch.setattr(normalization,'enqueue',lambda track_id,session:jobs.append(track_id))
    upload(c)
    with sessions() as db:track_id=db.scalars(select(GalleryTrack)).one().id
    data={'csrf':'test-csrf','title':'Track','artist':'','normalize':'true','target_lufs':'-14'}
    assert c.post(f'/admin/music/{track_id}',data=data,follow_redirects=False).status_code==303
    assert jobs==[track_id]
    with sessions() as db:
        t=db.get(GalleryTrack,track_id)
        assert t.normalization_enabled and t.normalization_status=='queued' and t.target_lufs==-14
    data['target_lufs']='-5'
    assert c.post(f'/admin/music/{track_id}',data=data).status_code==400


def test_published_track_can_switch_back_to_original(library):
    from uuid import uuid4
    c,sessions=library
    upload(c)
    normalized=uuid4().hex+'.mp3'
    audio.track_path(normalized).write_bytes(b'ID3normalized')
    with sessions.begin() as db:
        track=db.scalars(select(GalleryTrack)).one();track_id=track.id
        track.published=True;track.normalization_enabled=True
        track.normalized_filename=normalized;track.normalization_status='ready'
    assert c.get(f'/media/audio/{track_id}').content==b'ID3normalized'
    c.post(f'/admin/music/{track_id}',data={'csrf':'test-csrf','title':'Track','artist':'','published':'true'})
    assert c.get(f'/media/audio/{track_id}').content==b'ID3'+b'0'*100


def test_real_processing_preserves_source_and_meets_target(library):
    import hashlib,math,shutil,struct,wave
    from uuid import uuid4
    from app import normalization
    if not shutil.which('ffmpeg'):pytest.skip('FFmpeg is exercised in the Docker image')
    _,sessions=library
    audio.AUDIO_ROOT.mkdir()
    filename=uuid4().hex+'.wav';path=audio.track_path(filename)
    with wave.open(str(path),'wb') as stream:
        stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(44100)
        stream.writeframes(b''.join(struct.pack('<h',int(3276*math.sin(2*math.pi*440*i/44100))) for i in range(88200)))
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    with sessions.begin() as db:
        t=GalleryTrack(title='Fixture',artist='',filename=filename,byte_size=path.stat().st_size,
            normalization_enabled=True,normalization_status='queued',target_lufs=-14)
        db.add(t);db.flush();track_id=t.id
    normalization.process(track_id,sessions)
    with sessions() as db:
        t=db.get(GalleryTrack,track_id)
        assert t.normalization_status=='ready',t.normalization_error
        assert abs(t.output_lufs+14)<0.5
        _,peak=normalization.measure(audio.track_path(t.normalized_filename))
        assert peak<=-1
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before


def test_artist_social_link_toggle_and_validation(library):
    c,sessions=library
    upload(c)
    with sessions() as db: track_id=db.scalars(select(GalleryTrack)).one().id
    fields={'csrf':'test-csrf','title':'Track','artist':'Artist','published':'true',
            'artist_social_url':'https://example.org/artist','artist_social_enabled':'true'}
    endpoint=f'/admin/music/{track_id}'
    assert c.post(endpoint,data=fields,follow_redirects=False).status_code==303
    assert 'https://example.org/artist' in c.get('/').text
    fields.pop('artist_social_enabled')
    assert c.post(endpoint,data=fields,follow_redirects=False).status_code==303
    assert 'https://example.org/artist' not in c.get('/').text
    with sessions() as db:
        track=db.get(GalleryTrack,track_id)
        assert track.artist_social_url=='https://example.org/artist' and not track.artist_social_enabled
    for bad in ['javascript:alert(1)','data:text/html,test','https://user:password@example.org','https://example.org/\nfoo']:
        fields['artist_social_url']=bad
        assert c.post(endpoint,data=fields).status_code==400
    fields.update(artist_social_url='',artist_social_enabled='true')
    assert c.post(endpoint,data=fields).status_code==400
