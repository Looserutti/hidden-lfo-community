"""Public member-project stories and staff-only publishing tools."""
from pathlib import Path
import shutil
import tempfile
from fastapi import APIRouter,Request,HTTPException,Form,Query
from fastapi.responses import RedirectResponse,FileResponse
from starlette.datastructures import UploadFile
from starlette.concurrency import run_in_threadpool
from app import project_store as store, gallery_store as gallery
from app.db import Setting,now
import json


def project_routes(session,admin,csrf_check,render):
    router=APIRouter()

    @router.get('/projects')
    def index(request: Request,page: int=Query(1,ge=1,le=10000)):
        with session() as db:
            records=sorted([r for r in store.all_posts(db) if r['published']],key=lambda r:r['published']['published_at'],reverse=True)
            return render(request,'projects.html',posts=[store.view(db,r) for r in records[(page-1)*6:page*6]],page=page,has_more=len(records)>page*6)

    @router.get('/projects/{post_id}')
    def detail(request: Request,post_id: str):
        with session() as db:
            record=store.get(db,post_id)
            if not record or not record['published']:raise HTTPException(404)
            return render(request,'projects.html',posts=[store.view(db,record)],single=True,page=1)

    @router.get('/admin/projects')
    def manager(request: Request):
        admin(request)
        with session() as db:return render(request,'admin_projects.html',posts=store.all_posts(db),used_mb=round(gallery.storage_bytes(db)/1024**2,1),storage_mb=gallery.MAX_STORAGE//1024**2)

    @router.get('/admin/projects/{post_id}')
    def editor(request: Request,post_id: str):
        admin(request)
        with session() as db:
            record=store.get(db,post_id)
            if not record:raise HTTPException(404)
            return render(request,'admin_project_edit.html',post=record,photo=store.view(db,record,True)['image'])

    @router.get('/admin/projects/{post_id}/preview')
    def preview(request: Request,post_id: str):
        admin(request)
        with session() as db:
            record=store.get(db,post_id)
            if not record:raise HTTPException(404)
            return render(request,'projects.html',posts=[store.view(db,record,True)],draft_preview=True,single=True,page=1)

    async def save(request,post_id=None):
        admin(request)
        try:length=int(request.headers.get('content-length','0'))
        except ValueError:raise HTTPException(400,'Invalid request size')
        if length<=0:raise HTTPException(411,'Request size is required')
        if length>gallery.MAX_FILE+1024**2:raise HTTPException(413,'Photo exceeds 20 MB')
        staging=None
        try:
            async with request.form(max_files=1,max_fields=7) as form:
                csrf_check(request,str(form.get('csrf','')))
                values=store.fields(form);file=form.get('photo');prepared=None
                if isinstance(file,UploadFile) and file.filename:
                    extension=Path(file.filename).suffix.lower()
                    if extension not in gallery.FORMATS:raise ValueError('Use a still JPEG, PNG, WebP or AVIF photo. Export HEIC as JPEG first.')
                    store.ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
                    staging=Path(tempfile.mkdtemp(prefix='.staging-',dir=store.ROOT))
                    name='input'+extension;size=0
                    with (staging/name).open('xb') as output:
                        while chunk:=await file.read(1024**2):
                            size+=len(chunk)
                            if size>gallery.MAX_FILE:raise HTTPException(413,'Photo exceeds 20 MB')
                            output.write(chunk)
                    if not size:raise ValueError('The selected photo is empty.')
                    dimensions,files=await run_in_threadpool(gallery.prepare,staging,[name]);prepared=(staging,dimensions,files)
                with session() as db:key=store.save(db,values,post_id,prepared)
        except ValueError as exc:raise HTTPException(400,str(exc))
        finally:
            if staging and staging.exists():shutil.rmtree(staging)
        return RedirectResponse('/admin/projects/'+key,status_code=303)

    @router.post('/admin/projects')
    async def create(request: Request):return await save(request)

    @router.post('/admin/projects/{post_id}/save')
    async def edit(request: Request,post_id: str):return await save(request,post_id)

    @router.post('/admin/projects/{post_id}/publish')
    def publish(request: Request,post_id: str,csrf: str=Form(...)):
        admin(request);csrf_check(request,csrf)
        try:
            with session() as db:store.publish(db,post_id)
        except ValueError as exc:raise HTTPException(409,str(exc))
        return RedirectResponse('/admin/projects/'+post_id,status_code=303)

    @router.post('/admin/projects/{post_id}/unpublish')
    def unpublish(request: Request,post_id: str,csrf: str=Form(...)):
        admin(request);csrf_check(request,csrf)
        with session() as db:
            gallery.serialize_writes(db);record=store.get(db,post_id)
            if not record:raise HTTPException(404)
            for photo_id in record['assets']:
                photo=store.asset(db,photo_id)
                if photo:
                    photo['published_at']=None
                    db.merge(Setting(key='projects.photo.'+photo_id,value=json.dumps(photo)))
            record.update(published=None,updated_at=now().isoformat());db.merge(Setting(key='projects.post.'+post_id,value=json.dumps(record)));db.commit()
        return RedirectResponse('/admin/projects/'+post_id,status_code=303)

    @router.post('/admin/projects/{post_id}/delete')
    def delete(request: Request,post_id: str,csrf: str=Form(...)):
        admin(request);csrf_check(request,csrf)
        with session() as db:
            gallery.serialize_writes(db);record=store.get(db,post_id)
            if not record:raise HTTPException(404)
            if record['published']:raise HTTPException(409,'Unpublish this post before deleting it.')
            for key in record['assets']:
                row=db.get(Setting,'projects.photo.'+key)
                if row:db.delete(row)
            db.delete(db.get(Setting,'projects.post.'+post_id));db.commit()
            for key in record['assets']:
                if gallery.ID.fullmatch(key) and (store.ROOT/key).exists():shutil.rmtree(store.ROOT/key)
        return RedirectResponse('/admin/projects',status_code=303)

    @router.get('/media/project-photos/{photo_id}/{filename}')
    def photo(request: Request,photo_id: str,filename: str):
        if not gallery.ID.fullmatch(photo_id) or not gallery.NAME.fullmatch(filename):raise HTTPException(404)
        with session() as db:
            record=store.asset(db,photo_id)
            if not record or filename not in record['files']:raise HTTPException(404)
            if not record['published_at']:admin(request)
        path=store.ROOT/photo_id/filename
        if path.is_symlink() or not path.is_file():raise HTTPException(404)
        return FileResponse(path,media_type='image/jpeg' if filename.endswith('.jpg') else 'image/webp',headers={'Cache-Control':'public, max-age=31536000, immutable' if record['published_at'] else 'private, no-store'})
    return router
