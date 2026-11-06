# Community Hub & Discord Bot

The current platform combines a public community website, moderated event calendar, Discord onboarding, staff activity tools, a photo carousel with audio playback, and member project highlights. The administrator control hub manages homepage photos, community events and imports, member projects, radio tracks, community activity, and system health.

**Audio playback is included on `main`.** Released in v0.2.0, the gallery player offers selectable tracks, artist credits and optional artist social links. Playback starts when a visitor presses Play and pauses when the expanded photo viewer closes. Administrators manage tracks through **Radio**; uploaded recordings remain in persistent server storage and complete backups, outside Git. See [audio setup and administration](docs/AUDIO.md).

See the [release record](RELEASES.md) for shipped features, validation evidence, and limitations. The `v0.1.0` tag preserves the historical November 5, 2026 baseline from before audio was added; it does not describe the current feature set on `main`.

Branding, social links, Discord invite, guild/role/channel IDs, and venue sources are configurable for other communities. Keep deployment credentials and member data outside Git. Example environments intentionally leave the Discord invite blank.

## Hosting and required services

Start with [Services, costs, and setup order](deploy/HOSTING.md) for provider links, free resources, SQLite storage, domain/DNS setup, and the production/preview workflow.

## On your Mac

1. Install Python 3.11+ and open this folder in VS Code.
2. Run `python3 -m venv .venv && source .venv/bin/activate`.
3. Run `pip install -r requirements.txt`.
4. Copy `.env.example` to `.env` and fill in settings. Generate SESSION_SECRET with `python -c 'import secrets; print(secrets.token_urlsafe(48))'`.
5. Set your Discord application's OAuth2 redirect URI to `http://localhost:8000/auth/callback` (development only). Enable Server Members Intent and Presence Intent in the Developer Portal. Invite bot with Manage Roles, Send Messages, Read Message History and relevant permissions; its role must be above Verified.
6. Initialize the database with `alembic upgrade head`, then run the website from the project root: `uvicorn app.web:app --reload`. Open http://localhost:8000.
7. In another terminal, activate the environment and run `python -m bot.main`.
8. Visit `/login` with an allowlisted admin Discord account; create and publish an event. Automatic Discord announcements require the separately configured `EVENT_PUBLISHING_ENABLED=true`; they are off by default.

## Security

Never commit `.env`. Never post your bot token or client secret in chat. Keep the admin dashboard private through Discord OAuth allowlist. Use HTTPS, a strong session secret, backups, and proper process supervision in production. Configure channel access so unverified members cannot use RSVP buttons. **Before applying restrictive channel permissions, preserve existing Member roles and review the explicit two-step onboarding permission plan.**

## Current limitations / next milestones

- Real-user onboarding is confirmed in the Hidden LFO server; other communities must validate their own role hierarchy and channel permissions.
- Activity tracking is observational. Presence is not server-specific, invisible/offline presence cannot be observed, and missing history is not proof of inactivity. No automatic removals.
- SQLite uses a local persistent volume and serialized RSVP writes. Multi-host SQLite, high-volume deployments, and PostgreSQL migration need separate validation.
- Automated Casbah/Soda Bar collection is not enabled in the reference deployment; it needs a supported source. External provider behavior can change.
- Website administrators use an explicit Discord-ID allowlist. Changes to Discord admin roles do not automatically update website access.
- Provider backups and verified database backups exist in the reference deployment. Complete encrypted application backups and restore timers are available; off-server protection requires an authorized destination.
- Automatic Discord event announcements and weekly staff reports remain opt-in and are disabled in the reference deployment. Their complete live acceptance is outside this baseline's confirmed onboarding check.
- Photo processing and audio normalization require supported Linux isolation; see [audio hosting requirements](docs/AUDIO.md). Direct Mac development does not provide that processing environment; playback of existing tracks remains available.
- A repository license has not yet been selected; choose one before describing reuse permissions as an open-source license grant.

The sections below describe feature milestones; [the release record](RELEASES.md) identifies the current baseline and validation scope.

## Version 3: public calendar and event discovery

