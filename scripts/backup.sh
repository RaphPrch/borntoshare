#!/bin/bash
# Saves the databases of this host (BornToShare, its audit, the 5S module when installed): make backup [directory].
# With the migration account (secret b2s_db_migrate). The key of the stored passwords stays out of it: back up the
# secret b2s_master_key apart (scripts/secrets.sh says how).
# Restore: see docs/infrastructure.md. The owner of the views is left out: their creator may not exist on the target server.
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/lib.sh
TARGET="${1:-backups/$(date +%Y%m%d-%H%M%S)}"
MIGRATE_USER="$(env_value DB_MIGRATE_USER b2s_migrate)"
DATABASES="$(env_value DB_NAME borntoshare) $(env_value LOGGING_DB_NAME borntoshare_logging)"
if has_secret b2s_db_fives; then
  FIVES_DB="$(env_value FIVES_DB_NAME)"; INVENTORY_DB="$(env_value FIVES_INVENTORY_DB_NAME)"
  DATABASES="$DATABASES ${FIVES_DB:-b2s_fives} ${INVENTORY_DB:-b2s_fives_inventory}"
fi
umask 077
mkdir -p "$TARGET"
for db in $DATABASES; do
  b2s_db b2s_db_migrate "$MIGRATE_USER" mariadb-dump --single-transaction "$db" \
    | sed -E 's/DEFINER=`[^`]+`@`[^`]+`//' | gzip > "$TARGET/$db.sql.gz"
  gzip -dc "$TARGET/$db.sql.gz" | tail -1 | grep -q "Dump completed" || { echo "Incomplete dump: $db" >&2; exit 1; }
  echo "$TARGET/$db.sql.gz"
done
