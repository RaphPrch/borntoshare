#!/bin/bash
# Installation without container (B2S_DEPLOY_MODE=native): the services of BornToShare as systemd units, on this host.
# Run as root by scripts/deploy.sh, from the root of the repository:
#   scripts/native/install-services.sh secrets     secrets of the wizard → /etc/borntoshare/secrets (0400, user b2s)
#   scripts/native/install-services.sh services    code, Python environments, env files, units, then (re)start
#   B2S_STAGE=/some/dir …                           writes every file under that directory, starts nothing (review, tests)
#
# Layout: /opt/borntoshare/app/<service> (code + venv; <service>.previous = the rollback point),
# /etc/borntoshare/env/<service>.env (0640 root:b2s), /etc/borntoshare/secrets (0400 b2s), /var/lib/borntoshare/redis.
# Every service listens on 127.0.0.1, except auth, core and 5S when the web interface is on an annex server
# (then on 0.0.0.0; the firewall opens them to that server only: scripts/web/firewall.sh).
set -euo pipefail
cd "$(dirname "$0")/../.."
. scripts/lib.sh

STAGE="${B2S_STAGE:-}"
APP="$STAGE/opt/borntoshare/app"
ETC="$STAGE/etc/borntoshare"
UNITS="$STAGE/etc/systemd/system"
VAR="$STAGE/var/lib/borntoshare"
CERTS="$STAGE/etc/b2s/certs"
SECRETS="$ETC/secrets"
USER_NAME=b2s

AUTH_PORT=$(env_value B2S_AUTH_PORT 8101)
CORE_PORT=$(env_value B2S_CORE_PORT 8102)
FIVES_PORT=$(env_value B2S_FIVES_PORT 8105)
AGENT_PORT=$(env_value B2S_AGENT_PORT 8180)
API_BIND=127.0.0.1
if [ "$(web_location)" = annex ]; then API_BIND=0.0.0.0; fi

run() { if [ -n "$STAGE" ]; then echo "  (stage) $*"; else "$@"; fi; }
owner() { [ -n "$STAGE" ] || chown "$@"; }

python_bin() {
  local candidate
  for candidate in "${B2S_PYTHON:-}" python3.14 python3.13 python3.12; do
    [ -n "$candidate" ] && command -v "$candidate" >/dev/null 2>&1 &&
      "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' && { echo "$candidate"; return; }
  done
  echo "Python 3.12 ou plus introuvable (dnf install python3.12 python3.12-devel) ; B2S_PYTHON=<chemin> pour un autre." >&2
  exit 1
}

do_secrets() {
  # Shared with the interface under httpd (b2s-web, web.env): crossed by both accounts, listed by none; each file
  # keeps its own owner
  install -d -m 0751 "$ETC"
  install -d -m 0700 "$SECRETS"
  if [ -z "$STAGE" ] && ! id "$USER_NAME" >/dev/null 2>&1; then
    useradd --system --home-dir /var/lib/borntoshare --shell /sbin/nologin "$USER_NAME"
    echo "compte système $USER_NAME créé"
  fi
  # 1. Files of the wizard (passwords of the SQL accounts)
  local file name
  for file in secrets/b2s_*; do
    [ -f "$file" ] || continue
    name=$(basename "$file")
    install -m 0400 "$file" "$SECRETS/$name"
    shred -u "$file" 2>/dev/null || rm -f "$file"
    echo "secret $name : importé de secrets/"
  done
  # 2. Generated when missing (key of the stored passwords, Redis)
  umask 077
  if [ ! -f "$SECRETS/b2s_master_key" ]; then
    head -c 32 /dev/urandom | base64 | tr -d '\n' > "$SECRETS/b2s_master_key"
    echo "secret b2s_master_key : généré (à sauvegarder à part : /etc/borntoshare/secrets/b2s_master_key)"
  fi
  if [ ! -f "$SECRETS/b2s_redis" ]; then
    head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 40 > "$SECRETS/b2s_redis"
    echo "secret b2s_redis : généré"
  fi
  for name in b2s_db_core b2s_db_migrate; do
    [ -f "$SECRETS/$name" ] || { echo "secret $name absent : lancer d'abord le wizard (make wizard)" >&2; exit 1; }
  done
  # Option files of the MariaDB client (make deploy, make backup): root only, the password never in an argument
  for name in b2s_db_migrate b2s_db_fives; do
    [ -f "$SECRETS/$name" ] || continue
    printf '[client]\npassword=%s\n' "$(cat "$SECRETS/$name")" > "$SECRETS/$name.cnf"
  done
  # The services read their secret files as b2s; the option files stay root's
  for file in "$SECRETS"/b2s_*; do
    chmod 0400 "$file"
    case "$file" in *.cnf) owner root:root "$file" ;; *) owner "$USER_NAME:$USER_NAME" "$file" ;; esac
  done
  owner root:root "$ETC"
  chmod 0751 "$SECRETS"
}

