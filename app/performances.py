"""Transactional performance workflow shared by web and Discord.

Use a fresh Session for execute/configure. All writes acquire a SQLite write lock
before reading state. No Discord network request runs inside a write transaction.
"""
import csv
from datetime import timedelta, timezone
from io import StringIO
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from app.db import Event, Member, now, PerformanceEvent, PerformanceSlot, PerformerRegistration, PerformanceAction, PerformanceNotice


class PerformanceError(ValueError):
    pass


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def lock(db):
    if db.in_transaction():
        raise PerformanceError('Use a fresh session for this action.')
    if db.bind.dialect.name != 'sqlite':
        raise PerformanceError('Live performances currently require SQLite.')
    db.connection().exec_driver_sql('BEGIN IMMEDIATE')


def configure(db, event_id, actor_id, *, authorized, channel_id, ends_at, capacity=25,
              set_minutes=15, transition_seconds=0, minimum_seconds=0,
              next_notice_minutes=10, deck_notice_minutes=25):
    if not authorized:
        raise PerformanceError('Organizer access required.')
    if not (1 <= capacity <= 100 and 1 <= set_minutes <= 120 and
            0 <= minimum_seconds <= transition_seconds <= 3600 and
            0 <= next_notice_minutes <= 120 and 0 <= deck_notice_minutes <= 120 and channel_id > 0):
        raise PerformanceError('Invalid capacity, duration, channel, or notification settings.')
    try:
        lock(db)
        event = db.get(Event, event_id)
        if not event or event.deleted_at is not None:
            raise PerformanceError('Event not found.')
        if db.get(PerformanceEvent, event_id):
            raise PerformanceError('Performance configuration is already frozen for this event.')
        if utc(ends_at) <= utc(event.starts_at):
            raise PerformanceError('The event end must follow its start.')
        config = PerformanceEvent(event_id=event_id, channel_id=channel_id,
            starts_at=utc(event.starts_at), ends_at=utc(ends_at), capacity=capacity,
            set_minutes=set_minutes, transition_seconds=transition_seconds,
            minimum_seconds=minimum_seconds, next_notice_minutes=next_notice_minutes,
            deck_notice_minutes=deck_notice_minutes)
        db.add(config); db.flush()
        for position in range(1, capacity + 1):
            start = utc(event.starts_at) + timedelta(seconds=(position - 1) * (set_minutes * 60 + transition_seconds))
            db.add(PerformanceSlot(event_id=event_id, position=position, original_start=start,
                                   original_end=start + timedelta(minutes=set_minutes)))
        db.add(PerformanceAction(event_id=event_id, request_id=f'configure:{event_id}',
            actor_id=actor_id, action='configure', result='Performance registration configured.'))
        db.commit()
    except Exception:
        db.rollback(); raise


def entries(db, event_id):
    return db.execute(select(PerformerRegistration, PerformanceSlot).join(
        PerformanceSlot, PerformerRegistration.slot_id == PerformanceSlot.id).where(
        PerformerRegistration.event_id == event_id, PerformerRegistration.status != 'cancelled'
    ).order_by(PerformanceSlot.position, PerformerRegistration.registered_at, PerformerRegistration.id)).all()


