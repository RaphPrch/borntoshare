# Shared by the scripts of this directory (sourced, run from the root of the repository).

env_value() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | sed 's/^"//; s/"$//' || true; }

has_secret() { podman secret inspect "$1" >/dev/null 2>&1; }

# A MariaDB client tool (mariadb, mariadb-dump) with the account USER, whose password is the podman secret SECRET:
# mounted in the client container, read there; it is never in an argument nor in the environment of the host.
#   b2s_db SECRET USER TOOL [arguments…]     (stdin and stdout are the tool's)
b2s_db() {
  local secret=$1 user=$2 tool=$3
  shift 3
  local port
  port="$(env_value DB_PORT)"
  # B2S_DB_NETWORK: network of the client container, when the server is a container (tests); the host's otherwise
  podman run --rm -i ${B2S_DB_NETWORK:+--network "$B2S_DB_NETWORK"} --secret "$secret" docker.io/library/mariadb:11.4 sh -c \
    'MYSQL_PWD="$(cat "/run/secrets/$0")" exec "$@"' "$secret" \
    "$tool" --skip-ssl -h "$(env_value DB_HOST)" -P "${port:-3306}" -u "$user" "$@"
}
