#!/bin/sh
# First-time setup: generates strong random secrets into .env (never commit this file).
set -eu
cd "$(dirname "$0")/.."
if [ -f .env ]; then echo ".env already exists – not overwriting."; exit 0; fi
rand() { openssl rand -base64 48 | tr -d '/+=\n' | cut -c1-"$1"; }
printf "Domain name (empty = localhost / office network): "; read -r DOMAIN
if [ -z "$DOMAIN" ]; then DOMAIN=localhost; TLS=internal
else printf "Admin e-mail for the free Let's Encrypt certificate: "; read -r TLS; fi
printf "Organisation name: "; read -r ORG
umask 077
cat > .env <<ENV
DOMAIN=$DOMAIN
TLS_MODE=$TLS
BIZ_ORG_NAME=${ORG:-BizPlatform}
BIZ_REQUIRE_2FA=true
POSTGRES_PASSWORD=$(rand 40)
BIZ_ENCRYPTION_KEY=$(openssl rand -base64 32 | tr '+/' '-_')
BACKUP_PASSPHRASE=$(rand 48)
BACKUP_KEEP_DAYS=30
ENV
mkdir -p backups && chmod 700 backups
echo
echo ".env created. IMPORTANT: store BACKUP_PASSPHRASE and BIZ_ENCRYPTION_KEY in a password manager –"
echo "without them backups and encrypted fields (ID numbers, license keys) cannot be recovered."
echo
echo "Next:  docker compose up -d --build"
echo "Then:  docker compose exec backend python -m app.cli create-admin --email you@company.co.il --name \"Your Name\""
