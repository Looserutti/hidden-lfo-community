# Calendar source adapters

A fresh checkout has an empty `config/sources.json` and no calendar sources. Nothing is collected or published automatically. Copy the fictional `config/sources.example.json` to **`config/sources.local.json`**, replace its settings with your community’s venues, and restart the web, bot and collector. The private file replaces the entire registry, rather than adding to bundled defaults. It is ignored by Git and excluded from Docker images. Compose mounts the config directory read-only into each app service. Keep the private file with your deployment configuration when upgrading releases; backups include it.

For non-Compose installations, the loader also accepts `CALENDAR_SOURCES_FILE` pointing to a JSON registry. An explicitly selected missing or malformed file fails startup instead of silently using another registry. The default precedence is that environment path, then `config/sources.local.json`, then the empty `config/sources.json`. Each source starts with collection and publication off until an administrator enables it. Stable IDs preserve existing records and source switches. Removing a source stops its listings from being published without deleting stored records. Sources reuse weekly scheduling, manual Pull now, per-listing exclusions and venue retention.

To import your own Discord scheduled Events, include a source with `id: "discord"`, `adapter: "discord"`, `name: "Discord scheduled Events"`, `url: "https://discord.com"` and `timezone: "UTC"`; the guild and credentials come from your private environment configuration. Dashboard source creation is not implemented yet; source definitions currently use the private file.

## Squarespace event lists

`squarespace_events` reads public `eventlist-event` articles, stable Squarespace item IDs, title links and UTC dates embedded in their published Google Calendar export links. It does not execute site JavaScript, fetch unrelated pages, or require Google authorization. It uses one bounded page request per collection; missing or changed required markup fails the pull while preserving existing records. Event links must stay on the configured venue origin/path. Source pages may be partial; absent venue entries are not automatically deleted.

Example for another community (replace the example URL and location):

```json
{
  "id": "local-venue",
  "name": "Local venue",
  "adapter": "squarespace_events",
  "url": "https://venue.example/events",
  "timezone": "America/Los_Angeles",
  "location": "Local venue, City",
  "concerts_only": true
}
```

With `concerts_only` enabled, Titles mentioning trivia, bingo, karaoke, open mic, DJ nights, all-vinyl nights, fundraisers, vendors/markets, holidays/closures, comedy or similar non-concert programming are excluded. A DJ promoter presenting an actual band concert is not excluded merely for having DJ in the promoter's name. Review imported selections in Calendar settings; title-based classification cannot guarantee the nature of every ambiguously named listing. Staff can exclude individual shows or manually add a verified concert that the filter omitted.

Filtered non-concerts are not stored as new listings. If an already-imported show is renamed into an excluded category, its existing row is made ineligible without clearing staff exclusions. A later eligible concert title can restore it, with staff exclusions still respected. Existing cancellations and rolling venue-only cleanup remain in effect. The adapter imports only entries the venue exposes on its public page; it is not a guarantee of a complete or continually updated venue schedule.

## Administrator health indicators

The overview shows collection freshness against the configured weekly weekday/hour, with a two-hour grace period. Paused collection is neutral; publication status is separate. Bot and collector heartbeat thresholds are five and 35 minutes. Preview explicitly reports those workers as not running.

For host backups, set `SYSTEM_HEALTH_DIR` in Compose's environment to a dedicated timestamp-only directory (Hidden LFO uses `/opt/hidden-lfo/shared/system-health`). Set the backup host's `BACKUP_HEALTH_DIR` to the same path. The backup helper atomically publishes `backup.json` there; the web mounts it read-only. Never mount the backup repository or credential directory into the web container. Backup/copy freshness is 36 hours; monthly verification freshness is 35 days. Missing telemetry is neutral, not proof of health. Indicators update on page reload; external alerts are not sent.
