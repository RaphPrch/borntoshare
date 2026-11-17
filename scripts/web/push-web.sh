#!/bin/bash
# Sends the web interface (dist/borntoshare-web, scripts/web/build-web.sh) to the annex web server and installs it
# there: SSH with a key (never a password), the account B2S_WEB_SSH_USER running sudo without password. The package
# goes to a private temporary directory of the annex (0700), removed after the installation.
set -euo pipefail
cd "$(dirname "$0")/../.."
. scripts/lib.sh

HOST=$(env_value B2S_WEB_HOST)
USER_NAME=$(env_value B2S_WEB_SSH_USER)
KEY=$(env_value B2S_WEB_SSH_KEY "$HOME/.ssh/id_ed25519")
KEY="${KEY/#\~/$HOME}"
[ -n "$HOST" ] && [ -n "$USER_NAME" ] || { echo "B2S_WEB_HOST et B2S_WEB_SSH_USER requis dans .env" >&2; exit 1; }
[ -f "$KEY" ] || { echo "Clé SSH $KEY introuvable sur ce serveur" >&2; exit 1; }
[ -d dist/borntoshare-web ] || { echo "dist/borntoshare-web absent : scripts/web/build-web.sh d'abord" >&2; exit 1; }

SSH=(ssh -i "$KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 "$USER_NAME@$HOST")
remote=$("${SSH[@]}" 'mktemp -d /tmp/b2s-web.XXXXXX')
[[ "$remote" =~ ^/tmp/b2s-web\.[A-Za-z0-9]+$ ]] || { echo "Répertoire temporaire inattendu sur $HOST" >&2; exit 1; }
echo "  envoi vers $USER_NAME@$HOST:$remote"
tar -C dist/borntoshare-web -czf - . | "${SSH[@]}" "tar -xzf - -C '$remote'"
"${SSH[@]}" "sudo -n '$remote/install-web.sh'; rc=\$?; rm -rf '$remote'; exit \$rc"
