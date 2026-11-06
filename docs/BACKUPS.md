# Complete community backups

The root-run host helper `deploy/backup.sh` creates encrypted, deduplicated restic backups of the live SQLite database, audio originals/playback copies and all saved photo batches referenced by that snapshot, and private deployment configuration. It does not require the website to stop. A short SQLite write lock prevents media metadata/deletion races while the database and referenced media are staged. Normal reads continue; writers may briefly wait. Run during a quiet period as the library grows.

Install `restic` from your host distribution; Google Drive additionally needs `rclone`. Set up a private restic repository and a root-only encryption password file, and copy `deploy/community-backup.env.example` to `/etc/community-backup.env`, mode 0600. Keep a separate recovery copy of the password in your password manager: losing the server and its only password copy makes encrypted backups unrecoverable. Never put backup passwords, OAuth configuration, databases or recordings in Git.

Install the helper and snapshot script together at `/opt/hidden-lfo/backup-tools/{deploy,scripts}` or adjust the service paths. The snapshot container uses the running web image and its data volume, and the host explicitly provisions the staging directory for UID 10001. It does not start the bot/collector or expose a new service port. Defaults assume the provided Docker layout; change the script arguments if your database path differs; set `BACKUP_AUDIO` and `BACKUP_PHOTOS` to match any custom in-container media paths.

Run a first backup and isolated verification before enabling timers:

```
sudo /opt/hidden-lfo/backup-tools/deploy/backup.sh backup
sudo /opt/hidden-lfo/backup-tools/deploy/backup.sh verify
```

Install the four `deploy/community-backup*.service` and `.timer` files into `/etc/systemd/system`, reload systemd, and enable `community-backup.timer` and `community-backup-verify.timer`. The example schedule is daily around 04:00 America/Los_Angeles (up to ten minutes randomized delay), with restore verification on the first of each month at 05:00. Change the timezone for your community. Persistent timers catch up missed schedules when the server returns.

Retention keeps seven daily and four weekly recovery points using restic's calendar policy; overlapping points do not require separate full media copies. Extra same-day deployment backups may be superseded by the retained daily point. `forget --prune` only handles snapshots tagged `community` in the configured repository. Keep milestone/release backups separately if you need them indefinitely. Private plaintext staging is removed on success or failure; a power loss may leave staging until the next run. Backup storage may still grow when audio or photos are replaced or deleted because retained snapshots preserve older files.

## Off-server Google Drive copy

Google Drive integration uses a server-side rclone OAuth remote. It does not depend on a Mac. Authorize the community-owned account and use the limited `drive.file` scope where supported, which permits files created by the backup app rather than arbitrary existing Drive content. Follow current [rclone Google Drive setup](https://rclone.org/drive/) and [headless authorization](https://rclone.org/remote_setup/). Create a dedicated OAuth client when required; keep the consent app in a suitable production/internal state to avoid short-lived testing credentials. Do not enable Cloud billing merely for this backup setup. Review any Google terms and OAuth access prompt yourself before approving.

Store rclone configuration root-only at `/etc/community-backup-rclone.conf`. Initialize the new offsite repository once, with the local repository's chunker parameters to preserve efficient deduplication:

```
# Run in a root shell with trusted /etc/community-backup.env sourced/exported.
restic -r "$RESTIC_REMOTE_REPOSITORY" init --copy-chunker-params \
  --from-repo "$RESTIC_REPOSITORY" --from-password-file "$RESTIC_PASSWORD_FILE"
```

Use the same private password file for these repositories unless adapting the helper for separate keys. Set `RESTIC_REMOTE_REPOSITORY` only after authorization/initialization succeeds. Backups first capture a local point, then copy snapshots to the remote repository and apply the same retention. Monthly verification restores from the remote repository when configured. If Drive is unavailable, the local point remains, but the service fails and the offsite success timestamp stays stale. Deleted remote objects may remain in Drive Trash and count toward provider usage; inspect usage/retention without automatically purging unrelated Drive data.

No recurring storage product is purchased by this helper. Available space, provider quotas, API limits and outbound traffic must still be monitored. Without a verified off-server destination, server loss protection remains incomplete.

## Check failures and recovery

```
systemctl list-timers 'community-backup*'
systemctl status community-backup.service community-backup-verify.service
journalctl -u community-backup.service -u community-backup-verify.service
```

`BACKUP_STATE` records `last-local-success`, `last-offsite-success` (when configured), `last-success`, `last-verified`, and `last-failure`. A failed service/journal is not an email or Discord notification; attach your chosen monitoring service separately. Check for stale success timestamps as well as failed services.

Verification restores to a temporary directory, validates file hashes and SQLite integrity, then removes the restored plaintext. It does not overwrite production or start a second Discord bot. For disaster recovery, restore into a new isolated data directory, verify the database/audio/photos/configuration, deploy the matching source release, provision correct ownership, and only then deliberately switch services. Test Discord gateway exclusivity before starting a replacement bot. Do not restore an old database simply to roll back website code.

Dashboard-managed photo batches (including drafts and retained batches) are recovered from `gallery-photos/` in the same snapshot as `community.db`; restore both together into the persistent data directory, alongside `gallery-audio/`. Use the application UID and private directory/file permissions. Project-folder source images/photos are recovered from Git when tracked. Untracked operator-added assets and additional custom configuration need explicit inclusion in your backup policy. Preview uses separate data and is not included by the production timer.