- `/calendar` shows a Sunday-first monthly calendar with previous/next month navigation; use `?year=2026&month=11` to navigate directly.
- Public event listing and detail timestamps can use browser-local formatting. Calendar grouping and display use the configured community IANA time zone, with UTC storage. Mobile shows rolling groups of ten upcoming events from local midnight today, with left/right browsing, load-more and Today reset; desktop retains the monthly grid.
- Set `DISCORD_INVITE_URL` in `.env` to a permanent invite created inside your Discord server. Visitors can join using the public website, but RSVPs still require the Verified role and happen inside Discord.
- No website event registration or member-only event visibility is implemented; all published events are public.

## Version 4: administrative activity dashboard

- `/admin/activity`: admin-only status counts, member activity timestamps, status and Discord-ID filters, and CSRF-protected exemption controls.
- `/admin/events/{id}/registrations`: admin-only registration list (Discord IDs and RSVP status).
- Discord `/activity` and `/activity-summary` commands for allowlisted admins; existing `/inactive` and `/exempt` remain.
- Set `STAFF_REPORT_CHANNEL_ID` to a **private staff-only text channel**. Weekly activity reports are no longer sent to the public events channel. The weekly loop runs every 168 hours after the bot becomes ready, not at a fixed calendar time, and may skip reports while offline.
- Classification distinguishes active, review, grace, unknown, and exempt. Observations are not proof of actual attendance or absence; no automatic removals.
- **Privacy:** member activity and registrations are administrator-only; limit access to staff who need them.
- **Important:** use `alembic upgrade head` for schema migrations; `Base.metadata.create_all()` does not upgrade existing tables.

## Version 5: reliability foundation

- SQLite RSVP operations use `BEGIN IMMEDIATE` to serialize capacity checks and updates across concurrent SQLite writers. Keep SQLite on a **local** persistent disk; do not share the file across hosts. PostgreSQL needs its own locking strategy before migration.
- Alembic initial migration added. **New installs:** run `alembic upgrade head` before launching services. **Existing Version 4 databases:** back up the DB, compare actual schema to the Version 4 models, then run `alembic stamp 0001` only if they match. Do not run the initial migration against existing tables.
- Consistent SQLite backups: `python -m scripts.backup_sqlite --output /safe/location/community.db`. Copy backups **off the server**, test restores, and schedule retention externally.
- Concurrency tests cover overbooking and cancellation. The reference deployment now uses Docker Compose, Caddy HTTPS, protected Discord OAuth admin access and isolated preview storage. See the release notes for what was tested and what remains operational follow-up.
- `init_db()` still uses `create_all()` for legacy compatibility; production startup should run migrations explicitly rather than depending on it.

## Version 6: single-server deployment (Docker Compose + Caddy)

This is the single-server deployment used for the working baseline. Each downstream deployment must validate its own integration and operational settings. It assumes one Ubuntu VPS, a DNS name, and a local Docker named volume for SQLite. Do not use networked SQLite volumes or scale the bot to multiple replicas.

1. Point the DNS A/AAAA record for your domain to the VPS; allow inbound TCP 80/443 and UDP 443. Install Docker Engine with the Compose plugin on a supported Linux distribution. Restrict SSH with keys and a firewall.
2. Copy `.env.example` to `.env`, set `SITE_DOMAIN` (e.g. `community.example.com`), `PUBLIC_BASE_URL=https://community.example.com`, `DISCORD_REDIRECT_URI=https://community.example.com/auth/callback`, a random `SESSION_SECRET`, bot credentials, guild/role/channel IDs, and `ADMIN_DISCORD_IDS`. Keep `.env` private; never commit it. Add the same HTTPS callback URI in Discord Developer Portal.
3. Run `docker compose config` to validate configuration, then `docker compose build`, `docker compose run --rm migrate` and `docker compose up -d web caddy`. The Compose services are `migrate`, `web`, `bot`, and `caddy`; Caddy obtains/renews HTTPS certificates when DNS and inbound ports are correct. Review logs with `docker compose logs -f web bot caddy`.
4. Check `https://your-domain/healthz`, then test a draft/published event, Discord RSVP, cancellation, and admin OAuth in a test server before announcing the website. `healthz` indicates only that the web process is responding; it does **not** confirm Discord connectivity or database correctness.
5. For complete encrypted backups, configure and run the root-only host helper `deploy/backup.sh` using [docs/BACKUPS.md](docs/BACKUPS.md). It captures SQLite, referenced audio and private configuration, supports daily/monthly systemd timers, retains seven daily and four weekly points, and optionally replicates to an authorized restic repository such as Google Drive via rclone. Do not consider backups complete without a verified off-server copy and a separately stored recovery password.
6. Before upgrades, back up and test restoring; run `docker compose run --rm migrate` to apply migrations, then `docker compose up -d --build web caddy`. Use a maintenance window for schema changes.

