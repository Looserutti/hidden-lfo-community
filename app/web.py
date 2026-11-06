import os
import secrets
from uuid import uuid4
from urllib.parse import urlsplit
from datetime import datetime, timezone
import calendar
from app.calendar_utils import month_grid, calendar_navigation, calendar_time, month_bounds
from urllib.parse import urlencode
import httpx
from fastapi import FastAPI, Request, HTTPException, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import select, func
from app.branding import site_context, SITE
from app import feeds
from app.config import ADMIN_IDS, BASE_URL
from app.config import DISCORD_INVITE_URL
from app.db import init_db, Session, Event, Registration, Member, Setting, ImportedEvent
from app.activity import report

app = FastAPI(title='Community Platform')
secret = os.getenv('SESSION_SECRET', '')
if not secret or secret == 'replace-with-long-random-value':
    raise RuntimeError('Set a strong SESSION_SECRET in .env before starting the website')
app.add_middleware(SessionMiddleware, secret_key=secret, same_site='lax', https_only=BASE_URL.startswith('https://'), max_age=60 * 60 * 8)
templates = Jinja2Templates(directory='templates')
CALENDAR_ZONE = SITE.get('calendar_timezone', 'UTC')
templates.env.filters['calendar_time'] = lambda stamp: calendar_time(stamp, CALENDAR_ZONE)

@app.middleware('http')
async def secure_response_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['X-Frame-Options'] = 'DENY'
    if request.url.path.startswith(('/admin', '/auth', '/login')):
        response.headers['Cache-Control'] = 'no-store'
    if BASE_URL.startswith('https://'):
        response.headers['Strict-Transport-Security'] = 'max-age=31536000'
    return response


@app.get('/healthz')
def healthz():
    return {'status': 'ok'}

# Database schema is upgraded explicitly by the deployment's migrate service.
# Local development: run `alembic upgrade head` before starting the web app.

def admin(request: Request):
    if int(request.session.get('discord_id', 0)) not in ADMIN_IDS:
        raise HTTPException(403, 'Admin access required. Sign in with an authorized Discord account.')

def csrf_check(request: Request, token: str):
    if not token or not secrets.compare_digest(token, request.session.get('csrf', '')):
        raise HTTPException(403, 'Invalid form token')

def context(request: Request, **kwargs):
    if 'csrf' not in request.session:
        request.session['csrf'] = secrets.token_urlsafe(32)
    return {'site': site_context(), 'request': request, 'user_id': request.session.get('discord_id'), 'is_admin': int(request.session.get('discord_id', 0)) in ADMIN_IDS, 'csrf': request.session['csrf'], **kwargs}

@app.get('/', response_class=HTMLResponse)
def home(request: Request):
    with Session() as db:
        events = db.scalars(select(Event).where(Event.published == True, Event.starts_at >= datetime.now(timezone.utc)).order_by(Event.starts_at)).all()
        counts = {e.id: db.scalar(select(func.count()).select_from(Registration).where(Registration.event_id == e.id, Registration.status == 'going')) for e in events}
        return templates.TemplateResponse(request, 'index.html', context(request, events=events, counts=counts, invite_url=DISCORD_INVITE_URL))

@app.get('/calendar', response_class=HTMLResponse)
def calendar_page(request: Request, year: int | None = None, month: int | None = None):
    today = calendar_time(datetime.now(timezone.utc), CALENDAR_ZONE)
    year = today.year if year is None else year
    month = today.month if month is None else month
    if not (2000 <= year <= 2100 and 1 <= month <= 12):
        raise HTTPException(400, 'Invalid calendar month')
    start, next_month = month_bounds(year, month, CALENDAR_ZONE)
    with Session() as db:
        events = db.scalars(select(Event).where(Event.published == True, Event.starts_at >= start, Event.starts_at < next_month).order_by(Event.starts_at)).all()
        counts = {e.id: db.scalar(select(func.count()).select_from(Registration).where(Registration.event_id == e.id, Registration.status == 'going')) or 0 for e in events}
        events = sorted([*events, *feeds.calendar_events(db, start, next_month)], key=lambda e: e.starts_at.replace(tzinfo=timezone.utc))
        prev, nxt = calendar_navigation(year, month)
        return templates.TemplateResponse(request, 'calendar.html', context(request, weeks=month_grid(year, month, events, CALENDAR_ZONE), calendar_timezone=CALENDAR_ZONE, month_name=calendar.month_name[month], year=year, month=month, previous=prev, following=nxt, counts=counts, invite_url=DISCORD_INVITE_URL))
  

