"""Run a synthetic stage rehearsal without Discord, credentials, or production data."""
import argparse
from datetime import datetime, timedelta, timezone
from itertools import count
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True, help='A NEW directory; never overwrites an existing directory')
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    database = output / 'synthetic-rehearsal.db'
    os.environ['DATABASE_URL'] = 'sqlite:///' + str(database)
    # Set before importing app.db, which creates the engine from configuration.
    subprocess.run([sys.executable,'-m','alembic','upgrade','head'],check=True,env=os.environ.copy())
    from sqlalchemy import select, func
    from app.db import Event, Registration, PerformanceEvent, PerformerRegistration
    from app import performances as p
    start = datetime(2035,1,1,19,tzinfo=timezone.utc)
    with p_event_sessions(database).begin() as db:
        db.add(Event(id=1,title='SYNTHETIC REHEARSAL ONLY',starts_at=start,published=True,capacity=1))
        db.add(Registration(event_id=1,discord_id=8000,status='going',created_at=start-timedelta(days=1)))
    sessions = p_event_sessions(database)
    with sessions() as db:
        p.configure(db,1,9000,authorized=True,channel_id=123,
                    ends_at=start+timedelta(hours=4),capacity=25)
    sequence = count()
    clock = start-timedelta(days=1)
    checks = []
    def action(name,user=9000,target=None,request=None,revision=None):
        with sessions() as db: current=db.get(PerformanceEvent,1).revision
        with sessions() as db:
            return p.execute(db,1,user,name,request or f'rehearsal:{next(sequence)}',
                verified=True,organizer=user==9000,target_id=target,
                expected_revision=current if revision is None else revision,at=clock)
    def snapshot():
        with sessions() as db: return p.snapshot(db,1,clock)
    def check(condition,label):
        if not condition: raise RuntimeError('Rehearsal failed: '+label)
        checks.append(label)
    for user in range(1000,1025): action('register',user)
    check(len(snapshot()['queue'])==25,'25 separate performer registrations accepted')
    check(snapshot()['overrun_seconds']==135*60,'25 full sets show a 2h15 overrun beyond the four-hour window')
    action('unregister',1001);action('register',1001)
    check(snapshot()['queue'][1]['discord_id']==1001,'Returning performer fills earliest vacancy without shifting others')
    for user in (1000,1001,1002): action('checkin',user);action('ready',user)
    action('activate')
    clock=start
    first=snapshot()['next']['id']
    revision=snapshot()['config'].revision
    action('start',target=first,request='first-start',revision=revision)
    clock=start+timedelta(minutes=8)
    action('end_set',target=first)
    check(snapshot()['current'] is None,'Ending a set waits for organizer approval')
    second=snapshot()['next']['id']
    check(snapshot()['next']['original_start']==start+timedelta(minutes=15),'Original time remains unchanged after an early finish')
    action('start',target=second)
    check(snapshot()['current']['actual_start']==clock,'Zero-gap handoff starts only through organizer action')
    clock+=timedelta(minutes=15)
    action('end_set',target=second)
    clock+=timedelta(minutes=4)
    check(snapshot()['next']['projected_start']==clock,'House-music wait shifts projections forward')
    sessions=p_event_sessions(database)
    check(snapshot()['next']['ready'],'Fresh database sessions retain arrival/readiness after restart')
    check(snapshot()['current'] is None,'Restart does not auto-start the next set')
    action('pause');action('resume')
    third=snapshot()['next']['id']
    action('start',target=third)
    clock+=timedelta(minutes=15)
    action('end_set',target=third);action('end_event')
    check(snapshot()['next'] is None,'Ending the event archives the unplayed lineup')
    with sessions() as db:
        check(db.scalar(select(func.count()).select_from(Registration))==1 and db.scalar(select(Registration.status))=='going','Attendance RSVP is unchanged')
        check(db.scalar(select(func.count()).select_from(PerformerRegistration))==26,'Withdrawal and re-registration history retained')
    report={'kind':'synthetic-offline-rehearsal','network_requests':0,'production_data_used':False,
            'database':str(database),'passed_checks':checks,'final_state':snapshot()['config'].lifecycle}
    (output/'rehearsal-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0


def p_event_sessions(database):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    return sessionmaker(create_engine('sqlite:///'+str(database)),expire_on_commit=False)


if __name__ == '__main__':
    raise SystemExit(main())
