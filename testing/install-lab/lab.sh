#!/bin/bash
# Install lab: plays a real installation of BornToShare (wizard, then scripts/deploy.sh) on simulated hosts, each a
# container with its own hostname, address and Podman, on an isolated network with no Internet access. Test only:
# nothing here is part of an installation.
#
#   testing/install-lab/lab.sh images              lab images + archive of the product images under test
#   testing/install-lab/lab.sh run containers      one scenario: up, install, checks, clean, report
#   testing/install-lab/lab.sh run hybrid
#   testing/install-lab/lab.sh down <scenario>     removes what a scenario created (after an interruption)
#   testing/install-lab/lab.sh report              summary of the runs (Markdown)
#   B2S_LAB_DRIVE=api …                             the wizard by its API instead of its screens
#
# Scenarios
#   containers  lab-db (MariaDB) + lab-app (every service and the interface in Podman)
#   hybrid      lab-db + lab-app (services in Podman, ports open to the annex) + lab-web (annex web server: systemd,
#               httpd, Node.js; the interface is pushed to it over SSH with a key made for this run)
#
# Everything of a run lives in $B2S_LAB_CACHE/runs/<date>-<scenario> (default ~/.cache/b2s-install-lab): the
# report, the generated configuration (secrets masked), the logs. The passwords of a run are test values made for
# it, in 0600 files, removed with the run's hosts.
set -euo pipefail
LAB="$(cd "$(dirname "$0")" && pwd)"
REPO="$(git -C "$LAB" rev-parse --show-toplevel)"
CACHE="${B2S_LAB_CACHE:-$HOME/.cache/b2s-install-lab}"
PRODUCT_IMAGES=(localhost/b2s-core-service:latest localhost/b2s-auth-service:latest localhost/b2s-capsule-runner:latest
  localhost/b2s-frontend-service:latest localhost/b2s-wizard-ui:latest docker.io/library/redis:8.10 docker.io/library/mariadb:11.4)
CONTROLLER_IMAGE="${B2S_LAB_CONTROLLER_IMAGE:-localhost/b2s-pw:latest}"

say() { printf '\n== %s\n' "$*"; }

# ---- images ---------------------------------------------------------------------------------------------------------
images() {
  mkdir -p "$CACHE"
  podman image exists localhost/b2s-lab-app-host || podman build -q -t localhost/b2s-lab-app-host -f "$LAB/Containerfile.app-host" "$LAB"
  podman image exists localhost/b2s-lab-web-host || podman build -q -t localhost/b2s-lab-web-host -f "$LAB/Containerfile.web-host" "$LAB"
  # The product images under test, saved once per set of image ids (the archive is reloaded in each simulated host)
  local ids
  ids=$(podman image inspect --format '{{.Id}}' "${PRODUCT_IMAGES[@]}" | sha256sum | cut -c1-16)
  if [ "$(cat "$CACHE/product-images.id" 2>/dev/null)" != "$ids" ]; then
    say "archive des images produit ($ids)"
    rm -f "$CACHE/product-images.tar"
    podman save -m -o "$CACHE/product-images.tar" "${PRODUCT_IMAGES[@]}"
    echo "$ids" > "$CACHE/product-images.id"
  fi
}

# ---- one scenario ---------------------------------------------------------------------------------------------------
setup_scenario() {
  SCEN="$1"
  # TOPO: the hosts of the scenario; « faults » breaks a hybrid installation one way at a time
  case "$SCEN" in containers) NET_N=31; TOPO=containers ;; hybrid) NET_N=32; TOPO=hybrid ;; faults) NET_N=33; TOPO=hybrid ;;
    *) echo "scénario inconnu : $SCEN (containers, hybrid, faults)" >&2; exit 1 ;; esac
  P="b2s-lab-$SCEN"
  NET="$P"
  SUBNET="10.89.$NET_N.0/24"
  IP_DB="10.89.$NET_N.5"; IP_APP="10.89.$NET_N.10"; IP_WEB="10.89.$NET_N.20"
}

