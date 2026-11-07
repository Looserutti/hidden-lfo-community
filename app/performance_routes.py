"""Private organizer interface. No public performer identities are exposed."""
from uuid import uuid4
from fastapi import APIRouter, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from app.db import Event, PerformanceEvent
from sqlalchemy import select
from app.calendar_utils import local_event_start
from sqlalchemy.exc import IntegrityError
from app import performances as service


def performance_routes(session, admin, csrf_check, render, calendar_zone):
    router = APIRouter()
    @router.get('/admin/meetups', response_class=HTMLResponse)
    def manager(request: Request):
        admin(request)
        with session() as db:
            events = db.scalars(select(Event).where(Event.deleted_at.is_(None)).order_by(Event.starts_at.desc(), Event.id.desc())).all()
            configs = {c.event_id: c for c in db.scalars(select(PerformanceEvent))}
            return render(request, template='admin_meetups.html', events=events, configs=configs)

    @router.get('/admin/meetups/{event_id}', response_class=HTMLResponse)
    @router.get('/admin/events/{event_id}/performances', response_class=HTMLResponse)
    def performances(request: Request, event_id: int):
        admin(request)
        with session() as db:
            event = db.get(Event, event_id)
            if not event or event.deleted_at is not None: raise HTTPException(404, 'Event not found')
            config = db.get(PerformanceEvent, event_id)
            state = service.snapshot(db, event_id) if config else None
            return render(request, event=event, state=state, request_id=uuid4().hex)

    @router.get('/admin/meetups/{event_id}/set-sheet.csv')
    def download_set_sheet(request: Request, event_id: int):
        admin(request)
        with session() as db:
            if not db.get(PerformanceEvent, event_id):
                raise HTTPException(404, 'No performance event found.')
            try:
                data = service.final_set_sheet_csv(service.snapshot(db, event_id))
            except service.PerformanceError as exc:
                raise HTTPException(409, str(exc))
        return Response(data, media_type='text/csv', headers={
            'Content-Disposition': f'attachment; filename="meetup-{event_id}-set-sheet.csv"',
            'Cache-Control': 'no-store',
        })

    @router.post('/admin/meetups/{event_id}/configure')
    @router.post('/admin/events/{event_id}/performances/configure')
    def configure(request: Request, event_id: int, csrf: str = Form(''), channel_id: str = Form(''),
                  end_date: str = Form(''), end_time: str = Form(''), capacity: str = Form('25'),
                  set_minutes: str = Form('15'), transition_seconds: str = Form('0'),
                  minimum_seconds: str = Form('0'), next_notice_minutes: str = Form('10'),
                  deck_notice_minutes: str = Form('25')):
        admin(request); csrf_check(request, csrf)
        try:
            end = local_event_start(end_date, end_time, calendar_zone)
            with session() as db:
                service.configure(db, event_id, int(request.session['discord_id']), authorized=True,
                    channel_id=int(channel_id), ends_at=end, capacity=int(capacity), set_minutes=int(set_minutes),
                    transition_seconds=int(transition_seconds), minimum_seconds=int(minimum_seconds),
                    next_notice_minutes=int(next_notice_minutes), deck_notice_minutes=int(deck_notice_minutes))
        except (ValueError, OverflowError) as exc:
            raise HTTPException(400, str(exc))
        except IntegrityError:
            raise HTTPException(409, 'That channel already belongs to a performance event.')
        return RedirectResponse(f'/admin/meetups/{event_id}', status_code=303)

    @router.post('/admin/meetups/{event_id}/action')
    @router.post('/admin/events/{event_id}/performances/action')
    def action(request: Request, event_id: int, csrf: str = Form(''), action: str = Form(''),
               revision: str = Form(''), request_id: str = Form(''), target_id: str = Form('')):
        admin(request); csrf_check(request, csrf)
        if not request_id or len(request_id) > 100:
            raise HTTPException(400, 'Missing or invalid action identifier. Refresh the page.')
        try:
            with session() as db:
                service.execute(db, event_id, int(request.session['discord_id']), action,
                    'web:' + request_id, organizer=True, expected_revision=int(revision),
                    target_id=int(target_id) if target_id else None)
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        return RedirectResponse(f'/admin/meetups/{event_id}', status_code=303)

    return router
