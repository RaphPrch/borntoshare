#!/bin/bash
# Installs the web interface of BornToShare on THIS server, published by Apache httpd (run as root, from the package
# made by scripts/web/build-web.sh: on the server of BornToShare, or copied to an annex web server).
#   - /opt/borntoshare/web: the interface (the one it replaces stays in web.previous, the rollback point);
#   - service b2s-web (Node.js on 127.0.0.1:3000, user b2s-web), its environment in /etc/borntoshare/web.env (0640) and
#     its two secrets as files in /etc/borntoshare/web-secrets (0440 root:b2s-web);
#   - /etc/httpd/conf.d/borntoshare.conf: HTTPS with the certificate given, HTTP redirected;
#   - SELinux (httpd may reach the interface), firewalld (HTTPS and HTTP open);
#   - checks: the configuration of httpd, then the sign-in page through httpd, then the services behind.
# B2S_STAGE=/dir writes the files under that directory and changes nothing on the system (review, tests).
set -euo pipefail
cd "$(dirname "$0")"

STAGE="${B2S_STAGE:-}"
value() { grep -E "^$1=" site.conf | tail -1 | cut -d= -f2-; }
SERVER_NAME=$(value SERVER_NAME); HTTPS_PORT=$(value HTTPS_PORT); CERT=$(value CERT); KEY=$(value KEY)
[[ "$SERVER_NAME" =~ ^[A-Za-z0-9.-]+$ ]] || { echo "Nom d'hôte invalide dans site.conf" >&2; exit 1; }
[[ "$HTTPS_PORT" =~ ^[0-9]+$ ]] || { echo "Port invalide dans site.conf" >&2; exit 1; }
run() { if [ -n "$STAGE" ]; then echo "  (stage) $*"; else "$@"; fi; }

if [ -z "$STAGE" ]; then
  [ "$(id -u)" = 0 ] || { echo "À lancer en root (sudo)" >&2; exit 1; }
  NODE=$(command -v node || true)
  [ -n "$NODE" ] || { echo "Node.js introuvable : dnf module install nodejs:22" >&2; exit 1; }
  major=$("$NODE" -p 'process.versions.node.split(".")[0]')
  [ "$major" -ge 22 ] || { echo "Node.js $major trop ancien : 22 au moins (Vite 8, SvelteKit)" >&2; exit 1; }
  command -v httpd >/dev/null || { echo "httpd introuvable : dnf install httpd mod_ssl" >&2; exit 1; }
  [ -e /etc/httpd/conf.modules.d/00-ssl.conf ] || { echo "mod_ssl absent : dnf install mod_ssl" >&2; exit 1; }
  [ -f "$CERT" ] || { echo "Certificat $CERT introuvable sur ce serveur" >&2; exit 1; }
  [ -f "$KEY" ] || { echo "Clé $KEY introuvable sur ce serveur" >&2; exit 1; }
  id b2s-web >/dev/null 2>&1 || useradd --system --home-dir /opt/borntoshare/web --shell /sbin/nologin b2s-web
else
  NODE=/usr/bin/node
fi

WEB="$STAGE/opt/borntoshare/web"
ETC="$STAGE/etc/borntoshare"
install -d -m 0755 "$STAGE/opt/borntoshare"
# Crossed by the accounts of the services too (b2s): never given to b2s-web, only web.env and web-secrets are
install -d -m 0755 "$ETC"
# The interface: the running one becomes the rollback point
rm -rf "$WEB.next"
cp -r app "$WEB.next"
if [ -d "$WEB" ]; then rm -rf "$WEB.previous"; mv "$WEB" "$WEB.previous"; fi
mv "$WEB.next" "$WEB"
chmod -R a+rX,go-w "$WEB"
install -m 0640 web.env "$ETC/web.env"
install -d -m 0750 "$ETC/web-secrets"
install -m 0440 secrets/b2s_internal_token secrets/b2s_principal_key "$ETC/web-secrets/"
if [ -z "$STAGE" ]; then
  chmod 0755 "$ETC"
  chown root:b2s-web "$ETC/web.env" "$ETC/web-secrets" "$ETC/web-secrets/b2s_internal_token" "$ETC/web-secrets/b2s_principal_key"
  rm -f "$ETC/web.secrets"  # the values in clear of earlier versions
fi

install -d "$STAGE/etc/systemd/system"
cat > "$STAGE/etc/systemd/system/b2s-web.service" <<UNIT
[Unit]
Description=BornToShare : interface web
After=network-online.target
Wants=network-online.target

