"""Common-language date/time entry without a network or AI dependency."""
import calendar
import re
from datetime import datetime, timedelta, timezone
from app.calendar_utils import calendar_time, local_event_start


def member_event_start(day_text, time_text, zone, reference=None):
    local = calendar_time(reference or datetime.now(timezone.utc), zone)
    day = re.sub(r'(?<=\d)(st|nd|rd|th)\b', '', day_text.strip().casefold()).replace(',', '')
    day = ' '.join(day.split())
    clock = time_text.strip().casefold().replace('.', '').removeprefix('at ').strip()
    if clock in ('noon', 'midnight'):
        hour, minute = (12, 0) if clock == 'noon' else (0, 0)
    else:
        match = re.fullmatch(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', clock)
        if not match:
            raise ValueError('For the time, try 7pm, 7:30pm, or 19:30.')
        hour, minute, period = int(match[1]), int(match[2] or 0), match[3]
        if minute > 59 or (period and not 1 <= hour <= 12) or (not period and (hour > 23 or match[2] is None)):
            raise ValueError('For the time, try 7pm, 7:30pm, or 19:30.')
        if period:
            hour = hour % 12 + (12 if period == 'pm' else 0)
    clock = f'{hour:02d}:{minute:02d}'
    weekdays = {name.casefold(): i for i,name in enumerate(calendar.day_name)}
    weekdays.update({name.casefold(): i for i,name in enumerate(calendar.day_abbr)})
    weekday = re.sub(r'^(this|next) ', '', day)
    if day in ('today', 'tomorrow'):
        date = local.date() + timedelta(days=day == 'tomorrow')
    elif weekday in weekdays:
        offset = (weekdays[weekday] - local.weekday()) % 7
        if offset == 0 and (day.startswith('next ') or (hour, minute) <= (local.hour, local.minute)):
            offset = 7
        date = local.date() + timedelta(days=offset)
    else:
        date = None
        formats = [('%Y-%m-%d',True),('%m/%d/%Y',True),('%m/%d/%y',True),
                   ('%b %d %Y',True),('%B %d %Y',True),('%m/%d',False),
                   ('%b %d',False),('%B %d',False),('%d %b',False)]
        for fmt, has_year in formats:
            try:
                date = datetime.strptime(day if has_year else f'{day} {local.year}',
                                         fmt if has_year else fmt+' %Y').date()
                if not has_year and (date, hour, minute) <= (local.date(), local.hour, local.minute):
                    date = date.replace(year=date.year+1)
                break
            except ValueError:
                date = None
        if date is None:
            raise ValueError('For the date, try tomorrow, Saturday, Nov 14, or 11/14 (month/day).')
    return local_event_start(date.isoformat(), clock, zone)