def snapshot(db, event_id, at=None):
    at = utc(at or now())
    config = db.get(PerformanceEvent, event_id)
    if not config:
        raise PerformanceError('This event has no performer registration.')
    event = db.get(Event, event_id)
    rows = entries(db, event_id)
    current = next((r for r, s in rows if r.status == 'playing'), None)
    anchor = max(at, utc(config.starts_at))
    if current:
        interruption = (at - utc(current.paused_at)).total_seconds() if current.paused_at else 0
        expected_end = utc(current.actual_start) + timedelta(minutes=config.set_minutes,
            seconds=current.paused_seconds + max(0, interruption))
        anchor = max(at, expected_end) + timedelta(seconds=config.transition_seconds)
    elif config.last_ended_at:
        anchor = max(anchor, utc(config.last_ended_at) + timedelta(seconds=config.transition_seconds))
    identities = {m.discord_id: m.server_display_name or m.discord_username for m in db.scalars(
        select(Member).where(Member.discord_id.in_([r.discord_id for r, slot in rows])))}
    queue = []
    for reg, slot in rows:
        projected_start = projected_end = None
        if reg.status == 'registered' and config.lifecycle != 'ended':
            projected_start = anchor
            projected_end = anchor + timedelta(minutes=config.set_minutes)
            anchor = projected_end + timedelta(seconds=config.transition_seconds)
        queue.append(dict(id=reg.id, discord_id=reg.discord_id, display_name=identities.get(reg.discord_id) or f'Discord {reg.discord_id}', position=slot.position,
            registered_at=reg.registered_at, status=reg.status, arrived=bool(reg.arrived_at), ready=bool(reg.ready_at),
            original_start=utc(slot.original_start), original_end=utc(slot.original_end),
            projected_start=projected_start, projected_end=projected_end,
            actual_start=utc(reg.actual_start) if reg.actual_start else None,
            actual_end=utc(reg.actual_end) if reg.actual_end else None,
            paused=bool(reg.paused_at), paused_seconds=reg.paused_seconds,
            remaining_seconds=max(0, config.set_minutes * 60 - ((utc(reg.paused_at) if reg.paused_at else utc(reg.actual_end) if reg.actual_end else at) - utc(reg.actual_start)).total_seconds() + reg.paused_seconds) if reg.actual_start else config.set_minutes * 60))
    pending = [r for r in queue if r['status'] == 'registered']
    finish = pending[-1]['projected_end'] if pending and config.lifecycle != 'ended' else (
        max(at, expected_end) if current else
        utc(config.last_ended_at) if config.last_ended_at else None)
    completed = [r for r in queue if r['status'] == 'completed']
    recoverable = max(completed, key=lambda r: (r['actual_end'], r['id'])) if completed and not current and config.lifecycle != 'ended' else None
    return dict(config=config, event=event, queue=queue, recoverable=recoverable,
        current=next((r for r in queue if r['status'] == 'playing'), None),
        next=pending[0] if pending and config.lifecycle != 'ended' else None,
        deck=pending[1] if len(pending) > 1 and config.lifecycle != 'ended' else None,
        projected_finish=finish, overrun_seconds=max(0, int((finish - utc(config.ends_at)).total_seconds())) if finish else 0,
        suspended=not event.published or config.lifecycle in ('paused', 'ended') or bool(current and current.paused_at))


ORGANIZER_ACTIONS = {'activate', 'pause', 'resume', 'end_event', 'reopen_event', 'close', 'open', 'start', 'end_set', 'skip', 'pause_set', 'resume_set', 'recover_set'}


