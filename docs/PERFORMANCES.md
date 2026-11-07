# Live performance management (v0.3 development)

This module is implemented in an isolated development copy. It is not deployed.
Existing ordinary event RSVPs, attendance capacity, onboarding, calendar imports,
projects, and media features keep their existing behavior.

## Operating model

Sets default to 15 minutes. Setup can overlap another performance, and an outgoing
performer can break down while the next plays. There is no exclusive 30-minute
reservation. An organizer starts every set explicitly: End current set records
its finish and waits, allowing an immediate handoff or a house-music transition.
Estimated transition time and enforced minimum handoff are separate settings;
both default to zero. An organizer can wait longer at any time.

A performer registers independently of an RSVP, then reports arrival and readiness
separately. Arrival alone never marks them ready. Checkout clears readiness.
Verified membership is required for member actions. Organizers use the existing
Discord-ID admin allowlist, with private website controls protected by OAuth and
CSRF checks. Only one set can be active per event.

## Configuration

Once reviewed and deployed to a test environment with a separate database:

1. Apply Alembic through 0009 before launching the upgraded services.
2. Create a native community event in the admin calendar; choose Manage performers
   & live stage. Assign an existing event text channel or thread by its Discord ID.
   A channel/thread maps to one event, preventing ambiguous commands.
3. Set event end, performer capacity (default 25, configurable 1–100), set duration,
   estimated/minimum handoff, and notification leads. Original performance times
   are frozen at this point, starting from the event's then-current start time.
   Later event-calendar edits do not rewrite this issued schedule.
4. Publish the native event. Drafts accept no performer signups and create no stage
   board. This does not change the general event-announcement opt-in.
5. Enable PERFORMANCE_MANAGEMENT_ENABLED=true only on the intended test gateway
   bot to start stage-board and notification reconciliation every 15 seconds.
   The default is false. Do not run a second gateway bot using the production token.

Bot permissions: View Channel, Send Messages, Read Message History, and Send
Messages in Threads for a thread. The board does not require pin-management
permission. Thread creation is manual in this version. Avoid archived/locked
threads and check channel membership/permissions during acceptance testing.

Configuration is deliberately frozen after save for this first version. Registration
can be closed/reopened independently of live progression. The existing calendar
unpublish action suspends new signups, readiness promotion, and performance starts;
a current set may still be ended. Republishing does not auto-start anything.

## Discord commands

The existing /event proposal command stays unchanged. The distinct /perform group
uses the channel/thread to identify the event:

- /perform action: Register as performer, Withdraw performer registration,
  Arrived, Ready to perform, Not ready, or Leave venue.
- /perform mystatus: own position, original/projected time, arrival/readiness.
- /perform setlist: current lineup with original/projected/actual starts.
- /perform stage: current, next, on-deck, projected finish and stage controls.
- /perform organize: activate, pause, resume, close/open registration, skip next,
  or end event. Organizer-only.

Persistent stage-board buttons explicitly start the next set or end the current
one. Start revalidates the board revision, target performer, arrival, readiness,
minimum handoff, event publication, and live lifecycle in one write transaction.
A stale board asks the organizer to refresh; no action advances twice.

## Registration and schedule rules

Acceptance timestamps are recorded after acquiring the SQLite write lock. Initial
positions follow this order; registration IDs break equal-timestamp ties. Withdrawn
attempts remain in history, but disappear from the active set sheet. Re-registration
creates a new attempt and takes the earliest unoccupied position ahead of actual
stage progression, even if its original time has passed while the event runs late. Other assignments do not move. Completed/skipped
positions remain part of the final history rather than becoming vacancies.

A skip removes that attempt from upcoming performances and retains its position in
history. It does not automatically give the performer a later place. They can sign
up again into an eligible vacancy while registration is open. Withdrawal from an
active set is blocked until its organizer ends it.

Original slot start/end values are immutable. Projected starts can shift earlier
or later based on actual finish and transition time. During a house-music wait,
projections move forward with the current time. An active overrun never projects
the next set in the past. Unready performers remain next until an organizer waits,
records their readiness, or skips them; they are not silently bypassed.

