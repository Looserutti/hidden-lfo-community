"""Read Squarespace's public event list without executing venue scripts."""
from datetime import datetime, timezone
from html.parser import HTMLParser
import re
from urllib.parse import parse_qs, urljoin, urlsplit

# Prefer excluding mixed/non-concert programming to publishing it accidentally.
NON_CONCERT = re.compile(
    r'\b(?:trivia|bingo|karaoke|open[\s-]*mic|private\s+event|closed|thanksgiving|'
    r'fundrais\w*|vendors?|markets?|workshops?|comedy|stand[\s-]*up|screening|'
    r'watch\s+party|game\s+night)\b|\ball[\s-]+vinyl\b|\bdj\s+night\b', re.I)


class EventBatch(list):
    """Keep filtered IDs so previously imported shows can become ineligible safely."""
    def __init__(self):
        super().__init__()
        self.excluded_ids = set()


class EventList(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.current = None
        self.title_open = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get('class', '').split()
        if tag == 'article' and 'eventlist-event' in classes:
            if self.current is not None:
                raise ValueError('Unexpected nested venue event')
            self.current = {'title': [], 'cancelled': any('cancel' in c for c in classes)}
        if self.current is None:
            return
        if tag == 'a' and 'eventlist-title-link' in classes:
            self.current['url'] = attrs.get('href', '')
            self.title_open = True
        if tag == 'a' and 'eventlist-meta-export-google' in classes:
            self.current['dates'] = parse_qs(urlsplit(attrs.get('href', '')).query).get('dates', [''])[0]
        if re.fullmatch(r'item-[a-f0-9]{24}', attrs.get('id', '')):
            self.current['id'] = attrs['id'][5:]

    def handle_data(self, data):
        if self.current is not None and self.title_open:
            self.current['title'].append(data)

    def handle_endtag(self, tag):
        if tag == 'a':
            self.title_open = False
        if tag == 'article' and self.current is not None:
            self.rows.append(self.current)
            self.current = None


def parse_events(html, source):
    parser = EventList()
    parser.feed(html)
    parser.close()
    if not parser.rows or parser.current is not None:
        raise ValueError('No complete supported venue event list found; existing listings kept')
    events = EventBatch()
    seen = set()
    base = urlsplit(source['url'])
    for row in parser.rows:
        title = ' '.join(''.join(row['title']).split())
        if not title:
            raise ValueError('Venue event is missing its title')
        if source.get('concerts_only', False) and NON_CONCERT.search(title):
            if row.get('id'):
                events.excluded_ids.add(row['id'])
            continue
        event_id = row.get('id', '')
        dates = row.get('dates', '')
        url = urljoin(source['url'], row.get('url', ''))
        target = urlsplit(url)
        if (not event_id or not row.get('url') or target.scheme != 'https'
                or target.netloc != base.netloc or not target.path.startswith(base.path.rstrip('/') + '/')
                or not re.fullmatch(r'\d{8}T\d{6}Z/\d{8}T\d{6}Z', dates)):
            raise ValueError('Venue event identity, link or export time is missing or unsupported')
        stamp = datetime.strptime(dates.split('/')[0], '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
        if event_id in seen:
            continue
        seen.add(event_id)
        events.append({'external_id': event_id, 'title': title[:250], 'starts_at': stamp,
            'location': source.get('location', source['name'])[:250], 'source_url': url,
            'cancelled': row['cancelled'] or bool(re.search(r'\bcancel[le]+d\b', title, re.I))})
    return events