@app.get('/events/{event_id}', response_class=HTMLResponse)
def event_detail(request: Request, event_id: int):
    with Session() as db:
        e = db.get(Event, event_id)
        if not e or not e.published:
            raise HTTPException(404)
        count = db.scalar(select(func.count()).select_from(Registration).where(Registration.event_id == e.id, Registration.status == 'going'))
        return templates.TemplateResponse(request, 'event.html', context(request, event=e, count=count, invite_url=DISCORD_INVITE_URL))

@app.get('/login')
def login(request: Request):
    client_id = os.getenv('DISCORD_CLIENT_ID', '')
    redirect_uri = os.getenv('DISCORD_REDIRECT_URI', '')
    if not client_id or not redirect_uri or not os.getenv('DISCORD_CLIENT_SECRET'):
        raise HTTPException(503, 'Discord OAuth not configured')
    state = secrets.token_urlsafe(32)
    request.session['oauth_state'] = state
    query = urlencode({'client_id': client_id, 'redirect_uri': redirect_uri, 'response_type': 'code', 'scope': 'identify', 'state': state})
    return RedirectResponse('https://discord.com/oauth2/authorize?' + query)

@app.get('/auth/callback')
async def callback(request: Request, code: str, state: str):
    expected = request.session.pop('oauth_state', None)
    if not expected or not secrets.compare_digest(expected, state):
        raise HTTPException(403, 'Invalid OAuth state')
    try:
      async with httpx.AsyncClient(timeout=15) as client:
        token_response = await client.post('https://discord.com/api/oauth2/token', data={'client_id': os.getenv('DISCORD_CLIENT_ID'), 'client_secret': os.getenv('DISCORD_CLIENT_SECRET'), 'grant_type': 'authorization_code', 'code': code, 'redirect_uri': os.getenv('DISCORD_REDIRECT_URI')})
        token_response.raise_for_status()
        token = token_response.json()['access_token']
        user_response = await client.get('https://discord.com/api/users/@me', headers={'Authorization': f'Bearer {token}'})
        user_response.raise_for_status()
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise HTTPException(502, 'Discord authentication temporarily unavailable') from exc
    if not str(user_response.json().get('id', '')).isdigit():
        raise HTTPException(502, 'Invalid Discord identity response')
    request.session.clear()
    request.session['discord_id'] = int(user_response.json()['id'])
    return RedirectResponse('/admin', status_code=303)

@app.post('/logout')
def logout(request: Request, csrf: str = Form(...)):
    csrf_check(request, csrf)
    request.session.clear()
    return RedirectResponse('/', status_code=303)

@app.get('/admin', response_class=HTMLResponse)
def dashboard(request: Request):
    admin(request)
    with Session() as db:
        events = db.scalars(select(Event).order_by(Event.starts_at.desc())).all()
        counts = {e.id: db.scalar(select(func.count()).select_from(Registration).where(Registration.event_id == e.id, Registration.status == 'going')) or 0 for e in events}
        _, activity_totals = report(db)
        upcoming_total = sum(e.published and e.starts_at.replace(tzinfo=timezone.utc) >= datetime.now(timezone.utc) for e in events)
        return templates.TemplateResponse(request, 'admin.html', context(request, events=events, counts=counts,
            activity_totals=activity_totals, member_total=sum(activity_totals.values()),
            upcoming_total=upcoming_total, draft_total=sum(not e.published for e in events)))

@app.post('/admin/events')
def create_event(request: Request, csrf: str = Form(...), title: str = Form(...), description: str = Form(''), starts_at: str = Form(...), location: str = Form('Discord'), capacity: str = Form('')):
    admin(request)
    csrf_check(request, csrf)
    start = datetime.fromisoformat(starts_at)
    if start.tzinfo is None:
        raise HTTPException(400, 'Start date must include a timezone offset')
    if not title.strip() or len(title) > 200:
        raise HTTPException(400, 'Invalid title')
    cap = int(capacity) if capacity.strip() else None
    if cap is not None and cap < 1:
        raise HTTPException(400, 'Capacity must be positive')
    with Session.begin() as db:
        db.add(Event(title=title.strip(), description=description, starts_at=start, location=location, capacity=cap, published=False))
    return RedirectResponse('/admin', status_code=303)

@app.post('/admin/events/{event_id}/publish')
def publish_event(request: Request, event_id: int, csrf: str = Form(...)):
    admin(request)
    csrf_check(request, csrf)
    with Session.begin() as db:
        e = db.get(Event, event_id)
        if not e:
            raise HTTPException(404)
        e.published = not e.published
    return RedirectResponse('/admin', status_code=303)
from fastapi.staticfiles import StaticFiles
app.mount('/static', StaticFiles(directory='static'), name='static')


