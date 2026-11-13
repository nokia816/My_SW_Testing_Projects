#!/bin/sh
# Nightly encrypted PostgreSQL backup (AES-256, PBKDF2). Runs inside the "backup" container.
set -eu
apk add --no-cache openssl >/dev/null 2>&1 || true
umask 077
while true; do
  TS=$(date +%Y%m%d-%H%M%S)
  OUT="/backups/bizplatform-$TS.sql.gz.enc"
  if pg_dump --no-owner --clean --if-exists | gzip -9 | \
     openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt -pass env:BACKUP_PASSPHRASE -out "$OUT"; then
    echo "[backup] OK $OUT"
  else
    echo "[backup] FAILED" >&2; rm -f "$OUT"
  fi
  find /backups -name 'bizplatform-*.sql.gz.enc' -mtime "+${BACKUP_KEEP_DAYS:-30}" -delete
  sleep 86400
done
