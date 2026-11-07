from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from itertools import count
import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from app.db import (Base, Event, Registration, PerformanceEvent, PerformanceSlot,
                    PerformerRegistration, PerformanceAction, PerformanceNotice)
from app import performances as p

START = datetime(2035, 1, 1, 19, tzinfo=timezone.utc)
BEFORE = START - timedelta(days=1)


@pytest.fixture
def store(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "performances.db"}', connect_args={'timeout': 20})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions.begin() as db:
        db.add(Event(id=1, title='Live test', starts_at=START, published=True, capacity=1))
        db.add(Event(id=2, title='Other event', starts_at=START, published=True))
        db.add(Registration(event_id=1, discord_id=888, status='going', created_at=BEFORE))
    with sessions() as db:
        p.configure(db, 1, 99, authorized=True, channel_id=123,
                    ends_at=START + timedelta(hours=4), capacity=25)
    return sessions


@pytest.fixture
def act(store):
    ids = count()
    def perform(action, user=10, at=BEFORE, target=None, request=None, revision=None, organizer=None):
        with store() as db:
            current_revision = db.get(PerformanceEvent, 1).revision
        with store() as db:
            return p.execute(db, 1, user, action, request or f'test:{next(ids)}', verified=True,
                organizer=action in p.ORGANIZER_ACTIONS if organizer is None else organizer,
                expected_revision=current_revision if revision is None else revision, target_id=target, at=at)
    return perform


def state(store, at=START):
    with store() as db: return p.snapshot(db, 1, at)


def prepare(act, users=(10, 11, 12)):
    for user in users:
        act('register', user)
        act('checkin', user)
        act('ready', user)
    act('activate', 99)


def test_rsvp_separation_vacancy_and_history(store, act):
    act('register', 10); act('register', 11); act('register', 12)
    original = [(r['discord_id'], r['position'], r['original_start']) for r in state(store)['queue']]
    act('unregister', 11); act('register', 11, at=BEFORE + timedelta(hours=1))
    rows = state(store)['queue']
    assert [(r['discord_id'],r['position'],r['original_start']) for r in rows] == original
    assert rows[1]['registered_at'].replace(tzinfo=timezone.utc) == BEFORE + timedelta(hours=1)
    with store() as db:
        assert db.scalar(select(func.count()).select_from(PerformerRegistration)) == 4
        assert db.get(Registration, 1).status == 'going'
        assert db.get(Event, 1).capacity == 1
        assert db.scalar(select(func.count()).select_from(PerformanceAction)) == 6


def test_concurrent_signup_fills_distinct_positions(store):
    def signup(user):
        with store() as db:
            try: return p.execute(db, 1, user, 'register', f'concurrent:{user}', verified=True, at=BEFORE)
            except p.PerformanceError as exc: return str(exc)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(signup, range(30)))
    assert sum('saved' in result for result in results) == 25
    with store() as db:
        rows = db.scalars(select(PerformerRegistration)).all()
        assert len(rows) == len({r.slot_id for r in rows}) == 25


def test_duplicate_request_is_idempotent_and_bound_to_actor(store, act):
    result = act('register', request='same')
    assert act('register', request='same') == result
    with pytest.raises(p.PerformanceError, match='identifier'): act('register', 11, request='same')
    with pytest.raises(p.PerformanceError, match='already'): act('register')
    assert len(state(store)['queue']) == 1


def test_arrival_and_readiness_are_separate(store, act):
    act('register')
    with pytest.raises(p.PerformanceError, match='Check in'): act('ready')
    act('checkin'); assert not state(store)['next']['ready']
    act('ready'); assert state(store)['next']['ready']
    act('checkout'); row = state(store)['next']
    assert not row['arrived'] and not row['ready']


def test_organizer_can_override_readiness(store, act):
    act('register', 10)
    act('checkin', 99, organizer=True, target=10)
    act('ready', 99, organizer=True, target=10)
    assert state(store)['next']['ready']


def test_end_waits_for_approval_zero_gap_and_actual_times(store, act):
    prepare(act)
    initial = state(store)
    first, second = initial['next']['id'], initial['deck']['id']
    act('start', 99, at=START, target=first)
    ended = START + timedelta(minutes=8)
    act('end_set', 99, at=ended, target=first)
    after = state(store, ended)
    assert after['current'] is None
    assert after['next']['id'] == second
    assert after['next']['projected_start'] == ended
    assert after['next']['original_start'] == START + timedelta(minutes=15)
    act('start', 99, at=ended, target=second)
    assert state(store, ended)['current']['actual_start'] == ended
    assert state(store, ended)['queue'][0]['actual_end'] == ended


