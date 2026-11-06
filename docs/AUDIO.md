# Gallery audio (post-v0.1 development)

Music is optional and appears only inside the expanded photo viewer. Opening a photo does not start playback. The visitor presses Play, photo navigation leaves the track running, and closing the viewer (including Escape) pauses it. Reopening keeps the selected track/progress but never resumes automatically. The player uses native browser audio controls for play, seek and volume, with a shared playlist selector and previous/next tracks. Slider/select arrow keys do not change photographs.

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

Back up **both** the SQLite database and the audio directory. The existing SQLite backup helper copies metadata, not uploaded audio files. Preserve matching metadata/files when restoring. Delete removes the working copy, not historical backups. There is no automatic off-server audio backup task.

Admin writes require the existing allowlist and CSRF token. Uploads have bounded size and quota checks; original filenames never become storage paths. Published media supports HTTP byte ranges for seeking and uses `Cache-Control: no-store` so publication changes are checked on new requests. Playing audio consumes server outbound bandwidth; media uses `preload="none"` and does not autoplay.

This phase does not add external embeds, photo-specific tracks, automatic music generation or automatic public deployment. Review uploaded tracks and the player on preview before promoting it.
