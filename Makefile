# ============================================================
# BornToShare — podman-compose.yml + .env (same directory)
# ============================================================

COMPOSE := podman-compose -f podman-compose.yml

.PHONY: backup help build up down restart ps logs logs-% wizard wizard-check wizard-down reset-admin uninstall wizard-binary otel-up otel-logs otel-down mail-up mail-down clean ad-lab-up ad-lab-down ad-lab-reset ad-lab-logs deploy lint

help:
	@echo "make build          build the images"
	@echo "make up             build if needed and start the stack"
	@echo "make down           stop the stack"
	@echo "make restart        down + up"
	@echo "make ps             containers status"
	@echo "make logs           follow all logs   (make logs-auth-service: one service)"
	@echo "make backup         save the two databases to backups/ (not the key of the secrets)"
	@echo "make wizard         start the database wizard (http://<host>:\$$WIZARD_PORT); WIZARD=binary: the executable"
	@echo "make wizard-binary  build the wizard as a single executable (dist/b2s-wizard)"
	@echo "make wizard-check   read the prerequisites again (shown by the wizard)"
	@echo "make wizard-down    stop the wizard"
	@echo "make reset-admin    lost password of a local account (ACCOUNT=admin): a temporary one, to change at sign-in"
	@echo "make clean          stop, then remove unused images and the Redis queue"
	@echo "make deploy         database packs, rollback point, build and recreate the services"
	@echo "make uninstall      what removing BornToShare would remove; CONFIRM=yes to do it (PURGE=1: secrets, data too)"
	@echo "make lint           Python lint of the four services (Ruff, rules in ruff.toml)"
	@echo "make ad-lab-up      test Active Directory adlab.example.test (end-to-end tests, never in production)"
	@echo "make ad-lab-down    stop it (data kept)     make ad-lab-reset: stop and delete its domain"

.env:
	@echo "Missing .env: copy .env.example to .env and fill it in." && exit 1

deploy: .env
	./scripts/deploy.sh

# Removes BornToShare from this server (never the databases): CONFIRM=yes make uninstall; PURGE=1 for the secrets too
uninstall: .env
	./scripts/uninstall.sh

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

# What this server offers (podman, Python, Node.js, httpd, SELinux…) is read first: the step « Prérequis » shows it.
# Without podman, the wizard runs in its own Python environment (installation without container).
# After the installation, without a command: .env, make deploy, then the stop of the wizard (scripts/after-wizard.sh)
wizard: .env
	install -d -m 700 secrets
	@scripts/host-check.sh
	@if [ "$(WIZARD)" != binary ] && command -v podman >/dev/null 2>&1; then \
		podman-compose --profile wizard -f podman-compose.yml up -d --build wizard-ui && \
		setsid -f scripts/after-wizard.sh >> secrets/.after-wizard.log 2>&1 < /dev/null; \
	else \
		scripts/wizard-native.sh && \
		B2S_WIZARD_PID="$$(cat secrets/.wizard.pid)" setsid -f scripts/after-wizard.sh >> secrets/.after-wizard.log 2>&1 < /dev/null; \
	fi
	@echo "Wizard started. Once the installation is done, the deployment follows by itself."

# The wizard as a single executable (dist/b2s-wizard: no Python, no Podman to run it); WIZARD=binary make wizard uses it
wizard-binary:
	./wizard-ui/binary/build.sh

# Read the prerequisites again (after installing httpd, Node.js…), then « Relire » in the wizard
wizard-check:
	@scripts/host-check.sh

wizard-down:
	@if [ -f secrets/.wizard.pid ]; then kill "$$(cat secrets/.wizard.pid)" 2>/dev/null || true; fi
	-podman-compose --profile wizard -f podman-compose.yml stop wizard-ui 2>/dev/null

# Lost password of a local account (ACCOUNT=admin by default): a temporary one, typed on the server, changed at the next sign-in
reset-admin: .env
	@./scripts/reset-admin.sh "$(or $(ACCOUNT),admin)"

# Test mail server of the lab: every e-mail of BornToShare ends there (http://<host>:8025), nothing goes out
otel-up: .env
	podman-compose --profile otel -f podman-compose.yml up -d otel-lab

otel-logs:
	podman logs -f --tail=100 otel-lab

otel-down:
	podman-compose --profile otel -f podman-compose.yml stop otel-lab

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
