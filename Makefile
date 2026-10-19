# ============================================================
# 🧰 BornToShare - Makefile global
# Podman / Podman Compose
# ============================================================

PROJECT_NAME := borntoshare
ROOT_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

# ------------------------------------------------------------
# Services directories (ORDER MATTERS)
# ------------------------------------------------------------
REDIS_DIR          := $(ROOT_DIR)/redis
AUTH_DIR           := $(ROOT_DIR)/auth-service
SECRET_BROKER_DIR  := $(ROOT_DIR)/secret-broker
CORE_DIR           := $(ROOT_DIR)/core-service

CAPSULE_RUNNER_DIR := $(ROOT_DIR)/capsule-runner
FRONTEND_DIR       := $(ROOT_DIR)/frontend-service
FRONTEND_SKIP_FILE := /tmp/borntoshare-skip-frontend-up

INFRA_SERVICES := \
	$(REDIS_DIR)

BACKEND_SERVICES := \
	$(AUTH_DIR) \
	$(SECRET_BROKER_DIR) \
	$(CORE_DIR)

WORKER_SERVICES := \
	$(CAPSULE_RUNNER_DIR)

UI_SERVICES := \
	$(FRONTEND_DIR)

ALL_SERVICES := \
	$(INFRA_SERVICES) \
	$(BACKEND_SERVICES) \
	$(WORKER_SERVICES) \
	$(UI_SERVICES)

# ------------------------------------------------------------
# Networks (STRICT SEGMENTATION)
# ------------------------------------------------------------
NETWORK_APP  := bts-app
NETWORK_DATA := bts-data
NETWORK_JOBS := bts-jobs

# ------------------------------------------------------------
# Podman
# ------------------------------------------------------------
COMPOSE_CMD := podman-compose
PODMAN_CMD  := podman

