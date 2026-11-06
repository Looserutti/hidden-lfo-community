# Community Platform — starter implementation

A **first working scaffold**, not a production-ready release. Public FastAPI event pages, Discord OAuth admin login, draft/publish/edit/unpublish events, SQLite models, Discord onboarding and RSVP buttons, and preliminary inactivity monitoring.

## On your Mac

1. Install Python 3.11+ and open this folder in VS Code.
2. Run `python3 -m venv .venv && source .venv/bin/activate`.
3. Run `pip install -r requirements.txt`.
4. Copy `.env.example` to `.env` and fill in settings. Generate SESSION_SECRET with `python -c 'import secrets; print(secrets.token_urlsafe(48))'`.
5. Set your Discord application's OAuth2 redirect URI to `http://localhost:8000/auth/callback` (development only). Enable Server Members Intent and Presence Intent in the Developer Portal. Invite bot with Manage Roles, Send Messages, Read Message History and relevant permissions; its role must be above Verified.
6. Run website from project root: `uvicorn app.web:app --reload`. Open http://localhost:8000.
7. In another terminal, activate the environment and run `python -m bot.main`.
8. Visit `/login` with an allowlisted admin Discord account; create and publish an event. Bot posts RSVP buttons to configured events channel.

## Security

Never commit `.env`. Never post your bot token or client secret in chat. Keep the admin dashboard private through Discord OAuth allowlist. Use HTTPS, a strong session secret, backups, and proper process supervision in production. Configure channel access so unverified members cannot use RSVP buttons. **Before applying restrictive channel permissions, grant Verified to existing members.**

## Known limitations / next milestones

- This is a scaffold, not fully tested against a live Discord server.
- Event editing, unpublishing, and Discord announcement synchronization are implemented using a 30-second reconciliation loop; test on a real Discord server before relying on it. Unpublishing preserves RSVP history.
- RSVP counts are refreshed on successful registration/cancellation and in the reconciliation loop.
- Weekly report currently posts to the events channel; configure a private admin report channel before production.
- Inactivity detection is observational only: Discord presence is not server-specific, offline/invisible presence cannot be observed, and missing history must not be treated as inactivity. Full `/activity`, `/activity-summary`, weekly scheduling, grace-period reporting, and reaction coverage for uncached messages are future work.
- Database tables use `create_all` for first-run setup; add Alembic migrations before production schema changes.
- Registration capacity checks should use transactional locking or PostgreSQL for high concurrency. Current SQLite logic may race under simultaneous clicks.
- A production deployment needs stronger operational controls, rate limiting, backup automation, OAuth error handling, privacy policy, and tests.
- Calendar grouping and display use the community’s configurable IANA time zone; stored timestamps remain UTC.
- For public event pages, the link points to the bot announcement when posted; newcomers need a separate server invite link (future enhancement).

## Version 3: public calendar and event discovery

- `/calendar` shows a Sunday-first monthly calendar with previous/next month navigation; use `?year=2026&month=11` to navigate directly.
- Public event listing and details use browser-local time formatting. The monthly calendar **groups days by UTC**, so events near midnight may appear on a different day than the visitor's local date; this is a known limitation to address in a future release.
- Set `DISCORD_INVITE_URL` in `.env` to a permanent invite created inside your Discord server. Visitors can join using the public website, but RSVPs still require the Verified role and happen inside Discord.
- No website event registration or member-only event visibility is implemented; all published events are public.

## Version 4: administrative activity dashboard