# Appends a step to the steps file of the run: step NAME OK(0|1) SECONDS DETAIL
step() {
  python3 - "$RUN/steps.json" "$1" "$2" "$3" "$4" <<'PY'
import json, sys
path, name, ok, seconds, detail = sys.argv[1:]
try:
    steps = json.load(open(path))
except (OSError, ValueError):
    steps = []
steps.append({"step": name, "ok": ok == "0", "seconds": float(seconds), "detail": detail[:900], "by": "lab"})
json.dump(steps, open(path, "w"), indent=2, ensure_ascii=False)
PY
  if [ "$2" = 0 ]; then echo "OK  $1 · ${4:0:160}"; else echo "KO  $1 · ${4:0:160}"; fi
}

# check NAME COMMAND…: runs it, records ok/ko, its duration and the last lines of its output
check() {
  local name="$1" started out rc
  shift
  started=$SECONDS
  set +e
  out=$("$@" 2>&1)
  rc=$?
  set -e
  step "$name" "$rc" "$((SECONDS - started))" "$(echo "$out" | tail -8)"
  return 0
}

app() { podman exec -w /srv/borntoshare "$P-app" "$@"; }
web() { podman exec "$P-web" "$@"; }
secret() { head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c "${1:-32}"; }

up() {
  setup_scenario "$1"
  RUN="$CACHE/runs/$(date +%Y%m%d-%H%M%S)-$SCEN"
  mkdir -p "$RUN/repo" "$RUN/storage" "$RUN/config"
  chmod 0700 "$RUN"
  echo "$RUN" > "$CACHE/current-$SCEN"
  say "$SCEN : hôtes simulés ($SUBNET, sans accès Internet) — $RUN"
  podman network create --internal --subnet "$SUBNET" "$NET" >/dev/null
  # Test values made for this run only
  (umask 077; secret 24 > "$RUN/db-root.pw"; secret 20 > "$RUN/admin.pw")

  podman run -d --name "$P-db" --hostname lab-db --network "$NET:ip=$IP_DB,alias=lab-db" \
    -e MARIADB_ROOT_PASSWORD_FILE=/run/lab/root.pw -v "$RUN/db-root.pw:/run/lab/root.pw:ro,z" \
    docker.io/library/mariadb:11.4 >/dev/null

  # The code under test: the committed tree (the report gives its commit)
  git -C "$REPO" archive HEAD | tar -x -C "$RUN/repo"
  git -C "$REPO" describe --always --dirty > "$RUN/commit"
  local origin="http://lab-app:3000"
  [ "$TOPO" = hybrid ] && origin="https://lab-web"
  # .env of a new installation (as the documentation asks: .env.example filled in), the wizard adds the rest
  sed -e "s|^INTERNAL_TOKEN=.*|INTERNAL_TOKEN=$(secret 48)|" -e "s|^PRINCIPAL_SIGNING_KEY=.*|PRINCIPAL_SIGNING_KEY=$(secret 48)|" \
      -e "s|^DB_HOST=.*|DB_HOST=lab-db|" -e "s|^FRONTEND_PUBLIC_ORIGIN=.*|FRONTEND_PUBLIC_ORIGIN=$origin|" \
      "$REPO/.env.example" > "$RUN/repo/.env"
  chmod 0600 "$RUN/repo/.env"

  podman run -d --privileged --name "$P-app" --hostname lab-app --network "$NET:ip=$IP_APP,alias=lab-app" \
    -v "$RUN/repo:/srv/borntoshare:z" -v "$RUN/storage:/var/lib/containers:z" \
    -v "$CACHE/product-images.tar:/lab/images.tar:ro,z" localhost/b2s-lab-app-host >/dev/null
  check "hôte lab-app : images produit chargées (sans registre)" app podman load -q -i /lab/images.tar

  if [ "$TOPO" = hybrid ]; then
    ssh-keygen -q -t ed25519 -N '' -C "b2s-install-lab" -f "$RUN/lab_ed25519"
    podman run -d --name "$P-web" --hostname lab-web --network "$NET:ip=$IP_WEB,alias=lab-web" localhost/b2s-lab-web-host >/dev/null
    for _ in $(seq 1 30); do web systemctl is-system-running 2>/dev/null | grep -qE 'running|degraded' && break; sleep 2; done
    podman cp "$RUN/lab_ed25519.pub" "$P-web:/home/labdeploy/.ssh/authorized_keys"
    web sh -c 'chown labdeploy: /home/labdeploy/.ssh/authorized_keys && chmod 0600 /home/labdeploy/.ssh/authorized_keys'
    web sh -c 'install -d -m 0755 /etc/pki/lab && openssl req -x509 -newkey rsa:2048 -nodes -days 7 -subj /CN=lab-web \
      -addext subjectAltName=DNS:lab-web -keyout /etc/pki/lab/web.key -out /etc/pki/lab/web.crt 2>/dev/null && chmod 0600 /etc/pki/lab/web.key'
    app install -d -m 0700 /root/.ssh
    podman cp "$RUN/lab_ed25519" "$P-app:/root/.ssh/lab_ed25519"
    app chmod 0600 /root/.ssh/lab_ed25519
    check "hôte lab-web : systemd, sshd, httpd, Node.js" web sh -c 'systemctl is-active sshd && httpd -v | head -1 && node --version'
  fi
}

