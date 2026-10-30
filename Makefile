# ============================================================
# BornToShare — podman-compose.yml + .env (same directory)
# ============================================================

COMPOSE := podman-compose -f podman-compose.yml

.PHONY: help build up down restart ps logs logs-% wizard wizard-down clean ad-lab-up ad-lab-down ad-lab-reset ad-lab-logs deploy

help:
	@echo "make build          build the images"
	@echo "make up             build if needed and start the stack"
	@echo "make down           stop the stack"
	@echo "make restart        down + up"
	@echo "make ps             containers status"
	@echo "make logs           follow all logs   (make logs-auth-service: one service)"
	@echo "make wizard         start the database wizard (http://<host>:\$$WIZARD_PORT)"
	@echo "make wizard-down    stop the wizard"
	@echo "make clean          stop, then remove unused images and the Redis queue"
	@echo "make deploy         database packs, rollback point, build and recreate the services"
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

wizard: .env
	$(COMPOSE) --profile wizard up -d --build wizard-ui

wizard-down:
	$(COMPOSE) --profile wizard stop wizard-ui

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
