#!/bin/bash
# The wizard without container (a host without podman, installation « sans conteneur », or WIZARD=binary make wizard):
# the single executable dist/b2s-wizard when it is there (make wizard-binary: no Python needed), otherwise its own
# Python environment in .wizard-venv. On WIZARD_PORT, the secrets of the accounts in secrets/ as with the container;
# scripts/after-wizard.sh follows it by its process (B2S_WIZARD_PID).
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/lib.sh

BINARY=""
[ -x dist/b2s-wizard ] && BINARY="$PWD/dist/b2s-wizard"
PY=""
for candidate in "${B2S_PYTHON:-}" python3.14 python3.13 python3.12; do
  if [ -n "$candidate" ] && command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)'; then PY=$candidate; break; fi
done
[ -n "$PY" ] || [ -n "$BINARY" ] || { echo "Python 3.12 ou plus requis (dnf install python3.12), ou le binaire : make wizard-binary" >&2; exit 1; }
if [ -z "$BINARY" ] && [ ! -x .wizard-venv/bin/uvicorn ]; then
  "$PY" -m venv .wizard-venv
  .wizard-venv/bin/pip install -q --disable-pip-version-check -r wizard-ui/requirements.txt
fi

# The fields of the wizard start from .env (names only, never a password)
for name in DB_HOST DB_PORT DB_NAME DB_USER DB_MIGRATE_USER LOGGING_DB_NAME FIVES_DB_NAME FIVES_INVENTORY_DB_NAME FIVES_DB_USER \
  FRONTEND_PUBLIC_ORIGIN FRONTEND_PUBLISHED_PORT B2S_DEPLOY_MODE B2S_WEB_LOCATION B2S_WEB_SERVER_NAME B2S_WEB_HTTPS_PORT B2S_WEB_CERT B2S_WEB_KEY \
  B2S_WEB_HOST B2S_WEB_IP B2S_API_HOST B2S_AUTH_PORT B2S_CORE_PORT B2S_FIVES_PORT B2S_WEB_PUSH B2S_WEB_SSH_USER B2S_WEB_SSH_KEY; do
  value=$(env_value "$name")
  if [ -n "$value" ]; then export "$name=$value"; fi
done
PORT=$(env_value WIZARD_PORT 8080)
export SECRETS_DIR="$PWD/secrets"
if [ -n "$BINARY" ]; then
  WIZARD_PORT="$PORT" setsid -f "$BINARY" > secrets/.wizard.log 2>&1 < /dev/null
  sleep 3
  pgrep -f "^$BINARY" | head -1 > secrets/.wizard.pid
  echo "Wizard démarré (binaire, processus $(cat secrets/.wizard.pid)), port $PORT."
  exit 0
fi
cd wizard-ui
setsid -f ../.wizard-venv/bin/uvicorn backend.app.main:app --host 0.0.0.0 --port "$PORT" > ../secrets/.wizard.log 2>&1 < /dev/null
sleep 2
pgrep -f "uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT" | head -1 > ../secrets/.wizard.pid
echo "Wizard démarré sans conteneur (processus $(cat ../secrets/.wizard.pid)), port $PORT."
