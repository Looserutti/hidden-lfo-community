# Gallery audio (post-v0.1 development)

Music is optional and appears only inside the expanded photo viewer. Opening a photo does not start playback. The visitor presses Play, photo navigation leaves the track running, and closing the viewer (including Escape) pauses it. Reopening keeps the selected track/progress but never resumes automatically. The player uses native browser audio controls for play, seek and volume, with always-visible previous/next track controls beside the playback timeline. The compact strip keeps track metadata hidden by default; use **Tracks** to reveal credits and a one-tap playlist with the selected track highlighted. Closing the viewer collapses those details again. Slider/select arrow keys do not change photographs.

## Manage from the website

Sign in as an allowlisted administrator and open **Gallery audio** (`/admin/music`).

1. Upload MP3, WAV or M4A, optionally entering a title and artist. New uploads are drafts and cannot be streamed publicly.
2. Check **Available in gallery** and **Save track** to publish it.
3. Edit titles/credits or use **Move up / Move down** to choose playback order.
4. Uncheck availability to remove it from the public playlist. **Remove track → Delete audio file** removes its metadata and stored file from this environment.

Refresh the homepage after playlist changes. Already-open pages retain their playlist until refreshed; unpublished/deleted media stops accepting new requests, but downloaded/browser-buffered audio cannot be recalled. Published audio URLs are publicly accessible; uploads are not access-controlled digital-rights storage.

The public player is hidden when there are no published tracks. A new/generic deployment has no audio bundled. Audio files and private deployment settings do not belong in Git or Docker source images.

## Storage and limits

Run `alembic upgrade head` before starting this feature; revision `0005` adds audio metadata. Files live in `GALLERY_AUDIO_DIR`, defaulting to `/data/gallery-audio` inside Docker and `var/gallery-audio` in local development. The Docker default uses the existing persistent data volume; preview has its own separate volume/library. Ensure the directory is writable by the app user (UID 10001 in the provided image).

Defaults are **50 MB per upload** and **512 MB total library storage**. Override with `GALLERY_AUDIO_MAX_UPLOAD_MB` and `GALLERY_AUDIO_MAX_STORAGE_MB`. The admin page shows current usage. MP3s are usually much smaller than WAVs; this version stores the original file without transcoding. Format-header checks reject obvious wrong files; final decoding support is determined by the visitor's browser.

Back up **both** the SQLite database and the audio directory. The existing SQLite backup helper copies metadata, not uploaded audio files. Preserve matching metadata/files when restoring. Delete removes the working copy, not historical backups. For complete encrypted backups and optional scheduled off-server replication, configure the host helper described in [BACKUPS.md](BACKUPS.md). Off-server replication requires a separately authorized destination.

Admin writes require the existing allowlist and CSRF token. Uploads have bounded size and quota checks; original filenames never become storage paths. Published media supports HTTP byte ranges for seeking and uses `Cache-Control: no-store` so publication changes are checked on new requests. Playing audio consumes server outbound bandwidth; media uses `preload="none"` and does not autoplay.

This phase does not add external embeds, photo-specific tracks, automatic music generation or automatic public deployment. Review uploaded tracks and the player on preview before promoting it.


## Optional loudness matching

Each track has **Normalize playback volume** and a target selector in Gallery audio. The default is −14 LUFS integrated (Spotify's Normal playback target); −16 and −18 are available. Save to queue processing, then use **Refresh status** to see queued, processing, ready or failed. Uncheck normalization and save to serve the original again. Changing the target generates a new copy from the original, not from a previously compressed copy.

The supplied Docker image includes FFmpeg. Local development needs FFmpeg installed separately for processing; uploads/playback still work without it. A single background worker processes tracks serially to limit CPU use. Interrupted work is marked failed on startup and can be retried by saving the option again; this initial queue is not a distributed worker service.

Processing measures integrated loudness and true peak, applies a fixed gain, and encodes a separate 192 kbps MP3 playback copy. It verifies the encoded file's loudness/peak and makes corrections as needed; successful copies have true peaks at or below −1 dBTP. It does not apply EQ or heavy dynamics processing. If reaching the selected LUFS would exceed available headroom, the copy remains quieter to preserve dynamics; the measured output LUFS is shown in admin. This is playback matching, not full mastering or guaranteed perceptual equality between every recording. Original and normalized files both count toward the library quota and both belong in backups.

Existing public players may retain buffered audio until refreshed; new media requests use the selected version. The original is used while a first normalization job is queued/processing or fails. If a normalized copy already exists, it remains available until its replacement completes. Artist recordings used in preview are not bundled with source or examples.

Artist social links: edit a track in Gallery audio, enter a full HTTP(S) profile URL, and enable “Show artist link in track details.” Links are off by default and appear only for the selected track in expanded details. Turning the option off preserves the saved URL while omitting it from the public playlist. Links open in a new tab. No social credentials or API services are needed.
