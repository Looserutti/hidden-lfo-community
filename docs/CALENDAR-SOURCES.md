# Calendar source adapters

Sources are configured in `config/sources.json`; a fresh generic installation can start from `config/sources.example.json`. Each source starts with collection and publication off until an administrator enables it. Sources reuse weekly scheduling, manual Pull now, per-listing exclusions and venue retention. Changing a bundled registry requires deploying/restarting the web, collector and bot so the website, collection and /shows use the same sources.

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

The reference Pour House Oceanside source uses this adapter with concerts_only enabled. Titles mentioning trivia, bingo, karaoke, open mic, DJ nights, all-vinyl nights, fundraisers, vendors/markets, holidays/closures, comedy or similar non-concert programming are excluded. A DJ promoter presenting an actual band concert is not excluded merely for having DJ in the promoter's name. Review imported selections in Calendar settings; title-based classification cannot guarantee the nature of every ambiguously named listing. Staff can exclude individual shows or manually add a verified concert that the filter omitted.

Filtered non-concerts are not stored as new listings. If an already-imported show is renamed into an excluded category, its existing row is made ineligible without clearing staff exclusions. A later eligible concert title can restore it, with staff exclusions still respected. Existing cancellations and rolling venue-only cleanup remain in effect. The adapter imports only entries the venue exposes on its public page; it is not a guarantee of a complete or continually updated venue schedule.