def execute(db, event_id, actor_id, action, request_id, *, verified=False, organizer=False,
            expected_revision=None, target_id=None, at=None):
    supplied_at = at
    if action in ORGANIZER_ACTIONS and not organizer:
        raise PerformanceError('Organizer access required.')
    if action not in ORGANIZER_ACTIONS and not verified and not organizer:
        raise PerformanceError('Verified membership required.')
    try:
        lock(db)
        # Timestamp acceptance after the write lock, so concurrent initial signups
        # are ordered by their committed acceptance time (then registration ID).
        at = utc(supplied_at or now())
        old = db.scalar(select(PerformanceAction).where(PerformanceAction.request_id == str(request_id)))
        if old:
            if old.event_id != event_id or old.actor_id != actor_id or old.action != action or old.target_id != target_id:
                raise PerformanceError('Request identifier already used for another action.')
            db.rollback(); return old.result
        config = db.get(PerformanceEvent, event_id)
        event = db.get(Event, event_id)
        if not config or not event:
            raise PerformanceError('This event has no performer registration.')
        if (action in ORGANIZER_ACTIONS or (organizer and target_id is not None)) and expected_revision != config.revision:
            raise PerformanceError('The stage changed. Refresh before trying again.')
        rows = entries(db, event_id)
        active = [(r, s) for r, s in rows if r.status in ('registered', 'playing')]
        mine = next((r for r, s in active if r.discord_id == (target_id if organizer and target_id is not None and action in {'checkin','ready','notready','checkout'} else actor_id)), None)
        current = next((r for r, s in active if r.status == 'playing'), None)
        pending = [r for r, s in active if r.status == 'registered']
        if config.lifecycle == 'ended' and action != 'reopen_event':
            raise PerformanceError('This live event has ended.')
        if not event.published and action not in {'unregister', 'end_set', 'end_event', 'pause', 'close', 'checkout', 'notready', 'pause_set'}:
            raise PerformanceError('The event is unpublished; live progression is suspended.')
        result = 'Saved.'
        if action == 'register':
            if not config.registration_open:
                raise PerformanceError('Performer registration is closed.')
            if mine:
                raise PerformanceError('You already have an active performer registration.')
            occupied = {s.id for r, s in rows}
            slots = db.scalars(select(PerformanceSlot).where(PerformanceSlot.event_id == event_id).order_by(PerformanceSlot.position)).all()
            # Live progression, not a potentially overdue original timestamp,
            # determines which vacancies are still ahead of the stage.
            frontier = max((s.position for r, s in rows if r.status in ('playing', 'completed', 'skipped')), default=0)
            slot = next((s for s in slots if s.id not in occupied and s.position > frontier), None)
            if not slot:
                raise PerformanceError('No eligible vacant performance position remains.')
            db.add(PerformerRegistration(event_id=event_id, slot_id=slot.id, discord_id=actor_id, registered_at=at))
            result = f'Performer registration saved: position {slot.position}.'
        elif action == 'unregister':
            if not mine:
                raise PerformanceError('You have no active performer registration.')
            if mine.status == 'playing':
                raise PerformanceError('The organizer must end your current set before withdrawal.')
            mine.status = 'cancelled'; mine.cancelled_at = at; mine.ready_at = None
            result = 'Performer registration cancelled. Your RSVP is unchanged.'
        elif action in {'checkin', 'ready', 'notready', 'checkout'}:
            if not mine:
                raise PerformanceError('No active performer registration found.')
            if action == 'checkin': mine.arrived_at = at
            if action == 'ready':
                if not mine.arrived_at:
                    raise PerformanceError('Check in on arrival before marking ready.')
                mine.ready_at = at
            if action in {'notready', 'checkout'}:
                if mine.status == 'playing':
                    raise PerformanceError('The organizer must end the current set first.')
                mine.ready_at = None
            if action == 'checkout': mine.arrived_at = None
            result = {'checkin':'Arrival recorded.', 'ready':'Ready to perform.', 'notready':'Marked not ready.', 'checkout':'Checked out; readiness cleared.'}[action]
        elif action == 'activate':
            if config.lifecycle != 'scheduled': raise PerformanceError('Event is already activated.')
            config.lifecycle = 'live'; result = 'Live event activated. Start the first set when ready.'
        elif action == 'pause':
            if config.lifecycle != 'live': raise PerformanceError('Only a live event can be paused.')
            config.lifecycle = 'paused'; result = 'Stage progression paused; an active set remains active until ended.'
        elif action == 'resume':
            if config.lifecycle != 'paused': raise PerformanceError('Event is not paused.')
            config.lifecycle = 'live'; result = 'Live event resumed; no set was started automatically.'
        elif action in {'open', 'close'}:
            config.registration_open = action == 'open'; result = f'Performer registration {"opened" if action == "open" else "closed"}.'
        elif action == 'start':
            if config.lifecycle != 'live' or current:
                raise PerformanceError('Start requires a live event with no set currently playing.')
            target = pending[0] if pending else None
            if not target or target.id != target_id:
                raise PerformanceError('The next performer changed. Refresh the stage board.')
            if not target.arrived_at or not target.ready_at:
                raise PerformanceError('The next performer must be arrived and ready.')
            if config.last_ended_at and at < utc(config.last_ended_at) + timedelta(seconds=config.minimum_seconds):
                raise PerformanceError('The configured minimum handoff time has not elapsed.')
            target.status = 'playing'; target.actual_start = at
            result = f'Performance started for Discord user {target.discord_id}.'
        elif action in {'pause_set', 'resume_set'}:
            if not current or current.id != target_id:
                raise PerformanceError('The current performer changed. Refresh the stage board.')
            if at < utc(current.actual_start): raise PerformanceError('Action cannot precede actual start.')
            if action == 'pause_set':
                if current.paused_at: raise PerformanceError('This performance is already paused.')
                current.paused_at = at
                result = 'Performance paused. Remaining set time is held; the next performer cannot start.'
            else:
                if config.lifecycle != 'live': raise PerformanceError('Resume stage progression before resuming the performance.')
                if not current.paused_at: raise PerformanceError('This performance is not paused.')
                if at < utc(current.paused_at): raise PerformanceError('Resume cannot precede pause.')
                current.paused_seconds += (at - utc(current.paused_at)).total_seconds()
                current.paused_at = None
                result = 'Performance resumed with its remaining set time. Original start preserved.'
        elif action == 'recover_set':
            if config.lifecycle != 'live' or current:
                raise PerformanceError('Recovery requires a live event with no other set playing.')
            completed = [r for r, slot in rows if r.status == 'completed']
            target = max(completed, key=lambda r: (utc(r.actual_end), r.id)) if completed else None
            if not target or target.id != target_id:
                raise PerformanceError('Only the most recently ended performance can be restored. Refresh the board.')
            if any(r.actual_start and utc(r.actual_start) > utc(target.actual_start) for r, slot in rows):
                raise PerformanceError('Another performance has already started; this set cannot be restored.')
            if any(r.discord_id == target.discord_id for r, slot in active):
                raise PerformanceError('This performer has another active signup; resolve it before restoring the set.')
            if not target.arrived_at: raise PerformanceError('The performer must still be checked in.')
            if at < utc(target.actual_end): raise PerformanceError('Recovery cannot precede the recorded end.')
            target.paused_seconds += (at - utc(target.actual_end)).total_seconds()
            target.actual_end = None
            target.status = 'playing'; target.ready_at = at
            previous = [r.actual_end for r in completed if r.id != target.id and r.actual_end]
            config.last_ended_at = max(previous, key=utc) if previous else None
            result = 'Accidentally ended set restored with its remaining time. The earlier end action remains in history.'
        elif action == 'end_set':
            if not current or current.id != target_id:
                raise PerformanceError('The current performer changed. Refresh the stage board.')
            if at < utc(current.actual_start): raise PerformanceError('End cannot precede actual start.')
            if current.paused_at:
                if at < utc(current.paused_at): raise PerformanceError('End cannot precede pause.')
                current.paused_seconds += (at - utc(current.paused_at)).total_seconds()
                current.paused_at = None
            current.status = 'completed'; current.actual_end = at; current.ready_at = None
            config.last_ended_at = at
            result = 'Set ended. Transition / house music; the next set awaits organizer approval.'
        elif action == 'skip':
            target = pending[0] if pending else None
            if not target or target.id != target_id: raise PerformanceError('Refresh before skipping the next performer.')
            target.status = 'skipped'; target.ready_at = None
            result = 'Next performer skipped. Position retained in history; organizer can arrange a new signup.'
        elif action == 'reopen_event':
            if config.lifecycle != 'ended':
                raise PerformanceError('Only an ended event can be reopened.')
            config.lifecycle = 'live'
            config.registration_open = True
            result = 'Live event reopened for performer registration. Set history preserved.'
        elif action == 'end_event':
            if current: raise PerformanceError('End the current set before ending the event.')
            config.lifecycle = 'ended'; config.registration_open = False
            result = 'Live event ended. Final set sheet preserved.'
        else:
            raise PerformanceError('Unknown performance action.')
        config.revision += 1
        db.add(PerformanceAction(event_id=event_id, request_id=str(request_id), actor_id=actor_id,
            action=action, target_id=target_id, recorded_at=at, result=result))
        db.flush()
        queue_notices(db, event_id, at)
        db.commit()
        return result
    except (IntegrityError, OperationalError) as exc:
        db.rollback(); raise PerformanceError('Performance registration is busy. Refresh and try again.') from exc
    except Exception:
        db.rollback(); raise


