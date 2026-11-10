#!/bin/bash
# Adds the 5S module to an installation made without it (idempotent: can be run again). At the first installation the
# wizard (make wizard) does the same, with the license.
#   DB_ADMIN_USER=root DB_ADMIN_PASSWORD_FILE=/path/to/0600-file scripts/modules/fives/install.sh
# - creates b2s_fives and b2s_fives_inventory, and the account FIVES_DB_USER: read and write on them only;
# - gives the migration account (DB_MIGRATE_USER) the schema rights on them, and applies their tables;
# - generates the password of the module account into the podman secret b2s_db_fives, never shown.
# Then: make deploy (starts the module), and the license in Réglages avancés › Fonctionnalités.
# The administrator password is read from a file (0600), never from the command line, and used for this run only.
set -euo pipefail
cd "$(dirname "$0")/../../.."
. scripts/lib.sh

: "${DB_ADMIN_USER:?DB_ADMIN_USER is required (an administrator of the MariaDB server)}"
: "${DB_ADMIN_PASSWORD_FILE:?DB_ADMIN_PASSWORD_FILE is required (a file holding its password, mode 0600)}"
[ -r "$DB_ADMIN_PASSWORD_FILE" ] || { echo "Cannot read $DB_ADMIN_PASSWORD_FILE" >&2; exit 1; }
USER_NAME="$(env_value FIVES_DB_USER)"; USER_NAME="${USER_NAME:-b2s_fives}"
MIGRATE_USER="$(env_value DB_MIGRATE_USER)"; MIGRATE_USER="${MIGRATE_USER:-b2s_migrate}"
FIVES_DB="$(env_value FIVES_DB_NAME)"; FIVES_DB="${FIVES_DB:-b2s_fives}"
INVENTORY_DB="$(env_value FIVES_INVENTORY_DB_NAME)"; INVENTORY_DB="${INVENTORY_DB:-b2s_fives_inventory}"

# The administrator password as a temporary podman secret (removed at the end), like the others
ADMIN_SECRET="b2s_tmp_admin_$$"
podman secret create "$ADMIN_SECRET" "$DB_ADMIN_PASSWORD_FILE" >/dev/null
SQL=$(mktemp); chmod 600 "$SQL"
trap 'rm -f "$SQL"; podman secret rm "$ADMIN_SECRET" >/dev/null 2>&1 || true' EXIT

# The password of the module account: kept when the secret exists, generated otherwise
if ! has_secret b2s_db_fives; then
  head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 40 | podman secret create b2s_db_fives - >/dev/null
  echo "secret b2s_db_fives: generated"
fi
FIVES_PASSWORD="$(podman secret inspect --showsecret --format '{{.SecretData}}' b2s_db_fives)"
cat > "$SQL" <<SQL
CREATE DATABASE IF NOT EXISTS \`$FIVES_DB\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS \`$INVENTORY_DB\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '$USER_NAME'@'%' IDENTIFIED BY '$FIVES_PASSWORD';
ALTER USER '$USER_NAME'@'%' IDENTIFIED BY '$FIVES_PASSWORD';
REVOKE ALL PRIVILEGES, GRANT OPTION FROM '$USER_NAME'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON \`$FIVES_DB\`.* TO '$USER_NAME'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON \`$INVENTORY_DB\`.* TO '$USER_NAME'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, INDEX, REFERENCES, CREATE VIEW, SHOW VIEW ON \`$FIVES_DB\`.* TO '$MIGRATE_USER'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, INDEX, REFERENCES, CREATE VIEW, SHOW VIEW ON \`$INVENTORY_DB\`.* TO '$MIGRATE_USER'@'%';
FLUSH PRIVILEGES;
SQL
unset FIVES_PASSWORD
b2s_db "$ADMIN_SECRET" "$DB_ADMIN_USER" mariadb < "$SQL"

# Their tables, with the migration account
for pack in wizard-ui/backend/app/sql/fives/*.sql; do b2s_db b2s_db_migrate "$MIGRATE_USER" mariadb "$FIVES_DB" < "$pack" >/dev/null; done
for pack in wizard-ui/backend/app/sql/fives_inventory/*.sql; do b2s_db b2s_db_migrate "$MIGRATE_USER" mariadb "$INVENTORY_DB" < "$pack" >/dev/null; done
echo "Module 5S databases ready: $FIVES_DB, $INVENTORY_DB (account $USER_NAME). Next: make deploy (starts fives-service)."