[Service]
User=b2s-web
Group=b2s-web
WorkingDirectory=/opt/borntoshare/web
EnvironmentFile=/etc/borntoshare/web.env
ExecStart=$NODE build/index.js
Restart=on-failure
RestartSec=5
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
CapabilityBoundingSet=

[Install]
WantedBy=multi-user.target
UNIT

LISTEN=""
[ "$HTTPS_PORT" = 443 ] || LISTEN="Listen $HTTPS_PORT https"
HTTPS_SUFFIX=""
[ "$HTTPS_PORT" = 443 ] || HTTPS_SUFFIX=":$HTTPS_PORT"
install -d "$STAGE/etc/httpd/conf.d"
cat > "$STAGE/etc/httpd/conf.d/borntoshare.conf" <<VHOST
# BornToShare (scripts/web/install-web.sh): rewritten at each deployment
$LISTEN
<VirtualHost *:$HTTPS_PORT>
  ServerName $SERVER_NAME
  SSLEngine on
  SSLCertificateFile    $CERT
  SSLCertificateKeyFile $KEY
  Protocols h2 http/1.1
  ProxyPreserveHost On
  ProxyTimeout 300
  ProxyPass        / http://127.0.0.1:3000/
  ProxyPassReverse / http://127.0.0.1:3000/
  RequestHeader set X-Forwarded-Proto "https"
  Header always set Strict-Transport-Security "max-age=31536000"
</VirtualHost>
<VirtualHost *:80>
  ServerName $SERVER_NAME
  Redirect permanent / https://$SERVER_NAME$HTTPS_SUFFIX/
</VirtualHost>
VHOST

if [ -n "$STAGE" ]; then echo "  (stage) fichiers écrits sous $STAGE"; exit 0; fi

# SELinux: httpd forwards to the interface on 127.0.0.1:3000; the certificate gets the label httpd reads
if [ "$(getenforce 2>/dev/null || echo Disabled)" != Disabled ]; then
  [ "$(getsebool httpd_can_network_connect | awk '{print $3}')" = on ] || setsebool -P httpd_can_network_connect 1
  restorecon -F "$CERT" "$KEY" 2>/dev/null || true
  if [ "$HTTPS_PORT" != 443 ]; then semanage port -a -t http_port_t -p tcp "$HTTPS_PORT" 2>/dev/null || true; fi
fi
if systemctl is-active -q firewalld; then
  firewall-cmd -q --permanent --add-service=http
  if [ "$HTTPS_PORT" = 443 ]; then firewall-cmd -q --permanent --add-service=https; else firewall-cmd -q --permanent --add-port="$HTTPS_PORT/tcp"; fi
  firewall-cmd -q --reload
fi

# A new httpd of RHEL/AlmaLinux: ssl.conf names the certificate httpd-init makes at the first start (localhost.crt)
if [ -f /etc/httpd/conf.d/ssl.conf ] && [ ! -s /etc/pki/tls/certs/localhost.crt ] && [ -x /usr/libexec/httpd-ssl-gencerts ]; then
  /usr/libexec/httpd-ssl-gencerts
fi
httpd -t
systemctl daemon-reload
systemctl enable -q b2s-web httpd
systemctl restart b2s-web
systemctl reload-or-restart httpd

# Checks: the interface, through httpd, then what it calls
ok=""
for _ in $(seq 1 20); do
  code=$(curl -sk -o /dev/null -w '%{http_code}' --resolve "$SERVER_NAME:$HTTPS_PORT:127.0.0.1" "https://$SERVER_NAME:$HTTPS_PORT/login" || true)
  if [ "$code" = 200 ]; then ok=1; break; fi
  sleep 2
done
[ -n "$ok" ] || { echo "L'interface ne répond pas par httpd (dernier code : ${code:-aucun}) : journalctl -u b2s-web" >&2; exit 1; }
echo "  https://$SERVER_NAME$HTTPS_SUFFIX répond"
for name in B2S_AUTH_URL B2S_CORE_URL; do
  url=$(grep -E "^$name=" web.env | cut -d= -f2-)
  probe="${url%/api}/health"
  if curl -s -o /dev/null -m 5 "$probe"; then echo "  $name joignable ($probe)"; else echo "  $name injoignable depuis ce serveur : $probe (pare-feu ?)" >&2; exit 1; fi
done