def set_warning(state):
    current = state['current']
    if state['suspended'] or state['config'].lifecycle != 'live' or not current:
        return None
    remaining = current['remaining_seconds']
    if 0 < remaining <= 30:
        return 'current-30', '30 seconds or less. Wrap up your set.'
    if 30 < remaining <= 120:
        return 'current-120', '2 minutes or less remaining in your set.'
    return None


def queue_notices(db, event_id, at):
    state = snapshot(db, event_id, at)
    config = state['config']
    valid_keys = set()
    pending = []
    if config.lifecycle == 'live' and state['event'].published and not state['suspended']:
        for name, minutes in [('next', config.next_notice_minutes), ('deck', config.deck_notice_minutes)]:
            row = state[name]
            if not row or not row['projected_start'] or row['projected_start'] - at > timedelta(minutes=minutes):
                continue
            content = f'<@{row["discord_id"]}> You are {"up next: prepare your setup and confirm readiness" if name == "next" else "on deck: gather your equipment"}. Estimated performance <t:{int(row["projected_start"].timestamp())}:t>; organizer approval required.'
            pending.append((row, name, content))
    warning = set_warning(state)
    if warning:
        name, message = warning
        row = state['current']
        pending.append((row, name, f'<@{row["discord_id"]}> {message}'))
    for row, name, content in pending:
        key = f'{event_id}:{row["id"]}:{name}'
        valid_keys.add(key)
        existing = db.scalar(select(PerformanceNotice).where(PerformanceNotice.delivery_key == key))
        if existing is None:
            db.add(PerformanceNotice(event_id=event_id, delivery_key=key, recipient_id=row['discord_id'], content=content, created_at=at))
        elif existing.sent_at is None:
            existing.content = content
            existing.obsolete = False
    for notice in db.scalars(select(PerformanceNotice).where(PerformanceNotice.event_id == event_id, PerformanceNotice.sent_at.is_(None))):
        if notice.delivery_key not in valid_keys: notice.obsolete = True


