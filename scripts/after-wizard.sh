#!/bin/bash
# Started by make wizard, on the host (the wizard, in its container, cannot run podman). Waits for the end of the
# installation, then without any command to type:
#   1. writes into .env the lines the wizard gives (the server, and the names that differ from the defaults);
#   2. runs scripts/deploy.sh (secrets, SQL packs, images, services), its progress shown by the last step of the wizard;
#   3. stops the wizard (it must not stay exposed).
# It exits when the wizard is stopped without an installation. Its files are in secrets/ (never a password there):
#   .installed       written by the wizard: the .env lines (JSON)
#   .deploy-status   written here: {"state": "running|done|failed", "phase": "<last phase of deploy.sh>"}
#   .deploy.log      the output of deploy.sh (it never prints a password)
#   .deploy-phases   the phases deploy.sh announces (« PHASES: … »), shown by the wizard
# (.smtp-password, written by the wizard when an SMTP password is given, is read by scripts/post-install.sh only)
set -uo pipefail
cd "$(dirname "$0")/.."
DIR=secrets
CONTAINER="${B2S_WIZARD_CONTAINER:-wizard-ui}"   # tests: another container
DEPLOY="${B2S_DEPLOY_CMD:-scripts/deploy.sh}"   # tests: another command
STOP_AFTER="${B2S_WIZARD_STOP_AFTER:-180}"      # seconds left to read the result before the wizard stops

# One watcher at a time (make wizard run twice)
exec 9> "$DIR/.after-wizard.lock"
flock -n 9 || exit 0

# The status as JSON (python3: the texts of deploy.sh may hold quotes)
status() {
  python3 -c 'import json, sys; print(json.dumps({"state": sys.argv[1], "phase": sys.argv[2], "phases": [p for p in sys.argv[3].split("|") if p]}))' \
    "$1" "$2" "$(cat "$DIR/.deploy-phases" 2>/dev/null)" > "$DIR/.deploy-status.tmp" && mv "$DIR/.deploy-status.tmp" "$DIR/.deploy-status"
}
# The wizard: its container, or its process when it runs without container (B2S_WIZARD_PID, make wizard)
running() {
  if [ -n "${B2S_WIZARD_PID:-}" ]; then kill -0 "$B2S_WIZARD_PID" 2>/dev/null; return; fi
  [ "$(podman inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" = "true" ]
}
stop_wizard() {
  if [ -n "${B2S_WIZARD_PID:-}" ]; then kill "$B2S_WIZARD_PID" 2>/dev/null || true; return; fi
  podman stop "$CONTAINER" >/dev/null 2>&1 || true
}

rm -f "$DIR/.installed" "$DIR/.deploy-status" "$DIR/.deploy.log" "$DIR/.deploy-phases"
# Wait for the installation (the wizard may stay open for a long time)
until [ -f "$DIR/.installed" ]; do
  running || exit 0
  sleep 3
done

status running "Lignes de .env"
python3 - "$DIR/.installed" <<'PY' || { status failed "Lignes de .env"; exit 1; }
import json, re, sys
lines = json.load(open(sys.argv[1])).get("env") or []
env = open(".env").read()
for name, value in lines:
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", str(name)) or "\n" in str(value):
        continue
    line = f"{name}={value}"
    if re.search(rf"^{name}=", env, re.M):
        env = re.sub(rf"^{name}=.*$", lambda _m: line, env, count=1, flags=re.M)
    else:
        env = env.rstrip("\n") + "\n" + line + "\n"
open(".env", "w").write(env)
PY

status running "Déploiement"
"$DEPLOY" 2>&1 | while IFS= read -r line; do
  printf '%s\n' "$line" >> "$DIR/.deploy.log"
  case "$line" in
    PHASES:*) printf '%s' "${line#PHASES: }" > "$DIR/.deploy-phases"; status running "Déploiement" ;;
    [0-9]/[0-9]*|[0-9][0-9]/[0-9]*) status running "$line" ;;
  esac
done
if [ "${PIPESTATUS[0]}" -eq 0 ]; then status done "BornToShare est démarré"; else status failed "$(tail -1 "$DIR/.deploy.log")"; fi

sleep "$STOP_AFTER"
stop_wizard
rm -f "$DIR/.installed"
