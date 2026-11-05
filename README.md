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
- Events have UTC display on the public site; add browser-local timezone rendering and calendar month view later.
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
3. Run `docker compose config` to validate configuration, then `docker compose build`, `docker compose run --rm migrate` and `docker compose up -d`. The Compose services are `migrate`, `web`, `bot`, and `caddy`; Caddy obtains/renews HTTPS certificates when DNS and inbound ports are correct. Review logs with `docker compose logs -f web bot caddy`.
4. Check `https://your-domain/healthz`, then test a draft/published event, Discord RSVP, cancellation, and admin OAuth in a test server before announcing the website. `healthz` indicates only that the web process is responding; it does **not** confirm Discord connectivity or database correctness.
5. For database backup on the host, run `./deploy/backup.sh`. Schedule this using host cron or a systemd timer (e.g. daily), **copy encrypted backups to an off-server destination**, and rehearse a restore. The included script retains local copies for 14 days but does not upload them. Do not consider backups complete without off-server replication.
6. Before upgrades, back up and test restoring; run `docker compose run --rm migrate` to apply migrations, then `docker compose up -d --build`. Use a maintenance window for schema changes.

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

- Edit **`config/site.json`** for the community name, location eyebrow, description, footer wording, social URLs, and gallery folder. No template or Python edits are needed. Restart the website after changing this JSON file.
- To start fresh, copy `config/site.example.json` to `config/site.json`. The example has generic wording, no social accounts. Blank social URLs hide their icons; an empty gallery folder hides the carousel and viewer. Any number of photos is supported, with counters generated automatically.
- **Drag and drop photos into `static/images/gallery/`**, then refresh the homepage. Delete photos from that folder to remove them. No JSON edits or server restart are needed for photo changes. The folder is scanned on each page request; an already-open page needs a refresh.
- Supported formats: JPG/JPEG, PNG, WebP, GIF, and AVIF (browser support varies). Convert HEIC photos to JPEG first. Hidden files, subfolders, and symlinks are ignored. Photos sort naturally by filename: use `01-stage.jpg`, `02-crowd.jpg`, etc. Filenames also supply the generated image descriptions, so use descriptive names.
- Change `gallery_folder` in `config/site.json` to use another folder relative to `static/`. Restart after configuration changes. The generic example uses the same folder; remove the example photos when rebranding. Use photos you have permission to distribute; existing event photos are not a promise of reuse rights.
- For a deployed site, add/remove files on the server or redeploy the updated folder; changing files on your Mac only updates your local preview.
- Edit **`static/theme.css`** for homepage, carousel, viewer, footer, and social icon styling. `static/style.css` contains shared application styles and color variables. Refresh the browser after CSS edits.
- Shared layout lives in `templates/base.html`; social vector artwork is isolated in `templates/_social_icon.html`. Account URLs are configuration, never embedded in icons.
- Configure the Discord invite, deployment base URL and OAuth callback in `.env` using `.env.example`. Public branding JSON must not contain credentials.

Keep future branding changes in these presentation files and configuration. Changes to events, permissions, authentication, or bot services should be scoped and reviewed separately.
