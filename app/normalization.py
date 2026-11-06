"""Serial background loudness processing, preserving the source audio."""
import json
import logging
import math
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from sqlalchemy import select, text
from app.db import GalleryTrack

TARGETS = (-14.0, -16.0, -18.0)
_worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix='gallery-audio')


def available():
    return shutil.which('ffmpeg') is not None


def read_loudness(stderr):
    match = re.search(r'\{\s*"input_i".*?\}',stderr,re.S)
    if not match:raise ValueError('The audio could not be measured.')
    result=json.loads(match.group())
    values=(float(result['input_i']),float(result['input_tp']))
    if not all(math.isfinite(x) for x in values):raise ValueError('No measurable audio was found.')
    return values


def measure(path):
    result=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-nostats','-i',str(path),
        '-map','0:a:0','-vn','-af','loudnorm=I=-14:TP=-1:print_format=json','-f','null','-'],
        capture_output=True,text=True,timeout=300)
    if result.returncode:raise ValueError('This file could not be decoded for volume analysis.')
    return read_loudness(result.stderr)


def initial_gain(lufs,peak,target):
    # Gain only: preserve dynamics and leave encoding headroom rather than compressing peaks.
    return min(target-lufs, -1.5-peak)


def enqueue(track_id, session):
    _worker.submit(process,track_id,session)


def process(track_id,session):
    from app import audio
    output=None
    committed=False
    try:
        with session() as db:
            track=db.get(GalleryTrack,track_id)
            if not track:return
            track.normalization_status='processing';track.normalization_error=''
            source=audio.track_path(track.filename);target=track.target_lufs
            db.commit()
        if not available():raise ValueError('Volume processing is unavailable on this installation.')
        lufs,peak=measure(source)
        gain=initial_gain(lufs,peak,target)
        output=audio.AUDIO_ROOT/(uuid4().hex+'.mp3')
        for _ in range(3):
            result=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
                '-i',str(source),'-map','0:a:0','-vn','-map_metadata','-1','-af',f'volume={gain:.5f}dB',
                '-c:a','libmp3lame','-b:a','192k','-ar','44100',str(output)],
                capture_output=True,text=True,timeout=300)
            if result.returncode:raise ValueError('A playback copy could not be created.')
            actual,actual_peak=measure(output)
            correction=min(target-actual,-1.25-actual_peak)
            if actual_peak<=-1 and (abs(target-actual)<=.2 or abs(correction)<=.1):break
            gain+=correction
        if actual_peak > -1.0:raise ValueError('A safe playback peak could not be reached; use the original.')
        size=output.stat().st_size
        with session() as db:
            if db.bind.dialect.name=='sqlite':db.execute(text('BEGIN IMMEDIATE'))
            track=db.get(GalleryTrack,track_id)
            if not track:return
            total=sum(t.byte_size+(t.normalized_byte_size or 0) for t in db.scalars(select(GalleryTrack)))
            if total-(track.normalized_byte_size or 0)+size>audio.MAX_STORAGE:
                raise ValueError('Audio storage limit reached. Remove a track before retrying.')
            old=track.normalized_filename
            output.chmod(0o600)
            track.normalized_filename=output.name;track.normalized_byte_size=size
            track.output_lufs=actual;track.normalization_status='ready';track.normalization_error=''
            db.commit();committed=True
        if old:audio.track_path(old).unlink(missing_ok=True)
    except Exception as exc:
        logging.exception('Gallery volume processing failed for track %s',track_id)
        with session() as db:
            track=db.get(GalleryTrack,track_id)
            if track:
                track.normalization_status='failed'
                track.normalization_error=str(exc)[:240] if isinstance(exc,ValueError) else 'Processing was interrupted. Save the option again to retry.'
                db.commit()
    finally:
        if output and not committed:output.unlink(missing_ok=True)
