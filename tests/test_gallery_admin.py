import base64
import io
import json
import sys
from pathlib import Path
from PIL import Image
import pytest
from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app import web, gallery_store as store
from app.db import Base


def jpeg():
    stream=io.BytesIO();Image.new('RGB',(80,60),'blue').save(stream,format='JPEG');return stream.getvalue()


@pytest.fixture
def manager(tmp_path,monkeypatch):
    engine=create_engine(f'sqlite:///{tmp_path}/photos.db',connect_args={'check_same_thread':False});Base.metadata.create_all(engine)
    sessions=sessionmaker(engine)
    monkeypatch.setattr(web,'Session',sessions);monkeypatch.setattr(web,'ADMIN_IDS',{123});monkeypatch.setattr(store,'ROOT',tmp_path/'photos')
    # Flow tests isolate authorization/atomic publication; real decoder tested separately on Linux.
    def prepare(staging,names):
        files={};dimensions=[]
        for i,name in enumerate(names):
            dimensions.append({'width':80,'height':60})
            for suffix in ['full.jpg','480.webp','960.webp','1600.webp']:
                target=staging/f'{i:02d}-{suffix}';Image.new('RGB',(80,60),'blue').save(target)
                files[target.name]=target.stat().st_size
        for name in names:(staging/name).unlink()
        return dimensions,files
    monkeypatch.setattr(store,'prepare',prepare)
    with TestClient(web.app) as client:
        payload=base64.b64encode(json.dumps({'discord_id':123,'csrf':'photo-csrf'}).encode())
        client.cookies.set('session',TimestampSigner(web.secret).sign(payload).decode(),domain='testserver.local',path='/')
        yield client,sessions
    engine.dispose()


def upload(client,label='Meet photos',csrf='photo-csrf',count=2):
    return client.post('/admin/photos/upload',data={'csrf':csrf,'label':label},files=[('photos',(f'photo-{i}.jpg',jpeg(),'image/jpeg')) for i in range(count)],follow_redirects=False)


def test_batch_is_private_until_atomic_publication_and_can_be_restored(manager):
    client,sessions=manager
    original=client.get('/').text
    response=upload(client);assert response.status_code==303
    path=response.headers['location'];key=path.rsplit('/',1)[-1]
    assert 'Draft — visible only to admins' in client.get(path).text
    assert f'/media/photos/{key}/' not in client.get('/').text
    assert client.post(path+'/publish',data={'csrf':'wrong'}).status_code==403
    assert client.post(path+'/publish',data={'csrf':'photo-csrf'},follow_redirects=False).status_code==303
    html=client.get('/').text;assert html.count(f'data-full-src="/media/photos/{key}/')==2
    assert client.post(path+'/delete',data={'csrf':'photo-csrf'}).status_code==409
    second=upload(client,'Next meet',count=1).headers['location']
    assert client.post(second+'/publish',data={'csrf':'photo-csrf'},follow_redirects=False).status_code==303
    assert f'/media/photos/{key}/' not in client.get('/').text
    assert client.post(path+'/publish',data={'csrf':'photo-csrf'},follow_redirects=False).status_code==303
    assert html.count(f'data-full-src="/media/photos/{key}/')==2
    client.cookies.clear()
    public=client.get(f'/media/photos/{key}/00-full.jpg')
    assert public.status_code==200 and 'immutable' in public.headers['cache-control']
    assert client.get('/admin/photos').status_code==403


def test_draft_media_denied_and_invalid_upload_preserves_current(manager):
    client,_=manager
    assert upload(client,csrf='wrong').status_code==403
    assert not list(store.ROOT.glob('.staging-*'))
    response=upload(client);key=response.headers['location'].rsplit('/',1)[-1]
    draft=client.get(f'/media/photos/{key}/00-full.jpg');assert draft.status_code==200 and draft.headers['cache-control']=='private, no-store'
    invalid=client.post('/admin/photos/upload',data={'csrf':'photo-csrf','label':'bad'},files={'photos':('bad.heic',b'bad','image/heic')})
    assert invalid.status_code==400
    assert not list(store.ROOT.glob('.staging-*'))
    client.cookies.clear();assert client.get(f'/media/photos/{key}/00-full.jpg').status_code==403


def test_inactive_batch_deletion_and_storage_cap(manager,monkeypatch):
    client,sessions=manager
    response=upload(client);path=response.headers['location'];key=path.rsplit('/',1)[-1]
    monkeypatch.setattr(store,'MAX_STORAGE',1)
    assert upload(client,'Too much').status_code==400
    with sessions() as db:assert len(store.batches(db))==1
    assert client.post(path+'/delete',data={'csrf':'photo-csrf'},follow_redirects=False).status_code==303
    assert not (store.ROOT/key).exists()


@pytest.mark.skipif(sys.platform!='linux',reason='Real isolated decoder exercised in release image')
def test_real_isolated_photo_processing_strips_metadata(tmp_path):
    staging=tmp_path/'job';staging.mkdir()
    image=Image.new('RGB',(400,300),'green');exif=Image.Exif();exif[270]='private metadata';image.save(staging/'input.jpg',exif=exif)
    dimensions,files=store.prepare(staging,['input.jpg'])
    assert dimensions==[{'width':400,'height':300}] and len(files)==4
    assert not Image.open(staging/'00-full.jpg').getexif()
    assert not (staging/'input.jpg').exists()
    bad=tmp_path/'bad';bad.mkdir();(bad/'input.jpg').write_bytes(b'not an image')
    with pytest.raises(ValueError):store.prepare(bad,['input.jpg'])
