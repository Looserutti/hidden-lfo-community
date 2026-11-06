from datetime import datetime,timezone
import pytest
from app.venue_squarespace import parse_events

SOURCE={'name':'Example Venue','url':'https://example.org/events','location':'Example venue, City','concerts_only':True}

def event(title,uid='a'*24,url='/events/show',dates='20261107T010000Z/20261107T040000Z'):
    return f'<article class="eventlist-event"><a class="eventlist-title-link" href="{url}">{title}</a><a class="eventlist-meta-export-google" href="https://www.google.com/calendar/event?action=TEMPLATE&amp;dates={dates}">Calendar</a><div id="item-{uid}"></div></article>'


def test_concerts_filter_keeps_bands_and_excludes_non_concerts():
    titles=['Billy &amp; Friends (Blues), Free','DJ Shattered Room presents Runs Deep, Cloud Types (Shoegaze)',
            'Karaoke Mondays','Musical Trivia & Bingo','Open-Mic Night','All-Vinyl DJ Night',
            'Fundraiser with music','Pour Out The Arts: bands and vendors','HAPPY THANKSGIVING!',
            'Comedy night','Private event']
    rows=parse_events(''.join(event(t,f'{i:024x}') for i,t in enumerate(titles)),SOURCE)
    assert [e['title'] for e in rows]==['Billy & Friends (Blues), Free',titles[1]]
    assert rows[0]['starts_at']==datetime(2026,11,7,1,tzinfo=timezone.utc)
    assert rows[0]['location']=='Example venue, City'


def test_identity_dedupe_and_changed_format_preserves_failures():
    assert len(parse_events(event('Band')+event('Band'),SOURCE))==1
    for html in ['<p>Changed calendar</p>',event('Band',dates='unknown'),event('Band',url='https://other.org/show'),
                 event('Band',uid='invalid'),event('Band').replace('</article>','')]:
        with pytest.raises(ValueError):parse_events(html,SOURCE)
    assert parse_events(event('Karaoke'),SOURCE)==[]
    assert len(parse_events(event('Karaoke'),{**SOURCE,'concerts_only':False}))==1
    assert parse_events(event('CANCELLED: Band'),SOURCE)[0]['cancelled']


def test_concert_renamed_as_non_concert_retires_without_losing_staff_exclusion():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db import Base,ImportedEvent
    from app.feeds import save_events
    engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    source={**SOURCE,'id':'venue','adapter':'squarespace_events'}
    with sessionmaker(engine)() as db:
        save_events(db,source,parse_events(event('Live Band'),source));db.commit()
        record=db.get(ImportedEvent,('venue','a'*24));record.suppressed=True;db.commit()
        save_events(db,source,parse_events(event('Karaoke'),source));db.commit()
        assert record.cancelled and record.suppressed
        save_events(db,source,parse_events(event('Live Band'),source));db.commit();db.refresh(record)
        assert not record.cancelled and record.suppressed
    engine.dispose()
