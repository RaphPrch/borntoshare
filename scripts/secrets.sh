#!/bin/bash
# The podman secrets of BornToShare (podman-compose.yml mounts them as files in /run/secrets): run by make deploy,
# idempotent. Never prints a value.
#   1. imports the files the wizard wrote in secrets/ (passwords of the SQL accounts), then removes them;
#   2. moves into secrets the passwords still in .env (installations from before), then removes their lines;
#   3. generates those that do not exist yet (key of the stored passwords, Redis).
# The key b2s_master_key encrypts the passwords stored by the application: back it up apart from the databases
#   podman secret inspect --showsecret --format '{{.SecretData}}' b2s_master_key
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/lib.sh

put() { podman secret create --replace "$1" - >/dev/null; }   # the value on stdin
value_of() { podman secret inspect --showsecret --format '{{.SecretData}}' "$1"; }

# 1. Files of the wizard
if [ -d secrets ]; then
  for file in secrets/b2s_*; do
    [ -f "$file" ] || continue
    name="$(basename "$file")"
    put "$name" < "$file"
    shred -u "$file" 2>/dev/null || rm -f "$file"
    echo "secret $name: imported from secrets/"
  done
fi

# 2. Values still in .env: moved, and their line removed once the secret holds the same value
move() {  # secret variable
  local name=$1 var=$2 value
  value="$(env_value "$var")"
  [ -n "$value" ] || return 0
  if ! has_secret "$name"; then
    printf '%s' "$value" | put "$name"
    echo "secret $name: moved from .env ($var)"
  fi
  if [ "$(value_of "$name")" = "$value" ]; then
    sed -i "/^$var=/d" .env
  else
    echo "secret $name differs from $var in .env: line kept, check which one is right" >&2
  fi
}
move b2s_master_key B2S_SECRET_MASTER_KEY
move b2s_redis REDIS_PASSWORD
# Passwords of the SQL accounts of before: replaced by the accounts of the wizard
for pair in "b2s_db_core DB_PASSWORD" "b2s_db_fives FIVES_DB_PASSWORD"; do
  set -- $pair
  if has_secret "$1" && grep -qE "^$2=" .env; then
    sed -i "/^$2=/d" .env
    echo ".env: $2 removed (the account now has the secret $1)"
  fi
done

# 3. Generated when missing
if ! has_secret b2s_master_key; then
  head -c 32 /dev/urandom | base64 | tr -d '\n' | put b2s_master_key
  echo "secret b2s_master_key: generated (back it up: see the top of scripts/secrets.sh)"
fi
if ! has_secret b2s_redis; then
  head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 40 | put b2s_redis
  echo "secret b2s_redis: generated"
fi
for required in b2s_db_core b2s_db_migrate; do
  has_secret "$required" || { echo "secret $required missing: run the wizard first (make wizard)" >&2; exit 1; }
done