def parse_event_fields(title: str, description: str, starts_at: str, location: str, capacity: str):
    try:
        start = datetime.fromisoformat(starts_at)
    except ValueError:
        raise HTTPException(400, 'Invalid ISO 8601 start date')
    if start.tzinfo is None or start.utcoffset() is None:
        raise HTTPException(400, 'Start date must include a timezone offset')
    if not title.strip() or len(title.strip()) > 200:
        raise HTTPException(400, 'Title must be between 1 and 200 characters')
    if len(location) > 250:
        raise HTTPException(400, 'Location is too long')
    try:
        cap = int(capacity) if capacity.strip() else None
    except ValueError:
        raise HTTPException(400, 'Capacity must be an integer')
    if cap is not None and cap < 1:
        raise HTTPException(400, 'Capacity must be positive')
    return dict(title=title.strip(), description=description, starts_at=start,
                location=location.strip() or 'Discord', capacity=cap)


@app.post('/admin/events/{event_id}/edit')
def edit_event(request: Request, event_id: int, csrf: str = Form(...),
               title: str = Form(...), description: str = Form(''),
               starts_at: str = Form(...), location: str = Form('Discord'),
               capacity: str = Form('')):
    admin(request)
    csrf_check(request, csrf)
    changes = parse_event_fields(title, description, starts_at, location, capacity)
    with Session.begin() as db:
        e = db.get(Event, event_id)
        if e is None:
            raise HTTPException(404, 'Event not found')
        attending = db.scalar(select(func.count()).select_from(Registration).where(
            Registration.event_id == event_id, Registration.status == 'going')) or 0
        if changes['capacity'] is not None and changes['capacity'] < attending:
            raise HTTPException(400, 'Capacity cannot be below current registration count')
        for key, value in changes.items():
            setattr(e, key, value)
    return RedirectResponse('/admin', status_code=303)


@app.post('/admin/events/{event_id}/cancel')
def cancel_event(request: Request, event_id: int, csrf: str = Form(...)):
    admin(request)
    csrf_check(request, csrf)
    with Session.begin() as db:
        e = db.get(Event, event_id)
        if e is None:
            raise HTTPException(404, 'Event not found')
        e.published = False
        # Preserve registration history for administrator review.
        # The bot reconciliation loop removes the public Discord announcement.
    return RedirectResponse('/admin', status_code=303)


