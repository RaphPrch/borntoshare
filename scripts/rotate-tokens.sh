#!/bin/bash
# New values for the secrets BornToShare generated itself, then the services that read them restarted:
#   make rotate-tokens                      the token shared by the services (b2s_internal_token): nobody notices
#   make rotate-tokens WHICH=session CONFIRM=oui   the key of the session cookie (b2s_principal_key): EVERY person is
#                                           signed out (their cookie was signed with the old key) and signs in again
#   make rotate-tokens WHICH=all CONFIRM=oui       both
# Same for the three ways to install: podman secrets (containers, hybrid) or /etc/borntoshare/secrets (native, root);
# the web interface outside a container gets its copy (this host) or its package again (annex server). Never prints a value.
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/lib.sh

WHICH="${WHICH:-internal}"
case "$WHICH" in
  internal) NAMES="b2s_internal_token" ;;
  session) NAMES="b2s_principal_key" ;;
  all) NAMES="b2s_internal_token b2s_principal_key" ;;
  *) echo "WHICH=internal (défaut), session ou all" >&2; exit 2 ;;
esac
if [ "$WHICH" != internal ] && [ "${CONFIRM:-}" != oui ]; then
  echo "Changer la clé des sessions déconnecte toutes les personnes connectées. Relancer avec CONFIRM=oui." >&2
  exit 2
fi
MODE=$(deploy_mode)
WEB=""
[ "$MODE" != containers ] && WEB=$(web_location)

new_value() { head -c 64 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 48; }

for name in $NAMES; do
  if [ "$MODE" = native ]; then
    new_value | as_root sh -c "umask 077; cat > '$NATIVE_SECRETS/$name.new' && chown b2s:b2s '$NATIVE_SECRETS/$name.new' && chmod 0400 '$NATIVE_SECRETS/$name.new' && mv '$NATIVE_SECRETS/$name.new' '$NATIVE_SECRETS/$name'"
  else
    new_value | podman secret create --replace "$name" - >/dev/null
  fi
  echo "secret $name : nouvelle valeur"
done

# The services read their secrets at start: restarted (or recreated: a podman secret is copied into the container)
if [ "$MODE" = native ]; then
  # Every unit b2s-* is PartOf=borntoshare.target: restarted with it (b2s-web apart, below)
  as_root systemctl restart borntoshare.target
  echo "  services systemd redémarrés"
else
  COMPOSE="podman-compose -f podman-compose.yml"
  [ "$MODE" = hybrid ] && COMPOSE="$COMPOSE -f podman-compose.hybrid.yml"
  SERVICES="core-service capsule-runner auth-service"
  SCALE=""
  [ "$MODE" = containers ] && SERVICES="$SERVICES frontend-service"
  if has_secret b2s_db_fives; then
    SERVICES="$SERVICES fives-service fives-scanner"
    # As many scanners as now
    running=$(podman ps --format '{{.Names}}' | grep -c 'fives-scanner' || true)
    SCALE="--scale fives-scanner=${running/#0/1}"
    COMPOSE="${COMPOSE/podman-compose /podman-compose --profile fives }"
    if podman container exists fives-lake; then
      SERVICES="$SERVICES fives-lake"
      COMPOSE="${COMPOSE/podman-compose /podman-compose --profile lake }"
      if has_secret b2s_lake_s3_access && has_secret b2s_lake_s3_secret; then COMPOSE="$COMPOSE -f podman-compose.lake-s3.yml"; fi
    fi
  fi
  [ "$WEB" = annex ] && export B2S_API_BIND=0.0.0.0
  # shellcheck disable=SC2086
  $COMPOSE up -d --force-recreate --no-deps $SCALE $SERVICES >/dev/null
  echo "  conteneurs recréés : $SERVICES"
fi

# The web interface outside a container: its copy of the secrets
if [ "$WEB" = local ]; then
  for name in b2s_internal_token b2s_principal_key; do
    secret_value "$name" | as_root sh -c "umask 027; cat > /etc/borntoshare/web-secrets/$name.new && chown root:b2s-web /etc/borntoshare/web-secrets/$name.new && chmod 0440 /etc/borntoshare/web-secrets/$name.new && mv /etc/borntoshare/web-secrets/$name.new /etc/borntoshare/web-secrets/$name"
  done
  as_root systemctl restart b2s-web
  echo "  interface (b2s-web) : secrets copiés, redémarrée"
elif [ "$WEB" = annex ]; then
  scripts/web/build-web.sh
  if [ "$(env_value B2S_WEB_PUSH ssh)" = ssh ]; then
    scripts/web/push-web.sh
    rm -rf dist/borntoshare-web
  else
    echo "  à réinstaller sur $(env_value B2S_WEB_HOST) : dist/borntoshare-web.tar.gz (nouveaux secrets), puis sudo borntoshare-web/install-web.sh"
  fi
fi
case "$NAMES" in *b2s_internal_token*) echo "Workers installés sur un autre serveur : leur donner le nouveau jeton (docs/infrastructure.md, Workers)." ;; esac
[ "$WHICH" != internal ] && echo "Clé des sessions changée : chacun se reconnecte."
exit 0
