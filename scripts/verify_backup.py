"""Verify a SQLite backup and restore to a new file, never over live data."""
import argparse
from pathlib import Path
import sqlite3


def restore_copy(source: Path, destination: Path):
    if not source.is_file():
        raise ValueError('Backup file does not exist')
    if source.resolve() == destination.resolve():
        raise ValueError('Restore destination must differ from the backup')
    # Read-only mode cannot create or alter the supplied backup.
    with sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True) as backup:
        if backup.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('SQLite integrity check failed')
        if backup.execute('PRAGMA foreign_key_check').fetchone() is not None:
            raise ValueError('SQLite foreign-key check failed')
        tables = {row[0] for row in backup.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'members', 'events', 'registrations'} <= tables:
            raise ValueError('Backup is missing expected community tables')
        # Exclusive creation prevents overwriting a live database or existing restore.
        with destination.open('xb'):
            pass
        try:
            with sqlite3.connect(destination) as restored:
                backup.backup(restored)
                if restored.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Restored copy failed integrity check')
        except Exception:
            destination.unlink(missing_ok=True)
            raise
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup', required=True, type=Path)
    parser.add_argument('--restore-to', required=True, type=Path)
    args = parser.parse_args()
    try:
        restore_copy(args.backup, args.restore_to)
    except (ValueError, FileExistsError, sqlite3.Error) as exc:
        parser.exit(1, str(exc) + '\n')
    print('Backup integrity and foreign keys verified; restored to a new file. Live data unchanged.')


if __name__ == '__main__':
    main()
