from datetime import datetime, timedelta, timezone
from app.activity import classify, report_text
from app.db import Member

NOW = datetime(2026, 11, 2, tzinfo=timezone.utc)
def test_statuses():
    old = NOW - timedelta(days=150)
    m = Member(discord_id=1, joined_at=old, last_server_activity=NOW-timedelta(days=61), exempt=False)
    assert classify(m, NOW)['status'] == 'review'
    m.last_observed_online = NOW-timedelta(days=2)
    assert classify(m, NOW)['status'] == 'active'
    m.exempt = True
    assert classify(m, NOW)['status'] == 'exempt'
    m.exempt = False
    m.last_server_activity = None
    m.last_observed_online = None
    assert classify(m, NOW)['status'] == 'unknown'
    m.joined_at = NOW-timedelta(days=10)
    assert classify(m, NOW)['status'] == 'grace'

def test_summary_text():
    result = report_text(dict(active=1, review=2, grace=3, unknown=4, exempt=5))
    assert 'Review: 2' in result and 'no automatic removals' in result