# The code of a service in <dir> (fives-scanner reuses files of capsule-runner, as its Containerfile does)
stage_code() {
  local svc=$1 next=$2
  rm -rf "$next"
  install -d "$next"
  case "$svc" in
    fives-scanner)
      install -d "$next/app/core" "$next/app/shared" "$next/app/services" "$next/app/actions"
      cp fives-scanner/requirements.txt capsule-runner/requirements-kerberos.txt "$next/"
      cp capsule-runner/app/core/__init__.py capsule-runner/app/core/settings.py "$next/app/core/"
      cp capsule-runner/app/shared/__init__.py capsule-runner/app/shared/winrm.py capsule-runner/app/shared/winrm_exec.py \
         capsule-runner/app/shared/server_scan.py capsule-runner/app/shared/name_resolution.py capsule-runner/app/shared/samba_auth.py "$next/app/shared/"
      cp capsule-runner/app/services/core_client.py capsule-runner/app/services/secret_client.py "$next/app/services/"
      cp capsule-runner/app/actions/__init__.py capsule-runner/app/actions/smb.py "$next/app/actions/"
      cp -r fives-scanner/scanner "$next/scanner" ;;
    capsule-runner)
      cp -r capsule-runner/app capsule-runner/requirements.txt capsule-runner/requirements-kerberos.txt "$next/" ;;
    *)
      cp -r "$svc/app" "$svc/requirements.txt" "$next/" ;;
  esac
  find "$next" -name '__pycache__' -prune -exec rm -rf {} +
  find "$next" -type d -name tests -prune -exec rm -rf {} +
}

venv() {
  local dir=$1 py
  if [ -n "$STAGE" ]; then echo "  (stage) venv + pip install -r requirements*.txt"; return; fi
  py=$(python_bin)
  "$py" -m venv "$dir/venv"
  "$dir/venv/bin/pip" install -q --disable-pip-version-check -r "$dir/requirements.txt"
  if [ -f "$dir/requirements-kerberos.txt" ]; then "$dir/venv/bin/pip" install -q --disable-pip-version-check -r "$dir/requirements-kerberos.txt"; fi
}

env_file() {  # name; lines NAME=value on stdin
  install -d -m 0750 "$ETC/env"
  (umask 027; cat > "$ETC/env/$1.env")
  chmod 0640 "$ETC/env/$1.env"
  owner "root:$USER_NAME" "$ETC/env/$1.env"
}

unit() {  # unit description command service-dir
  install -d "$UNITS"
  cat > "$UNITS/$1.service" <<UNIT
[Unit]
Description=BornToShare : $2
After=network-online.target b2s-redis.service
Wants=network-online.target
PartOf=borntoshare.target

[Service]
User=$USER_NAME
Group=$USER_NAME
WorkingDirectory=/opt/borntoshare/app/$4
EnvironmentFile=/etc/borntoshare/env/$4.env
ExecStart=$3
Restart=on-failure
RestartSec=5
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
CapabilityBoundingSet=

[Install]
WantedBy=borntoshare.target
UNIT
}

