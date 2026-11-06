# Services, costs, and setup order

This guide describes the reference setup for a small community hub: one Ubuntu server running the website, Discord bot, calendar collector, and an optional independent preview website. It is an example deployment, not a requirement to use a particular hosting company.

## Accounts and resources

| Resource | Reference service / official instructions | Cost and purpose |
| --- | --- | --- |
| Source repository | [GitHub](https://github.com/pricing) | A free account can fork the project and store source history. GitHub is not the running web server in this setup. |
| Always-on server | [DigitalOcean Basic Droplet](https://www.digitalocean.com/pricing/droplets) | Paid. A regular 1 vCPU / 2 GiB RAM / 50 GiB SSD Ubuntu server is the reference starting size. Monitor usage as the community grows. Other Ubuntu VPS providers can work. |
| Domain | Your domain registrar | Registration and renewal are separate costs; use a domain you own. A preview subdomain uses that same domain. |
| DNS | [Cloudflare Free](https://www.cloudflare.com/plans/free/) | Free DNS is sufficient for this setup; an equivalent DNS provider also works. The domain itself is not included. |
| Discord application | [Discord Developer Portal](https://discord.com/developers/applications) and [official bot setup guide](https://docs.discord.com/developers/quick-start/getting-started) | Create your own application for OAuth login and the bot. These project features do not require a Discord Nitro subscription. |
| Database | [SQLite](https://www.sqlite.org/whentouse.html), [public-domain licensing](https://www.sqlite.org/copyright.html) | Included with the Python runtime in the app image. No database account, database server installation, or separate database subscription is needed. Files live in Docker volumes on your server. |
| App runtime | [Docker Engine and Compose on Ubuntu](https://docs.docker.com/engine/install/ubuntu/) | Install the server runtime using official instructions. Docker Desktop and a paid Desktop subscription are not needed on the Ubuntu server. The project installs its Python dependencies during image build. |
| HTTPS | [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https) | The supplied Compose setup runs Caddy and obtains/renews certificates automatically. No separate paid certificate is required for this configuration. |
| Backups | [DigitalOcean backup pricing](https://docs.digitalocean.com/products/backups/details/pricing/) and the project's SQLite backup scripts | Provider backups are optional and paid. SQLite backup/restore helpers are included, but an off-server destination and a recurring copy process must be arranged separately. |

Prices checked November 5, 2026: the reference DigitalOcean server lists at $12/month. Percentage-based weekly backups add 20%, for a $14.40/month baseline before tax, domain renewal, usage overages, or optional products. Preview currently shares that server, so it does not require a second server purchase. This is not a hard spending cap; verify the provider's checkout and current prices for your account and region. Avoid adding a managed database, load balancer, object storage, or extra server unless you intentionally need one.

## Which database services must I sign up for?

None. SQLite is the database used by this deployment. The live application stores members, observations, calendar records, proposals, and settings in its persistent database volume. Preview has a different volume and session secret. Source code goes in Git; database contents and credentials do not.

Supabase, Neon, Firebase, Cloudflare D1, and other hosted database products are not required or configured by these instructions. Moving to a managed database would be separate implementation and migration work, including replacing the SQLite-specific backup workflow. Free tiers of unrelated services are not dependencies of this project.

## First setup: follow this order

1. **Fork or clone the project.** Read the repository license before redistributing code or assets. Keep your copy under version control. Start with `config/site.example.json` for branding and `config/sources.example.json` for sources; use media you have permission to distribute.
2. **Create your Discord application.** Follow the official Discord guide linked above. Save the application client ID, OAuth client secret, bot token, server ID, verified-role ID, and required channel IDs in a private environment file. Get numeric user IDs for admins. Enable the Server Members and Presence intents for the activity tracker. Give the bot the permissions needed for the features you enable, and put its role above Verified for role assignment. Do not enable message-content intent just for this tracker; it does not read message bodies.
3. **Choose your domain and DNS provider.** Add the domain to your DNS provider and update nameservers at the registrar if needed. Once the server exists, point the main hostname, `www`, and optional `preview` hostname to its public address. The reference setup uses DNS-only records with Caddy providing HTTPS directly.
4. **Create the Ubuntu server.** Choose the reference size or an equivalent VPS. Set up key-based SSH access and install Docker Engine/Compose from Docker's official Ubuntu instructions. Allow SSH and TCP 80/443; UDP 443 is optional for HTTP/3. Do not publish app port 8000 or a database port. Docker-published ports need separate care because Docker can bypass ordinary UFW rules; see Docker's firewall guidance on the installation page.
5. **Configure the main website.** Follow [STAGING.md](STAGING.md) for environment settings, build, preflight checks, migrations, and website startup. Those commands can launch a staging or main hostname: replace every example origin consistently. Register the exact `https://YOUR-HOST/auth/callback` in Discord OAuth2 redirects before testing login. `SITE_DOMAIN`, `PUBLIC_BASE_URL`, and `DISCORD_REDIRECT_URI` must agree.
6. **Add preview if wanted.** Follow [PREVIEW.md](PREVIEW.md) and copy [preview.env.example](preview.env.example) to a private `.env.preview`. Use a fresh session secret and fresh test database. Keep the production bot token and member database out of preview. Configure the shared proxy route; preview must not remain a redirect alias for production.
7. **Enable live processes deliberately.** Run the bot preflight, stop any previous gateway bot, then enable the `bot` profile. Start the separate `shows` profile for calendar collection. Admins configure collection and website/source publication separately. Defaults keep outbound event announcements and staff reports off. `/shows` and `/event` require the configured verified role. Weekly source scheduling and venue retention are configured in `config/site.json`.
8. **Verify and back up.** Test HTTPS, authorized/unauthorized admin access, member tracking, calendar selection, and mobile layouts. Rehearse database restoration to a new file. Configure the complete encrypted host backup helper and systemd timers using [docs/BACKUPS.md](../docs/BACKUPS.md). The helper provisions private staging for the container UID and supports seven daily/four weekly retained points. Arrange and verify an authorized off-server repository and separate recovery key; a backup script alone is not a backup schedule.

## Normal design and code changes

Edit locally, test, commit/push, deploy the chosen version to preview, review it, then deliberately deploy the accepted version to the live site. Preserve the live database and back it up before migrations. Git pushes alone do not deploy. Preview and live may use different code versions. Test Discord bot changes with a separate test application/server rather than launching a second copy of the production bot.

Site names, social links, gallery folders, calendar time zone, weekly schedule, and venue retention are configuration settings. Keep community-specific branding out of reusable application logic. Existing photos and logos are not an automatic grant of reuse rights.