plan_json() {
  local deploy
  if [ "$TOPO" = containers ]; then
    deploy='{"mode": "containers", "web": {"origin": "http://lab-app:3000", "published_port": 3000}}'
  else
    deploy=$(jq -n --arg ip "$IP_WEB" '{mode: "hybrid",
      web: {location: "annex", server_name: "lab-web", https_port: 443, cert: "/etc/pki/lab/web.crt", key: "/etc/pki/lab/web.key"},
      network: {auth_port: 8101, core_port: 8102, fives_port: 8105, web_host: "lab-web", web_ip: $ip, api_host: "lab-app",
                push: "ssh", ssh_user: "labdeploy", ssh_key: "/root/.ssh/lab_ed25519"}}')
  fi
  # B2S_LAB_DRIVE: « screens » (default) plays the wizard by its screens in a browser, « api » calls its API
  jq -n --arg root "$(cat "$RUN/db-root.pw")" --arg admin "$(cat "$RUN/admin.pw")" --argjson deploy "$deploy" --arg scen "$SCEN" --arg topo "$TOPO" \
     --arg drive "$([ "$SCEN" = faults ] && echo api || echo "${B2S_LAB_DRIVE:-screens}")" '{
    scenario: $scen, drive: $drive, wizard_url: "http://lab-app:8080",
    app_url: (if $topo == "containers" then "http://lab-app:3000" else "https://lab-web" end),
    plan: {server: {host: "lab-db", port: 3306, user: "root", password: $root},
           app: {db_name: "borntoshare", logging_db_name: "borntoshare_logs", user: "b2s_app", migrate_user: "b2s_migrate"},
           admin: {username: "admin", email: "admin@lab.test", password: ("Lab-" + $admin + "-9a")},
           modules: {governance: true}, deploy: $deploy}}'
}