**Security notes:** Caddy is the only public-facing service; the web and bot do not publish host ports. OAuth administrator access remains allowlist-controlled. Do not expose Docker's socket or the SQLite volume. The deployment needs a production security review (CSRF, OAuth error cases, privacy, rate limits), monitoring, and live Discord tests before use with real member data. `--forwarded-allow-ips '*'` is safe only while web port 8000 is inaccessible from outside the private Compose network; if topology changes, narrow trusted proxy IPs.

**Local non-Docker startup:** `alembic upgrade head` is now required before `uvicorn app.web:app` or `python -m bot.main` because automatic table creation has been removed from startup.

## Version 7: security checks and first live integration test

Security additions: the bot checks the configured guild before honoring administrative commands or rules agreement, OAuth callbacks reject invalid state and handle upstream failures, website sessions expire after eight hours, and admin/auth routes disable browser caching. Browser responses include `X-Frame-Options`, `X-Content-Type-Options`, and a referrer policy. HTTPS deployments also enable HSTS. These are baseline controls, **not** a complete production security audit.

Run locally from the repository root after installing dependencies:

```bash
export SESSION_SECRET='a-local-test-secret-only'
python -m pytest -q
python -m compileall -q app bot scripts
```

### First live Discord test checklist (use a private test channel)

1. Back up your database and verify the Discord bot is restricted to your server (`DISCORD_GUILD_ID`). Never paste your token into a chat or commit `.env`.
2. Enable the Server Members and Presence privileged intents in the Discord Developer Portal. Confirm the bot has appropriate role permissions and its highest role is above `Verified`.
3. Run `alembic upgrade head`, start the web app and bot, and check `/healthz`. Confirm `/admin` denies unsigned visitors.
4. Authenticate to the admin dashboard using an account in `ADMIN_DISCORD_IDS`; confirm another account cannot access it.
5. Post rules in a test rules channel. Confirm a new test member can click **I Agree** and receives the Verified role; check that unverified members cannot access ordinary channels.
6. Create and publish a test event in the admin dashboard. Confirm the bot publishes exactly one Discord announcement with working buttons.
7. Confirm an unverified server member cannot RSVP; a verified member can RSVP once, cancel, and register again. Test a capacity-one event with two distinct verified accounts.
8. Edit, unpublish, and republish the event; verify the Discord message and public calendar remain consistent. Inspect logs for errors.
9. Confirm activity reports are only visible to authorized staff and no automatic member removal occurs.
10. Only after successful testing, configure HTTPS, persistent storage, off-server backups, and production monitoring.

**Known limitations:** Discord OAuth2 and real Discord interactions are not exercised by unit tests. Docker and live bot permissions still require testing. SQLite concurrency is suitable for this initial single-host architecture but must be reevaluated if traffic or write contention grows.

## Branding and reuse

This platform is intended for other communities and artists to build on. Hidden LFO is the current example community; Discord, calendar, event and authentication behavior remain separate from presentation.

- Edit **`config/site.json`** for the community name, location eyebrow, description, footer wording, social URLs, gallery folder, and `calendar_timezone` (an IANA zone such as `America/Los_Angeles`). No template or Python edits are needed. Restart the website after changing this JSON file.
- To start fresh, copy `config/site.example.json` to `config/site.json`. The example has generic wording, no social accounts. Blank social URLs hide their icons; an empty gallery folder hides the carousel and viewer. Any number of photos is supported, with counters generated automatically.
- **Drag and drop photos into `static/images/gallery/`**, then refresh the homepage. Delete photos from that folder to remove them. No JSON edits or server restart are needed for photo changes. The folder is scanned on each page request; an already-open page needs a refresh.
- Supported formats: JPG/JPEG, PNG, WebP, GIF, and AVIF (browser support varies). Convert HEIC photos to JPEG first. Hidden files, subfolders, and symlinks are ignored. Photos sort naturally by filename: use `01-stage.jpg`, `02-crowd.jpg`, etc. Filenames also supply the generated image descriptions, so use descriptive names.
- Change `gallery_folder` in `config/site.json` to use another folder relative to `static/`. Restart after configuration changes. The generic example uses the same folder; remove the example photos when rebranding. Use photos you have permission to distribute; existing event photos are not a promise of reuse rights.
- For a deployed site, add/remove files on the server or redeploy the updated folder; changing files on your Mac only updates your local preview.
- Edit **`static/theme.css`** for homepage, carousel, viewer, footer, and social icon styling. `static/style.css` contains shared application styles and color variables. Refresh the browser after CSS edits.
- Shared layout lives in `templates/base.html`; social vector artwork is isolated in `templates/_social_icon.html`. Account URLs are configuration, never embedded in icons.
- Configure the Discord invite, deployment base URL and OAuth callback in `.env` using `.env.example`. Public branding JSON must not contain credentials.

