import sqlite3
import pytest
from scripts.backup_bundle import snapshot, verify


def test_complete_snapshot_and_corruption_detection(tmp_path):
    source=tmp_path/'live.db'; audio=tmp_path/'audio'; audio.mkdir()
    names=['a'*32+'.mp3','b'*32+'.mp3']
    for name in names:(audio/name).write_bytes(b'ID3test')
    with sqlite3.connect(source) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE gallery_tracks(filename TEXT,byte_size INTEGER,normalized_filename TEXT,normalized_byte_size INTEGER)')
        db.execute('INSERT INTO gallery_tracks VALUES (?,?,?,?)',(names[0],7,names[1],7))
        db.execute('CREATE TABLE members(id INTEGER)');db.execute('INSERT INTO members VALUES (123)')
    output=tmp_path/'backup'
    assert snapshot(source,audio,output)==2
    assert verify(output)==3
    with sqlite3.connect(output/'community.db') as db:assert db.execute('SELECT id FROM members').fetchone()==(123,)
    (output/'gallery-audio'/names[0]).write_bytes(b'changed')
    with pytest.raises(ValueError):verify(output)


def test_missing_audio_fails_instead_of_claiming_success(tmp_path):
    source=tmp_path/'live.db'
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE gallery_tracks(filename TEXT,byte_size INTEGER)')
        db.execute('INSERT INTO gallery_tracks VALUES (?,?)',('a'*32+'.wav',8))
    with pytest.raises(FileNotFoundError):snapshot(source,tmp_path/'audio',tmp_path/'backup')


def test_saved_photo_batches_are_backed_up_and_verified(tmp_path):
    import json
    source=tmp_path/'live.db';photos=tmp_path/'photos';key='c'*32
    folder=photos/key;folder.mkdir(parents=True)
    (folder/'00-full.jpg').write_bytes(b'photo')
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE settings(key TEXT,value TEXT)')
        db.execute('INSERT INTO settings VALUES (?,?)',('gallery.batch.'+key,json.dumps({'files':{'00-full.jpg':5}})))
    output=tmp_path/'backup'
    assert snapshot(source,tmp_path/'audio',output,photos)==1
    assert verify(output)==2
    (output/'gallery-photos'/key/'00-full.jpg').write_bytes(b'changed')
    with pytest.raises(ValueError):verify(output)


def test_project_photos_are_included_with_matching_post_database(tmp_path):
    import json
    source=tmp_path/'live.db';root=tmp_path/'projects';key='d'*32;folder=root/key;folder.mkdir(parents=True)
    (folder/'00-full.jpg').write_bytes(b'photo')
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE settings(key TEXT,value TEXT)')
        db.execute('INSERT INTO settings VALUES (?,?)',('projects.photo.'+key,json.dumps({'files':{'00-full.jpg':5}})))
    output=tmp_path/'backup'
    assert snapshot(source,tmp_path/'audio',output,project_photos=root)==1
    assert verify(output)==2 and (output/'project-photos'/key/'00-full.jpg').read_bytes()==b'photo'