The event end is a planning window, not an automatic cutoff. Twenty full 15-minute
sets take five hours before extra transitions. The board shows the projected finish
and overrun without shortening sets. Ending an event freezes actual history and
stops projecting unplayed entries.

## Notices and recovery

Next-performer reminders default to 10 minutes before their projected start;
on-deck reminders default to 25 minutes, so with 15-minute sets both roles can be
warned during the current set. Leads are configurable when enabling the event.
Notifications begin only when the event is live and published, and are sent once
per registration attempt per role. They explicitly say estimates require organizer
approval. No automatic public roster or direct messages are added in this version.

Notices target only the intended Discord user mention, with role/everyone mentions
disabled. The durable queue retries HTTP failures. Cancelled/outdated pending
notices are marked obsolete. Sent notices stay recorded through restarts.

Database commits occur before Discord edits/sends. The single gateway worker
reconciles the saved stage board and restores persistent handlers after restart.
Stable message markers recover a send that succeeded just before a receipt-save
failure by inspecting the most recent 100 channel messages. This substantially
reduces duplicates but is not an exactly-once delivery guarantee: message deletion,
a very busy channel, or a network race can still cause a duplicate/stale notice.
No recovery timer starts or ends a set automatically. Discord outages can delay
boards and reminders; database state remains authoritative.

## Storage and upgrade validation

Five additive tables: performance_events, performance_slots,
performer_registrations, performance_actions, performance_notices. The existing
registrations table is untouched. SQLite BEGIN IMMEDIATE serializes allocations
and transitions; unique indexes prevent active-member, occupied-position, and
current-performance duplicates. This version explicitly requires SQLite for live
writes; PostgreSQL locking needs separate implementation/validation.

Migration 0008 uses frozen table definitions and checks individual table/index
existence to coexist with the legacy initial migration's current-metadata creation.
Tests exercise fresh installs, the existing legacy fixture, and a representative
0007 schema with sample Event/Registration rows. The latter checks unchanged row
values, integrity/foreign-key checks, indexes, and schema equivalence to a fresh DB.
No production database is used for tests or preview.

Before any real deployment: use the established verified-backup procedure, rehearse
on an isolated preview, check real Discord permissions and restart behavior with a
dedicated test application, and review this implementation. No production update
or migration has been performed by this development task.

Additional delivery checks re-read event publication, pause state, and queue role
after Discord history lookup, before sending a new notice. Per-event database
failures are isolated so other event boards continue reconciling. A state change
during the final send itself can still race with delivery; the existing delivery
limitations remain applicable.

## Performer buttons and interrupted sets

The stage board now has persistent member buttons for Register, Withdraw, My status,
I've arrived, Ready, Not ready, and Leave venue. These identify the person tapping
the button and use the same service/verification rules as slash commands. My status
is private. Commands remain available. The bottom row is labelled for organizers;
server-side permissions prevent performers from starting, ending, pausing, or
restoring sets even though those controls are visible on the shared message.

Pause this performance freezes its remaining set time, holds the current performer
on stage, and suppresses upcoming preparation reminders until resumed. Resume
continues the remaining clock. Queue pause/resume remains a separate event control
and does not itself pause or resume the current performance clock. Estimates for
a paused performance assume it resumes now; they remain provisional.

Restore last set recovers the most recently ended performance if no other performer
has started and the event is still live. Original actual start is preserved, the
interruption does not consume remaining set time, and the earlier end action stays
in the audit history. It does not reset the performer to a fresh 15 minutes.
Recovery is rejected if that performer already holds a separate active signup.

Migration 0009 adds paused_at and accumulated paused_seconds. Paused sets retain
playing status so existing uniqueness constraints continue preventing another
current performance. Pause/recovery actions require organizer access and a current
revision, and the clock state is durable across gateway restarts.

## Meet Up Manager navigation

The feature is named Meet Up Manager and has its own admin dashboard tile and
sidebar/mobile navigation entry. /admin/meetups lists native community events;
/admin/meetups/{event_id} opens setup or live performance controls. Community
Calendar retains event details, publication, submissions, imports, and attendance
RSVPs. Existing /admin/events/{id}/performances URLs/actions remain compatible.