- `/admin/activity`: admin-only status counts, member activity timestamps, status and Discord-ID filters, and CSRF-protected exemption controls.
- `/admin/events/{id}/registrations`: admin-only registration list (Discord IDs and RSVP status).
- Discord `/activity` and `/activity-summary` commands for allowlisted admins; existing `/inactive` and `/exempt` remain.
- Set `STAFF_REPORT_CHANNEL_ID` to a **private staff-only text channel**. Weekly activity reports are no longer sent to the public events channel. The weekly loop runs every 168 hours after the bot becomes ready, not at a fixed calendar time, and may skip reports while offline.
- Classification distinguishes active, review, grace, unknown, and exempt. Observations are not proof of actual attendance or absence; no automatic removals.
- **Privacy:** member activity and registrations are administrator-only; limit access to staff who need them.
- **Important:** `Base.metadata.create_all()` does not perform schema migrations. Add Alembic before changing production tables.

## Version 5: reliability foundation

- SQLite RSVP operations use `BEGIN IMMEDIATE` to serialize capacity checks and updates across concurrent SQLite writers. Keep SQLite on a **local** persistent disk; do not share the file across hosts. PostgreSQL needs its own locking strategy before migration.
- Alembic initial migration added. **New installs:** run `alembic upgrade head` before launching services. **Existing Version 4 databases:** back up the DB, compare actual schema to the Version 4 models, then run `alembic stamp 0001` only if they match. Do not run the initial migration against existing tables.
- Consistent SQLite backups: `python -m scripts.backup_sqlite --output /safe/location/community.db`. Copy backups **off the server**, test restores, and schedule retention externally.
- Concurrency tests cover overbooking and cancellation. This is still a development build; production hardening (reverse proxy, HTTPS, monitoring, OAuth security review, deployment services, Discord integration tests) is outstanding.
- `init_db()` still uses `create_all()` for legacy compatibility; production startup should run migrations explicitly rather than depending on it.

## Version 6: single-server deployment (Docker Compose + Caddy)

This deployment is a **candidate for integration testing**, not a security-certified production release. It assumes one Ubuntu VPS, a DNS name, and a local Docker named volume for SQLite. Do not use networked SQLite volumes or scale the bot to multiple replicas.

1. Point the DNS A/AAAA record for your domain to the VPS; allow inbound TCP 80/443 and UDP 443. Install Docker Engine with the Compose plugin on a supported Linux distribution. Restrict SSH with keys and a firewall.
2. Copy `.env.example` to `.env`, set `SITE_DOMAIN` (e.g. `community.example.com`), `PUBLIC_BASE_URL=https://community.example.com`, `DISCORD_REDIRECT_URI=https://community.example.com/auth/callback`, a random `SESSION_SECRET`, bot credentials, guild/role/channel IDs, and `ADMIN_DISCORD_IDS`. Keep `.env` private; never commit it. Add the same HTTPS callback URI in Discord Developer Portal.
3. Run `docker compose config` to validate configuration, then `docker compose build`, `docker compose run --rm migrate` and `docker compose up -d web caddy`. The Compose services are `migrate`, `web`, `bot`, and `caddy`; Caddy obtains/renews HTTPS certificates when DNS and inbound ports are correct. Review logs with `docker compose logs -f web bot caddy`.
4. Check `https://your-domain/healthz`, then test a draft/published event, Discord RSVP, cancellation, and admin OAuth in a test server before announcing the website. `healthz` indicates only that the web process is responding; it does **not** confirm Discord connectivity or database correctness.
5. For database backup on the host, run `./deploy/backup.sh`. Schedule this using host cron or a systemd timer (e.g. daily), **copy encrypted backups to an off-server destination**, and rehearse a restore. The included script retains local copies for 14 days but does not upload them. Do not consider backups complete without off-server replication.
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

**Venue sources:** edit `config/sources.json` to add/remove source definitions; `config/sources.example.json` is a neutral starting point. IDs must remain stable, since they identify stored listings and source switches. Supported adapters are `discord` and `ticketweb_calendar` (FullCalendar literal data in the format exercised by the Music Box calendar). Set each venue's IANA timezone so local start times convert to UTC correctly. Restart the web app and collector after editing source configuration. More source formats need a separate reader module; no brand-specific logic belongs in calendar templates.

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
