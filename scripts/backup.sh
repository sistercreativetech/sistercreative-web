#!/bin/sh
# Cadangkan database + file upload. Jalankan di VPS dari folder proyek, mis. via cron:
#   0 2 * * * cd /opt/sistercreative && ./scripts/backup.sh >> backups/backup.log 2>&1
set -eu

STAMP=$(date +%Y%m%d-%H%M%S)
DEST=${BACKUP_DIR:-./backups}
KEEP_DAYS=${BACKUP_KEEP_DAYS:-14}
COMPOSE="docker compose -f docker-compose.prod.yml --env-file .env"

mkdir -p "$DEST"

$COMPOSE exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner' \
  | gzip > "$DEST/db-$STAMP.sql.gz"

$COMPOSE exec -T web tar -czf - -C /app media > "$DEST/media-$STAMP.tar.gz"

find "$DEST" -name 'db-*.sql.gz' -mtime +"$KEEP_DAYS" -delete
find "$DEST" -name 'media-*.tar.gz' -mtime +"$KEEP_DAYS" -delete

echo "Backup selesai: $DEST/db-$STAMP.sql.gz dan media-$STAMP.tar.gz"