Keep future branding changes in these presentation files and configuration. Changes to events, permissions, authentication, or bot services should be scoped and reviewed separately.

## Admin dashboard and member names

`/admin` provides the community overview and event management. `/admin/activity` provides status summaries, name/ID search, a paginated member list (50 per page), and CSRF-protected exemptions. These pages require an allowlisted Discord login and do not cache staff data.

Member records keep the latest Discord username and server display name alongside the stable Discord ID. The server display name uses the server nickname when present, otherwise Discord's global display name or username. Names are synced on bot startup, member joins, member updates and user updates for the configured guild. Existing members show an ID fallback until observed. Name changes do not count as activity; no historical name log is retained. This remains a single-guild installation.

Before starting the updated web app or bot, back up SQLite and run `alembic upgrade head` to add the nullable name columns (revision `0002`). Restart both services afterward. No member records or RSVP history are removed. Live Discord name synchronization still requires an integration test with the bot connected.

Activity classifications remain observation-based: a 90-day new-member grace period and a 60-day observation window. Online presence is not server-specific, unknown data does not establish inactivity, and no automatic removals occur.

## Calendar collection and source publishing

`/admin/settings` controls imports independently of onboarding, activity tracking and community event management. All collection and publication settings default **off** and persist in SQLite.

1. Back up the database and run `alembic upgrade head` (revision `0003` adds a separate imported-listings table); restart the web app.
2. Sign in as an allowlisted administrator. Enable global collection and select **Collect this source** for each desired source. **Pull now** reads one source immediately and displays success/error status.
3. For scheduled checks, run `python -m app.feeds` in a separate process. It wakes every 15 minutes and pulls enabled sources only when their weekly schedule is due, independently of the Discord gateway bot. Docker installations can run `docker compose --profile shows up -d calendar-collector`; the optional worker uses the same database volume and environment.
4. Enable global website publishing and **Publish this source on the calendar** for the desired sources. Imported listings appear on `/calendar`, with source attribution and an external show link. Pausing collection preserves stored listings; pausing website publishing hides them. Neither switch changes manually managed community events.
5. Add venue shows manually if a source cannot be read. The same publication switches apply. A staff Hide action survives future imports and can be reversed with Unhide.

**Discord scheduled Events:** the collector reads the configured guild's native scheduled Events using the existing `DISCORD_BOT_TOKEN` and `DISCORD_GUILD_ID` settings. It does not read channel posts, publish Discord messages, or create scheduled Events. Turning on website publishing makes imported event titles, times and locations public. Recurring events currently expose the next scheduled occurrence only. Canceled/ended or missing scheduled Events are retired on the next successful snapshot. Live integration with your guild still needs a test; imported website listings do not add website RSVPs or change Discord event subscriptions.

**Venue sources:** fresh installations have no configured sources. Copy `config/sources.example.json` to ignored `config/sources.local.json` and replace the fictional venue with your own sources. Hidden LFO’s deployment registry is not included. Supported adapters are `discord`, `ticketweb_calendar` and `squarespace_events`. Compose mounts configuration read-only at runtime; the private registry is excluded from Git and Docker images. Restart the web, bot and collector after changing it. Collection and publication start off for new source IDs. See [calendar source setup](docs/CALENDAR-SOURCES.md).