checks_after_install() {
  local services="core-service auth-service capsule-runner redis"
  [ "$TOPO" = containers ] && services="$services frontend-service"
  # Configuration generated by the wizard and the deployment (secret values masked)
  check "configuration : .env complété par le wizard" app sh -c "grep -E '^(B2S_DEPLOY_MODE|DB_HOST|FRONTEND_PUBLIC_ORIGIN|B2S_WEB_[A-Z_]+|B2S_API_HOST|B2S_[A-Z]+_PORT)=' .env"
  app sh -c "sed -E 's/^([A-Z_]*(TOKEN|KEY|PASSWORD|SECRET)[A-Z_]*)=.*/\1=***masqué***/' .env" > "$RUN/config/env.masked" || true
  app sh -c 'podman secret ls --format "{{.Name}}"' > "$RUN/config/podman-secrets.txt" || true
  cp "$RUN/repo/podman-compose.yml" "$RUN/config/"; [ "$TOPO" = hybrid ] && cp "$RUN/repo/podman-compose.hybrid.yml" "$RUN/config/"
  app sh -c 'cat secrets/.deploy.log 2>/dev/null' > "$RUN/config/deploy.log" || true
  check "configuration : secrets podman créés" app sh -c 'names=$(podman secret ls --format "{{.Name}}" | sort | tr "\n" " "); echo "$names"; echo "$names" | grep -q b2s_db_core'
  check "images et versions en service" app sh -c "podman ps --format '{{.Names}} {{.Image}} {{.ImageID}}' | sort"
  check "healthchecks : services sains ($services)" app sh -c "for s in $services; do st=\$(podman inspect -f '{{.State.Health.Status}}' \$s 2>/dev/null || echo absent); echo \"\$s \$st\"; [ \"\$st\" = healthy ] || bad=1; done; [ -z \"\${bad:-}\" ]"
  check "connectivité : core → base et file Redis (/health)" app podman exec core-service python3 -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())"
  check "connectivité : core → auth-service, capsule-runner" app podman exec core-service python3 -c "
import urllib.request
for url in ('http://auth-service:8000/health', 'http://capsule-runner:8080/health'):
    print(url, urllib.request.urlopen(url, timeout=5).status)"
  check "bases initialisées (tables, administrateur)" podman exec "$P-db" sh -c 'MYSQL_PWD="$(cat /run/lab/root.pw)" mariadb -N -e "
    SELECT CONCAT(table_schema, \": \", COUNT(*), \" tables\") FROM information_schema.tables WHERE table_schema IN (\"borntoshare\", \"borntoshare_logs\") GROUP BY table_schema;
    SELECT CONCAT(\"administrateurs : \", COUNT(*)) FROM borntoshare.identities WHERE username = \"admin\";"'
  if [ "$TOPO" = hybrid ]; then
    check "hybride : services publiés pour l'annexe (B2S_API_BIND)" app sh -c "podman port auth-service; podman port core-service"
    check "hybride : lab-web joint auth et core sur lab-app" web sh -c 'curl -s -o /dev/null -w "auth %{http_code}\n" http://lab-app:8101/health && curl -s -o /dev/null -w "core %{http_code}\n" http://lab-app:8102/health'
    check "hybride : b2s-web et httpd actifs sur lab-web (systemd)" web sh -c 'systemctl is-active b2s-web httpd && systemctl is-enabled b2s-web httpd'
    check "hybride : vhost et certificat sur lab-web" web sh -c 'httpd -t 2>&1 | tail -1; curl -sk -o /dev/null -w "https://lab-web/login %{http_code}\n" https://lab-web/login'
    web cat /etc/httpd/conf.d/borntoshare.conf > "$RUN/config/lab-web-borntoshare.conf" 2>/dev/null || true
    web sh -c "sed -E 's/=.*/=***masqué***/' /etc/borntoshare/web.secrets; cat /etc/borntoshare/web.env" > "$RUN/config/lab-web-env.masked" 2>/dev/null || true
  fi
}

checks_resilience() {
  # Repeated installation: make deploy again on the installed host (idempotent packs, data kept)
  check "réinstallation : make deploy une 2e fois" app sh -c 'FORCE=1 make deploy > /tmp/redeploy.log 2>&1; rc=$?; tail -4 /tmp/redeploy.log; exit $rc'
  check "réinstallation : l'administrateur et ses données restent" podman exec "$P-db" sh -c 'MYSQL_PWD="$(cat /run/lab/root.pw)" mariadb -N -e "SELECT CONCAT(\"administrateurs : \", COUNT(*)) FROM borntoshare.identities WHERE username = \"admin\""'
  # Restart of the services after a stop
  check "redémarrage : arrêt puis reprise des services" app sh -c 'podman stop -t 10 core-service auth-service redis >/dev/null && podman start redis auth-service core-service >/dev/null &&
    for i in $(seq 1 40); do [ "$(podman inspect -f "{{.State.Health.Status}}" core-service)" = healthy ] && echo "core sain après $((i*3)) s" && exit 0; sleep 3; done; exit 1'
  # A degraded situation: the database stops, the core says so, then comes back alone
  check "panne simulée : base indisponible détectée par le core" sh -c "podman stop -t 5 $P-db >/dev/null; sleep 4;
    podman exec -w /srv/borntoshare $P-app podman exec core-service python3 -c \"
import urllib.request, urllib.error
try:
    urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=10); print('health 200 : panne NON détectée'); raise SystemExit(1)
except urllib.error.HTTPError as e:
    print('health', e.code, e.read().decode()[:200])\""
  check "panne simulée : retour de la base, le core redevient sain" sh -c "podman start $P-db >/dev/null;
    for i in \$(seq 1 40); do podman exec $P-app podman exec core-service python3 -c \"import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)\" 2>/dev/null && echo \"sain après \$((i*3)) s\" && exit 0; sleep 3; done; exit 1"
}

