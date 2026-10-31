#!/bin/bash
# Deploys the working copy on this host: database packs (idempotent), rollback point, build, recreate.
#   make deploy
set -euo pipefail
cd "$(dirname "$0")/.."
TS=$(date +%Y%m%d-%H%M%S)
SERVICES="secret-broker core-service frontend-service capsule-runner auth-service"
PACKS="135_access_expiry_schedule 136_storage_root_acl_exceptions 137_close_phantom_revoke_requests 138_tag_family 139_access_request_permission_change 140_identity_source_ldap_settings 141_secret_items"

env_value() { grep -E "^$1=" .env | cut -d= -f2- | sed 's/^"//; s/"$//'; }

echo "1/4 database: $PACKS"
for pack in $PACKS; do
  podman run --rm -i -e MYSQL_PWD="$(env_value DB_PASSWORD)" docker.io/library/mariadb:11.4 mariadb --skip-ssl \
    -h "$(env_value DB_HOST)" -u "$(env_value DB_USER)" "$(env_value DB_NAME)" \
    < "wizard-ui/backend/app/sql/schema/$pack.sql"
done

echo "2/4 rollback point: rollback-$TS"
for s in $SERVICES; do
  podman tag "localhost/b2s-$s:latest" "localhost/b2s-$s:rollback-$TS"
done

echo "3/4 build + recreate: $SERVICES"
podman-compose -f podman-compose.yml build $SERVICES
podman-compose -f podman-compose.yml up -d --force-recreate --no-deps $SERVICES

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
  podman-compose -f podman-compose.yml up -d --force-recreate --no-deps $SERVICES
ROLLBACK