The Music Box reader was checked against its public calendar markup; private-event blocks are excluded. The Casbah Presents/Soda Bar source is registered, but the current site returned HTTP 403 to our automated request. Automatic imports there remain unverified; use manual entries or a supported/venue-approved feed. No access-control bypass is attempted. Venue pages can be partial: missing entries never delete existing listings, so cancellations must be reviewed and hidden by staff when needed. Matches use source ID plus external event ID; the same show listed by two sources or added manually may require manual deduplication.

Collection failures preserve earlier data and are shown in the admin source status. Source URLs are trusted deployment configuration, not user-submitted fetch destinations. Source JSON contains public settings only; credentials stay in `.env`. The current import upsert uses SQLite, matching this single-host starter architecture. Public calendar day grouping remains UTC. Discord show roundups/outbound publication are a separate future feature.

## Hosted staging preparation

See [deploy/STAGING.md](deploy/STAGING.md) for the website-only launch, optional bot cutover, preflight validation and backup restoration rehearsal. Bot and collector services are opt-in Compose profiles. Outbound bot event announcements and staff reports also require their explicit environment switches.

### Automatic calendar collection schedule

All enabled sources, including Discord scheduled Events and external venues, are attempted once on Tuesdays at or after 09:00 in `calendar_timezone` (within the next worker cycle). Change `calendar_collection` in `config/site.json`: `weekday` is Monday=0 through Sunday=6; `hour` uses 0–23. Restart the web and collector after editing configuration. The generic example uses UTC; Hidden LFO uses America/Los_Angeles, including daylight-saving changes.

Last-attempt timestamps persist in the database, preventing another automatic source pull after a worker restart on the same day. Failed attempts also count toward that day's limit. If the collector is offline or paused for the entire scheduled window, it waits until the next configured weekday. Admin “Pull now” remains available any day when collection and the source are enabled; a manual pull on the scheduled day also counts toward that day's automatic limit. Publication switches remain independent.

For individual imported listings, check **Exclude from publishing** and click **Save selection** to withhold an event without deleting it. Uncheck and save to restore eligibility; global and source publishing switches still apply. The choice survives later imports. Listing pages show 50 records each; use **More listings** to review the rest.

### Venue listing retention

`venue_retention_days` in `config/site.json` defaults to 30. The collector removes venue listings whose start time is more than that many elapsed days in the past on its 15-minute maintenance cycle, even when collection is paused. Incoming venue records older than the cutoff are skipped, preventing deleted listings from reappearing. Manually added venue listings follow the same rule. Discord imports, community events, RSVPs, and member observations are unaffected. The worker must be running for cleanup. Deleted SQLite space is reusable; the database file does not necessarily shrink immediately. Existing backup copies follow their own retention.

### Member concert lookup

Verified members can run `/shows` inside the configured Discord server for published calendar listings starting now through the next seven days (the exact upper boundary is excluded). Replies are private to the requester. The command respects website/source publication switches, individual exclusions, and cancelled listings; it includes published community events too. Dates use the community `calendar_timezone`. Lists show eight events per page; use `/shows page:2` for additional results. No automatic channel post is sent. The bot syncs the guild command at startup.

Admin event creation and editing use date/time pickers interpreted in `calendar_timezone`, with UTC storage and automatic daylight-saving offsets. Invalid or ambiguous daylight-saving times are rejected rather than silently shifted.

For a main-domain cutover, set the server `SITE_DOMAIN`, `PUBLIC_BASE_URL`, and `DISCORD_REDIRECT_URI` to the canonical host; register its OAuth callback first. Optional `SITE_ALIASES` is a comma-prefixed list (for example `", www.community.example.com, preview.community.example.com"`). Point each alias DNS record to the server. Caddy obtains certificates and redirects aliases to the canonical HTTPS host while preserving the path and query. Recreate Caddy and app services after changing environment values.

### Member event proposals

Verified members can use `/event` inside the server to open a private submission form (title, day, local start time, venue, and optional description). Dates use the configured community time zone. Future events enter a separate pending queue; nothing appears on the calendar or in `/shows` before staff approval. Members may have up to five pending proposals. Admins review submissions on **Overview & events → Member event submissions**, edit details if needed, then **Approve & publish to calendar** or **Reject submission**. Review records preserve submitter identity, reviewer, decision time, and the resulting event ID. Repeated review clicks cannot create duplicate events. Approval publishes a website community event; it does not create a Discord scheduled Event or automatically send a channel announcement. Existing outbound job switches remain independent.

