#!/bin/bash
# Restores a backup made by scripts/backup.sh on this server: make restore FROM=backups/<date>
#   make restore FROM=…                 checks the backup and says what would be restored, changes nothing
#   CONFIRM=yes make restore FROM=…     restores, then make deploy (SQL packs, services), then checks
# B2S_BACKUP_PASSPHRASE_FILE=<file>: the passphrase of an encrypted backup (secrets.tar.gz.enc, config.tar.gz.enc).
#
# What is restored:
#   - the databases: replaced by those of the backup (same names, those of .env), with the migration account;
#   - the key of the stored passwords (b2s_master_key): always, it is the one of the restored data;
#   - the other secrets (passwords of the SQL accounts, Redis): only those this server does not have. A server
#     reinstalled with the wizard keeps the passwords of its new SQL accounts;
#   - .env and the certificates of the worker: only when this server has none (otherwise .env of the backup is
#     left in .env.from-backup, to compare).
# The databases and the SQL accounts must exist (the wizard creates them on a new MariaDB server).
set -euo pipefail
cd "$(dirname "$0")/.."
FROM="${1:-${FROM:-}}"
[ -n "$FROM" ] && [ -d "$FROM" ] || { echo "Sauvegarde introuvable : make restore FROM=backups/<date>" >&2; exit 1; }
FROM=$(cd "$FROM" && pwd)
DO=0
[ "${CONFIRM:-}" = yes ] && DO=1
PASSPHRASE="${B2S_BACKUP_PASSPHRASE_FILE:-}"

# ---- the backup: complete and intact ----
[ -f "$FROM/MANIFEST" ] || { echo "$FROM/MANIFEST absent : ce n'est pas une sauvegarde complète (make backup)" >&2; exit 1; }
(cd "$FROM" && grep -E '^[0-9a-f]{64}  ' MANIFEST | sha256sum --quiet -c -) ||
  { echo "Sauvegarde altérée : une empreinte de $FROM/MANIFEST ne correspond plus" >&2; exit 1; }
DATABASES=$(sed -n 's/^databases=//p' "$FROM/MANIFEST")
echo "Sauvegarde $FROM : $(sed -n 's/^date=//p' "$FROM/MANIFEST"), version $(sed -n 's/^version=//p' "$FROM/MANIFEST"), mode $(sed -n 's/^mode=//p' "$FROM/MANIFEST"), intacte"

