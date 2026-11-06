"""Staff batch upload, review, publication and inactive-batch removal."""
from pathlib import Path
import shutil
import tempfile
from fastapi import APIRouter, Request, HTTPException, Form
from fastapi.responses import RedirectResponse, FileResponse
from starlette.datastructures import UploadFile
from starlette.concurrency import run_in_threadpool
from app import gallery_store as store


def gallery_routes(session, require_admin, csrf_check, render, site_name):
    router=APIRouter()

    @router.get('/admin/photos')
    def manager(request: Request):
        require_admin(request)
        with session() as db:
            records=store.batches(db);active=store.active_id(db)
            return render(request,batches=records,active=active,used_mb=round(sum(b['bytes'] for b in records)/1024**2,1),max_storage_mb=store.MAX_STORAGE//1024**2,
                          max_files=store.MAX_FILES,max_file_mb=store.MAX_FILE//1024**2,max_batch_mb=store.MAX_BATCH//1024**2)

    @router.post('/admin/photos/upload')
    async def upload(request: Request):
        require_admin(request)
        try:length=int(request.headers.get('content-length','0'))
        except ValueError:raise HTTPException(400,'Invalid upload size')
        if length<=0:raise HTTPException(411,'Upload size is required')
        if length>store.MAX_BATCH+1024**2:raise HTTPException(413,'Batch exceeds the upload limit')
        store.ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
        staging=Path(tempfile.mkdtemp(prefix='.staging-',dir=store.ROOT))
        try:
            async with request.form(max_files=store.MAX_FILES,max_fields=4) as form:
                csrf_check(request,str(form.get('csrf','')))
                label=str(form.get('label','')).strip()
                if not 1<=len(label)<=120:raise HTTPException(400,'Give this batch a name of 1–120 characters.')
                uploads=form.getlist('photos')
                if not 1<=len(uploads)<=store.MAX_FILES:raise HTTPException(400,'Choose at least one photo within the batch limit.')
                total=0;filenames=[];captions=[]
                for index,file in enumerate(uploads):
                    if not isinstance(file,UploadFile):raise HTTPException(400,'Choose photo files.')
                    extension=Path(file.filename or '').suffix.lower()
                    if extension not in store.FORMATS:raise HTTPException(400,'Use JPEG, PNG, WebP or AVIF. Export HEIC photos as JPEG first.')
                    filename=f'input-{index:02d}{extension}';size=0
                    with (staging/filename).open('xb') as target:
                        while chunk:=await file.read(1024**2):
                            size+=len(chunk);total+=len(chunk)
                            if size>store.MAX_FILE or total>store.MAX_BATCH:raise HTTPException(413,'Photo or batch exceeds the upload limit.')
                            target.write(chunk)
                    if not size:raise HTTPException(400,'One of the photos is empty.')
                    filenames.append(filename);captions.append(Path(file.filename or '').stem.replace('_',' ').replace('-',' ')[:160])
            dimensions,files=await run_in_threadpool(store.prepare,staging,filenames)
            with session() as db:key=store.save_batch(db,staging,dimensions,files,captions,label)
        except ValueError as exc:raise HTTPException(400,str(exc))
        except TimeoutError:raise HTTPException(400,'Photo processing took too long. Try a smaller batch.')
        finally:
            if staging.exists():shutil.rmtree(staging)
        return RedirectResponse(f'/admin/photos/{key}',status_code=303)

    @router.get('/admin/photos/{batch_id}')
    def review(request: Request,batch_id: str):
        require_admin(request)
        with session() as db:
            record=store.batch(db,batch_id)
            if not record:raise HTTPException(404)
            return render(request,batch=record,active=store.active_id(db),photos=store.photos(record,site_name))

    @router.post('/admin/photos/{batch_id}/publish')
    def publish(request: Request,batch_id: str,csrf: str=Form(...)):
        require_admin(request);csrf_check(request,csrf)
        try:
            with session() as db:store.publish(db,batch_id)
        except ValueError as exc:raise HTTPException(409,str(exc))
        return RedirectResponse('/admin/photos?published=1',status_code=303)

    @router.post('/admin/photos/builtin')
    def builtin(request: Request,csrf: str=Form(...)):
        require_admin(request);csrf_check(request,csrf)
        with session() as db:
            store.serialize_writes(db)
            row=db.get(store.Setting,'gallery.active_batch')
            if row:db.delete(row)
            db.commit()
        return RedirectResponse('/admin/photos',status_code=303)

    @router.post('/admin/photos/{batch_id}/delete')
    def delete(request: Request,batch_id: str,csrf: str=Form(...)):
        require_admin(request);csrf_check(request,csrf)
        with session() as db:
            store.serialize_writes(db)
            if store.active_id(db)==batch_id:raise HTTPException(409,'Publish another batch before deleting the active one.')
            record=store.batch(db,batch_id)
            if not record:raise HTTPException(404)
            # Same SQLite write lock as consistent backups; referenced files cannot disappear mid-snapshot.
            directory=store.ROOT/batch_id
            db.delete(db.get(store.Setting,'gallery.batch.'+batch_id));db.commit()
            if directory.exists():shutil.rmtree(directory)
        return RedirectResponse('/admin/photos',status_code=303)

    @router.get('/media/photos/{batch_id}/{filename}')
    def media(request: Request,batch_id: str,filename: str):
        if not store.ID.fullmatch(batch_id) or not store.NAME.fullmatch(filename):raise HTTPException(404)
        with session() as db:
            record=store.batch(db,batch_id)
            if not record or filename not in record['files']:raise HTTPException(404)
            if not record['published_at']:require_admin(request)
        path=store.ROOT/batch_id/filename
        if not path.is_file() or path.is_symlink():raise HTTPException(404)
        return FileResponse(path,media_type='image/jpeg' if filename.endswith('.jpg') else 'image/webp',
            headers={'Cache-Control':'public, max-age=31536000, immutable' if record['published_at'] else 'private, no-store'})
    return router