# ---- faults (11.6): each one must stop with a message that names its cause, then make deploy takes it up again ----
# expect_failure NAME PATTERN COMMAND…: OK when the command fails AND its output matches PATTERN (grep -Ei)
expect_failure() {
  local name="$1" pattern="$2" started out rc
  shift 2
  started=$SECONDS
  set +e
  out=$("$@" 2>&1)
  rc=$?
  set -e
  if [ "$rc" != 0 ] && echo "$out" | grep -Eiq "$pattern"; then
    step "$name" 0 "$((SECONDS - started))" "refusé avec : $(echo "$out" | grep -Ei "$pattern" | tail -2)"
  elif [ "$rc" = 0 ]; then
    step "$name" 1 "$((SECONDS - started))" "NON détecté : la commande a réussi. $(echo "$out" | tail -3)"
  else
    step "$name" 1 "$((SECONDS - started))" "échec sans message explicite (attendu : $pattern) : $(echo "$out" | tail -4)"
  fi
  return 0
}

# The wizard's check of a MariaDB server, from the host itself; the JSON (with the password) goes on stdin
server_check_must_fail() {  # json → output; status 0 only when the wizard accepted the server
  local out
  out=$(printf '%s' "$1" | podman exec -i "$P-app" curl -s -w ' HTTP%{http_code}' -X POST -H 'content-type: application/json' \
    --data-binary @- http://127.0.0.1:8080/api/server/check)
  echo "$out"
  case "$out" in *HTTP200) return 0 ;; *) return 1 ;; esac
}

faults_before_install() {
  local root
  root=$(cat "$RUN/db-root.pw")
  for _ in $(seq 1 40); do app curl -sf -o /dev/null http://127.0.0.1:8080/health && break; sleep 3; done
  expect_failure "panne : DNS faux (serveur MariaDB inconnu)" "Unknown (MySQL|MariaDB) server host|Name or service not known|lab-nodb" \
    server_check_must_fail "$(jq -nc --arg p "$root" '{host: "lab-nodb", port: 3306, user: "root", password: $p}')"
  expect_failure "panne : port fermé (3307)" "Can't connect|Connection refused|2003" \
    server_check_must_fail "$(jq -nc --arg p "$root" '{host: "lab-db", port: 3307, user: "root", password: $p}')"
}

redeploy() { app bash -c 'FORCE=1 make deploy > /tmp/deploy.out 2>&1; rc=$?; tail -25 /tmp/deploy.out; exit $rc'; }
# The /health of the core; its answer is printed even when it is a 503 (it names the check that fails)
core_health() { app podman exec core-service python3 -c "
import urllib.request, urllib.error
try:
    print(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=10).read().decode())
