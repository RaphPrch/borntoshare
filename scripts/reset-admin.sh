#!/bin/bash
# Lost password of a local account. The first administrator of a 5S-only installation is often the only one:
# it gets a temporary password, typed here (never shown, never on the command line), to change at its next sign-in.
# On the server only, with the migration account (secret b2s_db_migrate).
#   make reset-admin                 the account « admin »
#   make reset-admin ACCOUNT=jdupont another local account
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/lib.sh

ACCOUNT="${1:-admin}"
if ! [[ "$ACCOUNT" =~ ^[A-Za-z0-9._@-]{1,190}$ ]]; then
  echo "Invalid account name: $ACCOUNT" >&2
  exit 1
fi
IMAGE="${B2S_CORE_IMAGE:-localhost/b2s-core-service:latest}"
podman image exists "$IMAGE" || { echo "Image $IMAGE missing: deploy BornToShare first (make deploy)." >&2; exit 1; }

read -rsp "Temporary password for $ACCOUNT: " first; echo
read -rsp "Again: " second; echo
if [ "$first" != "$second" ]; then
  echo "The two passwords differ: nothing changed." >&2
  exit 1
fi

# Same rules as the wizard; the hash as core-service writes it (bcrypt, 12 rounds). The password goes through stdin.
hash="$(printf '%s' "$first" | podman run --rm -i -e ACCOUNT="$ACCOUNT" "$IMAGE" python -c '
import os, re, sys
import bcrypt
password = sys.stdin.read()
rules = [len(password) >= 12, re.search("[a-z]", password), re.search("[A-Z]", password), re.search(r"[0-9]", password),
         re.search(r"[^A-Za-z0-9]", password), os.environ["ACCOUNT"].lower() not in password.lower()]
if not all(rules):
    sys.exit("12 characters or more, with a lowercase, an uppercase, a digit and a special character, without the account name: nothing changed.")
print("b2s$v=1$bcrypt$" + bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt(rounds=12)).decode())
')"
unset first second

# The hash holds letters, digits, « $ », « . » and « / » only: nothing to escape in the SQL. Active again, in case.
changed="$(printf "UPDATE local_credentials lc JOIN identities i ON i.id = lc.identity_id
  SET lc.password_hash = '%s', lc.password_version = 'b2s\$v=1\$bcrypt', lc.last_rotated_at = NOW(6),
      lc.must_change_password = 1, i.is_active = 1
  WHERE LOWER(i.username) = LOWER('%s') AND i.auth_source IN ('local', 'internal');
SELECT ROW_COUNT();\n" "$hash" "$ACCOUNT" \
  | b2s_db b2s_db_migrate "$(env_value DB_MIGRATE_USER b2s_migrate)" mariadb -N "$(env_value DB_NAME borntoshare)")"

if [ "${changed:-0}" -gt 0 ]; then
  echo "Done: $ACCOUNT signs in with this temporary password, then chooses its own before anything else."
else
  echo "No local account named $ACCOUNT: nothing changed." >&2
  exit 1
fi
