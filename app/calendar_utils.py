import calendar
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

def calendar_time(stamp, zone="UTC"):
    return stamp.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(zone)) if stamp.tzinfo is None else stamp.astimezone(ZoneInfo(zone))

def month_bounds(year, month, zone="UTC"):
    tz = ZoneInfo(zone)
    start = datetime(year, month, 1, tzinfo=tz)
    end = datetime(year + 1, 1, 1, tzinfo=tz) if month == 12 else datetime(year, month + 1, 1, tzinfo=tz)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)

def month_grid(year: int, month: int, events, zone="UTC"):
    if not 1 <= month <= 12 or not 2000 <= year <= 2100:
        raise ValueError('Invalid calendar month')
    by_day = {}
    for event in events:
        day = calendar_time(event.starts_at, zone).date()
        by_day.setdefault(day, []).append(event)
    weeks = []
    for week in calendar.Calendar(firstweekday=6).monthdatescalendar(year, month):
        weeks.append([{'date': date, 'in_month': date.month == month, 'events': by_day.get(date, []) if date.month == month else []} for date in week])
    return weeks

def calendar_navigation(year: int, month: int):
    previous = (year - 1, 12) if month == 1 else (year, month - 1)
    following = (year + 1, 1) if month == 12 else (year, month + 1)
    return previous, following


def local_event_start(date, time, zone):
    """Convert date/time picker values to UTC; reject DST gaps and overlaps."""
    naive = datetime.fromisoformat(date + 'T' + time)
    if naive.tzinfo is not None:
        raise ValueError('Use a date and local time without a timezone offset')
    tz = ZoneInfo(zone)
    candidates = set()
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=tz, fold=fold).astimezone(timezone.utc)
        if candidate.astimezone(tz).replace(tzinfo=None) == naive:
            candidates.add(candidate)
    if not candidates:
        raise ValueError('This time does not exist because of the daylight-saving change; choose another time')
    if len(candidates) > 1:
        raise ValueError('This time occurs twice during the daylight-saving change; choose an unambiguous time')
    return candidates.pop()


def agenda_page(events, zone, reference, page=0, size=10):
    """Chronological event batches from local midnight today, across months."""
    today = calendar_time(reference, zone).date()
    eligible = sorted((e for e in events if calendar_time(e.starts_at, zone).date() >= today),
                      key=lambda e: calendar_time(e.starts_at, 'UTC'))
    offset = page * size
    selected = eligible[offset:offset + size]
    days = {}
    for event in selected:
        date = calendar_time(event.starts_at, zone).date()
        days.setdefault(date, []).append(event)
    return {'days': [{'date': date, 'events': items} for date,items in days.items()],
            'has_next': len(eligible) > offset + size, 'count': len(selected),
            'first': offset + 1 if selected else 0, 'last': offset + len(selected)}
