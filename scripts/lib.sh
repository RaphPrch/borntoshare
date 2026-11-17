# Shared by the scripts of this directory (sourced, run from the root of the repository).

# The value of .env, or the default when the line is absent or empty: env_value NAME [DEFAULT]
env_value() {
  local value
  value="$(grep -E "^$1=" .env | tail -1 | cut -d= -f2- | sed 's/^"//; s/"$//' || true)"
  printf '%s' "${value:-${2:-}}"
}

has_secret() {
  if [ "$(deploy_mode)" = native ]; then as_root test -f "$NATIVE_SECRETS/$1"; return; fi
  podman secret inspect "$1" >/dev/null 2>&1
}

# A MariaDB client tool (mariadb, mariadb-dump) with the account USER, whose password is the podman secret SECRET:
# mounted in the client container, read there; it is never in an argument nor in the environment of the host.
#   b2s_db SECRET USER TOOL [arguments…]     (stdin and stdout are the tool's)
b2s_db() {
  local secret=$1 user=$2 tool=$3
  shift 3
  # Without container: the client of the host, its password in a root-only option file (never an argument)
  if [ "$(deploy_mode)" = native ]; then
    as_root "$tool" --defaults-extra-file="$NATIVE_SECRETS/$secret.cnf" --skip-ssl -h "$(env_value DB_HOST)" -P "$(env_value DB_PORT 3306)" -u "$user" "$@"
    return
  fi

  # B2S_DB_NETWORK: network of the client container, when the server is a container (tests); the host's otherwise
  podman run --rm -i ${B2S_DB_NETWORK:+--network "$B2S_DB_NETWORK"} --secret "$secret" docker.io/library/mariadb:11.4 sh -c \
    'MYSQL_PWD="$(cat "/run/secrets/$0")" exec "$@"' "$secret" \
    "$tool" --skip-ssl -h "$(env_value DB_HOST)" -P "$(env_value DB_PORT 3306)" -u "$user" "$@"
}

# How this installation runs (the wizard writes it): containers | hybrid | native
deploy_mode() { env_value B2S_DEPLOY_MODE containers; }
# Where the web interface runs, hybrid and native: local | annex
web_location() { env_value B2S_WEB_LOCATION local; }

# A command as root: directly, or with sudo when it needs no password. Otherwise says the command to run and stops
# (exit 3): the deployment goes on with make deploy once it is done.
as_root() {
  if [ "$(id -u)" = 0 ]; then "$@"; return; fi
  if sudo -n true 2>/dev/null; then sudo -n "$@"; return; fi
  echo "Cette phase demande root : lancer « sudo $* » sur ce serveur, puis make deploy." >&2
  exit 3
}

# Installation without container: the secrets are files of /etc/borntoshare/secrets (0400, user b2s)
NATIVE_SECRETS=/etc/borntoshare/secrets

# The value of a secret, on stdout (for a file or a pipe only, never shown): secret_value NAME
secret_value() {
  if [ "$(deploy_mode)" = native ]; then as_root cat "$NATIVE_SECRETS/$1"; return; fi
  podman secret inspect --showsecret --format '{{.SecretData}}' "$1"
}
