"""Versioned member-project drafts and separately published snapshots."""
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
from urllib.parse import urlsplit
from uuid import uuid4
from sqlalchemy import select
from app.db import Setting, now
from app import gallery_store as gallery

ROOT=Path(os.getenv('PROJECT_PHOTO_DIR') or ('/data/project-photos' if Path('/data').is_dir() else 'var/project-photos')).resolve()


def get(db,key):
    if not gallery.ID.fullmatch(key):return None
    row=db.get(Setting,'projects.post.'+key)
    return json.loads(row.value) if row else None


def all_posts(db):
    return sorted([json.loads(row.value) for row in db.scalars(select(Setting).where(Setting.key.like('projects.post.%')))],key=lambda item:item['updated_at'],reverse=True)


def asset(db,key):
    if not key or not gallery.ID.fullmatch(key):return None
    row=db.get(Setting,'projects.photo.'+key)
    return json.loads(row.value) if row else None


def fields(form):
    result={key:str(form.get(key,'')).strip() for key in ('title','member','body','photo_alt')}
    for key,limit in [('title',160),('member',160),('body',12000),('photo_alt',250)]:
        if len(result[key])>limit or key in ('title','body') and not result[key]:raise ValueError(f'{key.replace("_"," ").capitalize()} is required and must fit within {limit} characters.')
    result['links']=[]
    for line in str(form.get('links','')).splitlines():
        if not line.strip():continue
        label,separator,url=line.strip().partition('|')
        if not separator:url,label=label,''
        url=url.strip();label=label.strip()
        parsed=urlsplit(url)
        if len(url)>2048 or any(c.isspace() or ord(c)<32 for c in url) or parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('External links must be full HTTPS URLs without login credentials.')
        label=label or parsed.hostname
        if len(label)>80:raise ValueError('Link labels must be 80 characters or fewer.')
        result['links'].append({'label':label,'url':url})
    if len(result['links'])>8:raise ValueError('Use up to eight external links.')
    return result


def save(db,values,key=None,prepared=None):
    gallery.serialize_writes(db)
    record=get(db,key) if key else None
    if key and not record:raise ValueError('Project post not found.')
    stamp=now().isoformat()
    record=record or {'id':uuid4().hex,'created_at':stamp,'published':None,'draft':{},'assets':[]}
    values={**values,'photo':record['draft'].get('photo')}
    target=None
    try:
        if prepared:
            staging,dimensions,files=prepared
            if gallery.storage_bytes(db)+sum(files.values())>gallery.MAX_STORAGE:raise ValueError('Shared photo storage is full. Remove unused photos before uploading more.')
            photo_id=uuid4().hex
            photo={'id':photo_id,'created_at':stamp,'published_at':None,'photos':[{**dimensions[0],'caption':'Project photograph'}],
                   'files':files,'bytes':sum(files.values())}
            target=ROOT/photo_id;staging.rename(target)
            db.add(Setting(key='projects.photo.'+photo_id,value=json.dumps(photo)))
            values['photo']=photo_id;record['assets'].append(photo_id)
        record.update(draft=values,updated_at=stamp)
        db.merge(Setting(key='projects.post.'+record['id'],value=json.dumps(record)));db.commit()
    except Exception:
        if target and target.exists():shutil.rmtree(target)
        raise
    return record['id']


def publish(db,key):
    gallery.serialize_writes(db)
    record=get(db,key)
    if not record:raise ValueError('Project post not found.')
    photo=asset(db,record['draft'].get('photo'))
    if not photo:raise ValueError('Upload a feature photo before publishing.')
    if any(not (ROOT/photo['id']/name).is_file() for name in photo['files']):raise ValueError('The feature photo is missing. Upload it again before publishing.')
    stamp=now().isoformat()
    # Only the currently published feature photo is public at the origin.
    for photo_id in record['assets']:
        saved=asset(db,photo_id)
        if saved:
            saved['published_at']=stamp if photo_id==photo['id'] else None
            db.merge(Setting(key='projects.photo.'+photo_id,value=json.dumps(saved)))
    record['published']={**record['draft'],'published_at':record.get('first_published_at') or stamp}
    record['first_published_at']=record['published']['published_at'];record['updated_at']=stamp
    db.merge(Setting(key='projects.post.'+key,value=json.dumps(record)));db.commit()


def view(db,record,draft=False):
    values=record['draft'] if draft else record['published']
    if values is None:return None
    photo=asset(db,values.get('photo'))
    image=gallery.photos(photo,'Project',base_path='/media/project-photos')[0] if photo else None
    if image:image['alt']=values.get('photo_alt') or f"{values['title']} — {values['member'] or 'member project'}"
    return {**values,'id':record['id'],'image':image,'published_stamp':datetime.fromisoformat(values['published_at']) if values.get('published_at') else None}
