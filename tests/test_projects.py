import base64
import io
import json
import os
os.environ.setdefault('SESSION_SECRET','isolated-project-test-secret')
from PIL import Image
import pytest
from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app import web, project_store as store, gallery_store as gallery
from app.db import Base


@pytest.fixture
def project_app(tmp_path,monkeypatch):
    engine=create_engine(f'sqlite:///{tmp_path}/projects.db',connect_args={'check_same_thread':False});Base.metadata.create_all(engine)
    sessions=sessionmaker(engine)
    monkeypatch.setattr(web,'Session',sessions);monkeypatch.setattr(web,'ADMIN_IDS',{123})
    monkeypatch.setattr(store,'ROOT',tmp_path/'project-photos');monkeypatch.setattr(gallery,'ROOT',tmp_path/'gallery-photos')
    def prepare(staging,names):
        files={}
        for suffix in ('full.jpg','480.webp','960.webp','1600.webp'):
            target=staging/('00-'+suffix);Image.new('RGB',(120,80),'blue').save(target);files[target.name]=target.stat().st_size
        for name in names:(staging/name).unlink()
        return [{'width':120,'height':80}],files
    monkeypatch.setattr(gallery,'prepare',prepare)
    with TestClient(web.app) as client:
        payload=base64.b64encode(json.dumps({'discord_id':123,'csrf':'project-csrf'}).encode())
        client.cookies.set('session',TimestampSigner(web.secret).sign(payload).decode(),domain='testserver.local',path='/')
        yield client,sessions
    engine.dispose()


def save(client,path='/admin/projects',title='Community synthesizer',photo=True,**overrides):
    data={'csrf':'project-csrf','title':title,'member':'Example member','body':'First paragraph.\n\nSecond paragraph.','links':'Project | https://example.org/project','photo_alt':'A synthesizer on a workbench',**overrides}
    stream=io.BytesIO();Image.new('RGB',(120,80),'blue').save(stream,format='JPEG')
    return client.post(path,data=data,files={'photo':('feature.jpg',stream.getvalue(),'image/jpeg')} if photo else None,follow_redirects=False)


def test_public_pages_menu_and_draft_isolation(project_app):
    client,sessions=project_app
    assert client.get('/projects').status_code==200
    home=client.get('/').text
    assert 'Navigation menu' in home and 'href="/projects"' in home
    response=save(client);assert response.status_code==303
    path=response.headers['location'];key=path.rsplit('/',1)[-1]
    assert client.get('/projects/'+key).status_code==404
    assert 'Community synthesizer' not in client.get('/projects').text
    with sessions() as db:photo=store.get(db,key)['draft']['photo']
    client.cookies.clear()
    assert client.get(f'/media/project-photos/{photo}/00-full.jpg').status_code==403
    assert client.get(path+'/preview').status_code==403
    assert client.get('/admin/projects').status_code==403
    assert client.get('/').status_code==client.get('/calendar').status_code==200


def test_publication_keeps_live_snapshot_until_saved_changes_are_published(project_app):
    client,sessions=project_app
    path=save(client).headers['location'];key=path.rsplit('/',1)[-1]
    assert client.post(path+'/publish',data={'csrf':'bad'}).status_code==403
    assert client.post(path+'/publish',data={'csrf':'project-csrf'},follow_redirects=False).status_code==303
    page=client.get('/projects').text
    assert 'Community synthesizer' in page and 'project-photo-toggle' in page
    assert 'First paragraph.' in page and 'EXPLORE THE PROJECT' in page and 'rel="noopener noreferrer"' in page
    with sessions() as db:first_photo=store.get(db,key)['published']['photo']
    assert save(client,path+'/save',title='Private replacement').status_code==303
    assert 'Private replacement' not in client.get('/projects').text
    assert 'Private replacement' in client.get(path+'/preview').text
    with sessions() as db:second_photo=store.get(db,key)['draft']['photo']
    client.cookies.clear()
    assert client.get(f'/media/project-photos/{first_photo}/00-full.jpg').status_code==200
    assert client.get(f'/media/project-photos/{second_photo}/00-full.jpg').status_code==403


def test_photo_required_and_links_and_html_are_safe(project_app):
    client,sessions=project_app
    path=save(client,photo=False,title='<script>alert(1)</script>').headers['location']
    assert client.post(path+'/publish',data={'csrf':'project-csrf'}).status_code==409
    assert '&lt;script&gt;' in client.get(path).text
    assert save(client,links='Bad | javascript:alert(1)').status_code==400
    assert save(client,links='Bad | https://user:password@example.org').status_code==400
    assert save(client,csrf='wrong').status_code==403
    with sessions() as db:assert len(store.all_posts(db))==1


def test_unpublish_and_delete_remove_post_assets_and_preserve_carousel(project_app):
    client,sessions=project_app
    path=save(client).headers['location'];key=path.rsplit('/',1)[-1]
    client.post(path+'/publish',data={'csrf':'project-csrf'})
    assert client.post(path+'/delete',data={'csrf':'project-csrf'}).status_code==409
    with sessions() as db:photo_id=store.get(db,key)['published']['photo']
    client.post(path+'/unpublish',data={'csrf':'project-csrf'})
    anonymous=TestClient(web.app)
    assert anonymous.get(f'/media/project-photos/{photo_id}/00-full.jpg').status_code==403
    anonymous.close()
    assert client.get('/projects/'+key).status_code==404
    assert client.post(path+'/delete',data={'csrf':'project-csrf'},follow_redirects=False).status_code==303
    with sessions() as db:
        assert not store.all_posts(db) and gallery.storage_bytes(db)==0 and not gallery.active_id(db)


def test_project_upload_respects_shared_photo_storage_cap(project_app,monkeypatch):
    client,sessions=project_app
    monkeypatch.setattr(gallery,'MAX_STORAGE',1)
    assert save(client).status_code==400
    with sessions() as db:assert not store.all_posts(db) and gallery.storage_bytes(db)==0
    assert not list(store.ROOT.glob('.staging-*'))