@app.get('/admin/activity', response_class=HTMLResponse)
def activity_dashboard(request: Request, status: str = 'all', search: str = '', page: int = Query(1, ge=1)):
    admin(request)
    allowed = {'all', 'active', 'review', 'grace', 'unknown', 'exempt'}
    if status not in allowed:
        raise HTTPException(400, 'Invalid status filter')
    with Session() as db:
        rows, totals = report(db)
    if status != 'all':
        rows = [r for r in rows if r['status'] == status]
    if search.strip():
        query = search.strip().casefold()
        rows = [r for r in rows if any(query in str(r.get(key) or '').casefold()
            for key in ('discord_id', 'discord_username', 'server_display_name'))]
    filtered_total = len(rows)
    page_size = 50
    page_count = max(1, (filtered_total + page_size - 1) // page_size)
    page = min(page, page_count)
    offset = (page - 1) * page_size
    page_url = lambda number: '/admin/activity?' + urlencode({'status': status, 'search': search, 'page': number})
    return templates.TemplateResponse(request, 'activity.html', context(request,
        rows=rows[offset:offset + page_size], totals=totals, status=status, search=search,
        filtered_total=filtered_total, page=page, page_count=page_count,
        first_result=offset + 1, last_result=min(offset + page_size, filtered_total),
        previous_page_url=page_url(page - 1), next_page_url=page_url(page + 1)))

@app.post('/admin/members/{discord_id}/exemption')
def member_exemption(request: Request, discord_id: int, csrf: str = Form(...), enabled: str = Form(...)):
    admin(request)
    csrf_check(request, csrf)
    if enabled not in ('true', 'false'):
        raise HTTPException(400, 'Invalid exemption value')
    with Session.begin() as db:
        m = db.get(Member, discord_id)
        if m is None:
            raise HTTPException(404, 'Member not found')
        m.exempt = enabled == 'true'
    return RedirectResponse('/admin/activity', status_code=303)

@app.get('/admin/events/{event_id}/registrations', response_class=HTMLResponse)
def event_registrations(request: Request, event_id: int):
    admin(request)
    with Session() as db:
        e = db.get(Event, event_id)
        if not e:
            raise HTTPException(404)
        regs = db.scalars(select(Registration).where(Registration.event_id == event_id).order_by(Registration.created_at.desc())).all()
        return templates.TemplateResponse(request, 'registrations.html', context(request, event=e, registrations=regs))

@app.get('/admin/settings', response_class=HTMLResponse)
def admin_settings(request: Request, page: int = Query(1, ge=1)):
    admin(request)
    with Session() as db:
        sources = [feeds.source_state(db, source) for source in feeds.SOURCES]
        collection = feeds.enabled(db, 'collection')
        website = feeds.enabled(db, 'website')
        worker = db.get(Setting, 'feeds.worker_seen')
        worker_seen = worker.value if worker else None
        listing_total = db.scalar(select(func.count()).select_from(ImportedEvent))
        listings = db.scalars(select(ImportedEvent).order_by(ImportedEvent.starts_at.desc(), ImportedEvent.source_id, ImportedEvent.external_id).offset((page - 1) * 50).limit(50)).all()
    return templates.TemplateResponse(request, 'admin_settings.html', context(request,
        public_base_url=BASE_URL, sources=sources, collection=collection, website=website,
        collection_weekday=calendar.day_name[SITE.get("calendar_collection", {"weekday": 1})["weekday"]],
        collection_hour=SITE.get("calendar_collection", {"hour": 9})["hour"], calendar_timezone=CALENDAR_ZONE,
        worker_seen=worker_seen, listings=listings, listing_page=page, listing_total=listing_total))


@app.post('/admin/settings/feeds')
def update_feed_settings(request: Request, csrf: str = Form(...), collection: bool = Form(False), website: bool = Form(False)):
    admin(request)
    csrf_check(request, csrf)
    with Session.begin() as db:
        feeds.set_enabled(db, 'collection', collection)
        feeds.set_enabled(db, 'website', website)
    return RedirectResponse('/admin/settings?saved=1', status_code=303)


@app.post('/admin/settings/sources/{source_id}')
def update_source_settings(request: Request, source_id: str, csrf: str = Form(...), collect: bool = Form(False), publish: bool = Form(False)):
    admin(request)
    csrf_check(request, csrf)
    if source_id not in {s['id'] for s in feeds.SOURCES}:
        raise HTTPException(404, 'Unknown calendar source')
    with Session.begin() as db:
        feeds.set_enabled(db, source_id + '.collect', collect)
        feeds.set_enabled(db, source_id + '.publish', publish)
    return RedirectResponse('/admin/settings?saved=1', status_code=303)


@app.post('/admin/settings/sources/{source_id}/pull')
async def pull_calendar_source(request: Request, source_id: str, csrf: str = Form(...)):
    admin(request)
    csrf_check(request, csrf)
    if source_id not in {s['id'] for s in feeds.SOURCES}:
        raise HTTPException(404, 'Unknown calendar source')
    with Session() as db:
        if not feeds.collection_enabled(db, source_id):
            raise HTTPException(409, 'Enable collection and this source before pulling')
    await feeds.collect_source(source_id)
    return RedirectResponse('/admin/settings#sources', status_code=303)


@app.post('/admin/settings/listings')
def add_source_listing(request: Request, csrf: str = Form(...), source_id: str = Form(...), title: str = Form(...), starts_at: str = Form(...), source_url: str = Form(...), location: str = Form('')):
    admin(request)
    csrf_check(request, csrf)
    if source_id not in {s['id'] for s in feeds.SOURCES}:
        raise HTTPException(400, 'Unknown source')
    try:
        stamp = datetime.fromisoformat(starts_at)
    except ValueError:
        raise HTTPException(400, 'Start time must be ISO 8601 with timezone offset')
    try:
        parsed_url = urlsplit(source_url)
    except ValueError:
        raise HTTPException(400, 'Invalid show URL')
    if stamp.tzinfo is None or not title.strip() or len(title) > 250 or len(location) > 250:
        raise HTTPException(400, 'Use a title, valid location and timezone-aware start time')
    if parsed_url.scheme != 'https' or not parsed_url.netloc or parsed_url.username or parsed_url.password:
        raise HTTPException(400, 'Provide a public HTTPS show or ticket link')
    with Session.begin() as db:
        db.add(ImportedEvent(source_id=source_id, external_id='manual-' + uuid4().hex,
            title=title.strip(), starts_at=stamp.astimezone(timezone.utc),
            location=location, source_url=source_url, cancelled=False, suppressed=False))
    return RedirectResponse('/admin/settings#listings', status_code=303)


@app.post('/admin/settings/listings/{source_id}/{external_id}/visibility')
def set_listing_visibility(request: Request, source_id: str, external_id: str, csrf: str = Form(...), hidden: bool = Form(False), page: int = Form(1, ge=1)):
    admin(request)
    csrf_check(request, csrf)
    with Session.begin() as db:
        listing = db.get(ImportedEvent, (source_id, external_id))
        if not listing:
            raise HTTPException(404, 'Listing not found')
        listing.suppressed = hidden
    return RedirectResponse(f'/admin/settings?page={page}#listings', status_code=303)
