from datetime import datetime, timezone
import pytest
from app.member_dates import member_event_start

REFERENCE=datetime(2026,11,5,22,tzinfo=timezone.utc)
ZONE='America/Los_Angeles'

@pytest.mark.parametrize('day,clock,expected',[
 ('tomorrow','7pm',datetime(2026,11,7,3,tzinfo=timezone.utc)),
 ('Saturday','7:30 PM',datetime(2026,11,8,3,30,tzinfo=timezone.utc)),
 ('Nov 14','19:30',datetime(2026,11,15,3,30,tzinfo=timezone.utc)),
 ('November 14th','7 p.m.',datetime(2026,11,15,3,tzinfo=timezone.utc)),
 ('11/14','noon',datetime(2026,11,14,20,tzinfo=timezone.utc)),
 ('2026-11-14','midnight',datetime(2026,11,14,8,tzinfo=timezone.utc)),
 ('Thursday','1pm',datetime(2026,11,12,21,tzinfo=timezone.utc)),
 ('Jan 2','7pm',datetime(2027,1,3,3,tzinfo=timezone.utc)),
 ('7/6/2027','7pm',datetime(2027,7,7,2,tzinfo=timezone.utc)),
])
def test_friendly_dates(day,clock,expected):
 assert member_event_start(day,clock,ZONE,REFERENCE)==expected

@pytest.mark.parametrize('day,clock',[('someday','7pm'),('11/31','7pm'),('tomorrow','7'),('tomorrow','13pm'),('tomorrow','19:99')])
def test_invalid_entries(day,clock):
 with pytest.raises(ValueError,match='try'): member_event_start(day,clock,ZONE,REFERENCE)

def test_community_date_and_dst_gap():
 assert member_event_start('tomorrow','7pm',ZONE,datetime(2026,11,6,2,tzinfo=timezone.utc))==datetime(2026,11,7,3,tzinfo=timezone.utc)
 with pytest.raises(ValueError,match='does not exist'): member_event_start('3/14/2027','2:30am',ZONE,REFERENCE)
