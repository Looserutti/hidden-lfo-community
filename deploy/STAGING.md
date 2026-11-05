# First hosted staging deployment

Use one Ubuntu server with local persistent storage. A 2 GB RAM / 1 vCPU VPS is a starting point; verify actual memory use after launch. Use a staging subdomain and the existing Discord OAuth application. The default Compose launch runs only migration, website and HTTPS proxy. The bot and calendar collector are optional profiles.

## Before launch

1. Run tests locally and commit reviewed code. Transfer a tracked source release (`git archive`) or clone the chosen commit on the server; do not upload the entire Mac working folder, `.env`, original photos or backup files.
2. On the server, copy `deploy/staging.env.example` to `.env`; replace the sample domain in all three URL fields, set OAuth credentials and allowlisted admin IDs, and generate a fresh session secret. Keep the local Mac `.env` unchanged. Protect the server file with `chmod 600 .env`.
3. Point only the staging hostname's DNS record to the server. Allow SSH with keys and HTTP/HTTPS (TCP 80/443; optional HTTP/3 uses UDP 443). Do not expose application port 8000. Keep an SSH connection open while adjusting firewall rules.
4. Add `https://YOUR-STAGING-HOST/auth/callback` to the existing Discord application's OAuth2 redirects, keeping the local callback. Log in to staging using the exact same hostname.
5. Install Docker Engine and its Compose plugin using the provider/official installation instructions. Run the preflight inside the image after building; no host Python installation is required.

## Website-only launch

```sh
docker compose config --quiet
docker compose build
docker compose run --rm --no-deps web python -m scripts.check_config --production
docker compose run --rm migrate
docker compose up -d web caddy
```

Test HTTPS, `/healthz`, public pages and an allowlisted admin login. Confirm an unlisted account is denied. `/healthz` checks HTTP responsiveness only. Caddy needs correct public DNS and reachable ports to issue a certificate.

Start staging with a fresh database unless a private data transfer is intentionally planned. This gives staff a layout/event testing environment without copying member observations onto a new server. Manually managed event publishing should only be tested against an isolated test channel.

## Optional processes: explicit cutover

Do not run a second bot against the same production guild/database workflow while the Mac's bot is still active. Stop the old process before starting the server bot. A website-only staging launch does not require the gateway bot.

```sh
docker compose run --rm --no-deps web python -m scripts.check_config --production --bot
docker compose --profile bot up -d bot
# Separately, when ready to test calendar collection:
docker compose --profile shows up -d calendar-collector
```

`EVENT_PUBLISHING_ENABLED` and `STAFF_REPORTS_ENABLED` default false. They opt into event announcements and weekly activity reports respectively; configure and test their destination channels before enabling. Weekly reports send on task startup, then every 168 hours while the process remains online. These switches do not control imported calendar listings. Calendar collection and website display have their own initially disabled switches in the admin dashboard. Do not enable feed publication until source content is reviewed.

## Backup and restore rehearsal

Run `sh deploy/backup.sh` on the server. It writes a consistent SQLite backup. Download it through your authenticated SSH connection to a private folder on your Mac; provider server snapshots supplement these database backups.

Verify the downloaded backup and rehearse restoration to a **new file**:

```sh
python -m scripts.verify_backup --backup /private/path/community-backup.db --restore-to /private/path/restore-check.db
```

A successful check does not replace a complete application recovery rehearsal. For actual recovery, stop every database writer (website, bot, collector), preserve the old database, restore the verified copy to the persistent volume using the deployment's ownership, and run migrations and smoke tests before restarting services. Do not restore over an open SQLite database. Keep backups off-server and establish a recurring copy/retention process before relying on this installation.

## Ready for staff review

- Public HTTPS and OAuth callback work; admin pages reject unsigned and unlisted visitors.
- Database survives a web container restart; backups verify and restore to a new file.
- Mobile homepage, calendar and staff forms are usable.
- Venue collection remains paused until tested; Casbah/Soda Bar automation remains blocked pending a supported source.
- Only one gateway bot is active for the production community.
- Server memory, disk space, error logs and costs are monitored. Container logs rotate at 10 MB × 3 files per service.

Docker startup, certificates, external DNS, firewall configuration, live Discord permissions and off-server backup copying must be tested on the actual server. Passing local unit tests is not a hosted-launch sign-off.