WORK=$(mktemp -d)
chmod 700 "$WORK"
trap 'find "$WORK" -type f -exec shred -u {} + 2>/dev/null; rm -rf "$WORK"' EXIT
mkdir "$WORK/secrets" "$WORK/config"
if ls "$FROM"/*.enc >/dev/null 2>&1 && ! command -v openssl >/dev/null; then
  echo "Sauvegarde chiffrée et openssl introuvable : dnf install openssl" >&2; exit 1
fi
unpack() {  # archive (without .enc) directory: decrypted first when the backup is encrypted
  if [ -f "$FROM/$1.enc" ]; then
    [ -n "$PASSPHRASE" ] && [ -s "$PASSPHRASE" ] || { echo "Sauvegarde chiffrée : B2S_BACKUP_PASSPHRASE_FILE=<fichier de la phrase de passe>" >&2; exit 1; }
    openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass "file:$PASSPHRASE" -in "$FROM/$1.enc" 2>/dev/null | tar -xzf - -C "$2" 2>/dev/null ||
      { echo "$1.enc illisible : phrase de passe fausse ?" >&2; exit 1; }
  else
    tar -xzf "$FROM/$1" -C "$2"
  fi
}
unpack secrets.tar.gz "$WORK/secrets"
unpack config.tar.gz "$WORK/config"
[ -s "$WORK/secrets/b2s_master_key" ] || { echo "La sauvegarde n'a pas la clé b2s_master_key" >&2; exit 1; }

act() { if [ "$DO" = 1 ]; then "$@"; else echo "  (à faire) $*"; fi; }

# ---- .env first: it says the mode and the databases ----
if [ ! -f .env ]; then
  echo "- .env : celui de la sauvegarde (ce serveur n'en a pas)"
  act install -m 0600 "$WORK/config/.env" .env
elif ! cmp -s .env "$WORK/config/.env"; then
  echo "- .env : celui de ce serveur est gardé ; celui de la sauvegarde va dans .env.from-backup (à comparer)"
  act install -m 0600 "$WORK/config/.env" .env.from-backup
fi
[ -f .env ] || cp "$WORK/config/.env" "$WORK/env.preview"
. scripts/lib.sh
if [ ! -f .env ]; then env_value() { local v; v="$(grep -E "^$1=" "$WORK/env.preview" | tail -1 | cut -d= -f2- || true)"; printf '%s' "${v:-${2:-}}"; }; fi
MODE=$(deploy_mode)

# ---- secrets ----
put_secret() {  # name file
  if [ "$MODE" = native ]; then
    as_root install -d -m 0700 "$NATIVE_SECRETS"
    as_root install -m 0400 "$2" "$NATIVE_SECRETS/$1"
  else
    cat "$2" | podman secret create --replace "$1" - >/dev/null
  fi
}
for file in "$WORK/secrets"/b2s_*; do
  name=$(basename "$file")
  if [ "$name" = b2s_master_key ]; then
    echo "- secret b2s_master_key : celui de la sauvegarde (il chiffre les mots de passe des données restaurées)"
    act put_secret "$name" "$file"
  elif has_secret "$name"; then
    echo "- secret $name : celui de ce serveur est gardé"
  else
    echo "- secret $name : celui de la sauvegarde (absent ici)"
    act put_secret "$name" "$file"
  fi
done

# ---- certificates of the worker ----
if [ "$MODE" = native ]; then
  if [ -d "$WORK/config/etc/b2s/certs" ] && ! as_root test -d /etc/b2s/certs; then
    echo "- certificats du worker : /etc/b2s/certs, ceux de la sauvegarde"
    act as_root sh -c "mkdir -p /etc/b2s && cp -a '$WORK/config/etc/b2s/certs' /etc/b2s/"
  fi
elif [ -d "$WORK/config/capsule-runner/certs" ]; then
  for file in "$WORK/config/capsule-runner/certs"/*; do
    [ -e "capsule-runner/certs/$(basename "$file")" ] && continue
    echo "- certificat du worker : capsule-runner/certs/$(basename "$file"), celui de la sauvegarde"
    act install -m 0600 "$file" "capsule-runner/certs/$(basename "$file")"
  done
fi

# ---- databases: the services stopped, then each one replaced ----
MIGRATE_USER="$(env_value DB_MIGRATE_USER b2s_migrate)"
echo "- services arrêtés pendant la restauration des bases"
if [ "$MODE" = native ]; then
  act as_root systemctl stop borntoshare.target
else
  COMPOSE="podman-compose -f podman-compose.yml"
  [ "$MODE" = hybrid ] && COMPOSE="$COMPOSE -f podman-compose.hybrid.yml"
  # shellcheck disable=SC2086
  act sh -c "$COMPOSE --profile fives stop >/dev/null 2>&1 || true"
fi
for db in $DATABASES; do
  echo "- base $db sur $(env_value DB_HOST) : remplacée par celle de la sauvegarde"
  if [ "$DO" = 1 ]; then
    # LOCK TABLES of the backups made before --skip-add-locks: the migration account may not lock
    gzip -dc "$FROM/$db.sql.gz" | sed -E '/^(UN)?LOCK TABLES/d' | b2s_db b2s_db_migrate "$MIGRATE_USER" mariadb "$db" ||
      { echo "Restauration de $db échouée (la base et le compte $MIGRATE_USER existent-ils ? make wizard sur un nouveau serveur)." >&2
        echo "Les services restent arrêtés : corriger, puis relancer CONFIRM=yes make restore FROM=$FROM" >&2; exit 1; }
  fi
done

if [ "$DO" = 0 ]; then
  echo ""
  echo "Rien n'a été restauré. Pour restaurer : CONFIRM=yes make restore FROM=$FROM"
  exit 0
fi

# ---- the services, on the restored data (packs replayed: a backup of an earlier version is brought up to date) ----
echo "- déploiement sur les données restaurées (make deploy)"
FORCE=1 scripts/deploy.sh
echo "Restauration terminée. Vérifier : un test d'annuaire réussit (il prouve que la clé correspond aux mots de passe)."
