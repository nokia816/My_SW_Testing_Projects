#!/bin/sh
# Restore an encrypted backup:  ./scripts/restore.sh backups/bizplatform-YYYYMMDD-HHMMSS.sql.gz.enc
set -eu
[ $# -eq 1 ] || { echo "usage: $0 <backup-file>"; exit 1; }
set -a; . ./.env; set +a
echo "This will OVERWRITE the current database with $1. Type YES to continue:"; read -r ok; [ "$ok" = "YES" ] || exit 1
openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass env:BACKUP_PASSPHRASE -in "$1" | gunzip | \
  docker compose exec -T -e PGPASSWORD="$POSTGRES_PASSWORD" db psql -U bizplatform -d bizplatform -v ON_ERROR_STOP=1
echo "Restore complete."
