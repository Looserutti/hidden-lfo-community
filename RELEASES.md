# Community Hub & Discord Bot releases

## Admin control hub — November 6, 2026

Runtime `6a9131c` replaces the long combined admin overview with six management interfaces: Homepage/carousel photos, Community Calendar, Member projects, Radio, Community activity and System health. Desktop has a section sidebar; mobile uses a collapsed native section switcher. Calendar events/approvals live at `/admin/calendar`, with a separate sources/imports tab preserving `/admin/settings`; health details move to `/admin/health`. Existing action/upload routes remain valid, event actions return to the calendar interface, and old root event-fragment bookmarks redirect appropriately. No public-page, publication-state, permission, media or schema changes.

Validation: 123 complete release-image tests passed, followed by targeted checks for the final health-label copy adjustment. Preview browser checks verified desktop cards, calendar/health separation, mobile 390px layout without overflow, Radio section switching with audio paused, and the legacy create-event bookmark. Previous web image `hidden-lfo-before-admin-hub:44f1e06` retained. Web-only deployment; bot/collector unchanged.

## Member projects and public navigation — November 6, 2026

Runtime `44f1e06` adds a compact top-right homepage hamburger menu and public `/projects` stories. Each feature has one responsive photo with an accessible monochrome/color toggle, plain-text paragraphs and external HTTPS links below the write-up. No carousel, player or new service. Optional site configuration controls the public section title/description.

Staff manage private drafts, photo uploads, previews, publish/republish, unpublish and deletion under Member projects. Published snapshots stay unchanged while edits are drafted. Project photos use isolated rendering, persistent storage outside Git and the shared 500 MB photo limit; complete backups include matching project photos and metadata. No database migration or bot/collector restart. Fresh installs contain no posts. Preview alone has an explicitly labelled layout sample; no sample was copied to production.

Validation: all 121 isolated release-image tests passed. Preview checks covered menu navigation/Escape focus, mouse/keyboard photo toggles, no mobile overflow, unsaved-edit publication guard and live snapshot isolation. Real preview publication/unpublication and media access checks passed. A complete preview snapshot verified all 21 database/audio/photo files. Previous web image `hidden-lfo-before-projects:9b1cdbf` retained; successful encrypted production backup before promotion.

## Dashboard carousel batches — November 6, 2026

Runtime `9b1cdbf` adds staff batch photo upload, private review, whole-carousel publication, retained-batch restoration and guarded inactive-batch deletion. Photos live in persistent data outside Git; new installs retain configurable folder-based galleries until staff publish a managed batch. Isolated photo rendering strips metadata, bounds dimensions and creates responsive display copies automatically. Limits: 20 photos, 20 MB each / 200 MB uploaded batch, 500 MB saved library. Camera originals are not retained; keep them separately. The encrypted snapshot helper now includes every saved photo batch with its matching database.

All 115 isolated release-image tests passed, including authorization/CSRF and private-media checks. A real unpublished preview upload survived redeployment, and a snapshot/verification rehearsal checked all 17 database/audio/photo files. Existing 24 MP photography processed successfully through the sandbox. Production promotion preserved the current carousel and retained the previous image `hidden-lfo-before-photo-admin:a785414`; no migration or bot/collector restart. See README and docs/BACKUPS.md for reuse and recovery instructions.

## Audio-processing isolation — November 6, 2026

Runtime `8f7a9e1` confines normalization to a credential-free Linux child with Landlock file restrictions, seccomp network/process restrictions, bounded resources and explicit audio container/decoder/protocol allowlists. Real MP3/WAV/AAC-M4A/ALAC-M4A processing and kernel denial checks passed in a 107-test release-image suite. Preview's deployed normalizer was checked with synthetic audio before production promotion. Existing source audio/playback files and LUFS targets remain intact; no database migration or bot/collector restart. Unsupported sandbox environments fail closed for normalization while playback remains available. This mitigates exposure; it does not resolve the underlying FFmpeg advisories. See docs/AUDIO.md for hosting requirements.

## Private calendar source configuration — November 6, 2026

Fresh installations now start with an empty source registry. Fictional examples are provided separately; deployment-specific registries belong in ignored `config/sources.local.json`, excluded from Docker images and mounted read-only at runtime. `CALENDAR_SOURCES_FILE` supports alternative locations. Existing source IDs and database publication settings remain unchanged during migration. Backup tooling includes the private registry. Historical commits still contain the previously public venue definitions; this change removes active defaults rather than rewriting Git history.

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
