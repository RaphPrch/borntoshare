#!/bin/bash
# The web interface outside its container (hybrid and native installations): prepares dist/borntoshare-web/, the
# package that scripts/web/install-web.sh installs on the web server (this host, or the annex web server).
#   app/           the built interface (SvelteKit adapter-node: build/ + package.json, nothing else to install)
#   web.env        its environment, without secret (addresses of auth, core and 5S, public origin)
#   web.secrets    the token of the services and the key of the sessions (0600): the only secret of the package
#   site.conf      name, HTTPS port, certificate and key for the httpd virtual host
#   install-web.sh run as root on the web server
# With podman, the interface is the one of its image (same build as the containers); without, npm builds it here.
set -euo pipefail
cd "$(dirname "$0")/../.."
. scripts/lib.sh

OUT=dist/borntoshare-web
rm -rf "$OUT"
install -d -m 0700 dist "$OUT" "$OUT/app"

if command -v podman >/dev/null 2>&1 && [ "$(deploy_mode)" != native ]; then
  podman-compose -f podman-compose.yml build frontend-service >/dev/null
  cid=$(podman create localhost/b2s-frontend-service:latest)
  trap 'podman rm -f "$cid" >/dev/null 2>&1 || true' EXIT
  podman cp "$cid:/app/build" "$OUT/app/build"
  podman cp "$cid:/app/package.json" "$OUT/app/package.json"
else
  command -v npm >/dev/null 2>&1 || { echo "npm introuvable : installer Node.js 26 (dnf module install nodejs:26)" >&2; exit 1; }
  (cd frontend-service && npm ci --no-fund --no-audit >/dev/null && B2S_VERSION="${B2S_VERSION:-}" npm run build >/dev/null)
  cp -r frontend-service/build "$OUT/app/build"
  cp frontend-service/package.json "$OUT/app/package.json"
fi

if [ "$(web_location)" = annex ]; then
  API="$(env_value B2S_API_HOST)"
  [ -n "$API" ] || { echo "B2S_API_HOST absent de .env : le serveur annexe ne saurait pas joindre ce serveur" >&2; exit 1; }
else
  API=127.0.0.1
fi
FIVES_URL=""
if has_secret b2s_db_fives || [ -f secrets/b2s_db_fives ]; then FIVES_URL="http://$API:$(env_value B2S_FIVES_PORT 8105)"; fi

cat > "$OUT/web.env" <<ENV
NODE_ENV=production
TZ=Europe/Paris
HOST=127.0.0.1
PORT=3000
ORIGIN=$(env_value FRONTEND_PUBLIC_ORIGIN)
ADDRESS_HEADER=X-Forwarded-For
XFF_DEPTH=1
B2S_AUTH_URL=http://$API:$(env_value B2S_AUTH_PORT 8101)
B2S_CORE_URL=http://$API:$(env_value B2S_CORE_PORT 8102)/api
B2S_FIVES_URL=$FIVES_URL
B2S_VERSION=${B2S_VERSION:-}
ENV
(umask 077; printf 'INTERNAL_TOKEN=%s\nPRINCIPAL_SIGNING_KEY=%s\n' "$(env_value INTERNAL_TOKEN)" "$(env_value PRINCIPAL_SIGNING_KEY)" > "$OUT/web.secrets")
cat > "$OUT/site.conf" <<CONF
SERVER_NAME=$(env_value B2S_WEB_SERVER_NAME)
HTTPS_PORT=$(env_value B2S_WEB_HTTPS_PORT 443)
CERT=$(env_value B2S_WEB_CERT)
KEY=$(env_value B2S_WEB_KEY)
CONF
install -m 0700 scripts/web/install-web.sh "$OUT/install-web.sh"

if [ "$(env_value B2S_WEB_PUSH ssh)" = bundle ] && [ "$(web_location)" = annex ]; then
  (umask 077; tar -C dist -czf dist/borntoshare-web.tar.gz borntoshare-web)
  echo "  paquet : $PWD/dist/borntoshare-web.tar.gz (contient web.secrets : à copier par un canal sûr, puis à supprimer)"
fi
echo "  interface prête : $OUT ($(du -sh "$OUT/app" | cut -f1))"
