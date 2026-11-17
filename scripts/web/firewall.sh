#!/bin/bash
# The web interface on an annex server: the ports of auth, core (and 5S) of this server open to that server only
# (firewalld rich rules, permanent). Run as root by scripts/deploy.sh. Rules of an earlier address are removed.
set -euo pipefail
cd "$(dirname "$0")/../.."
. scripts/lib.sh

IP=$(env_value B2S_WEB_IP)
[[ "$IP" =~ ^[0-9a-fA-F.:]+$ ]] || { echo "B2S_WEB_IP absent ou invalide dans .env" >&2; exit 1; }
FAMILY=ipv4
[[ "$IP" == *:* ]] && FAMILY=ipv6
PORTS="$(env_value B2S_AUTH_PORT 8101) $(env_value B2S_CORE_PORT 8102)"
if has_secret b2s_db_fives; then PORTS="$PORTS $(env_value B2S_FIVES_PORT 8105)"; fi

if ! systemctl is-active -q firewalld; then
  echo "  firewalld inactif : les ports $PORTS sont ouverts à tous. À filtrer sur le pare-feu du réseau (seul $IP)." >&2
  exit 0
fi
# Each rule twice, permanent and at once, never « firewall-cmd --reload »: a reload drops the rules podman put for its
# networks (the services in containers no longer find each other by name)
for port in $PORTS; do
  # Earlier rules of BornToShare on this port (another annex address)
  for scope in --permanent ""; do
    # shellcheck disable=SC2086
    firewall-cmd $scope --list-rich-rules | grep -E "port port=\"$port\" protocol=\"tcp\" accept" | while read -r rule; do
      firewall-cmd -q $scope --remove-rich-rule="$rule"
    done
    # shellcheck disable=SC2086
    firewall-cmd -q $scope --add-rich-rule="rule family=\"$FAMILY\" source address=\"$IP\" port port=\"$port\" protocol=\"tcp\" accept"
  done
done
echo "  ports $PORTS ouverts à $IP seulement"
