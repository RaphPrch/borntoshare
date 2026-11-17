#!/bin/bash
# What this server offers for each way to install, read before the wizard opens (make wizard, make wizard-check):
# written to secrets/.host-check.json, shown by the step « Prérequis » of the wizard (it runs in a container and cannot
# look at the host). Reads only: installs nothing, changes nothing, never prints a password.
set -uo pipefail
cd "$(dirname "$0")/.."
install -d -m 700 secrets

version_of() { "$@" 2>/dev/null | head -1 | grep -oE '[0-9]+(\.[0-9]+)+' | head -1; }
has() { command -v "$1" >/dev/null 2>&1; }

PODMAN=$(has podman && version_of podman --version)
COMPOSE=$(has podman-compose && version_of podman-compose --version)
PYTHON_BIN=""
for candidate in python3.14 python3.13 python3.12 python3; do
  if has "$candidate" && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then PYTHON_BIN=$candidate; break; fi
done
PYTHON=$( [ -n "$PYTHON_BIN" ] && version_of "$PYTHON_BIN" --version )
PYTHON_ANY=$(has python3 && version_of python3 --version)
NODE=$(has node && version_of node --version)
HTTPD=$( (has httpd && version_of httpd -v) || true)
MOD_SSL=$( [ -e /etc/httpd/conf.modules.d/00-ssl.conf ] || [ -e /usr/lib64/httpd/modules/mod_ssl.so ] && echo yes)
REDIS=$( (has redis-server && version_of redis-server --version) || true)
MARIADB_CLIENT=$( (has mariadb && version_of mariadb --version) || true)
FIREWALLD=$(systemctl is-active firewalld 2>/dev/null | head -1)
SELINUX=$(getenforce 2>/dev/null || echo Disabled)
HTTPD_NET=$(getsebool httpd_can_network_connect 2>/dev/null | awk '{print $3}')
SUDO=$( [ "$(id -u)" = 0 ] && echo root || (sudo -n true 2>/dev/null && echo nopasswd) || echo password)
DISK_GB=$(df -Pk . | awk 'NR==2 {printf "%d", $4/1024/1024}')
port_free() { ! ss -Hltn "sport = :$1" 2>/dev/null | grep -q .; }
PORT_3000=$(port_free "$(grep -E '^FRONTEND_PUBLISHED_PORT=' .env 2>/dev/null | cut -d= -f2 || echo 3000)" && echo free || echo used)
PORT_443=$(port_free 443 && echo free || echo used)
SSH=$(has ssh && echo yes)
SECRETS_OK=$( [ -w secrets ] && echo yes)

export PODMAN COMPOSE PYTHON PYTHON_BIN PYTHON_ANY NODE HTTPD MOD_SSL REDIS MARIADB_CLIENT FIREWALLD SELINUX HTTPD_NET SUDO DISK_GB \
  PORT_3000 PORT_443 SSH SECRETS_OK
# The values go through the environment, never pasted into code
python3 - <<'PY' > secrets/.host-check.json.tmp || { rm -f secrets/.host-check.json.tmp; echo "Lecture des prérequis impossible" >&2; exit 1; }
import datetime, getpass, json, os, socket
e = lambda name: os.environ.get(name, "").strip()
print(json.dumps({
    "checked_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "host": socket.getfqdn(), "user": getpass.getuser(),
    "podman": e("PODMAN"), "podman_compose": e("COMPOSE"),
    "python": e("PYTHON"), "python_bin": e("PYTHON_BIN"), "python_any": e("PYTHON_ANY"),
    "node": e("NODE"), "httpd": e("HTTPD"), "mod_ssl": e("MOD_SSL") == "yes", "redis": e("REDIS"), "mariadb_client": e("MARIADB_CLIENT"),
    "firewalld": e("FIREWALLD") or "inactive", "selinux": e("SELINUX"), "httpd_can_network_connect": e("HTTPD_NET"),
    "sudo": e("SUDO"), "disk_free_gb": int(e("DISK_GB") or 0), "port_frontend": e("PORT_3000"), "port_443": e("PORT_443"),
    "ssh": e("SSH") == "yes", "secrets_writable": e("SECRETS_OK") == "yes",
}, indent=1))
PY
mv secrets/.host-check.json.tmp secrets/.host-check.json
chmod 600 secrets/.host-check.json
echo "Prérequis lus : secrets/.host-check.json"
