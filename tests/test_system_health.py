from datetime import datetime, timedelta, timezone
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db import Base, Setting
from app import feeds
from app.system_health import check, summary

NOW=datetime(2026,11,6,17,tzinfo=timezone.utc)

def test_status_is_labelled_and_failures_survive_until_new_success():
    assert check('Backup',None,None,timedelta(hours=36),NOW)['state']=='neutral'
    assert check('Backup',NOW.isoformat(),None,timedelta(hours=36),NOW)['state']=='ok'
    old=(NOW-timedelta(days=2)).isoformat()
    assert check('Backup',old,None,timedelta(hours=36),NOW)['state']=='error'
    assert check('Backup',old,NOW.isoformat(),timedelta(days=7),NOW)['state']=='error'
    assert check('Backup',NOW.isoformat(),old,timedelta(days=7),NOW)['state']=='ok'

def test_weekly_source_overdue_paused_and_preview(tmp_path,monkeypatch):
    monkeypatch.setenv('SYSTEM_HEALTH_FILE',str(tmp_path/'missing'))
    monkeypatch.setenv('SITE_ENVIRONMENT','preview')
    monkeypatch.setattr(feeds,'SOURCES',[dict(id='venue',name='Example venue',adapter='squarespace_events')])
    engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    with Session(engine) as db:
        assert summary(db,NOW)[-1]['label']=='Paused'
        for key in ['collection','venue.collect']:feeds.set_enabled(db,key,True)
        db.commit()
        assert summary(db,NOW)[-1]['state']=='error'
        db.add(Setting(key='feeds.result.venue',value=json.dumps({'last_success':(NOW-timedelta(days=3)).isoformat(),'error':''})));db.commit()
        cards=summary(db,NOW)
        assert cards[-1]['state']=='ok'
        assert cards[3]['label']=='Not running in preview'
        assert cards[0]['state']=='neutral'
