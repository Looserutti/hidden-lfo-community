from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from app.calendar_utils import month_grid, calendar_navigation

def test_month_grid_contains_event():
    event = SimpleNamespace(starts_at=datetime(2026, 11, 14, 19, tzinfo=timezone.utc))
    weeks = month_grid(2026, 11, [event])
    matching = [d for w in weeks for d in w if d['date'].day == 14 and d['in_month']]
    assert len(matching) == 1 and matching[0]['events'] == [event]

def test_navigation_year_boundary():
    assert calendar_navigation(2026, 12) == ((2026, 11), (2027, 1))
    assert calendar_navigation(2026, 1) == ((2025, 12), (2026, 2))

def test_reject_invalid_month():
    with pytest.raises(ValueError):
        month_grid(2026, 13, [])
