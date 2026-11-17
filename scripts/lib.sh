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

# The MariaDB server of a database: the one of the 5S module (FIVES_DB_HOST, when its bases are on a server of their
# own) for its two bases, the one of BornToShare (DB_HOST) for the others. Prints « fives » or « core ».
db_server_for() {
  case "$1" in
    "$(env_value FIVES_DB_NAME b2s_fives)"|"$(env_value FIVES_INVENTORY_DB_NAME b2s_fives_inventory)") echo fives ;;
    *) echo core ;;
  esac
}

# Private authority of the MariaDB servers (DB_TLS=on), when they do not use a public one
DB_TLS_CA_FILE=capsule-runner/certs/db-ca.pem

# A MariaDB client tool (mariadb, mariadb-dump) with the account USER, whose password is the podman secret SECRET:
# mounted in the client container, read there; it is never in an argument nor in the environment of the host.
#   b2s_db SECRET USER TOOL [arguments…]     (stdin and stdout are the tool's)
# The server: the one of the 5S for the secret b2s_db_fives or with B2S_DB_SERVER=fives, else the one of BornToShare.
# DB_TLS=on: encrypted, certificate and name of the server checked (DB_TLS_CA_FILE, else the authorities of the system).
b2s_db() {
  local secret=$1 user=$2 tool=$3 host port tls
  shift 3
  host=$(env_value DB_HOST)
  port=$(env_value DB_PORT 3306)
  if [ "$secret" = b2s_db_fives ] || [ "${B2S_DB_SERVER:-core}" = fives ]; then
    host=$(env_value FIVES_DB_HOST "$host")
    port=$(env_value FIVES_DB_PORT "$port")
  fi
  tls=(--skip-ssl)
  # Without container: the client of the host, its password in a root-only option file (never an argument)
  if [ "$(deploy_mode)" = native ]; then
    if [ "$(env_value DB_TLS off)" = on ]; then
      tls=(--ssl --ssl-verify-server-cert)
      [ -f /etc/b2s/certs/db-ca.pem ] && tls+=(--ssl-ca=/etc/b2s/certs/db-ca.pem)
    fi
    as_root "$tool" --defaults-extra-file="$NATIVE_SECRETS/$secret.cnf" "${tls[@]}" -h "$host" -P "$port" -u "$user" "$@"
    return
  fi

  local mount=()
  if [ "$(env_value DB_TLS off)" = on ]; then
    tls=(--ssl --ssl-verify-server-cert)
    if [ -f "$DB_TLS_CA_FILE" ]; then
      mount=(-v "$PWD/$DB_TLS_CA_FILE:/etc/b2s/db-ca.pem:ro,z")
      tls+=(--ssl-ca=/etc/b2s/db-ca.pem)
    fi
  fi
  # B2S_DB_NETWORK: network of the client container, when the server is a container (tests); the host's otherwise
  podman run --rm -i ${B2S_DB_NETWORK:+--network "$B2S_DB_NETWORK"} "${mount[@]}" --secret "$secret" docker.io/library/mariadb:11.4 sh -c \
    'MYSQL_PWD="$(cat "/run/secrets/$0")" exec "$@"' "$secret" \
    "$tool" "${tls[@]}" -h "$host" -P "$port" -u "$user" "$@"
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