def test_house_music_wait_overrun_and_originals(store, act):
    prepare(act)
    first = state(store)['next']['id']
    act('start', 99, at=START, target=first)
    overrun = state(store, START + timedelta(minutes=20))
    assert overrun['next']['projected_start'] == START + timedelta(minutes=20)
    act('end_set', 99, at=START + timedelta(minutes=20), target=first)
    waiting = state(store, START + timedelta(minutes=27))
    assert waiting['next']['projected_start'] == START + timedelta(minutes=27)
    assert waiting['next']['original_start'] == START + timedelta(minutes=15)


def test_readiness_stale_revision_and_minimum_handoff(store, act):
    prepare(act)
    s = state(store); first = s['next']['id']; stale = s['config'].revision
    act('notready', 10)
    with pytest.raises(p.PerformanceError, match='stage changed'): act('start', 99, at=START, target=first, revision=stale)
    with pytest.raises(p.PerformanceError, match='ready'): act('start', 99, at=START, target=first)
    act('ready', 10); act('start', 99, at=START, target=first)
    with store.begin() as db:
        c = db.get(PerformanceEvent, 1); c.minimum_seconds = c.transition_seconds = 60
    end = START + timedelta(minutes=15)
    act('end_set', 99, at=end, target=first)
    second = state(store, end)['next']['id']
    with pytest.raises(p.PerformanceError, match='minimum'): act('start', 99, at=end, target=second)
    act('start', 99, at=end + timedelta(seconds=60), target=second)


def test_simultaneous_start_and_restart(store, act):
    prepare(act)
    s = state(store); target = s['next']['id']; revision = s['config'].revision
    def start(i):
        with store() as db:
            try: return p.execute(db, 1, 99, 'start', f'start:{i}', organizer=True,
                expected_revision=revision, target_id=target, at=START)
            except p.PerformanceError as exc: return str(exc)
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(start, [1,2]))
    assert sum('Performance started' in result for result in results) == 1
    # New engine/session factory represents process recovery from persistent storage.
    recovered = sessionmaker(create_engine(store.kw['bind'].url), expire_on_commit=False)
    s = state(recovered)
    assert s['current']['id'] == target
    assert s['current']['actual_start'] == START
    assert s['next']['ready'] and s['next']['arrived']


def test_pause_unpublish_end_and_permissions(store, act):
    prepare(act)
    first = state(store)['next']['id']
    with pytest.raises(p.PerformanceError, match='Organizer'): act('start', 10, target=first, organizer=False)
    act('pause', 99)
    with pytest.raises(p.PerformanceError, match='live event'): act('start', 99, target=first)
    act('resume', 99)
    with store.begin() as db: db.get(Event,1).published = False
    with pytest.raises(p.PerformanceError, match='unpublished'): act('start', 99, target=first)
    act('end_event', 99)
    assert state(store)['current'] is None
    with pytest.raises(p.PerformanceError, match='ended'): act('register', 13)


def test_skip_closed_registration_and_delayed_vacancy(store, act):
    prepare(act)
    first = state(store)['next']['id']
    act('skip', 99, target=first)
    assert state(store)['queue'][0]['status'] == 'skipped'
    act('close', 99)
    with pytest.raises(p.PerformanceError, match='closed'): act('register', 13)
    act('open', 99)
    act('unregister', 11)
    act('register', 13, at=START + timedelta(minutes=16))
    assert next(r for r in state(store)['queue'] if r['discord_id']==13)['position'] == 2


def test_notices_durable_deduplicated_and_obsolete(store, act):
    prepare(act)
    first = state(store)['next']['id']
    act('start', 99, at=START, target=first)
    with store() as db:
        p.lock(db); p.queue_notices(db, 1, START + timedelta(minutes=5)); db.commit()
    with store() as db:
        notices = list(db.scalars(select(PerformanceNotice)))
        next_notice = next(n for n in notices if n.recipient_id == 11 and ':next' in n.delivery_key)
        notice_id = next_notice.id
    with store() as db:
        p.lock(db); p.queue_notices(db, 1, START + timedelta(minutes=6)); db.commit()
    with store() as db:
        assert db.scalar(select(func.count()).select_from(PerformanceNotice).where(PerformanceNotice.id==notice_id)) == 1
    act('unregister', 11, at=START + timedelta(minutes=7))
    with store() as db: assert db.get(PerformanceNotice, notice_id).obsolete


