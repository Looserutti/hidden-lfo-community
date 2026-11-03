import calendar
from datetime import datetime, timezone

def month_grid(year: int, month: int, events):
    if not 1 <= month <= 12 or not 2000 <= year <= 2100:
        raise ValueError('Invalid calendar month')
    by_day = {}
    for event in events:
        day = event.starts_at.date().day
        by_day.setdefault(day, []).append(event)
    weeks = []
    for week in calendar.Calendar(firstweekday=6).monthdatescalendar(year, month):
        weeks.append([{'date': date, 'in_month': date.month == month, 'events': by_day.get(date.day, []) if date.month == month else []} for date in week])
    return weeks

def calendar_navigation(year: int, month: int):
    previous = (year - 1, 12) if month == 1 else (year, month - 1)
    following = (year + 1, 1) if month == 12 else (year, month + 1)
    return previous, following
