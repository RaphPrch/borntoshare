#!/bin/bash
# Runs every automated test suite of BornToShare, each in the image of its service (Python 3.14, Node.js 26), the
# way the CI does, and prints one line per suite. Exit status 1 if one suite fails.
#   testing/run-tests.sh                      lint + the public services + the interface
#   testing/run-tests.sh core-service auth-service   only those suites
#   FIVES_REPO=~/b2s-fives-module testing/run-tests.sh   also the 5S module (private repository), laid out as installed
# The images are the local ones (localhost/b2s-<service>:latest, made by make build); the code tested is this
# working copy, mounted read-only.
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
FIVES="${FIVES_REPO:-}"
PIP="python -m pip install -q --root-user-action=ignore --target /tmp/pt pytest pytest-asyncio httpx >/dev/null 2>&1"
LOGS=$(mktemp -d)
status=0

suites=("$@")
if [ ${#suites[@]} = 0 ]; then
  suites=(lint core-service auth-service capsule-runner wizard-ui frontend-service)
  [ -n "$FIVES" ] && suites+=(fives-service fives-scanner)
fi

result() { # name, exit code, summary line
  if [ "$2" = 0 ]; then printf '  OK  %-17s %s\n' "$1" "$3"; else printf '  KO  %-17s %s (journal : %s)\n' "$1" "$3" "$LOGS/$1.log"; status=1; fi
}

pytest_in() { # suite, image, extra podman args..., -- command dir
  local name=$1 image=$2; shift 2
  local args=() ; while [ "$1" != -- ]; do args+=("$1"); shift; done; shift
  podman run --rm --user 0 --entrypoint sh "${args[@]}" "$image" -c \
    "$PIP; cd $1 && PYTHONPATH=/tmp/pt:$1 python -m pytest -q -p no:cacheprovider" >"$LOGS/$name.log" 2>&1
  local rc=$?
  result "$name" $rc "$(grep -E '^[0-9]+ (passed|failed)|^=+ .*(passed|failed|error)' "$LOGS/$name.log" | tail -1 | tr -d '=')"
}

for suite in "${suites[@]}"; do
  case "$suite" in
    lint)
      podman run --rm -e PIP_DISABLE_PIP_VERSION_CHECK=1 -v "$ROOT:/src:ro,z" -w /src docker.io/library/python:3.14-slim-trixie \
        sh -c "pip install -q --root-user-action=ignore ruff==0.13.0 >/dev/null && ruff check --no-cache core-service auth-service capsule-runner wizard-ui" \
        >"$LOGS/lint.log" 2>&1
      result lint $? "$(tail -1 "$LOGS/lint.log")" ;;
    core-service|capsule-runner)
      # The whole repository, as in the CI checkout: the guardrail tests read the SQL packs of wizard-ui
      pytest_in "$suite" "localhost/b2s-$suite:latest" -v "$ROOT:/r:ro,z" -- "/r/$suite" ;;
    auth-service)
      # Its settings require INTERNAL_TOKEN (as in the CI)
      pytest_in auth-service localhost/b2s-auth-service:latest -e INTERNAL_TOKEN=ci-internal-token -v "$ROOT:/r:ro,z" -- /r/auth-service ;;
    wizard-ui)
      # From wizard-ui: the tests import backend.app.main
      pytest_in wizard-ui localhost/b2s-wizard-ui:latest -v "$ROOT:/r:ro,z" -- /r/wizard-ui ;;
    fives-service|fives-scanner)
      [ -n "$FIVES" ] || { result "$suite" 1 "FIVES_REPO non défini (dépôt du module 5S)"; continue; }
      # As installed: the module next to capsule-runner and wizard-ui, its SQL packs in the packs of the wizard
      pytest_in "$suite" "localhost/b2s-$suite:latest" \
        -v "$FIVES/fives-service:/r/fives-service:ro,z" -v "$FIVES/fives-scanner:/r/fives-scanner:ro,z" \
        -v "$ROOT/capsule-runner:/r/capsule-runner:ro,z" -v "$ROOT/wizard-ui:/r/wizard-ui:ro,z" \
        -v "$FIVES/wizard-sql/fives:/r/wizard-ui/backend/app/sql/fives:ro,z" \
        -v "$FIVES/wizard-sql/fives_inventory:/r/wizard-ui/backend/app/sql/fives_inventory:ro,z" -- "/r/$suite" ;;
    frontend-service)
      # A copy (node_modules is installed in the container, never in the working copy), npm cache kept between runs
      # Laid out as in the repository: some tests read the core next to it (../core-service)
      podman run --rm -v "$ROOT/frontend-service:/src:ro,z" -v "$ROOT/core-service:/r/core-service:ro,z" -v b2s-test-npm-cache:/root/.npm docker.io/library/node:26-alpine sh -c '
        set -e; mkdir -p /r/frontend-service; cd /src; tar --exclude=node_modules --exclude=.svelte-kit --exclude=build -cf - . | tar -xf - -C /r/frontend-service; cd /r/frontend-service
        npm ci --no-audit --no-fund >/dev/null
        n=0; for s in $(node -p "Object.keys(require(\"./package.json\").scripts).filter(k => k.startsWith(\"test:\")).join(\" \")"); do
          echo "== $s"; npm run -s "$s"; n=$((n+1)); done
        npm run -s check -- --threshold error
        echo "RESULT $n scripts de test, check sans erreur"' >"$LOGS/frontend-service.log" 2>&1
      rc=$?
      result frontend-service $rc "$(grep '^RESULT' "$LOGS/frontend-service.log" | cut -c8- || true)" ;;
    *) result "$suite" 1 "suite inconnue" ;;
  esac
done
[ "$status" = 0 ] && rm -rf "$LOGS"
exit $status