def test_configuration_validation_and_no_rewrite(store):
    with store() as db:
        with pytest.raises(p.PerformanceError, match='frozen'):
            p.configure(db,1,99,authorized=True,channel_id=123,ends_at=START+timedelta(hours=4))
    with store() as db:
        with pytest.raises(p.PerformanceError, match='Invalid'):
            p.configure(db,2,99,authorized=True,channel_id=456,ends_at=START+timedelta(hours=4),minimum_seconds=60)


def test_finish_warns_for_twenty_performers(store, act):
    for user in range(20): act('register', user)
    s = state(store)
    assert s['projected_finish'] == START + timedelta(hours=5)
    assert s['overrun_seconds'] == 3600


def test_ended_schedule_does_not_keep_drifting(store, act):
    prepare(act)
    first=state(store)['next']['id']
    act('start',99,at=START,target=first)
    finish=START+timedelta(minutes=15)
    act('end_set',99,at=finish,target=first)
    act('end_event',99,at=finish)
    late=state(store,START+timedelta(hours=6))
    assert late['projected_finish']==finish
    assert late['next'] is None and late['deck'] is None
    assert all(row['projected_start'] is None for row in late['queue'])


def test_repeated_start_request_cannot_start_another_set(store, act):
    prepare(act)
    s=state(store); first=s['next']['id']; revision=s['config'].revision
    message=act('start',99,at=START,target=first,request='repeat-start',revision=revision)
    act('end_set',99,at=START+timedelta(minutes=15),target=first)
    assert act('start',99,at=START+timedelta(minutes=16),target=first,request='repeat-start',revision=revision)==message
    assert state(store)['current'] is None


def test_readiness_change_blocks_stale_organizer_override(store, act):
    act('register',10)
    revision=state(store)['config'].revision
    act('checkin',10)
    with pytest.raises(p.PerformanceError,match='stage changed'):
        act('checkout',99,target=10,organizer=True,revision=revision)
    assert state(store)['next']['arrived']


def test_vacancy_behind_stage_is_not_reused_but_overdue_next_slot_is(store, act):
    act('register',10);act('register',11);act('register',12)
    act('unregister',10)
    act('checkin',11);act('ready',11);act('activate',99)
    second=state(store)['next']['id']
    act('start',99,at=START+timedelta(hours=1),target=second)
    act('unregister',12,at=START+timedelta(hours=1))
    act('register',13,at=START+timedelta(hours=1))
    rows=state(store,START+timedelta(hours=1))['queue']
    replacement=next(r for r in rows if r['discord_id']==13)
    assert replacement['position']==3
    assert replacement['original_start']==START+timedelta(minutes=30)


def test_pause_set_preserves_remaining_time_and_survives_restart(store, act):
    prepare(act)
    first=state(store)['next']['id']
    act('start',99,at=START,target=first)
    act('pause_set',99,at=START+timedelta(minutes=5),target=first)
    recovered=sessionmaker(create_engine(store.kw['bind'].url),expire_on_commit=False)
    paused=state(recovered,START+timedelta(minutes=12))
    assert paused['current']['paused'] and paused['suspended']
    assert paused['current']['remaining_seconds']==600
    assert paused['next']['projected_start']==START+timedelta(minutes=22)
    act('resume_set',99,at=START+timedelta(minutes=12),target=first)
    resumed=state(store,START+timedelta(minutes=14))
    assert not resumed['current']['paused']
    assert resumed['current']['remaining_seconds']==480
    assert resumed['current']['actual_start']==START
    assert resumed['next']['projected_start']==START+timedelta(minutes=22)


def test_pause_and_queue_pause_are_independent(store, act):
    prepare(act)
    first=state(store)['next']['id']
    act('start',99,at=START,target=first)
    act('pause_set',99,at=START+timedelta(minutes=5),target=first)
    act('pause',99,at=START+timedelta(minutes=5))
    with pytest.raises(p.PerformanceError,match='Resume stage progression'):
        act('resume_set',99,at=START+timedelta(minutes=8),target=first)
    act('resume',99,at=START+timedelta(minutes=8))
    assert state(store,START+timedelta(minutes=8))['current']['paused']
    act('resume_set',99,at=START+timedelta(minutes=8),target=first)
    second=state(store)['next']['id']
    with pytest.raises(p.PerformanceError,match='no set currently playing'):
        act('start',99,target=second,at=START+timedelta(minutes=8))


