#!/bin/bash
# Installs the databases of the 5S module on the MariaDB server of BornToShare (idempotent: can be run again).
#   DB_ADMIN_USER=root DB_ADMIN_PASSWORD_FILE=/path/to/0600-file scripts/modules/fives/install.sh
# - creates b2s_fives and b2s_fives_inventory, and the account FIVES_DB_USER (rights on these two databases only);
# - the password of that account is generated once and written in .env (FIVES_DB_PASSWORD), never shown.
# At the first installation, the wizard (make wizard) creates them instead, with the license.
# The administrator password is read from a file (0600), never from the command line.
set -euo pipefail
cd "$(dirname "$0")/../../.."

env_value() { grep -E "^$1=" .env | cut -d= -f2- | sed 's/^"//; s/"$//' || true; }
: "${DB_ADMIN_USER:?DB_ADMIN_USER is required (an administrator of the MariaDB server)}"
: "${DB_ADMIN_PASSWORD_FILE:?DB_ADMIN_PASSWORD_FILE is required (a file holding its password, mode 0600)}"
[ -r "$DB_ADMIN_PASSWORD_FILE" ] || { echo "Cannot read $DB_ADMIN_PASSWORD_FILE" >&2; exit 1; }
HOST="$(env_value FIVES_DB_HOST)"; HOST="${HOST:-$(env_value DB_HOST)}"
PORT="$(env_value DB_PORT)"; PORT="${PORT:-3306}"
USER_NAME="$(env_value FIVES_DB_USER)"; USER_NAME="${USER_NAME:-b2s_fives}"
FIVES_DB="$(env_value FIVES_DB_NAME)"; FIVES_DB="${FIVES_DB:-b2s_fives}"
INVENTORY_DB="$(env_value FIVES_INVENTORY_DB_NAME)"; INVENTORY_DB="${INVENTORY_DB:-b2s_fives_inventory}"

if [ -z "$(env_value FIVES_DB_PASSWORD)" ]; then
  GENERATED="$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 32)"
  if grep -qE '^FIVES_DB_PASSWORD=' .env; then
    sed -i "s/^FIVES_DB_PASSWORD=.*/FIVES_DB_PASSWORD=$GENERATED/" .env   # the empty line of .env.example
  else
    printf '\n# Module 5S: account of its databases (scripts/modules/fives/install.sh)\nFIVES_DB_PASSWORD=%s\n' "$GENERATED" >> .env
  fi
  unset GENERATED
  echo "FIVES_DB_PASSWORD generated in .env"
fi
FIVES_PASSWORD="$(env_value FIVES_DB_PASSWORD)"

SQL=$(mktemp); chmod 600 "$SQL"; trap 'rm -f "$SQL"' EXIT
cat > "$SQL" <<SQL
CREATE DATABASE IF NOT EXISTS \`$FIVES_DB\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS \`$INVENTORY_DB\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '$USER_NAME'@'%' IDENTIFIED BY '$FIVES_PASSWORD';
ALTER USER '$USER_NAME'@'%' IDENTIFIED BY '$FIVES_PASSWORD';
GRANT ALL PRIVILEGES ON \`$FIVES_DB\`.* TO '$USER_NAME'@'%';
GRANT ALL PRIVILEGES ON \`$INVENTORY_DB\`.* TO '$USER_NAME'@'%';
FLUSH PRIVILEGES;
SQL

podman run --rm -i -e MYSQL_PWD="$(cat "$DB_ADMIN_PASSWORD_FILE")" docker.io/library/mariadb:11.4 \
  mariadb --skip-ssl -h "$HOST" -P "$PORT" -u "$DB_ADMIN_USER" < "$SQL"
echo "Module 5S databases ready: $FIVES_DB, $INVENTORY_DB (account $USER_NAME). Next: make deploy (starts fives-service)."
