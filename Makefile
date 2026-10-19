# ============================================================
# BornToShare — podman-compose.yml + .env (same directory)
# ============================================================

COMPOSE := podman-compose -f podman-compose.yml

.PHONY: help build up down restart ps logs logs-% wizard wizard-down clean

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

.env:
	@echo "Missing .env: copy .env.example to .env and fill it in." && exit 1

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