def final_set_sheet_csv(state):
    """Export the finalized lineup, with UTC timestamps and measured set lengths."""
    if state['config'].lifecycle != 'ended':
        raise PerformanceError('End the live event before exporting its final set sheet.')
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Position', 'Performer', 'Discord account ID', 'Status',
                     'Original start (UTC)', 'Original end (UTC)', 'Actual start (UTC)',
                     'Actual end (UTC)', 'Playing seconds', 'Paused seconds',
                     'Changeover seconds before set'])

    def stamp(value):
        return value.isoformat(timespec='seconds') if value else ''

    previous_end = None
    for row in state['queue']:
        start, end = row['actual_start'], row['actual_end']
        name = row['display_name']
        if name.lstrip().startswith(('=', '+', '-', '@')) or name.startswith(('\t', '\r', '\n')):
            name = "'" + name
        writer.writerow([
            row['position'], name, row['discord_id'], row['status'],
            stamp(row['original_start']), stamp(row['original_end']), stamp(start), stamp(end),
            round(max(0, (end - start).total_seconds() - row['paused_seconds']), 1) if start and end else '',
            round(row['paused_seconds'], 1) if start else '',
            round((start - previous_end).total_seconds(), 1) if start and previous_end else '',
        ])
        if end:
            previous_end = end
    return output.getvalue().encode('utf-8-sig')
