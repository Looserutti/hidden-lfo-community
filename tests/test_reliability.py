from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from app.db import Base, Event, Registration
from app.services import rsvp

def test_capacity_under_concurrent_registrations(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "test.db"}', connect_args={'timeout': 10})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine)
    with sessions() as db:
        db.add(Event(id=1, title='Limited', starts_at=datetime.now(timezone.utc), published=True, capacity=1))
        db.commit()
    def register(i):
        with sessions() as db:
            return rsvp(db, 1, i, True, True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(register, range(1, 9)))
    with sessions() as db:
        count = db.scalar(select(func.count()).select_from(Registration).where(Registration.status == 'going'))
    assert count == 1
    assert results.count('You are registered!') == 1

def test_cancel_and_reregister(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "test.db"}')
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine)
    with sessions() as db:
        db.add(Event(id=1, title='Test', starts_at=datetime.now(timezone.utc), published=True, capacity=1))
        db.commit()
        assert rsvp(db, 1, 10, True, True) == 'You are registered!'
        assert rsvp(db, 1, 10, True, True) == 'You are already registered.'
        assert rsvp(db, 1, 10, True, False) == 'Your registration has been cancelled.'
        assert rsvp(db, 1, 11, True, True) == 'You are registered!'