except urllib.error.HTTPError as e:
    print(e.code, e.read().decode()); raise SystemExit(1)"; }

checks_faults() {
  # Database stopped during a deployment, then back
  podman stop -t 5 "$P-db" >/dev/null
  expect_failure "panne : base arrêtée pendant le déploiement" "lab-db|Can't connect|Unknown server|MariaDB|mysql" redeploy
  podman start "$P-db" >/dev/null; sleep 5
  check "reprise : make deploy après le retour de la base" redeploy

  # Redis stopped: the core says the job queue is down, then recovers
  app podman stop -t 5 redis >/dev/null
  expect_failure "panne : Redis arrêté, signalé par le core" "job_queue|redis|Connection refused" core_health
  app podman start redis >/dev/null
  check "reprise : Redis redémarré, core sain" sh -c "for i in \$(seq 1 30); do podman exec $P-app podman exec core-service python3 -c \"import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)\" 2>/dev/null && echo \"sain après \$((i*3)) s\" && exit 0; sleep 3; done; exit 1"

  # Worker stopped: the core cannot reach its agent; a deployment brings it back
  app podman stop -t 5 capsule-runner >/dev/null
  expect_failure "panne : worker arrêté, injoignable depuis le core" "capsule-runner|Name or service|refused|URLError" \
    app podman exec core-service python3 -c "import urllib.request;urllib.request.urlopen('http://capsule-runner:8080/health', timeout=5)"
  check "reprise : make deploy relance le worker" redeploy

  # Missing image on a server without Internet access: the deployment builds it, and its base image cannot be pulled
  # (no offline installation: nothing ships the images)
  app podman untag localhost/b2s-core-service:latest localhost/b2s-core-service:latest
  expect_failure "panne : image absente, serveur sans accès au registre" "registry|pull|no such host" redeploy
  app podman load -q -i /lab/images.tar >/dev/null
  check "reprise : image rechargée, make deploy" redeploy

  # Annex web server unreachable during the push of the interface
  podman stop -t 10 "$P-web" >/dev/null
  expect_failure "panne : serveur annexe injoignable (SSH)" "lab-web|ssh|Connection|resolve" redeploy
  podman start "$P-web" >/dev/null
  for _ in $(seq 1 30); do web systemctl is-active sshd >/dev/null 2>&1 && break; sleep 2; done
  check "reprise : annexe revenue, make deploy" redeploy

  # SSH to the annex (11.4): a key it does not know, an account without sudo, a host key that changed
  app sh -c 'ssh-keygen -q -t ed25519 -N "" -f /root/.ssh/lab_unknown && sed -i "s|^B2S_WEB_SSH_KEY=.*|B2S_WEB_SSH_KEY=/root/.ssh/lab_unknown|" .env'
  expect_failure "panne SSH : clé inconnue de l'annexe" "Permission denied|publickey" redeploy
  app sh -c 'sed -i "s|^B2S_WEB_SSH_KEY=.*|B2S_WEB_SSH_KEY=/root/.ssh/lab_ed25519|" .env && rm -f /root/.ssh/lab_unknown*'
  web mv /etc/sudoers.d/labdeploy /root/labdeploy.sudoers
  expect_failure "panne SSH : compte sans sudo sur l'annexe" "sudo|password is required|not in the sudoers" redeploy
  web mv /root/labdeploy.sudoers /etc/sudoers.d/labdeploy
  web sh -c 'rm -f /etc/ssh/ssh_host_*key* && ssh-keygen -A >/dev/null && systemctl restart sshd'
  expect_failure "panne SSH : clé d'hôte de l'annexe changée" "HOST IDENTIFICATION HAS CHANGED|Host key verification failed" redeploy
  # The administrator checks the new key, then removes the old one from known_hosts
  app ssh-keygen -R lab-web >/dev/null 2>&1
  check "reprise : clé d'hôte acceptée, make deploy" redeploy

  # Certificate missing on the annex
  app sed -i 's|^B2S_WEB_CERT=.*|B2S_WEB_CERT=/etc/pki/lab/absent.crt|' .env
  expect_failure "panne : certificat introuvable sur l'annexe" "Certificat|absent.crt" redeploy
  app sed -i 's|^B2S_WEB_CERT=.*|B2S_WEB_CERT=/etc/pki/lab/web.crt|' .env

  # Incomplete .env: the token shared by the services is missing
  app sh -c 'grep "^INTERNAL_TOKEN=" .env > /tmp/token.line && sed -i "/^INTERNAL_TOKEN=/d" .env'
  expect_failure "panne : .env incomplet (INTERNAL_TOKEN absent)" "INTERNAL_TOKEN" redeploy
  app sh -c 'cat /tmp/token.line >> .env && rm -f /tmp/token.line'
  check "reprise : .env complété, make deploy" redeploy
  check "reprise : connexion de bout en bout par l'annexe" web sh -c 'curl -sk -o /dev/null -w "https://lab-web/login %{http_code}\n" https://lab-web/login | grep " 200"'
}

