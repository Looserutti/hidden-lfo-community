#!/bin/sh
# Host-only, root-run encrypted backups. Configure /etc/community-backup.env first.
set -eu
umask 077
[ "$(id -u)" -eq 0 ] || { echo 'Run as root on the Docker host' >&2; exit 1; }
. "${BACKUP_ENV:-/etc/community-backup.env}"
: "${RESTIC_REPOSITORY:?Set RESTIC_REPOSITORY}"
: "${RESTIC_PASSWORD_FILE:?Set RESTIC_PASSWORD_FILE}"
export RESTIC_REPOSITORY RESTIC_PASSWORD_FILE
RCLONE_CONFIG=${RCLONE_CONFIG:-/etc/community-backup-rclone.conf}
export RCLONE_CONFIG
APP_CURRENT=${APP_CURRENT:-/opt/hidden-lfo/current}
APP_CONTAINER=${APP_CONTAINER:-community-platform-web-1}
BACKUP_STATE=${BACKUP_STATE:-/var/lib/community-backup}
SCRIPT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
install -d -m 700 "$BACKUP_STATE"
exec 9>"$BACKUP_STATE/run.lock"
flock -n 9 || { echo 'Another backup or restore check is running' >&2; exit 1; }
image=$(docker inspect "$APP_CONTAINER" --format '{{.Image}}')
stage="$BACKUP_STATE/staging"
cleanup() { rm -rf "$stage"; }
BACKUP_MODE=${1:-backup}
finish() {
    result=$?
    cleanup
    if [ "$result" -ne 0 ]; then
        if [ "$BACKUP_MODE" = verify ]; then
            date -u +%FT%TZ > "$BACKUP_STATE/last-verify-failure"
        else
            date -u +%FT%TZ > "$BACKUP_STATE/last-failure"
        fi
        echo 'Backup/verification failed; inspect systemd journal. Last good snapshots remain.' >&2
    fi
    # Publish timestamp-only status; no credentials or backup contents enter the web container.
    export BACKUP_STATE
    export BACKUP_HEALTH_DIR=${BACKUP_HEALTH_DIR:-/opt/hidden-lfo/shared/system-health}
    python3 - <<'HEALTH' || true
import json,os
from pathlib import Path
state=Path(os.environ['BACKUP_STATE']); target=Path(os.environ['BACKUP_HEALTH_DIR'])
target.mkdir(parents=True,exist_ok=True);target.chmod(0o755)
values={p.name:p.read_text().strip() for p in state.glob('last-*') if p.is_file()}
tmp=target/'backup.json.tmp';tmp.write_text(json.dumps(values));tmp.chmod(0o644);tmp.replace(target/'backup.json')
HEALTH
    exit "$result"
}
trap finish EXIT
trap 'exit 1' HUP INT TERM
cleanup
install -d -m 700 -o 10001 -g 10001 "$stage"
if [ "${1:-backup}" = verify ]; then
    repository=${RESTIC_REMOTE_REPOSITORY:-$RESTIC_REPOSITORY}
    restic -r "$repository" check
    restic -r "$repository" restore latest --tag community --target "$stage"
    docker run --rm --network none --read-only --user 0 -v "$stage:/restore:ro" -v "$SCRIPT_ROOT/scripts/backup_bundle.py:/backup_bundle.py:ro" --entrypoint python "$image" /backup_bundle.py --verify --output "/restore$BACKUP_STATE/staging"
    date -u +%FT%TZ > "$BACKUP_STATE/last-verified"
    exit 0
fi
[ "${1:-backup}" = backup ] || { echo 'Use backup or verify' >&2; exit 1; }
docker run --rm --network none --read-only --volumes-from "$APP_CONTAINER" -v "$stage:/backups" -v "$SCRIPT_ROOT/scripts/backup_bundle.py:/backup_bundle.py:ro" --entrypoint python "$image" /backup_bundle.py --output /backups --audio "${BACKUP_AUDIO:-/data/gallery-audio}" --photos "${BACKUP_PHOTOS:-/data/gallery-photos}" --project-photos "${BACKUP_PROJECT_PHOTOS:-/data/project-photos}"
# Trusted private deployment configuration; encrypted by restic with all other files.
install -d -m 700 "$stage/deployment"
for file in .env compose.yaml config/site.json config/sources.json config/sources.local.json; do
    if [ -f "$APP_CURRENT/$file" ]; then
        install -D -m 600 "$APP_CURRENT/$file" "$stage/deployment/$file"
    fi
done
readlink -f "$APP_CURRENT" > "$stage/deployment/release.txt"
printf '%s\n' "$image" > "$stage/deployment/image.txt"
# Include deployment files in verification without displaying their contents.
python3 - "$stage" <<'MANIFEST'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1])
manifest={}
for path in root.rglob('*'):
    if path.is_file() and path.name!='manifest.json':
        with path.open('rb') as stream: manifest[str(path.relative_to(root))]=hashlib.file_digest(stream,'sha256').hexdigest()
(root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
MANIFEST
restic backup --tag community "$stage"
date -u +%FT%TZ > "$BACKUP_STATE/last-local-success"
if [ -n "${RESTIC_REMOTE_REPOSITORY:-}" ]; then
    restic -r "$RESTIC_REMOTE_REPOSITORY" copy --from-repo "$RESTIC_REPOSITORY" --from-password-file "$RESTIC_PASSWORD_FILE" --tag community
    restic -r "$RESTIC_REMOTE_REPOSITORY" forget --tag community --keep-daily 7 --keep-weekly 4 --prune
    restic -r "$RESTIC_REMOTE_REPOSITORY" check
    date -u +%FT%TZ > "$BACKUP_STATE/last-offsite-success"
fi
# Only this application's snapshots; deduplication retains unchanged media once.
restic forget --tag community --keep-daily 7 --keep-weekly 4 --prune
restic check
date -u +%FT%TZ > "$BACKUP_STATE/last-success"
echo 'Backup complete. Check off-server coverage separately.'