def test_accidental_end_recovery_keeps_clock_and_audit(store, act):
    prepare(act)
    before=state(store);first=before['next']['id'];original=before['next']['original_start']
    act('start',99,at=START,target=first)
    act('end_set',99,at=START+timedelta(minutes=8),target=first)
    assert state(store)['recoverable']['id']==first
    act('recover_set',99,at=START+timedelta(minutes=10),target=first)
    restored=state(store,START+timedelta(minutes=10))
    assert restored['current']['id']==first and restored['current']['actual_start']==START
    assert restored['current']['actual_end'] is None
    assert restored['current']['remaining_seconds']==420
    assert restored['current']['original_start']==original
    with store() as db:
        actions=db.scalars(select(PerformanceAction).where(PerformanceAction.target_id==first)).all()
        assert {a.action for a in actions}>={'start','end_set','recover_set'}
    act('end_set',99,at=START+timedelta(minutes=17),target=first)
    assert state(store,START+timedelta(minutes=17))['queue'][0]['remaining_seconds']==0


def test_recovery_rejects_new_current_and_stale_action(store, act):
    prepare(act)
    first=state(store)['next']['id']
    act('start',99,at=START,target=first)
    act('end_set',99,at=START+timedelta(minutes=8),target=first)
    old=state(store)['config'].revision
    second=state(store)['next']['id']
    act('start',99,at=START+timedelta(minutes=8),target=second)
    with pytest.raises(p.PerformanceError,match='stage changed'):
        act('recover_set',99,at=START+timedelta(minutes=9),target=first,revision=old)
    with pytest.raises(p.PerformanceError,match='no other set'):
        act('recover_set',99,at=START+timedelta(minutes=9),target=first)


def test_ending_paused_set_then_recovery_excludes_all_interruption_time(store, act):
    prepare(act)
    first=state(store)['next']['id']
    act('start',99,at=START,target=first)
    act('pause_set',99,at=START+timedelta(minutes=5),target=first)
    act('end_set',99,at=START+timedelta(minutes=8),target=first)
    act('recover_set',99,at=START+timedelta(minutes=10),target=first)
    assert state(store,START+timedelta(minutes=10))['current']['remaining_seconds']==600


def test_set_warnings_follow_current_performer_clock(store, act):
    from app.db import PerformanceNotice

    prepare(act, users=(10,))
    performer = state(store)['next']
    act('start', 99, target=performer['id'], at=START)

    def warnings(at):
        with store.begin() as db:
            p.queue_notices(db, 1, at)
            db.flush()
            return [(n.delivery_key.rsplit(':', 1)[-1], n.recipient_id)
                    for n in db.scalars(select(PerformanceNotice))
                    if not n.obsolete]

    two_minutes = START + timedelta(minutes=13)
    assert warnings(two_minutes) == [('current-120', 10)]
    assert warnings(two_minutes) == [('current-120', 10)]
    act('pause_set', 99, target=performer['id'], at=two_minutes)
    assert warnings(two_minutes + timedelta(minutes=1)) == []
    resumed = two_minutes + timedelta(minutes=2)
    act('resume_set', 99, target=performer['id'], at=resumed)
    assert warnings(resumed + timedelta(seconds=90)) == [('current-30', 10)]
    act('end_set', 99, target=performer['id'], at=resumed + timedelta(seconds=95))
    assert warnings(resumed + timedelta(seconds=96)) == []


def test_managed_meetup_accepts_advance_performers_but_no_new_attendance_rsvps(store, act):
    from app.services import rsvp

    with store() as db:
        assert 'attend without an RSVP' in rsvp(db, 1, 10, verified=True, attending=True)
        assert rsvp(db, 2, 10, verified=True, attending=True) == 'You are registered!'
    act('register', 10, at=START - timedelta(days=30))
    with store() as db:
        attendance = db.scalars(select(Registration).where(Registration.event_id == 1)).all()
        assert [row.discord_id for row in attendance] == [888]
    assert state(store)['queue'][0]['discord_id'] == 10
