#!/bin/bash
# Saves the two databases of this host: make backup [directory]. The key of the secrets stays out of it: keep B2S_SECRET_MASTER_KEY elsewhere.
# Restore: see docs/infrastructure.md. The owner of the views is left out: their creator may not exist on the target server.
set -euo pipefail
cd "$(dirname "$0")/.."
env_value() { grep -E "^$1=" .env | cut -d= -f2- | sed 's/^"//; s/"$//'; }
TARGET="${1:-backups/$(date +%Y%m%d-%H%M%S)}"
umask 077
mkdir -p "$TARGET"
for db in "$(env_value DB_NAME)" "$(env_value LOGGING_DB_NAME)"; do
  podman run --rm -e MYSQL_PWD="$(env_value DB_PASSWORD)" docker.io/library/mariadb:11.4 mariadb-dump --skip-ssl \
    -h "$(env_value DB_HOST)" -u "$(env_value DB_USER)" --single-transaction --routines "$db" \
    | sed -E 's/DEFINER=`[^`]+`@`[^`]+`//' | gzip > "$TARGET/$db.sql.gz"
  gzip -dc "$TARGET/$db.sql.gz" | tail -1 | grep -q "Dump completed" || { echo "Incomplete dump: $db" >&2; exit 1; }
  echo "$TARGET/$db.sql.gz"
done
