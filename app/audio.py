"""Gallery audio storage and administration, separate from event/Discord services."""
import os
import re
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from fastapi.responses import RedirectResponse, FileResponse
from starlette.datastructures import UploadFile
from sqlalchemy import select, text
from app.db import GalleryTrack
from app import normalization

AUDIO_ROOT = Path(os.getenv('GALLERY_AUDIO_DIR') or ('/data/gallery-audio' if Path('/data').is_dir() else 'var/gallery-audio'))
MAX_UPLOAD = int(os.getenv('GALLERY_AUDIO_MAX_UPLOAD_MB', '50')) * 1024 * 1024
MAX_STORAGE = int(os.getenv('GALLERY_AUDIO_MAX_STORAGE_MB', '512')) * 1024 * 1024
MIMES = {'.mp3':'audio/mpeg', '.wav':'audio/wav', '.m4a':'audio/mp4'}


def track_path(filename):
    if not re.fullmatch(r'[a-f0-9]{32}\.(mp3|wav|m4a)', filename):
        raise HTTPException(404, 'Audio not found')
    return AUDIO_ROOT / filename


def playlist(db):
    return [{'id': t.id, 'title': t.title, 'artist': t.artist, 'url': f'/media/audio/{t.id}'}
            for t in db.scalars(select(GalleryTrack).where(GalleryTrack.published == True)
                                .order_by(GalleryTrack.position, GalleryTrack.id)).all()]


def valid_signature(header, extension):
    if extension == '.mp3':
        return header.startswith(b'ID3') or (len(header) > 1 and header[0] == 255 and header[1] & 224 == 224)
    if extension == '.wav':
        return header.startswith(b'RIFF') and header[8:12] == b'WAVE'
    return header[4:8] == b'ftyp'


