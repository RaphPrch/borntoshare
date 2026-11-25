#!/bin/bash
# Removes the web interface of BornToShare from THIS server (what scripts/web/install-web.sh installed), as root.
# Run by scripts/uninstall.sh (here, or over SSH on the annex web server). Idempotent.
#   PURGE=1   also removes the account b2s-web
# Kept: httpd itself, mod_ssl, Node.js, the certificate and its key, the rules of firewalld (http, https) and the
# SELinux boolean httpd_can_network_connect, which other sites of this httpd may use.
set -uo pipefail
[ "$(id -u)" = 0 ] || { echo "À lancer en root (sudo)" >&2; exit 1; }

if systemctl list-unit-files b2s-web.service >/dev/null 2>&1; then
  systemctl disable --now b2s-web >/dev/null 2>&1 || true
fi
rm -f /etc/systemd/system/b2s-web.service
systemctl daemon-reload
if [ -f /etc/httpd/conf.d/borntoshare.conf ]; then
  rm -f /etc/httpd/conf.d/borntoshare.conf
  if systemctl is-active -q httpd; then systemctl reload httpd; fi
  echo "  vhost /etc/httpd/conf.d/borntoshare.conf retiré"
fi
rm -rf /opt/borntoshare/web /opt/borntoshare/web.previous /opt/borntoshare/web.next
rm -f /etc/borntoshare/web.env /etc/borntoshare/web.secrets
# The directories go once empty (the native services may share them)
rmdir /opt/borntoshare /etc/borntoshare 2>/dev/null || true
if [ "${PURGE:-0}" = 1 ] && id b2s-web >/dev/null 2>&1; then userdel b2s-web && echo "  compte b2s-web supprimé"; fi
echo "  interface web retirée de $(hostname)"
