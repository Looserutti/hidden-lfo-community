# Community Hub & Discord Bot releases

## v0.2.2 — Pour House concert listings

Released November 6, 2026. Adds a reusable Squarespace events adapter and a concerts-only source for Pour House Oceanside. Trivia, karaoke, open mic and other recognized non-concert listings are excluded. Administrators retain collection, publication and per-event exclusion controls; ambiguous titles should be reviewed. Listings use the existing Tuesday 9am Pacific collection schedule and venue-only 30-day retention.

Production and preview runtime: `2d951c9`; schema remains 0007. The first collection found 15 upcoming concerts. Production web, bot and collector were updated so `/shows` recognizes the new source. A successful encrypted off-server backup preceded promotion; previous service images are retained as `hidden-lfo-before-pour-house:web`, `:bot` and `:calendar-collector`. No preview database was copied to production.

Validation: all 93 tests passed in the release container, including source parsing, filtering, timezone handling and retirement of listings reclassified as non-concerts. Preview and public calendars were checked visually. The live gateway bot reconnected successfully. No additional paid service was added.

## v0.2.1 — Community calendar clarity

Released November 6, 2026. Homepage upcoming events now include visible imported listings, with corrected timezone-aware browser dates. Dashboard statistics distinguish upcoming community events (native and Discord scheduled events) from external venue listings. Community events use a configurable aqua accent and a visible label, with a calendar key in desktop and mobile views. Native event registration links now include the Discord server ID.

Production web code: `c32cad2`; database schema remains 0007. Previous public web release `2a61dae` is retained for rollback. No preview database was copied to production, and the gateway bot/collector were not restarted.

## v0.2.0 — Gallery audio and Hidden LFO Radio

Released November 6, 2026. Adds an admin-managed audio library, optional peak-safe LUFS normalization, a compact photo-viewer player with selectable tracks and optional artist social links, and refined mobile landscape photo layouts. Playback starts only when a visitor presses Play and pauses when the photo viewer closes. Branding remains configurable. Audio files live in persistent storage outside Git.

Production web code: `e5958fc`. Database migration: `0007`. The prior public web release `94ca766` and `v0.1.0` pre-audio milestone remain available. The deployment preserves a pre-audio database backup and web image. Prefer rolling back website code while retaining current data, so new community activity is preserved; database restoration requires a separate deliberate recovery decision. The bot and calendar collector were not restarted for this release.

## v0.1.0 — First Working Community Hub & Discord Bot

**Release date:** November 5, 2026 (America/Los_Angeles).  
**Milestone:** first working, publicly deployed community hub and Discord bot baseline, saved before audio-player development.  
**Reference deployment:** [Hidden LFO](https://hiddenlfo.com/) and its [independent preview](https://preview.hiddenlfo.com/).

The annotated Git tag `v0.1.0` identifies this documented baseline. This is an initial functional release, not a claim that every optional integration has completed live acceptance testing.

### Included website features

- Configurable community identity, footer text, social accounts, Discord invitation, timezone and venue sources.
- Folder-discovered photo carousel, fullscreen viewer, compact controls, and a prominent Discord invitation using private deployment configuration.
- Public calendar and event details; desktop month grid and a readable mobile agenda.
- Mobile agenda starts with the next ten events from local midnight today, includes today's events, and continues across month boundaries. Left/right arrows browse groups, the down-arrow control appends more, and Today resets the list.
- Discord OAuth administrator login with a private allowlist, protected administration pages, staff activity views and event review tools.
- Draft/edit/publish controls and administrator approval or rejection of member event proposals.
- Configurable event imports with independent collection/publication controls, manual collection, weekly scheduling, per-listing exclusions and venue-only rolling 30-day retention.
- Separate live and preview environments, persistent SQLite storage, Alembic migrations, Docker Compose deployment and Caddy HTTPS. Preview data and credentials stay separate from production.

### Included Discord features

- Two-step onboarding: acknowledge rules to receive Verified, then introduce yourself to receive Member and unlock community channels.
- Private verification feedback and onboarding guidance; a persistent acknowledgment button.
- Verified-member `/shows` lookup for published concerts over the next seven days.
- Verified-member `/event` proposals using familiar date/time input, retained correction fields and administrator approval before calendar publication.
- Observed member identity/activity tracking and staff controls. Server display names and Discord usernames are stored separately.
- RSVP and cancellation support; automatic event announcements and weekly staff reports are separately opt-in.

### Confirmed real-user onboarding acceptance

On November 5, 2026, the project owner reported that a real community user successfully completed the full flow:

1. Join the server and read the conversations in the introduction channel (`#banter` in Hidden LFO), with the remaining community channels hidden.
2. Visit the rules channel and press **I Agree** to receive Verified.
3. Post an introduction in the introduction channel.
4. Receive Member and gain visibility of the remaining community channels.

This resolves the previously pending human onboarding acceptance check. It supplements the automated and permission checks; it is a user-reported live result, not an invented test account run. Existing Member roles were preserved, and staff-only channels stayed restricted.

### Validation recorded for this baseline

- **75 automated tests passed** in a Python 3.12 container with isolated temporary database storage, including calendar timezone boundaries, rolling event batches, date handling, authorization, submissions, imports, onboarding and SQLite RSVP concurrency.
- After the test run, a browser-only Today reset correction and script cache version were added. They were checked on preview and live: ten initial rows, twenty unique rows after loading more, and ten rows again after Today. The complete automated suite was not rerun for those JavaScript/template-only corrections.
- Mobile calendar checks at 320px and 390px; desktop grid checks at 1280px. Month navigation, empty-state behavior and absence of horizontal overflow were checked during development.
- Public HTTPS/homepage/calendar/health checks and rejection of unauthenticated admin requests. Admin OAuth login was exercised during setup.
- Live Discord permissions checked for newcomer, Verified and Member states, protected staff channels and retained access for existing members.
- Database persistence and backup/restore rehearsal were completed during deployment work; a consistent production database backup preceded public calendar promotion.
- Audio playback has not been implemented, tested or enabled.

### Reference deployment configuration and limits

Discord scheduled Events and Music Box listings are enabled for the website calendar. Automated Casbah/Soda Bar collection remains disabled pending a supported source. Imports do not create Discord scheduled Events; automatic Discord announcements and weekly staff reports remain disabled in the reference deployment.

Website admin access is a saved Discord-ID allowlist, not automatic synchronization with Discord role membership. Activity records are observations, not attendance proof, and do not trigger automatic removals. The initial deployment uses one server and local SQLite storage; multi-host scaling and other database engines require separate validation. Recurring off-server database backup copying remains an operational follow-up.

Public preview is for test data. Sample concert listings used for preview were already public; member records were not copied into preview. Publishing source to GitHub does not automatically deploy it: test a candidate on preview, then promote the approved image to production without copying the preview database.

### Reuse and release boundaries

See [README.md](README.md), [hosting prerequisites](deploy/HOSTING.md), [deployment](deploy/STAGING.md), and [preview setup](deploy/PREVIEW.md). Customize the example branding/source files and private environment values. Keep actual credentials, private allowlists, member databases and local backups out of Git; the generic Discord invite remains blank in example environments.

A source-code license has not yet been chosen. This release records the reusable project structure and working baseline; it does not invent license permissions. Audio/player design, music storage, uploads and playlist management belong to the next development phase.