def audio_routes(session, require_admin, csrf_check, render):
    router = APIRouter()

    @router.get('/admin/music')
    def music(request: Request):
        require_admin(request)
        with session() as db:
            tracks = db.scalars(select(GalleryTrack).order_by(GalleryTrack.position, GalleryTrack.id)).all()
            return render(request, tracks=tracks, upload_mb=MAX_UPLOAD//1024//1024,
                          storage_mb=MAX_STORAGE//1024//1024, used_mb=round(sum(t.byte_size+(t.normalized_byte_size or 0) for t in tracks)/1024/1024,1), normalization_available=normalization.available())

    @router.post('/admin/music/upload')
    async def upload(request: Request):
        require_admin(request)
        try:
            length = int(request.headers.get('content-length', '0'))
        except ValueError:
            raise HTTPException(400, 'Invalid upload size')
        if length <= 0:
            raise HTTPException(411, 'Upload size is required')
        if length > MAX_UPLOAD + 1024*1024:
            raise HTTPException(413, 'File exceeds the upload limit')
        async with request.form(max_files=1, max_fields=6) as form:
            csrf_check(request, str(form.get('csrf', '')))
            file = form.get('audio')
            if not isinstance(file, UploadFile):
                raise HTTPException(400, 'Choose an audio file')
            extension = Path(file.filename or '').suffix.lower()
            if extension not in MIMES:
                raise HTTPException(400, 'Use an MP3, WAV or M4A audio file')
            title = str(form.get('title', '')).strip() or Path(file.filename).stem
            artist = str(form.get('artist', '')).strip()
            if not 1 <= len(title) <= 200 or len(artist) > 160:
                raise HTTPException(400, 'Title or artist is too long')
            AUDIO_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
            filename = uuid4().hex + extension
            destination = track_path(filename)
            temporary = destination.with_suffix('.upload')
            moved = False
            try:
                total = 0
                header = b''
                with temporary.open('xb') as output:
                    temporary.chmod(0o600)
                    while chunk := await file.read(1024*1024):
                        if not header: header = chunk[:16]
                        total += len(chunk)
                        if total > MAX_UPLOAD:
                            raise HTTPException(413, 'File exceeds the upload limit')
                        output.write(chunk)
                if not total or not valid_signature(header, extension):
                    raise HTTPException(400, 'This does not look like a supported audio file')
                with session() as db:
                    # Serialize final quota check and file publication on SQLite.
                    if db.bind.dialect.name == 'sqlite': db.execute(text('BEGIN IMMEDIATE'))
                    tracks = db.scalars(select(GalleryTrack)).all()
                    if sum(t.byte_size+(t.normalized_byte_size or 0) for t in tracks) + total > MAX_STORAGE:
                        raise HTTPException(413, 'Audio library storage limit reached')
                    temporary.replace(destination)
                    moved = True
                    db.add(GalleryTrack(title=title, artist=artist, filename=filename, byte_size=total,
                                        position=max((t.position for t in tracks),default=-1)+1, published=False))
                    db.commit()
            except Exception:
                if moved: destination.unlink(missing_ok=True)
                raise
            finally:
                temporary.unlink(missing_ok=True)
        return RedirectResponse('/admin/music', status_code=303)

    @router.post('/admin/music/{track_id}')
    async def edit(request: Request, track_id: int, background_tasks: BackgroundTasks):
        require_admin(request)
        form = await request.form()
        csrf_check(request, str(form.get('csrf', '')))
        title, artist = str(form.get('title','')).strip(), str(form.get('artist','')).strip()
        if not 1 <= len(title) <= 200 or len(artist) > 160:
            raise HTTPException(400, 'Enter a title (up to 200 characters) and artist (up to 160)')
        normalize = form.get('normalize') == 'true'
        try: target_lufs = float(form.get('target_lufs', '-14'))
        except ValueError: raise HTTPException(400, 'Choose a loudness target')
        if target_lufs not in normalization.TARGETS: raise HTTPException(400, 'Choose a listed loudness target')
        if normalize and not normalization.available(): raise HTTPException(409, 'Volume processing is unavailable')
        with session() as db:
            track = db.get(GalleryTrack, track_id)
            if not track: raise HTTPException(404, 'Track not found')
            track.title, track.artist = title, artist
            track.published = form.get('published') == 'true'
            changed_target = target_lufs != track.target_lufs
            if changed_target and track.normalization_status in ('queued','processing'):
                raise HTTPException(409, 'Wait for the current volume processing to finish before changing its target')
            track.normalization_enabled = normalize
            track.target_lufs = target_lufs
            if normalize and (changed_target or track.normalization_status not in ('queued','processing','ready')):
                track.normalization_status='queued';track.normalization_error=''
                background_tasks.add_task(normalization.enqueue,track_id,session)
            tracks = db.scalars(select(GalleryTrack).order_by(GalleryTrack.position, GalleryTrack.id)).all()
            index = next(i for i,t in enumerate(tracks) if t.id == track_id)
            direction = str(form.get('move',''))
            target = index + (-1 if direction == 'up' else 1 if direction == 'down' else 0)
            if 0 <= target < len(tracks) and target != index:
                tracks[index], tracks[target] = tracks[target], tracks[index]
            for i,t in enumerate(tracks): t.position = i
            db.commit()
        return RedirectResponse('/admin/music', status_code=303)

    @router.post('/admin/music/{track_id}/delete')
    async def delete(request: Request, track_id: int):
        require_admin(request)
        form = await request.form()
        csrf_check(request, str(form.get('csrf','')))
        with session() as db:
            track = db.get(GalleryTrack, track_id)
            if not track: raise HTTPException(404, 'Track not found')
            path = track_path(track.filename)
            normalized = track_path(track.normalized_filename) if track.normalized_filename else None
            db.delete(track)
            db.commit()
            path.unlink(missing_ok=True)
            if normalized: normalized.unlink(missing_ok=True)
        return RedirectResponse('/admin/music', status_code=303)

    @router.get('/media/audio/{track_id}')
    def media(track_id: int):
        with session() as db:
            track = db.get(GalleryTrack, track_id)
            if not track or not track.published: raise HTTPException(404, 'Audio not found')
            filename = track.normalized_filename if track.normalization_enabled and track.normalized_filename else track.filename
            path = track_path(filename)
            if not path.is_file(): raise HTTPException(404, 'Audio not found')
            return FileResponse(path, media_type=MIMES[path.suffix], headers={'Cache-Control':'no-store'})

    @router.on_event('startup')
    def interrupted_jobs():
        with session() as db:
            for track in db.scalars(select(GalleryTrack).where(GalleryTrack.normalization_status.in_(['queued','processing']))):
                track.normalization_status='failed'
                track.normalization_error='Processing was interrupted. Save normalization again to retry.'
            db.commit()

    return router