# ------------------------------------------------------------
# Colors
# ------------------------------------------------------------
GREEN  := \033[0;32m
YELLOW := \033[1;33m
RED    := \033[0;31m
NC     := \033[0m

# ============================================================
# Sanity checks
# ============================================================

check-compose:
	@echo "$(YELLOW)🔍 Vérification des podman-compose.yml...$(NC)"
	@for d in $(ALL_SERVICES); do \
		if [ ! -f $$d/podman-compose.yml ]; then \
			echo "$(RED)❌ $$d : podman-compose.yml manquant$(NC)"; exit 1; \
		else \
			echo "$(GREEN)✔ $$d OK$(NC)"; \
		fi \
	done

# ============================================================
# Networks (EXPLICIT & AUDITABLE)
# ============================================================

create-networks:
	@echo "$(YELLOW)🌐 Création des réseaux Zero Trust$(NC)"

	@$(PODMAN_CMD) network exists $(NETWORK_APP)  || $(PODMAN_CMD) network create $(NETWORK_APP)
	@$(PODMAN_CMD) network exists $(NETWORK_DATA) || $(PODMAN_CMD) network create --internal $(NETWORK_DATA)
	@$(PODMAN_CMD) network exists $(NETWORK_JOBS) || $(PODMAN_CMD) network create --internal $(NETWORK_JOBS)

	@echo "$(GREEN)✔ Réseaux prêts$(NC)"

# ============================================================
# Permissions (logs)
# ============================================================

fix-perms:
	@echo "$(YELLOW)🔧 Permissions$(NC)"
	@echo "$(GREEN)✔ Permissions OK$(NC)"

# ============================================================
# Port preflight
# ============================================================

prepare-frontend-port:
	@port=$$(awk -F= '/^FRONTEND_PUBLISHED_PORT=/{print $$2}' $(FRONTEND_DIR)/.env 2>/dev/null | tail -n 1); \
	port=$${port:-3000}; \
	rm -f $(FRONTEND_SKIP_FILE); \
	echo "$(YELLOW)🔎 Vérification port frontend : $$port$(NC)"; \
	$(PODMAN_CMD) rm -f frontend-service >/dev/null 2>&1 || true; \
	if command -v ss >/dev/null 2>&1 && ss -ltn "sport = :$$port" | awk 'NR > 1 { found = 1 } END { exit found ? 0 : 1 }'; then \
		if ps -eo args | grep -Eq '(^|[[:space:]])-n frontend-service([[:space:]]|$$)' || curl -fsS --max-time 2 "http://127.0.0.1:$$port" >/dev/null 2>&1; then \
			echo "$(YELLOW)⚠ Frontend déjà joignable sur le port $$port : démarrage UI ignoré pour éviter un doublon.$(NC)"; \
			touch $(FRONTEND_SKIP_FILE); \
			exit 0; \
		fi; \
		echo "$(RED)❌ Le port frontend $$port est déjà utilisé hors du conteneur frontend-service.$(NC)"; \
		ss -ltnp "sport = :$$port" || true; \
		echo "$(YELLOW)Change FRONTEND_PUBLISHED_PORT dans $(FRONTEND_DIR)/.env ou libère le port avant make up.$(NC)"; \
		exit 1; \
	fi

stop-frontend:
	@port=$$(awk -F= '/^FRONTEND_PUBLISHED_PORT=/{print $$2}' $(FRONTEND_DIR)/.env 2>/dev/null | tail -n 1); \
	port=$${port:-3000}; \
	rm -f $(FRONTEND_SKIP_FILE); \
	echo "$(YELLOW)🛑 Arrêt frontend-service$(NC)"; \
	cd $(FRONTEND_DIR) && $(COMPOSE_CMD) down >/dev/null 2>&1 || true; \
	$(PODMAN_CMD) rm -f frontend-service >/dev/null 2>&1 || true; \
	if sudo -n true >/dev/null 2>&1; then \
		sudo $(PODMAN_CMD) rm -f frontend-service >/dev/null 2>&1 || true; \
	fi; \
	if command -v ss >/dev/null 2>&1 && ss -ltn "sport = :$$port" | awk 'NR > 1 { found = 1 } END { exit found ? 0 : 1 }'; then \
		echo "$(RED)❌ Le port frontend $$port écoute encore après make down.$(NC)"; \
		echo "$(YELLOW)Un frontend a probablement été lancé dans un autre contexte Podman ou rootful.$(NC)"; \
		ps -eo pid,ppid,user,comm,args | grep -E 'frontend-service|node build/index.js' | grep -v grep || true; \
		echo "$(YELLOW)Arrête-le avec le contexte propriétaire, par exemple : sudo podman rm -f frontend-service$(NC)"; \
		exit 1; \
	fi; \
	echo "$(GREEN)✔ Frontend arrêté$(NC)"

# ============================================================
# Build
# ============================================================

build: check-compose create-networks
	@echo "$(YELLOW)🏗️  Build BornToShare$(NC)"
	@echo "$(YELLOW)📦 Préparation Redis (broker Dramatiq)$(NC)"
	@cd $(REDIS_DIR) && $(COMPOSE_CMD) pull || true
	@for d in $(ALL_SERVICES); do \
		if [ -f $$d/Containerfile ]; then \
			echo "➡️  Build $$d"; \
			cd $$d && $(COMPOSE_CMD) build; \
		fi \
	done
	@echo "$(GREEN)✔ Build terminé$(NC)"

# ============================================================
# UP / DOWN (GLOBAL)
# ============================================================

up: check-compose fix-perms create-networks prepare-frontend-port
	@echo "$(YELLOW)🚀 Démarrage BornToShare$(NC)"
	@for d in $(INFRA_SERVICES); do cd $$d && $(COMPOSE_CMD) up -d; done
	@for d in $(BACKEND_SERVICES); do cd $$d && $(COMPOSE_CMD) up -d; done
	@for d in $(WORKER_SERVICES); do cd $$d && $(COMPOSE_CMD) up -d; done
	@if [ -f $(FRONTEND_SKIP_FILE) ]; then \
		echo "$(YELLOW)⚠ UI déjà démarrée : skip frontend-service$(NC)"; \
	else \
		for d in $(UI_SERVICES); do cd $$d && $(COMPOSE_CMD) up -d; done; \
	fi
	@echo "$(GREEN)🎉 Stack démarrée$(NC)"

up-rootless: check-compose create-networks prepare-frontend-port
	@echo "$(YELLOW)🚀 Démarrage BornToShare (rootless)$(NC)"
	@for d in $(INFRA_SERVICES); do cd $$d && $(COMPOSE_CMD) up -d; done
	@for d in $(BACKEND_SERVICES); do cd $$d && $(COMPOSE_CMD) up -d; done
	@for d in $(WORKER_SERVICES); do cd $$d && $(COMPOSE_CMD) up -d; done
	@if [ -f $(FRONTEND_SKIP_FILE) ]; then \
		echo "$(YELLOW)⚠ UI déjà démarrée : skip frontend-service$(NC)"; \
	else \
		for d in $(UI_SERVICES); do cd $$d && $(COMPOSE_CMD) up -d; done; \
	fi
	@echo "$(GREEN)🎉 Stack rootless démarrée$(NC)"

down:
	@echo "$(YELLOW)🛑 Arrêt BornToShare$(NC)"
	@for d in $(ALL_SERVICES); do cd $$d && $(COMPOSE_CMD) down; done
	@$(MAKE) --no-print-directory stop-frontend
	@echo "$(GREEN)✔ Arrêt terminé$(NC)"

restart: down up

# ============================================================
# Partial startup
# ============================================================

up-infra:
	@for d in $(INFRA_SERVICES); do cd $$d && $(COMPOSE_CMD) up -d; done

up-backend:
	@for d in $(BACKEND_SERVICES); do cd $$d && $(COMPOSE_CMD) up -d; done

up-ui: prepare-frontend-port
	@if [ -f $(FRONTEND_SKIP_FILE) ]; then \
		echo "$(YELLOW)⚠ UI déjà démarrée : skip frontend-service$(NC)"; \
	else \
		for d in $(UI_SERVICES); do cd $$d && $(COMPOSE_CMD) up -d; done; \
	fi

up-redis: create-networks
	@echo "$(YELLOW)🚀 Démarrage Redis$(NC)"
	@cd $(REDIS_DIR) && $(COMPOSE_CMD) up -d
	@echo "$(GREEN)✔ Redis démarré$(NC)"

down-redis:
	@echo "$(YELLOW)🛑 Arrêt Redis$(NC)"
	@cd $(REDIS_DIR) && $(COMPOSE_CMD) down || true
	@echo "$(GREEN)✔ Redis arrêté$(NC)"

clear-redis: down-redis
	@echo "$(YELLOW)🧼 Suppression Redis (conteneurs + volumes, y compris les anciens de governance-service)$(NC)"
	@$(PODMAN_CMD) rm -f redis b2s-redis governance-service_redis_1 >/dev/null 2>&1 || true
	@$(PODMAN_CMD) volume ls --format '{{.Name}}' | grep -E 'redis' | xargs -r $(PODMAN_CMD) volume rm -f >/dev/null 2>&1 || true
	@echo "$(GREEN)✔ Redis nettoyé$(NC)"

restart-redis: down-redis up-redis

# ============================================================
# Observability / Debug
# ============================================================

ps:
	@$(PODMAN_CMD) ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

logs-core:
	@$(PODMAN_CMD) logs -f core-service

logs:
	@echo "$(YELLOW)📋 Logs des services (CTRL+C pour quitter)$(NC)"
	@for d in $(ALL_SERVICES); do \
		if [ -f $$d/podman-compose.yml ]; then \
			name=$$(basename $$d); \
			echo "$(GREEN)==> $$name$(NC)"; \
			cd $$d && $(COMPOSE_CMD) logs -f --tail=200; \
		fi; \
	done

doctor:
	@echo "$(YELLOW)🩺 Diagnostic BornToShare$(NC)"
	@$(PODMAN_CMD) ps
	@$(PODMAN_CMD) network ls
	@curl -s -o /dev/null -w "Frontend HTTP → %{http_code}\n" http://127.0.0.1:3000 || true

# ============================================================
# Maintenance
# ============================================================

clean: down
	@echo "$(RED)🧹 Clean complet$(NC)"
	@$(MAKE) clear-redis
	@$(PODMAN_CMD) volume prune -f
	@$(PODMAN_CMD) image prune -f
	@echo "$(GREEN)✔ Clean OK$(NC)"

help:
	@echo ""
	@echo "Targets disponibles :"
	@echo "  make build"
	@echo "  make up | down | restart"
	@echo "  make up-infra | up-backend | up-ui"
	@echo "  make up-redis | down-redis | restart-redis | clear-redis"
	@echo "  make ps | doctor"
	@echo "  make logs-core | logs"
	@echo "  make clean"
