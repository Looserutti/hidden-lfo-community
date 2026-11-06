"""Consistent SQLite + referenced audio snapshot and offline verification."""
from contextlib import closing
import argparse
import hashlib
import json
import re
import shutil
import sqlite3
from pathlib import Path


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def snapshot(database, audio, destination, photos=None, project_photos=None):
    database, audio, destination = map(Path, (database, audio, destination))
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    if any(destination.iterdir()):
        raise ValueError('Snapshot destination must be empty')
    if not database.is_file():
        raise FileNotFoundError(database)
    # Block metadata mutations/deletes while copying referenced files. WAL readers continue.
    with closing(sqlite3.connect(database, timeout=30)) as lock:
        lock.execute('BEGIN IMMEDIATE')
        try:
            with closing(sqlite3.connect(database)) as source, closing(sqlite3.connect(destination/'community.db')) as saved:
                source.backup(saved)
                saved.execute('PRAGMA journal_mode=DELETE')
                if saved.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Database integrity check failed')
                tables = {row[0] for row in saved.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                files = []
                if 'gallery_tracks' in tables:
                    columns = {r[1] for r in saved.execute('PRAGMA table_info(gallery_tracks)')}
                    fields = 'filename,byte_size' + (',normalized_filename,normalized_byte_size' if 'normalized_filename' in columns else '')
                    for row in saved.execute('SELECT '+fields+' FROM gallery_tracks'):
                        for i in range(0,len(row),2):
                            name,size=row[i:i+2]
                            if not name: continue
                            if not re.fullmatch(r'[a-f0-9]{32}\.(mp3|wav|m4a)',name):
                                raise ValueError('Invalid stored audio filename')
                            source_file=audio/name
                            if source_file.is_symlink() or source_file.stat().st_size != size:
                                raise ValueError('Audio missing or size mismatch')
                            target=destination/'gallery-audio'/name
                            target.parent.mkdir(exist_ok=True,mode=0o700)
                            shutil.copyfile(source_file,target)
                            target.chmod(0o600)
                            files.append(name)
                if 'settings' in tables:
                    for prefix,storage,subfolder in [('gallery.batch.',photos,'gallery-photos'),('projects.photo.',project_photos,'project-photos')]:
                        for key,value in saved.execute("SELECT key,value FROM settings WHERE key LIKE ?",(prefix+'%',)):
                            batch_id=key.removeprefix(prefix)
                            if not re.fullmatch(r'[a-f0-9]{32}',batch_id):raise ValueError('Invalid photo identifier')
                            if storage is None:raise ValueError('Photo storage is required for this snapshot')
                            record=json.loads(value);directory=Path(storage)/batch_id
                            if directory.is_symlink():raise ValueError('Invalid photo directory')
                            for name,size in record['files'].items():
                                if not re.fullmatch(r'\d{2}-(?:full\.jpg|(?:480|960|1600)\.webp)',name):raise ValueError('Invalid photo filename')
                                source_file=directory/name
                                if source_file.is_symlink() or source_file.stat().st_size!=size:raise ValueError('Photo missing or size mismatch')
                                target=destination/subfolder/batch_id/name
                                target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                                shutil.copyfile(source_file,target);target.chmod(0o600);files.append(batch_id+'/'+name)
        finally:
            lock.rollback()
    (destination/'community.db').chmod(0o600)
    manifest={str(p.relative_to(destination)):digest(p) for p in destination.rglob('*') if p.is_file()}
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (destination/'manifest.json').chmod(0o600)
    return len(files)


def verify(destination):
    destination=Path(destination)
    manifest=json.loads((destination/'manifest.json').read_text())
    for name,expected in manifest.items():
        path=destination/name
        if Path(name).is_absolute() or '..' in Path(name).parts or path.is_symlink() or digest(path)!=expected:
            raise ValueError('Restored file verification failed')
    with sqlite3.connect(f'file:{destination / "community.db"}?mode=ro',uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise ValueError('Restored database integrity failed')
    return len(manifest)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--database',default='/data/community.db')
    parser.add_argument('--audio',default='/data/gallery-audio')
    parser.add_argument('--photos',default='/data/gallery-photos')
    parser.add_argument('--project-photos',default='/data/project-photos')
    parser.add_argument('--output',required=True)
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    if args.verify: print('Verified database and files:',verify(args.output))
    else: print('Snapshot media files:',snapshot(args.database,args.audio,args.output,args.photos,args.project_photos))
