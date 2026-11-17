#!/bin/bash
# Deploys the working copy on this host, the way the wizard chose (B2S_DEPLOY_MODE in .env):
#   containers  every service and the web interface in Podman (the default, installations from before)
#   hybrid      the services in Podman; the web interface a Node.js service behind httpd, here or on an annex server
#   native      every service a systemd unit (scripts/native/install-services.sh); the interface behind httpd
# Phases: secrets, database packs (idempotent), rollback point, services, web interface, firewall, settings of the
# wizard (e-mail, syslog), check. Their list is printed first (« PHASES: … ») and each one as « N/T name »: the last
# screen of the wizard follows them. A phase that needs root without sudo says the command to run, then make deploy.
#   make deploy
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/lib.sh
TS=$(date +%Y%m%d-%H%M%S)
MODE=$(deploy_mode)
case "$MODE" in containers|hybrid|native) ;; *) echo "B2S_DEPLOY_MODE inconnu : $MODE (containers, hybrid, native)" >&2; exit 1 ;; esac
WEB=""
[ "$MODE" != containers ] && WEB=$(web_location)

PHASES=(secrets database rollback services)
[ -n "$WEB" ] && PHASES+=("web")
[ "$WEB" = annex ] && PHASES+=("firewall")
[ -f secrets/.post-install.json ] && PHASES+=("settings")
PHASES+=("check")
LABEL_secrets="Secrets"; LABEL_database="Paquets SQL"; LABEL_rollback="Point de retour"; LABEL_services="Services"
LABEL_web="Interface web"; LABEL_firewall="Pare-feu"; LABEL_settings="Messagerie et syslog"; LABEL_check="Vérification"
labels=(); for p in "${PHASES[@]}"; do v="LABEL_$p"; labels+=("${!v}"); done
(IFS='|'; echo "PHASES: ${labels[*]}")
phase() {  # phase key detail
  local i
  for i in "${!PHASES[@]}"; do [ "${PHASES[$i]}" = "$1" ] && break; done
  local v="LABEL_$1"
  echo "$((i + 1))/${#PHASES[@]} ${!v}${2:+ : $2}"
}

# ---- secrets --------------------------------------------------------------------------------------------------
phase secrets "$MODE"
if [ "$MODE" = native ]; then as_root scripts/native/install-services.sh secrets; else scripts/secrets.sh; fi

SERVICES="core-service capsule-runner auth-service"
[ "$MODE" = containers ] && SERVICES="core-service frontend-service capsule-runner auth-service"
COMPOSE="podman-compose -f podman-compose.yml"
[ "$MODE" = hybrid ] && COMPOSE="$COMPOSE -f podman-compose.hybrid.yml"
FIVES=""
if has_secret b2s_db_fives; then
  FIVES=1
  SERVICES="$SERVICES fives-service fives-scanner"
  COMPOSE="${COMPOSE/podman-compose /podman-compose --profile fives }"
  # The Parquet lake of the module, when .env says where it is (B2S_LAKE_URI): same image as fives-service
  if [ -n "$(env_value B2S_LAKE_URI)" ]; then
    LAKE=1
    COMPOSE="${COMPOSE/podman-compose /podman-compose --profile lake }"
    # On an S3 store: its keys, podman secrets, mounted in fives-lake
    if has_secret b2s_lake_s3_access && has_secret b2s_lake_s3_secret; then COMPOSE="$COMPOSE -f podman-compose.lake-s3.yml"; fi
  fi
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

