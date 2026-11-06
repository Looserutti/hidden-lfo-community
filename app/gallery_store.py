"""Persistent photo batches. One database pointer swaps the entire public carousel."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from uuid import uuid4
from sqlalchemy import select, text
from app.db import Setting, now

ROOT=Path(os.getenv('GALLERY_PHOTO_DIR') or ('/data/gallery-photos' if Path('/data').is_dir() else 'var/gallery-photos')).resolve()
MAX_FILES=20
MAX_FILE=20*1024**2
MAX_BATCH=200*1024**2
MAX_STORAGE=500*1024**2
FORMATS={'.jpg','.jpeg','.png','.webp','.avif'}
ID=re.compile(r'[a-f0-9]{32}')
NAME=re.compile(r'\d{2}-(?:full\.jpg|(?:480|960|1600)\.webp)')


def batch(db, key):
    if not ID.fullmatch(key):return None
    row=db.get(Setting,'gallery.batch.'+key)
    return json.loads(row.value) if row else None


def batches(db):
    return sorted([json.loads(row.value) for row in db.scalars(select(Setting).where(Setting.key.like('gallery.batch.%')))],key=lambda b:b['created_at'],reverse=True)


def active_id(db):
    row=db.get(Setting,'gallery.active_batch')
    return row.value if row else ''


def photos(record, name):
    result=[]
    for index,item in enumerate(record['photos']):
        base=f"/media/photos/{record['id']}/{index:02d}-"
        # Sizes describe the image width, including portrait images constrained on their long edge.
        candidates=[]
        for size in (480,960,1600):
            width=max(1,round(item['width']*min(1,size/max(item['width'],item['height']))))
            if width not in [w for w,_ in candidates]:candidates.append((width,base+str(size)+'.webp'))
        result.append({'src':base+'full.jpg','display_src':base+'960.webp',
                       'srcset':', '.join(f'{url} {width}w' for width,url in candidates),
                       'width':item['width'],'height':item['height'],'alt':f"{name} — {item['caption']}"})
    return result


def current_gallery(db, name):
    key=active_id(db)
    if not key:return None
    record=batch(db,key)
    return photos(record,name) if record else None


def serialize_writes(db):
    if db.bind.dialect.name=='sqlite':db.execute(text('BEGIN IMMEDIATE'))


def prepare(staging, filenames):
    if sys.platform!='linux':raise ValueError('Photo processing requires the supported Linux deployment.')
    import fcntl
    with (staging.parent/'.processing.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Another photo batch is being prepared. Try again shortly.')
        return _prepare(staging,filenames)


def _prepare(staging, filenames):
    if sys.platform!='linux':raise ValueError('Photo processing requires the supported Linux deployment.')
    worker=Path(__file__).with_name('photo_worker.py')
    shutil.copyfile(worker,staging/'worker.py')
    (staging/'request.json').write_text(json.dumps(filenames))
    env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','HOME':str(staging),'TMPDIR':str(staging),'OMP_NUM_THREADS':'2'}
    wrapper=Path(__file__).with_name('media_sandbox.py').resolve()
    try:
        result=subprocess.run([sys.executable,'-I',str(wrapper),str(staging),sys.executable,'-I',str(staging/'worker.py')],
        env=env,cwd=staging,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True,timeout=300)
    except subprocess.TimeoutExpired:
        raise ValueError('Photo processing took too long. Try a smaller batch.')
    if result.returncode:raise ValueError('A photo could not be processed safely. Use still JPEG, PNG, WebP or AVIF images under 40 megapixels.')
    dimensions=json.loads((staging/'result.json').read_text())
    if len(dimensions)!=len(filenames):raise ValueError('Incomplete photo batch.')
    files={}
    for index,item in enumerate(dimensions):
        if not (type(item['width']) is int and type(item['height']) is int and 0<item['width']<=3200 and 0<item['height']<=3200):raise ValueError('Invalid image dimensions.')
        for suffix in ('full.jpg','480.webp','960.webp','1600.webp'):
            name=f'{index:02d}-{suffix}';path=staging/name
            if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=MAX_FILE:raise ValueError('Incomplete photo output.')
            files[name]=path.stat().st_size
    # Nothing uploaded is publicly served directly; only sanitized rendered outputs survive.
    for path in staging.iterdir():
        if path.name not in files:path.unlink()
    return dimensions,files


def save_batch(db, staging, dimensions, files, captions, label):
    serialize_writes(db)
    if sum(b['bytes'] for b in batches(db))+sum(files.values())>MAX_STORAGE:raise ValueError('Photo storage is full. Delete an unused batch before uploading more.')
    key=uuid4().hex
    record={'id':key,'label':label,'created_at':now().isoformat(),'published_at':None,
            'photos':[{**item,'caption':caption} for item,caption in zip(dimensions,captions)],'files':files,'bytes':sum(files.values())}
    target=ROOT/key
    staging.rename(target)
    try:
        db.add(Setting(key='gallery.batch.'+key,value=json.dumps(record)));db.commit()
    except Exception:
        shutil.rmtree(target);raise
    return key


def publish(db, key):
    serialize_writes(db)
    record=batch(db,key)
    if not record:raise ValueError('Photo batch not found.')
    if any(not (ROOT/key/name).is_file() for name in record['files']):raise ValueError('This batch has missing files and cannot be published.')
    record['published_at']=now().isoformat()
    db.merge(Setting(key='gallery.batch.'+key,value=json.dumps(record)))
    db.merge(Setting(key='gallery.active_batch',value=key));db.commit()
