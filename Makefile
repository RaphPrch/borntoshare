# ============================================================
# BornToShare — podman-compose.yml + .env (same directory)
# ============================================================

COMPOSE := podman-compose -f podman-compose.yml

.PHONY: backup help build up down restart ps logs logs-% wizard wizard-url wizard-down reset-admin mail-up mail-down clean ad-lab-up ad-lab-down ad-lab-reset ad-lab-logs deploy lint

help:
	@echo "make build          build the images"
	@echo "make up             build if needed and start the stack"
	@echo "make down           stop the stack"
	@echo "make restart        down + up"
	@echo "make ps             containers status"
	@echo "make logs           follow all logs   (make logs-auth-service: one service)"
	@echo "make backup         save the two databases to backups/ (not the key of the secrets)"
	@echo "make wizard         start the database wizard (http://<host>:\$$WIZARD_PORT)"
	@echo "make wizard-url     show again the address of the wizard (with its one-time token)"
	@echo "make wizard-down    stop the wizard"
	@echo "make reset-admin    lost password of a local account (ACCOUNT=admin): a temporary one, to change at sign-in"
	@echo "make clean          stop, then remove unused images and the Redis queue"
	@echo "make deploy         database packs, rollback point, build and recreate the services"
	@echo "make lint           Python lint of the four services (Ruff, rules in ruff.toml)"
	@echo "make ad-lab-up      test Active Directory adlab.example.test (end-to-end tests, never in production)"
	@echo "make ad-lab-down    stop it (data kept)     make ad-lab-reset: stop and delete its domain"

.env:
	@echo "Missing .env: copy .env.example to .env and fill it in." && exit 1

deploy: .env
	./scripts/deploy.sh

build: .env
	$(COMPOSE) build

up: .env
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

restart: down up

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=200

logs-%:
	$(COMPOSE) logs -f --tail=200 $*

backup: .env
	./scripts/backup.sh

wizard: .env
	install -d -m 700 secrets
	@# A new one-time token at each start: the wizard answers only the address that carries it
	@umask 077; python3 -c "import secrets; print(secrets.token_urlsafe(24))" > secrets/.wizard-token
	podman-compose --profile wizard -f podman-compose.yml up -d --build wizard-ui
	@# After the installation, without a command: .env, make deploy, then the stop of the wizard (scripts/after-wizard.sh)
	@setsid -f scripts/after-wizard.sh >> secrets/.after-wizard.log 2>&1 < /dev/null
	@echo "Wizard started. Once the installation is done, the deployment follows by itself."
	@$(MAKE) --no-print-directory wizard-url

wizard-url:
	@test -s secrets/.wizard-token || { echo "No wizard running: make wizard"; exit 1; }
	@echo "Open: http://$$(hostname -I | awk '{print $$1}'):$$(grep -E '^WIZARD_PORT=' .env | cut -d= -f2 | grep . || echo 8080)/?t=$$(cat secrets/.wizard-token)"

wizard-down:
	podman-compose --profile wizard -f podman-compose.yml stop wizard-ui
	@rm -f secrets/.wizard-token

# Lost password of a local account (ACCOUNT=admin by default): a temporary one, typed on the server, changed at the next sign-in
reset-admin: .env
	@./scripts/reset-admin.sh "$(or $(ACCOUNT),admin)"

# Test mail server of the lab: every e-mail of BornToShare ends there (http://<host>:8025), nothing goes out
mail-up: .env
	podman-compose --profile mail -f podman-compose.yml up -d mailpit

mail-down:
	podman-compose --profile mail -f podman-compose.yml stop mailpit

clean: down
	podman volume rm -f b2s-redis-data
	podman image prune -f

# ------------------------------------------------------------
# Test Active Directory (testing/ad-lab): end-to-end tests only
# ------------------------------------------------------------
AD_LAB := podman-compose -f testing/ad-lab/compose.yml

ad-lab-up:
	@podman network exists b2s-app || (echo "Start the stack first (make up): the lab joins its b2s-app network." && exit 1)
	$(AD_LAB) up -d --build
	@echo "adlab.example.test: provisioning takes about a minute the first time (make ad-lab-logs)."

ad-lab-down:
	$(AD_LAB) down

ad-lab-reset:
	$(AD_LAB) down
	-podman volume rm b2s-ad-lab-samba b2s-ad-lab-shares

ad-lab-logs:
	$(AD_LAB) logs -f --tail=100

lint:
	podman run --rm -e PIP_DISABLE_PIP_VERSION_CHECK=1 -v "$(CURDIR)":/src:z,ro -w /src docker.io/library/python:3.14-slim-trixie \
		sh -c "pip install -q --root-user-action=ignore ruff==0.13.0 >/dev/null && ruff check --no-cache core-service auth-service capsule-runner wizard-ui"
