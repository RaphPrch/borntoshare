#!/bin/bash
# Removes BornToShare from this server, the way it was installed (B2S_DEPLOY_MODE in .env): its services, its web
# interface (here or on the annex web server), the firewall rules it opened.
#   make uninstall                    says what would be removed, removes nothing
#   CONFIRM=yes make uninstall        removes it
#   CONFIRM=yes PURGE=1 make uninstall   also the secrets, the data of Redis, the images and the system accounts
#
# Never removed: the databases (on the MariaDB server: the SQL to drop them is printed), this working copy and its .env.
# Kept unless PURGE=1: the secrets, the key of the stored passwords (b2s_master_key) included. Without that key the
# passwords kept encrypted in the database can no longer be read: back it up before a purge. A later
# make deploy (or make wizard) reinstalls on the same databases.
set -uo pipefail
cd "$(dirname "$0")/.."
. scripts/lib.sh
MODE=$(deploy_mode)
WEB=""
[ "$MODE" != containers ] && WEB=$(web_location)
PURGE="${PURGE:-0}"
DO=0
[ "${CONFIRM:-}" = yes ] && DO=1

say() { echo "$*"; }
act() { if [ "$DO" = 1 ]; then "$@"; else echo "  (à faire) $*"; fi; }

if [ "$DO" = 0 ]; then
  say "Ce que la désinstallation retirerait (mode $MODE$([ -n "$WEB" ] && echo ", interface $WEB")), sans rien toucher :"
else
  say "Désinstallation de BornToShare (mode $MODE$([ "$PURGE" = 1 ] && echo ", avec purge"))"
fi

# ---- services -------------------------------------------------------------------------------------------------------
if [ "$MODE" = native ]; then
  units=$(systemctl list-unit-files --no-legend 'b2s-*.service' 'borntoshare.target' 2>/dev/null | awk '{print $1}' | grep -v '^b2s-web' | tr '\n' ' ')
  say "- services systemd : ${units:-aucun}"
  if [ -n "$units" ]; then
    # shellcheck disable=SC2086
    act as_root systemctl disable --now $units
    # shellcheck disable=SC2086
    act as_root sh -c "cd /etc/systemd/system && rm -f $units && systemctl daemon-reload"
  fi
  say "- code et environnements Python : /opt/borntoshare/app ; réglages : /etc/borntoshare/env, redis.conf"
  act as_root rm -rf /opt/borntoshare/app /etc/borntoshare/env /etc/borntoshare/redis.conf
else
  COMPOSE="podman-compose -f podman-compose.yml"
  [ "$MODE" = hybrid ] && COMPOSE="$COMPOSE -f podman-compose.hybrid.yml"
  say "- conteneurs et réseaux de BornToShare (podman-compose down)$([ "$PURGE" = 1 ] && echo ", avec le volume de Redis")"
  # Every profile, so that the 5S module and the wizard go too
  # shellcheck disable=SC2086
  act $COMPOSE --profile fives --profile wizard down $([ "$PURGE" = 1 ] && echo -v)
fi

# ---- web interface (hybrid, native) ----------------------------------------------------------------------------------
if [ "$WEB" = local ]; then
  say "- interface web de ce serveur : service b2s-web, vhost httpd, /opt/borntoshare/web"
  act as_root env PURGE="$PURGE" scripts/web/uninstall-web.sh
elif [ "$WEB" = annex ]; then
  HOST=$(env_value B2S_WEB_HOST)
  if [ "$(env_value B2S_WEB_PUSH ssh)" = ssh ]; then
    USER_NAME=$(env_value B2S_WEB_SSH_USER)
    KEY=$(env_value B2S_WEB_SSH_KEY "$HOME/.ssh/id_ed25519")
    KEY="${KEY/#\~/$HOME}"
    say "- interface web du serveur annexe $HOST (par SSH, $USER_NAME)"
    if [ "$DO" = 1 ]; then
      ssh -i "$KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 "$USER_NAME@$HOST" \
        "sudo -n env PURGE=$PURGE bash -s" < scripts/web/uninstall-web.sh ||
        echo "  l'annexe $HOST n'a pas pu être nettoyée : y lancer scripts/web/uninstall-web.sh en root" >&2
    else
      echo "  (à faire) ssh $USER_NAME@$HOST sudo bash -s < scripts/web/uninstall-web.sh"
    fi
  else
    say "- interface web du serveur annexe $HOST : y lancer, en root, scripts/web/uninstall-web.sh (copié avec le paquet)"
  fi
  # The ports of the services opened to the annex
  IP=$(env_value B2S_WEB_IP)
  if systemctl is-active -q firewalld 2>/dev/null && [ -n "$IP" ]; then
    say "- pare-feu : règles ouvrant les ports des services à $IP"
    for port in $(env_value B2S_AUTH_PORT 8101) $(env_value B2S_CORE_PORT 8102) $(env_value B2S_FIVES_PORT 8105); do
      act as_root firewall-cmd -q --permanent --remove-rich-rule="rule family=\"ipv4\" source address=\"$IP\" port port=\"$port\" protocol=\"tcp\" accept"
    done
    act as_root firewall-cmd -q --reload
  fi
fi

# ---- purge --------------------------------------------------------------------------------------------------------------
if [ "$PURGE" = 1 ]; then
  if [ "$MODE" = native ]; then
    say "- secrets /etc/borntoshare/secrets, données de Redis /var/lib/borntoshare, certificats /etc/b2s/certs, compte b2s"
    act as_root rm -rf /etc/borntoshare/secrets /var/lib/borntoshare /etc/b2s/certs
    act as_root sh -c 'id b2s >/dev/null 2>&1 && userdel b2s || true; rmdir /etc/borntoshare /opt/borntoshare /etc/b2s 2>/dev/null || true'
  else
    secrets=$(podman secret ls --format '{{.Name}}' 2>/dev/null | grep '^b2s_' | tr '\n' ' ')
    say "- secrets podman : ${secrets:-aucun}"
    # shellcheck disable=SC2086
    [ -n "$secrets" ] && act podman secret rm $secrets
    images=$(podman images --format '{{.Repository}}:{{.Tag}}' | grep -E '^localhost/b2s-' | tr '\n' ' ')
    say "- images : ${images:-aucune}"
    # shellcheck disable=SC2086
    [ -n "$images" ] && act podman rmi -f $images
  fi
else
  say "- conservés : les secrets (dont la clé b2s_master_key), les données de Redis, les images (PURGE=1 pour les retirer)"
fi

# ---- databases: never removed here ------------------------------------------------------------------------------------
dbs="$(env_value DB_NAME borntoshare) $(env_value LOGGING_DB_NAME)"
has_secret b2s_db_fives 2>/dev/null && dbs="$dbs $(env_value FIVES_DB_NAME) $(env_value FIVES_INVENTORY_DB_NAME)"
users="$(env_value DB_USER) $(env_value DB_MIGRATE_USER) $(env_value FIVES_DB_USER)"
say "- conservées : les bases sur $(env_value DB_HOST) ($(echo $dbs)). Pour les supprimer, un administrateur MariaDB :"
for db in $dbs; do echo "    DROP DATABASE \`$db\`;"; done
for user in $users; do echo "    DROP USER '$user'@'%';"; done

if [ "$DO" = 0 ]; then
  say ""
  say "Rien n'a été retiré. Pour désinstaller : CONFIRM=yes make uninstall (PURGE=1 en plus pour les secrets et les données)."
else
  say "BornToShare est retiré de ce serveur. Réinstaller sur les mêmes bases : make deploy (ou make wizard)."
fi