# ---- database packs ---------------------------------------------------------------------------------------------
# Schema changes with the migration account only (the accounts of the services only read and write)
MIGRATE_USER="$(env_value DB_MIGRATE_USER b2s_migrate)"
PACKS="135_access_expiry_schedule 136_storage_root_acl_exceptions 137_close_phantom_revoke_requests 138_tag_family 139_access_request_permission_change 140_identity_source_ldap_settings 141_secret_items 142_worker_agent_token 143_identity_source_flavor 144_integrity 145_dfs_read_schedule 146_access_request_justification 147_extensions 148_notification_log 149_storage_root_sensitivity 150_governance_policies 151_policy_jobs 152_sensitivity_ignores 153_guardian_substitutes 154_storage_root_quotas 155_content_history_remediations 156_folder_scans_duplicates 157_licenses_features 158_scan_progress 159_simplify_tables 160_auto_tags 161_user_notifications 162_folder_tags 163_local_password_change 164_access_reviews 165_request_item_target_index"
# Views whose definition changed since the installation: replayed too (CREATE OR REPLACE)
VIEWS="141_views_workflow 141_views_naming_policy_effective 142_views_zone_policy"
phase database "compte $MIGRATE_USER${FIVES:+, module 5S}"
# One pack: tried again up to 3 times when the client container could not start (rootless network of podman:
# « pasta failed », seen once in a while); a pack is idempotent, so a second try is safe. An SQL error stops at once.
apply_pack() {  # database file
  local try out
  for try in 1 2 3; do
    if out=$(B2S_DB_SERVER=$(db_server_for "$1") b2s_db b2s_db_migrate "$MIGRATE_USER" mariadb "$1" < "$2" 2>&1 >/dev/null); then return 0; fi
    case "$out" in *"pasta failed"*|*"netlink"*) echo "  $(basename "$2"): conteneur client non démarré (essai $try), nouvel essai" >&2; sleep 2 ;; *) echo "$out" >&2; return 1 ;; esac
  done
  echo "$out" >&2; return 1
}
for pack in $PACKS; do apply_pack "$(env_value DB_NAME borntoshare)" "wizard-ui/backend/app/sql/schema/$pack.sql"; done
for view in $VIEWS; do apply_pack "$(env_value DB_NAME borntoshare)" "wizard-ui/backend/app/sql/views/$view.sql"; done
if [ -n "$FIVES" ]; then
  FIVES_DB="$(env_value FIVES_DB_NAME)"; INVENTORY_DB="$(env_value FIVES_INVENTORY_DB_NAME)"
  for pack in wizard-ui/backend/app/sql/fives/*.sql; do apply_pack "${FIVES_DB:-b2s_fives}" "$pack"; done
  for pack in wizard-ui/backend/app/sql/fives_inventory/*.sql; do apply_pack "${INVENTORY_DB:-b2s_fives_inventory}" "$pack"; done
fi

# Shown in the menu of the application: commit and date of this deploy
export B2S_VERSION="$(git describe --always --dirty 2>/dev/null || echo unknown) · $(date +%Y-%m-%d)"

# ---- rollback point ---------------------------------------------------------------------------------------------
if [ "$MODE" = native ]; then
  phase rollback "le code en service devient /opt/borntoshare/app/<service>.previous"
else
  phase rollback "rollback-$TS"
  for s in $SERVICES; do
    podman tag "localhost/b2s-$s:latest" "localhost/b2s-$s:rollback-$TS" 2>/dev/null || echo "  (no image yet for $s)"
  done
  # Only the last 3 rollback points of each service are kept (each deploy left one more: 25 GB of images after 170)
  KEEP_ROLLBACKS=${KEEP_ROLLBACKS:-3}
  for s in $SERVICES; do
    # « podman untag IMAGE NAME »: only this name goes (« podman untag NAME » alone removes every name of the image,
    # :latest too when it is the same image)
    { podman images --format '{{.Repository}}:{{.Tag}}' | grep "^localhost/b2s-$s:rollback-" || true; } | sort -u -r | tail -n +$((KEEP_ROLLBACKS + 1)) |
      while read -r old; do podman untag "$old" "$old" >/dev/null 2>&1 || true; done
  done
fi

# ---- services -----------------------------------------------------------------------------------------------------
if [ "$MODE" = native ]; then
  phase services "unités systemd"
  as_root scripts/native/install-services.sh services
else
  phase services "build + recreate: $SERVICES"
  # The ports of the services: on this host only, or open to the annex web server (then filtered by the firewall)
  export B2S_API_BIND=127.0.0.1
  [ "$WEB" = annex ] && export B2S_API_BIND=0.0.0.0
  $COMPOSE build $SERVICES
  # The scanner of earlier versions had a fixed name: replaced by its instances (no fixed name, FIVES_SCANNERS)
  if [ -n "$FIVES" ] && podman container exists fives-scanner 2>/dev/null; then
    podman stop fives-scanner >/dev/null && podman container rm fives-scanner >/dev/null && echo "  ancien conteneur fives-scanner remplacé par ses instances"
  fi
  # The job queue is not rebuilt, but nothing works without it (recreated: its password is a secret, its data a volume)
  $COMPOSE up -d --force-recreate --no-deps redis
  # The scanners of the 5S: FIVES_SCANNERS instances (environment, else .env, else 1)
  SCALE=""
  WANTED=${FIVES_SCANNERS:-$(env_value FIVES_SCANNERS 1)}
  [ -n "$FIVES" ] && SCALE="--scale fives-scanner=$WANTED"
  $COMPOSE up -d --force-recreate --no-deps $SCALE $SERVICES
  # Fewer scanners than before: --scale does not remove the extra instances (they would keep the old image and keep
  # taking scans). Stopped gracefully: a scan in progress is taken again by another instance (heartbeat, backoff).
  if [ -n "$FIVES" ]; then
    for name in $(podman ps -a --format '{{.Names}}' | grep -E '_fives-scanner_[0-9]+$' || true); do
      if [ "${name##*_}" -gt "$WANTED" ]; then
        podman stop "$name" >/dev/null && podman rm "$name" >/dev/null && echo "  $name retiré (FIVES_SCANNERS=$WANTED)"
      fi
    done
  fi
  if [ -n "${LAKE:-}" ]; then $COMPOSE up -d --force-recreate --no-deps fives-lake; fi
  # Podman as root with firewalld: netavark trusts only the networks that are not internal; the DNS of the internal
  # ones (b2s-jobs, b2s-data), answered by the host on their gateway, falls in the default zone and is refused. Every
  # name lookup then waits for that server (5 s) before asking the next one: calls between services time out now and
  # then. Port 53 only, from these networks to this host: nothing else is opened, they stay internal.
  if [ "$(id -u)" = 0 ] && systemctl is-active -q firewalld 2>/dev/null; then
    for net in b2s-jobs b2s-data; do
      subnet=$(podman network inspect "$net" --format '{{range .Subnets}}{{.Subnet}} {{end}}' 2>/dev/null | awk '{print $1}')
      [ -n "$subnet" ] || continue
      for proto in udp tcp; do
        rule="rule family=\"ipv4\" source address=\"$subnet\" port port=\"53\" protocol=\"$proto\" accept"
        for scope in --permanent ""; do
          # shellcheck disable=SC2086
          firewall-cmd -q $scope --query-rich-rule="$rule" || firewall-cmd -q $scope --add-rich-rule="$rule"
        done
      done
    done
    echo "  firewalld : DNS des réseaux internes de podman autorisé (port 53 seulement)"
  fi
  # Hybrid: the container of the interface of an earlier installation in containers is stopped (httpd replaces it)
  if [ "$MODE" = hybrid ] && podman container exists frontend-service; then
    podman stop frontend-service >/dev/null && echo "  conteneur frontend-service arrêté : l'interface passe par httpd"
  fi
fi

# ---- web interface (hybrid, native) -------------------------------------------------------------------------------
if [ -n "$WEB" ]; then
  phase web "$([ "$WEB" = annex ] && echo "serveur annexe $(env_value B2S_WEB_HOST)" || echo "ce serveur")"
  scripts/web/build-web.sh
  if [ "$WEB" = local ]; then
    as_root dist/borntoshare-web/install-web.sh
  elif [ "$(env_value B2S_WEB_PUSH ssh)" = ssh ]; then
    scripts/web/push-web.sh
  else
    echo "  à installer sur $(env_value B2S_WEB_HOST) : copier dist/borntoshare-web.tar.gz, puis tar -xzf borntoshare-web.tar.gz && sudo borntoshare-web/install-web.sh"
  fi
  # The package holds the token of the services: kept only when it must be copied by hand
  if [ "$WEB" = local ] || [ "$(env_value B2S_WEB_PUSH ssh)" = ssh ]; then rm -rf dist/borntoshare-web; fi
fi
if [ "$WEB" = annex ]; then
  phase firewall "ports des services ouverts à $(env_value B2S_WEB_IP)"
  as_root scripts/web/firewall.sh
fi

# ---- check -------------------------------------------------------------------------------------------------------
wait_healthy() {
  if [ "$MODE" = native ]; then
    local port
    for port in "$(env_value B2S_AUTH_PORT 8101)" "$(env_value B2S_CORE_PORT 8102)"; do
      for _ in $(seq 1 40); do curl -sf -o /dev/null "http://127.0.0.1:$port/health" && break; sleep 3; done
      curl -sf -o /dev/null "http://127.0.0.1:$port/health" || { echo "Le service du port $port ne répond pas : journalctl -u 'b2s-*'" >&2; return 1; }
    done
    systemctl --no-pager --plain list-units 'b2s-*' | grep -E '^b2s-' || true
    return 0
  fi
  local pattern unhealthy
  # A service by its name, or its instances (« <project>_fives-scanner_2 »: no fixed name, several of them)
  pattern="^([a-z0-9-]+_)?($(echo "$SERVICES" | tr ' ' '|'))(_[0-9]+)? "
  for _ in $(seq 1 40); do
    sleep 5
    unhealthy=$(podman ps --format '{{.Names}} {{.Status}}' | grep -E "$pattern" | grep -vc "(healthy)" || true)
    [ "$unhealthy" = "0" ] && break
  done
  podman ps --format '{{.Names}}  {{.Status}}' | grep -E "$pattern"
  [ "$unhealthy" = "0" ] || { echo "Des services ne sont pas sains : make logs" >&2; return 1; }
}

if [ -f secrets/.post-install.json ]; then
  wait_healthy
  phase settings "enregistrés par le core"
  scripts/post-install.sh
fi

phase check "$MODE"
wait_healthy
# Images without a name, after a week only: the build stages (the Kerberos wheels compiled with gcc, minutes) stay in
# the cache for the next deployments
[ "$MODE" != native ] && { podman image prune -f --filter until=168h >/dev/null 2>&1 || true; }

if [ "$MODE" = native ]; then
  cat <<ROLLBACK

Rollback:
  for d in /opt/borntoshare/app/*.previous; do sudo rm -rf "\${d%.previous}" && sudo mv "\$d" "\${d%.previous}"; done
  sudo systemctl restart borntoshare.target
ROLLBACK
else
  cat <<ROLLBACK

Rollback:
  for s in $SERVICES; do podman tag localhost/b2s-\$s:rollback-$TS localhost/b2s-\$s:latest; done
  # The job queue is not rebuilt, but nothing works without it
$COMPOSE up -d --no-deps redis
$COMPOSE up -d --force-recreate --no-deps $SERVICES
ROLLBACK
fi