Discord `/event` accepts `tomorrow`, `Saturday`, `Nov 14`, `11/14` (month/day), or ISO dates, with `7pm`, `7:30pm`, `19:30`, `noon`, or `midnight`. Relative dates use the community time zone; weekdays mean the next occurrence and dates without a year roll forward if past. The receipt shows the exact interpreted date and year. Validation errors provide an **Edit event details** button that retains all entered fields.

For independently reviewing changes before publication, see [the preview deployment guide](deploy/PREVIEW.md). Preview has separate test storage, a visible environment banner, and no gateway bot.

### Optional two-step onboarding

Set `ONBOARDING_ENABLED=true`, `MEMBER_ROLE_ID`, and `INTRO_CHANNEL_ID` alongside the existing Verified role and rules channel IDs. Newcomers can read the introduction channel and rules. The persistent rules button grants Verified and privately explains the introduction step. A normal non-bot message or reply in the introduction channel, sent after verification, grants Member. Message bodies are not read or evaluated; an introduction is any normal member-authored post, not a slash-command response. Existing Member roles are not removed.

Channel permissions must match: everyone can view/read rules and introductions; only Verified/Member can post introductions; community channels deny everyone and allow Member. Verified alone does not unlock those channels. Other role or per-user allow overrides can bypass a deny and must be reviewed; leave staff-only channels restricted. Keep other bots from automatically granting Member before the introduction. The server welcome/system channel and invite destination should point at the introduction channel. Discord controls the client's exact initial channel display.

Rules-button message ID and first observed introduction timestamps are stored in settings, not in source control. The bot needs Manage Roles and a role above Verified/Member. Test the permission plan and the two onboarding states before applying it broadly. This feature is off by default for downstream deployments.

Permission setup can be planned with `python -m scripts.configure_onboarding --policy /private/onboarding-policy.json --backup /private/permission-snapshot.json`. Use `config/onboarding.example.json` as the shape, classifying every guild channel and category by numeric ID; rules/introduction IDs come from the environment. Private channels are never modified. The tool defaults to a read-only plan and writes a private snapshot. Add `--apply` only after reviewing the plan and starting the configured bot so its acknowledgment button exists. Snapshot paths must be new files. Changes to role/per-user View Channel allows in community channels are deliberate to prevent bypassing Member; individual deny overrides and staff restrictions remain in force. The tool does not remove roles or messages.


## Gallery soundtrack and Radio (released in v0.2.0)

Admins manage uploads, track credits, ordering and publication in **Radio** (`/admin/music`). Music appears only inside the expanded photo viewer and pauses when it closes. Audio files stay in persistent storage outside Git; new deployments start with no tracks. See [audio documentation](docs/AUDIO.md) for migrations, limits and backup requirements.

**Approved member announcements:** set `MEMBER_EVENT_ANNOUNCEMENTS_ENABLED=true` and configure `EVENTS_CHANNEL_ID` to your announcement channel. The bot posts future admin-approved `/event` submissions within roughly 30 seconds, with the event details, calendar link and RSVP buttons. Rejected/pending submissions and external venue imports are not announced. This switch is independent of general `EVENT_PUBLISHING_ENABLED`. Set `MEMBER_EVENT_ANNOUNCEMENTS_SINCE` to an ISO timestamp with timezone when enabling it on an existing install to avoid announcing older approvals. Message IDs are persisted to avoid repeated posts during ordinary polls/restarts; edits/RSVP counts update the existing message. Keep one gateway bot instance; a crash between Discord accepting a send and the database commit can still require staff reconciliation. Mentions are disabled in submitted announcement text.

**Carousel performance:** the homepage generates 480/960/1600-pixel WebP display copies automatically in `static/gallery-optimized/`. Originals remain in the gallery folder and are used by the expanded viewer. Only the first slide starts immediately; the next slide warms after the visible one loads (except on data-saver connections). Hashed display URLs receive long-lived browser caching and change when the original changes. Docker builds pre-generate copies; dropping/replacing photos still works without a restart, with one-time generation when discovered. Generated files are excluded from Git/images' build context and can be rebuilt from originals. Animated or unsupported images retain their original behavior.


