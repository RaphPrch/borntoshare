#!/bin/bash
# Deploys the working copy on this host: secrets, database packs (idempotent), rollback point, build, recreate.
#   make deploy
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/lib.sh
TS=$(date +%Y%m%d-%H%M%S)

echo "0/4 secrets"
scripts/secrets.sh

SERVICES="core-service frontend-service capsule-runner auth-service"
# The 5S module runs once its databases are installed (the wizard: secret b2s_db_fives)
COMPOSE="podman-compose -f podman-compose.yml"
FIVES=""
if has_secret b2s_db_fives; then
  FIVES=1
  SERVICES="$SERVICES fives-service fives-scanner"
  COMPOSE="podman-compose --profile fives -f podman-compose.yml"
fi
# A 5S measure running would be cut by the restart (its walk is lost, its result may not reach the core): wait
# for it, or FORCE=1 make deploy (the scanner queues the interrupted measure again at its start)
if [ -n "$FIVES" ] && [ "${FORCE:-0}" != "1" ]; then
  running=$(echo "SELECT COUNT(*) FROM scan_runs WHERE status = 'running'" \
    | b2s_db b2s_db_fives "$(env_value FIVES_DB_USER b2s_fives)" mariadb -N "$(env_value FIVES_DB_NAME b2s_fives)" 2>/dev/null || echo 0)
  if [ "${running:-0}" -gt 0 ]; then
    echo "Une mesure 5S est en cours ($running) : le déploiement la couperait. Attendez sa fin, ou relancez avec FORCE=1 make deploy." >&2
    exit 2
  fi
fi
# Schema changes with the migration account only (the accounts of the services only read and write)
MIGRATE_USER="$(env_value DB_MIGRATE_USER b2s_migrate)"
PACKS="135_access_expiry_schedule 136_storage_root_acl_exceptions 137_close_phantom_revoke_requests 138_tag_family 139_access_request_permission_change 140_identity_source_ldap_settings 141_secret_items 142_worker_agent_token 143_identity_source_flavor 144_integrity 145_dfs_read_schedule 146_access_request_justification 147_extensions 148_notification_log 149_storage_root_sensitivity 150_governance_policies 151_policy_jobs 152_sensitivity_ignores 153_guardian_substitutes 154_storage_root_quotas 155_content_history_remediations 156_folder_scans_duplicates 157_licenses_features 158_scan_progress 159_simplify_tables 160_auto_tags 161_user_notifications"
# Views whose definition changed since the installation: replayed too (CREATE OR REPLACE)
VIEWS="141_views_workflow 141_views_naming_policy_effective 142_views_zone_policy"

echo "1/4 database (account $MIGRATE_USER): $PACKS, views $VIEWS${FIVES:+, module 5S}"
for pack in $PACKS; do
  b2s_db b2s_db_migrate "$MIGRATE_USER" mariadb "$(env_value DB_NAME borntoshare)" < "wizard-ui/backend/app/sql/schema/$pack.sql" >/dev/null
done
for view in $VIEWS; do
  b2s_db b2s_db_migrate "$MIGRATE_USER" mariadb "$(env_value DB_NAME borntoshare)" < "wizard-ui/backend/app/sql/views/$view.sql" >/dev/null
done
if [ -n "$FIVES" ]; then
  FIVES_DB="$(env_value FIVES_DB_NAME)"; INVENTORY_DB="$(env_value FIVES_INVENTORY_DB_NAME)"
  for pack in wizard-ui/backend/app/sql/fives/*.sql; do b2s_db b2s_db_migrate "$MIGRATE_USER" mariadb "${FIVES_DB:-b2s_fives}" < "$pack" >/dev/null; done
  for pack in wizard-ui/backend/app/sql/fives_inventory/*.sql; do
    b2s_db b2s_db_migrate "$MIGRATE_USER" mariadb "${INVENTORY_DB:-b2s_fives_inventory}" < "$pack" >/dev/null
  done
fi

echo "2/4 rollback point: rollback-$TS"
for s in $SERVICES; do
  podman tag "localhost/b2s-$s:latest" "localhost/b2s-$s:rollback-$TS" 2>/dev/null || echo "  (no image yet for $s)"
done

# Shown in the menu of the application: commit and date of this deploy
export B2S_VERSION="$(git describe --always --dirty 2>/dev/null || echo unknown) · $(date +%Y-%m-%d)"
echo "3/4 build + recreate: $SERVICES"
$COMPOSE build $SERVICES
# The job queue is not rebuilt, but nothing works without it (recreated: its password is a secret, its data a volume)
$COMPOSE up -d --force-recreate --no-deps redis
$COMPOSE up -d --force-recreate --no-deps $SERVICES

echo "4/4 waiting for the services"
pattern="^($(echo "$SERVICES" | tr ' ' '|')) "
for _ in $(seq 1 40); do
  sleep 5
  unhealthy=$(podman ps --format '{{.Names}} {{.Status}}' | grep -E "$pattern" | grep -vc "(healthy)" || true)
  [ "$unhealthy" = "0" ] && break
done
podman ps --format '{{.Names}}  {{.Status}}' | grep -E "$pattern"

cat <<ROLLBACK

Rollback:
  for s in $SERVICES; do podman tag localhost/b2s-\$s:rollback-$TS localhost/b2s-\$s:latest; done
  # The job queue is not rebuilt, but nothing works without it
$COMPOSE up -d --no-deps redis
$COMPOSE up -d --force-recreate --no-deps $SERVICES
ROLLBACK
