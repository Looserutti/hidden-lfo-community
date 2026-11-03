#!/bin/sh
# Run on the Docker host: ./deploy/backup.sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p backups
stamp=$(date -u +%Y%m%d-%H%M%S)
docker compose run --rm --no-deps -v "$(pwd)/backups:/backups" --entrypoint python web -m scripts.backup_sqlite --output "/backups/community-$stamp.db"
find backups -type f -name 'community-*.db' -mtime +14 -delete
printf '%s\n' 'Backup complete. Copy encrypted backups off this server and test restoration.'