down() {
  setup_scenario "$1"
  RUN="$(cat "$CACHE/current-$SCEN" 2>/dev/null || true)"
  podman rm -f -t 5 "$P-app" "$P-web" "$P-db" >/dev/null 2>&1 || true
  podman network rm -f "$NET" >/dev/null 2>&1 || true
  if [ -n "$RUN" ] && [ -d "$RUN" ]; then
    # The nested storage and the copy of the code are large; the passwords and the key of the run go with them
    podman unshare rm -rf "$RUN/storage" "$RUN/repo"
    rm -f "$RUN/db-root.pw" "$RUN/admin.pw" "$RUN/lab_ed25519" "$RUN/lab_ed25519.pub" "$RUN/run.json"
  fi
}

run_scenario() {
  images
  setup_scenario "$1"
  down "$SCEN" 2>/dev/null || true
  local t0=$SECONDS
  up "$SCEN"
  # The wizard, the way the documentation says (make wizard), on the simulated host
  check "wizard : make wizard sur lab-app" app make wizard
  [ "$SCEN" = faults ] && faults_before_install
  (umask 077; plan_json > "$RUN/run.json")
  say "$SCEN : installation par le wizard, déploiement, parcours (contrôleur Playwright)"
  podman run --rm --network "$NET" -v "$LAB:/lab:ro,z" -v "$RUN:/run-dir:z" --entrypoint python3 "$CONTROLLER_IMAGE" \
    /lab/controller.py /run-dir/run.json /run-dir/steps.json || true
  say "$SCEN : contrôles depuis les hôtes"
  checks_after_install
  if [ "$SCEN" = faults ]; then checks_faults; else checks_resilience; fi
  echo "$((SECONDS - t0))" > "$RUN/duration"
  say "$SCEN : nettoyage"
  down "$SCEN"
  local left
  left=$(podman ps -a --format '{{.Names}}' | grep -c "^b2s-lab-$SCEN-" || true)
  left=$((left + $(podman network ls --format '{{.Name}}' | grep -c "^b2s-lab-$SCEN$" || true)))
  step "nettoyage : aucune ressource orpheline" "$([ "$left" = 0 ] && echo 0 || echo 1)" 0 "$left conteneur(s) ou réseau restant(s)"
  python3 "$LAB/report.py" "$CACHE"
}

case "${1:-}" in
  images) images ;;
  run) run_scenario "${2:?scénario : containers, hybrid ou faults}" ;;
  down) down "${2:?scénario}" ;;
  report) python3 "$LAB/report.py" "$CACHE" ;;
  *) sed -n '2,20p' "$0"; exit 1 ;;
esac