**Admin photo batches:** choose **Homepage** in the control hub to open carousel photos. Select up to 20 JPEG/PNG/WebP/AVIF stills (20 MB each, 200 MB per upload), name the batch, review its private previews and publish to swap the whole carousel atomically. Retained batches can be restored; inactive batches can be deleted deliberately. Use project-folder photos instead restores folder discovery. Dashboard uploads live in `/data/gallery-photos` (or `GALLERY_PHOTO_DIR`), not Git; they persist in the existing data volume and complete backups include all saved batches. Preview has its own separate volume and uploads. The 500 MB library limit includes active, draft and retained output batches; no automatic photo deletion. Keep camera originals separately: uploads are rendered to metadata-free JPEGs up to 3200 px plus responsive WebP copies. HEIC must be exported as JPEG first. Image processing uses the same supported Linux Landlock/seccomp environment as audio; jobs are serialized and fail safely where isolation is unavailable. Configuration and routes contain no community-specific branding or source URLs.

If overriding `GALLERY_PHOTO_DIR` or `GALLERY_AUDIO_DIR`, also set host backup `BACKUP_PHOTOS` / `BACKUP_AUDIO` to the same in-container paths. The paths must be in a persistent volume. Backups stop with an error if referenced media is missing instead of claiming a complete snapshot.


**Member projects:** the homepage hamburger menu links to the public `/projects` page. Administrators manage posts under **Member projects** in the dashboard. Save a draft with a title, member name, plain-text paragraphs, one photo and up to eight external HTTPS links (`Label | URL`, one per line). Preview, then publish. Edits stay private until republished; unpublish removes the post from public pages. Feature photos toggle between grayscale and color by click/keyboard, without a carousel or audio player. A fresh install has no seeded posts. Set optional `projects_title` and `projects_description` in site configuration to rename this section.

Project photos use `/data/project-photos` (or `PROJECT_PHOTO_DIR` in a persistent volume), the existing isolated photo processor and the shared 500 MB photo storage limit. Originals are not retained; rendered files and draft/published post metadata are backed up together. If overriding the path, match host `BACKUP_PROJECT_PHOTOS`. Replaced images stay with the post until an administrator unpublishes and deletes it. Previously published images may remain in browser or CDN caches after unpublishing. No uploaded photos or community posts belong in Git.

**Admin control hub:** signing in opens `/admin`, with separate interfaces for Homepage (`/admin/photos`), Community Calendar (`/admin/calendar`), Member projects (`/admin/projects`), Radio (`/admin/music`), Community activity (`/admin/activity`) and System health (`/admin/health`). Calendar sources/imports remain at `/admin/settings`, linked from the calendar interface. Desktop uses a sidebar; mobile uses a collapsed section switcher. Existing edit/upload/action URLs remain valid, and legacy `/admin#create-event` / `/admin#member-submissions` bookmarks redirect to the calendar interface. This navigation change does not alter public pages, permissions, publication state or stored content.

### Member project publication notifications
Set `PROJECT_ANNOUNCEMENTS_CHANNEL_ID` to your community's Discord text channel ID to announce newly published member highlights. Leave it blank to disable; no destination is bundled with a fresh install. The gateway bot must belong to the configured guild and have View Channel and Send Messages permission there. Preview overrides the destination to blank and runs no gateway bot.

First publication creates a persistent notification alongside the published snapshot. The bot checks every 30 seconds, sends a short title/byline and the public post link without mentions, and records the message ID. Drafts, already published legacy posts, edits, and repeat publication do not create new notifications. Unpublished/deleted posts are not sent. Discord HTTP errors are retried later. As with event notifications, a process crash after Discord accepts a message but before the database records its ID can produce a duplicate; routine retries/restarts after a recorded send do not. No notification is sent for existing posts when enabling this option.


## Homepage link previews

The homepage includes server-rendered Open Graph and social-card metadata, using `PUBLIC_BASE_URL` for its canonical homepage URL. Configure optional `share_description`, `share_image` and `share_image_alt` in `config/site.json`. A blank sharing description uses the site description; a blank image omits image tags. The image must be a public `/static/` path (for example `/static/images/share/homepage-v1.jpg`); use your own photo and descriptive alternative text. The generic example has no bundled sharing image selected. Rebuild/redeploy when adding a source image, and restart web after configuration changes.

This currently applies only to the homepage; event and project pages do not receive homepage preview metadata. Shared previews are controlled and cached by the destination service, so previously posted links may retain an older preview. The link card does not embed the site's audio player.
