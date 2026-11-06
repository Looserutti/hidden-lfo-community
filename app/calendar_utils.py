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
