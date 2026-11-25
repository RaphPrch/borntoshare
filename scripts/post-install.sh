#!/bin/bash
# The e-mail and syslog settings chosen in the wizard, recorded by the core once it runs (run by scripts/deploy.sh
# after the services start). The wizard left them in secrets/: .post-install.json (no password) and, when given,
# .smtp-password (0600). Removed once the core has them. Never prints a password.
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/lib.sh

[ -f secrets/.post-install.json ] || { echo "  rien à enregistrer"; exit 0; }
# The payload (with the password, when there is one) goes on stdin only
payload() {
  python3 - "$1" <<'PY'
import json, pathlib, sys
plan = json.loads(pathlib.Path("secrets/.post-install.json").read_text())
password = pathlib.Path("secrets/.smtp-password")
plan["smtp_password"] = password.read_text() if password.exists() else ""
plan["core_url"] = sys.argv[1]
print(json.dumps(plan))
PY
}
if [ "$(deploy_mode)" = native ]; then
  # The tokens and the key of .env, through the environment of this process only (the container has them already)
  payload "http://127.0.0.1:$(env_value B2S_CORE_PORT 8102)/api" | INTERNAL_TOKEN="$(env_value INTERNAL_TOKEN)" \
    B2S_SERVICE_TOKEN="$(env_value B2S_TOKEN_FRONTEND)" PRINCIPAL_SIGNING_KEY="$(env_value PRINCIPAL_SIGNING_KEY)" python3 scripts/post_install.py
else
  payload "http://127.0.0.1:8000/api" | podman exec -i core-service python -c "$(cat scripts/post_install.py)"
fi
shred -u secrets/.smtp-password 2>/dev/null || rm -f secrets/.smtp-password
rm -f secrets/.post-install.json
