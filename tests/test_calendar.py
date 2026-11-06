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


def test_pacific_calendar_groups_utc_next_day_on_local_date():
    from app.calendar_utils import calendar_time, month_bounds
    event = SimpleNamespace(starts_at=datetime(2026, 11, 7, 2))
    weeks = month_grid(2026, 11, [event], 'America/Los_Angeles')
    assert next(d for w in weeks for d in w if str(d['date']) == '2026-11-06')['events'] == [event]
    assert calendar_time(event.starts_at, 'America/Los_Angeles').hour == 18
    # A month boundary crosses UTC dates; DST changes the UTC offset in November.
    start, end = month_bounds(2026, 11, 'America/Los_Angeles')
    assert start == datetime(2026, 11, 1, 7, tzinfo=timezone.utc)
    assert end == datetime(2026, 12, 1, 8, tzinfo=timezone.utc)
    boundary = SimpleNamespace(starts_at=datetime(2026, 12, 1, 2, tzinfo=timezone.utc))
    assert next(d for w in month_grid(2026, 11, [boundary], 'America/Los_Angeles') for d in w if str(d['date']) == '2026-11-30')['events'] == [boundary]


def test_date_picker_converts_winter_summer_and_rejects_dst_gaps():
    from app.calendar_utils import local_event_start
    assert local_event_start('2026-11-06','18:00','America/Los_Angeles') == datetime(2026,11,7,2,tzinfo=timezone.utc)
    assert local_event_start('2027-07-06','18:00','America/Los_Angeles') == datetime(2027,7,7,1,tzinfo=timezone.utc)
    with pytest.raises(ValueError, match='does not exist'):
        local_event_start('2027-03-14','02:30','America/Los_Angeles')
    with pytest.raises(ValueError, match='occurs twice'):
        local_event_start('2027-11-07','01:30','America/Los_Angeles')

@pytest.mark.parametrize('with_event', [True, False])
def test_agenda_groups_on_local_date_and_handles_empty_month(with_event):
    from datetime import date
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    from app.calendar_utils import calendar_time, agenda_page
    env = Environment(loader=FileSystemLoader('templates'), autoescape=select_autoescape())
    env.filters['calendar_time'] = lambda stamp: calendar_time(stamp, 'America/Los_Angeles')
    event = SimpleNamespace(id=42, title='A concert with a longer readable title',
        starts_at=datetime(2026, 11, 7, 2), location='Local venue', external_url='', source_name='')
    html = env.get_template('calendar.html').render(
        site={'name':'Community','socials':{},'footer_text':''},
        weeks=month_grid(2026,11,[event] if with_event else [],'America/Los_Angeles'),
        today=date(2026,11,6), agenda=agenda_page([event] if with_event else [], 'America/Los_Angeles', datetime(2026,11,6,12,tzinfo=timezone.utc)), agenda_page=0, month_name='November', year=2026,
        previous=(2026,10), following=(2026,12), calendar_timezone='America/Los_Angeles')
    agenda = html.split('<div class="calendar-agenda"',1)[1]
    if with_event:
        assert 'id="agenda-2026-11-06"' in agenda
        assert 'id="agenda-2026-11-07"' not in agenda
        assert 'Today</span>' in agenda and '6:00 PM' in agenda and 'PST' in agenda
        assert event.title in agenda and 'Local venue' in agenda and 'href="/events/42"' in agenda
        assert 'agenda-empty' not in agenda
    else:
        assert 'No upcoming events published' in agenda
        assert 'class="agenda-day' not in agenda


def test_rolling_agenda_counts_events_includes_today_and_crosses_months():
    from datetime import timedelta
    from app.calendar_utils import agenda_page
    reference = datetime(2026,12,1,7,tzinfo=timezone.utc)  # Nov 30, 11pm Pacific
    earlier_today = datetime(2026,11,30,9,tzinfo=timezone.utc)
    events = [SimpleNamespace(id=i, starts_at=earlier_today+timedelta(days=i//2,hours=i%2)) for i in range(23)]
    yesterday = SimpleNamespace(id=99, starts_at=earlier_today-timedelta(days=1))
    candidates = list(reversed([yesterday,*events]))
    first = agenda_page(candidates,'America/Los_Angeles',reference)
    second = agenda_page(candidates,'America/Los_Angeles',reference,page=1)
    third = agenda_page(candidates,'America/Los_Angeles',reference,page=2)
    ids = lambda batch: [e.id for d in batch['days'] for e in d['events']]
    assert ids(first)==list(range(10)) and first['has_next']
    assert first['days'][0]['date'].isoformat()=='2026-11-30'
    assert any(d['date'].month==12 for d in first['days'])
    assert ids(second)==list(range(10,20)) and second['has_next']
    assert ids(third)==[20,21,22] and not third['has_next']
    assert second['first']==11 and second['last']==20
