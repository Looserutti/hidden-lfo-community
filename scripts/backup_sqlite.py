"""Consistent online SQLite backup using SQLite backup API."""
import argparse
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import unquote
from app.config import DATABASE_URL

def backup(destination: Path):
    if not DATABASE_URL.startswith('sqlite:///') or DATABASE_URL.endswith(':memory:'):
        raise RuntimeError('Backup helper supports only file-based SQLite DATABASE_URL')
    source = Path(unquote(DATABASE_URL[len('sqlite:///'):]))
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() == destination.resolve():
        raise ValueError('Backup destination must differ from source')
    with sqlite3.connect(str(source)) as src, sqlite3.connect(str(destination)) as dst:
        src.backup(dst)
        result = dst.execute('PRAGMA integrity_check').fetchone()[0]
        if result != 'ok':
            raise RuntimeError(f'Backup integrity check failed: {result}')
    return destination

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('backups') / f'community-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.db')
    args = parser.parse_args()
    print(backup(args.output))
