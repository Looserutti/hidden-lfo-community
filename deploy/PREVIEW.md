# Independent preview website

Run a second website on the same server with a separate Compose project, pinned image, private environment, session secret and database volume. There is no preview gateway bot or scheduled collector. Production tracking continues unchanged. Preview is publicly viewable, so use test data only; its banner and noindex header distinguish it from production.

1. Test and commit the candidate source, then build a versioned image: `docker build -t your-community-preview:COMMIT .`.
2. Copy `deploy/preview.env.example` to `.env.preview` and fill the preview origin, registered Discord OAuth callback, existing OAuth client credentials, admin allowlist, proxy network name and a fresh session secret. Use mode 600. Leave the bot token blank.
3. Run `docker compose --env-file .env.preview -f compose.preview.yaml config --quiet`, then `docker compose --env-file .env.preview -f compose.preview.yaml up -d`. This runs its own migrations and website only. It never replaces the production database.
4. Point preview DNS at the existing server. Remove preview from production `SITE_ALIASES`. Set production `PREVIEW_ROUTES_DIR` to a persistent absolute directory outside release checkouts. Put a route in that directory, such as `preview.community.example.com { reverse_proxy preview-web:8000 }`. The production Caddy container imports this directory and shares its external network with preview. Validate Caddy configuration before recreating/reloading the proxy.
5. Verify preview HTTPS, admin OAuth login, noindex header, test data and production health. Preview host cookies do not sign in to production; the secrets and databases differ.

For later changes, build a new candidate image, change **only preview** PREVIEW_IMAGE, and run the preview Compose commands from the candidate checkout. Review it in desktop/mobile browsers. After acceptance, deploy that tested commit and any necessary backed-up migrations to production. Do not copy a preview database to production. Keep the previous image/release for rollback. Git pushes do not automatically deploy either environment.

A single shared server reduces cost but is not infrastructure isolation: both sites share host resources and the proxy network. Watch memory/disk usage. Large changes can require a separate server later. Public preview is not a place for member database copies or production bot credentials. Provider backups retain existing server data under their configured retention.
