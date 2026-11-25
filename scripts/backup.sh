#!/bin/bash
# Saves what a restore needs, in one directory (make backup [directory]; backups/<date> by default):
#   <base>.sql.gz   each database of this host (BornToShare, its audit, the 5S module when installed), with the
#                   migration account (secret b2s_db_migrate); the owner of the views is left out (their creator may
#                   not exist on the target server)
#   config.tar.gz   .env and the certificates of the worker (capsule-runner/certs, or /etc/b2s/certs in native)
#   secrets.tar.gz  the secrets, the key of the stored passwords (b2s_master_key) included: without it a restored
#                   database has its passwords of directories and servers unreadable
#   MANIFEST        date, version, mode, and the SHA-256 of each file (checked by scripts/restore.sh)
# B2S_BACKUP_PASSPHRASE_FILE=<file>: the secrets and the configuration (.env holds INTERNAL_TOKEN and the signing
# key, the certificates a private key) are encrypted with that passphrase (*.tar.gz.enc, AES-256, openssl), to copy
# the backup off this server. Without it the directory is readable by its owner only, like the
# secrets on this server: encrypt it before it leaves.
# Restore: scripts/restore.sh <directory> (docs/exploitation.md).
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/lib.sh
TARGET="${1:-backups/$(date +%Y%m%d-%H%M%S)}"
MODE=$(deploy_mode)
PASSPHRASE="${B2S_BACKUP_PASSPHRASE_FILE:-}"
[ -z "$PASSPHRASE" ] || [ -s "$PASSPHRASE" ] || { echo "Phrase de passe introuvable ou vide : $PASSPHRASE" >&2; exit 1; }
# Checked before anything is dumped: a backup asked encrypted is never left in clear nor half made
[ -z "$PASSPHRASE" ] || command -v openssl >/dev/null || { echo "openssl introuvable : dnf install openssl (chiffrement de la sauvegarde)" >&2; exit 1; }
MIGRATE_USER="$(env_value DB_MIGRATE_USER b2s_migrate)"
DATABASES="$(env_value DB_NAME borntoshare) $(env_value LOGGING_DB_NAME borntoshare_logging)"
if has_secret b2s_db_fives; then
  FIVES_DB="$(env_value FIVES_DB_NAME)"; INVENTORY_DB="$(env_value FIVES_INVENTORY_DB_NAME)"
  DATABASES="$DATABASES ${FIVES_DB:-b2s_fives} ${INVENTORY_DB:-b2s_fives_inventory}"
fi
umask 077
if [ -d "$TARGET" ] && [ -n "$(ls -A "$TARGET")" ]; then echo "$TARGET existe et n'est pas vide" >&2; exit 1; fi
mkdir -p "$TARGET"
# A failed backup does not stay behind looking like a good one
complete=""
cleanup() {
  [ -n "$complete" ] && return
  rm -rf "$TARGET/.secrets"
  mv "$TARGET" "$TARGET.incomplete" 2>/dev/null || true
  echo "Sauvegarde incomplète, inutilisable : $TARGET.incomplete" >&2
}
trap cleanup EXIT

# ---- databases ----
for db in $DATABASES; do
  # Without LOCK TABLES around the inserts: the migration account has no right to lock (least privilege), and the
  # restore needs none (the services are stopped)
  b2s_db b2s_db_migrate "$MIGRATE_USER" mariadb-dump --single-transaction --skip-add-locks "$db" \
    | sed -E 's/DEFINER=`[^`]+`@`[^`]+`//' | gzip > "$TARGET/$db.sql.gz"
  gzip -dc "$TARGET/$db.sql.gz" | tail -1 | grep -q "Dump completed" || { echo "Dump incomplet : $db" >&2; exit 1; }
  echo "$TARGET/$db.sql.gz"
done

# ---- configuration: .env, certificates of the worker ----
if [ "$MODE" = native ]; then
  certs=""
  as_root test -d /etc/b2s/certs && certs="etc/b2s/certs"
  # shellcheck disable=SC2086
  as_root tar -czf - -C "$PWD" .env ${certs:+-C / $certs} > "$TARGET/config.tar.gz"
else
  # shellcheck disable=SC2046
  tar -czf "$TARGET/config.tar.gz" .env $(find capsule-runner/certs -maxdepth 1 -type f \( -name '*.crt' -o -name '*.key' -o -name '*.pem' \) 2>/dev/null)
fi
if [ -n "$PASSPHRASE" ]; then
  openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass "file:$PASSPHRASE" -in "$TARGET/config.tar.gz" -out "$TARGET/config.tar.gz.enc"
  shred -u "$TARGET/config.tar.gz" 2>/dev/null || rm -f "$TARGET/config.tar.gz"
  echo "$TARGET/config.tar.gz.enc (chiffré)"
else
  echo "$TARGET/config.tar.gz"
fi

# ---- secrets ----
mkdir "$TARGET/.secrets"
if [ "$MODE" = native ]; then
  # The option files (*.cnf) are made again by make deploy from the passwords
  as_root sh -c 'cd "$1" && for f in b2s_*; do case "$f" in *.cnf) ;; *) cat "$f" > "$2/$f" ;; esac; done' \
    sh "$NATIVE_SECRETS" "$PWD/$TARGET/.secrets"
else
  for name in $(podman secret ls --format '{{.Name}}' | grep '^b2s_'); do
    podman secret inspect --showsecret --format '{{.SecretData}}' "$name" > "$TARGET/.secrets/$name"
  done
fi
[ -s "$TARGET/.secrets/b2s_master_key" ] || { echo "Secret b2s_master_key introuvable : la sauvegarde serait inutilisable" >&2; exit 1; }
if [ -n "$PASSPHRASE" ]; then
  tar -czf - -C "$TARGET/.secrets" . | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass "file:$PASSPHRASE" -out "$TARGET/secrets.tar.gz.enc"
  echo "$TARGET/secrets.tar.gz.enc (chiffré)"
else
  tar -czf "$TARGET/secrets.tar.gz" -C "$TARGET/.secrets" .
  echo "$TARGET/secrets.tar.gz (en clair, lisible par vous seul : B2S_BACKUP_PASSPHRASE_FILE pour le chiffrer)"
fi
for f in "$TARGET/.secrets"/*; do shred -u "$f" 2>/dev/null || rm -f "$f"; done
rmdir "$TARGET/.secrets"

# ---- manifest ----
{
  echo "date=$(date -Is)"
  echo "version=$(git rev-parse --short HEAD 2>/dev/null || echo inconnue)"
  echo "mode=$MODE"
  echo "databases=$DATABASES"
  (cd "$TARGET" && sha256sum -- *.sql.gz config.tar.gz* secrets.tar.gz*)
} > "$TARGET/MANIFEST"
complete=1
echo "Sauvegarde complète : $TARGET"