do_services() {
  local fives="" svc services common units
  if [ -f "$SECRETS/b2s_db_fives" ]; then fives=1; fi
  services="auth-service core-service capsule-runner${fives:+ fives-service fives-scanner}"
  install -d -m 0755 "$APP" "$CERTS"
  install -d -m 0750 "$VAR/redis"
  owner "$USER_NAME:$USER_NAME" "$VAR" "$VAR/redis"

  # Code and environments: built beside the running ones, then swapped (the running one becomes .previous)
  # The units run « venv/bin/python -m … », never the scripts of venv/bin: their first line names the .next directory
  # the environment was built in, and no longer exists once it is swapped
  for svc in $services; do
    echo "  $svc : code et environnement Python"
    stage_code "$svc" "$APP/$svc.next"
    venv "$APP/$svc.next"
  done
  # Certificates (agent, private authorities), read in /etc/b2s/certs as in the containers
  for file in capsule-runner/certs/*.pem capsule-runner/certs/*.crt capsule-runner/certs/*.key; do
    [ -f "$file" ] && install -m 0644 "$file" "$CERTS/"
  done
  if [ -f "$CERTS/agent.key" ]; then chmod 0440 "$CERTS/agent.key"; owner "root:$USER_NAME" "$CERTS/agent.key"; fi

  # Environment of each service: what podman-compose.yml gives its container, with the local addresses
  common="TZ=Europe/Paris
LOG_LEVEL=INFO
LOG_FORMAT=$(env_value LOG_FORMAT text)
INTERNAL_TOKEN=$(env_value INTERNAL_TOKEN)
PYTHONUNBUFFERED=1"
  env_file auth-service <<ENV
$common
PRINCIPAL_SIGNING_KEY=$(env_value PRINCIPAL_SIGNING_KEY)
B2S_SERVICE_TOKEN=$(env_value B2S_TOKEN_AUTH)
SESSION_STORE_BACKEND=redis
REDIS_HOST=127.0.0.1
REDIS_DB=1
REDIS_PASSWORD_FILE=/etc/borntoshare/secrets/b2s_redis
CORE_URL=http://127.0.0.1:$CORE_PORT
ENV
  env_file core-service <<ENV
$common
B2S_SECRET_MASTER_KEY_FILE=/etc/borntoshare/secrets/b2s_master_key
B2S_TOKEN_FRONTEND=$(env_value B2S_TOKEN_FRONTEND)
B2S_TOKEN_AUTH=$(env_value B2S_TOKEN_AUTH)
B2S_TOKEN_CAPSULE=$(env_value B2S_TOKEN_CAPSULE)
B2S_TOKEN_FIVES=$(env_value B2S_TOKEN_FIVES)
PRINCIPAL_SIGNING_KEY=$(env_value PRINCIPAL_SIGNING_KEY)
DB_HOST=$(env_value DB_HOST)
DB_PORT=$(env_value DB_PORT 3306)
DB_NAME=$(env_value DB_NAME borntoshare)
DB_USER=$(env_value DB_USER b2s_core)
DB_PASSWORD_FILE=/etc/borntoshare/secrets/b2s_db_core
LOGGING_DB_NAME=$(env_value LOGGING_DB_NAME borntoshare_logging)
DB_MIGRATE_USER=$(env_value DB_MIGRATE_USER b2s_migrate)
CAPSULE_BROKER_URL=redis://127.0.0.1:6379/2
REDIS_PASSWORD_FILE=/etc/borntoshare/secrets/b2s_redis
B2S_AUTH_URL=http://127.0.0.1:$AUTH_PORT
B2S_FIVES_URL=http://127.0.0.1:$FIVES_PORT
ENV
  env_file capsule-runner <<ENV
$common
CAPSULE_BROKER_URL=redis://127.0.0.1:6379/2
REDIS_PASSWORD_FILE=/etc/borntoshare/secrets/b2s_redis
RUNNER_MAX_SCOPE=$(env_value RUNNER_MAX_SCOPE write)
B2S_SERVICE_TOKEN=$(env_value B2S_TOKEN_CAPSULE)
CORE_URL=http://127.0.0.1:$CORE_PORT
ENV
  if [ -n "$fives" ]; then
    local fives_env
    fives_env="FIVES_DB_HOST=$(env_value DB_HOST)
FIVES_DB_PORT=$(env_value DB_PORT 3306)
FIVES_DB_USER=$(env_value FIVES_DB_USER b2s_fives)
FIVES_DB_PASSWORD_FILE=/etc/borntoshare/secrets/b2s_db_fives
FIVES_DB_NAME=$(env_value FIVES_DB_NAME b2s_fives)
FIVES_INVENTORY_DB_NAME=$(env_value FIVES_INVENTORY_DB_NAME b2s_fives_inventory)"
    env_file fives-service <<ENV
$common
B2S_CORE_URL=http://127.0.0.1:$CORE_PORT
B2S_SERVICE_TOKEN=$(env_value B2S_TOKEN_FIVES)
$fives_env
ENV
    env_file fives-scanner <<ENV
$common
CORE_URL=http://127.0.0.1:$CORE_PORT
SCANNER_ID=$(env_value FIVES_SCANNER_ID scanner-1)
B2S_SERVICE_TOKEN=$(env_value B2S_TOKEN_FIVES)
$fives_env
ENV
  fi

  # Redis of the system, its own instance (its password in a file only b2s reads)
  (umask 077; printf 'bind 127.0.0.1\nport 6379\nprotected-mode yes\nrequirepass %s\ndir /var/lib/borntoshare/redis\nappendonly yes\nappendfsync everysec\n' \
    "$(cat "$SECRETS/b2s_redis")" > "$ETC/redis.conf")
  chmod 0400 "$ETC/redis.conf"
  owner "$USER_NAME:$USER_NAME" "$ETC/redis.conf"

  # Units: one per process, grouped by borntoshare.target (systemctl restart borntoshare.target)
  install -d "$UNITS"
  cat > "$UNITS/borntoshare.target" <<UNIT
[Unit]
Description=BornToShare : tous les services

[Install]
WantedBy=multi-user.target
UNIT
  cat > "$UNITS/b2s-redis.service" <<UNIT
[Unit]
Description=BornToShare : Redis (file des travaux, sessions)
PartOf=borntoshare.target

[Service]
User=$USER_NAME
Group=$USER_NAME
ExecStart=$(command -v redis-server || echo /usr/bin/redis-server) /etc/borntoshare/redis.conf
Restart=on-failure
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=/var/lib/borntoshare/redis

[Install]
WantedBy=borntoshare.target
UNIT
  local bin=/opt/borntoshare/app
  unit b2s-auth "authentification" "$bin/auth-service/venv/bin/python -m uvicorn app.main:app --host $API_BIND --port $AUTH_PORT" auth-service
  unit b2s-core "API" "$bin/core-service/venv/bin/python -m uvicorn app.main:app --host $API_BIND --port $CORE_PORT" core-service
  # The worker: its agent (declared in Infrastructure › Workers as 127.0.0.1:$AGENT_PORT) and its two job queues
  if [ -f "$CERTS/agent.crt" ] && [ -f "$CERTS/agent.key" ]; then
    unit b2s-agent "agent du worker (HTTPS)" "$bin/capsule-runner/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port $AGENT_PORT --no-access-log --ssl-certfile /etc/b2s/certs/agent.crt --ssl-keyfile /etc/b2s/certs/agent.key" capsule-runner
  else
    unit b2s-agent "agent du worker" "$bin/capsule-runner/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port $AGENT_PORT --no-access-log" capsule-runner
  fi
  unit b2s-jobs "travaux du worker" "$bin/capsule-runner/venv/bin/python -m dramatiq app.jobs.tasks --queues capsule_identity capsule_provisioning capsule_acl capsule_probes" capsule-runner
  unit b2s-scans "parcours des dossiers" "$bin/capsule-runner/venv/bin/python -m dramatiq app.jobs.tasks --queues capsule_scans --processes 1 --threads 2" capsule-runner
  units="b2s-redis b2s-auth b2s-core b2s-agent b2s-jobs b2s-scans"
  if [ -n "$fives" ]; then
    unit b2s-fives "module 5S" "$bin/fives-service/venv/bin/python -m uvicorn app.main:app --host $API_BIND --port $FIVES_PORT" fives-service
    unit b2s-scanner "scanner du module 5S" "$bin/fives-scanner/venv/bin/python -m scanner" fives-scanner
    units="$units b2s-fives b2s-scanner"
  fi

  # Swap: the running code becomes the rollback point, then restart
  for svc in $services; do
    if [ -d "$APP/$svc" ]; then rm -rf "$APP/$svc.previous"; mv "$APP/$svc" "$APP/$svc.previous"; fi
    mv "$APP/$svc.next" "$APP/$svc"
  done
  run systemctl daemon-reload
  # shellcheck disable=SC2086
  run systemctl enable borntoshare.target $units
  # shellcheck disable=SC2086
  run systemctl restart $units
  # The target itself too: « systemctl restart borntoshare.target » (rollback, documentation) acts on its units
  run systemctl start borntoshare.target
  echo "  unités : $units"
}

case "${1:-}" in
  secrets) do_secrets ;;
  services) do_services ;;
  *) echo "usage: $0 secrets|services" >&2; exit 2 ;;
esac
