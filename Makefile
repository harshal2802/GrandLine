.DEFAULT_GOAL := help
SHELL := /bin/bash

# ── Config ────────────────────────────────────────────────────────────────────
COMPOSE_FILE := src/infra/docker/docker-compose.yml
BACKEND := src/backend
FRONTEND := src/frontend
VENV := $(BACKEND)/venv
PY := $(VENV)/bin/python3
PIP := $(VENV)/bin/pip

# Container runtime selection: prefer `docker compose` (Docker Desktop),
# fall back to `podman compose`. Override with COMPOSE=... if needed.
COMPOSE ?= $(shell \
	if docker compose version >/dev/null 2>&1; then echo "docker compose"; \
	elif command -v podman >/dev/null 2>&1 && podman compose version >/dev/null 2>&1; then echo "podman compose"; \
	else echo "docker compose"; fi) -f $(COMPOSE_FILE)

# ── Help ──────────────────────────────────────────────────────────────────────
.PHONY: help
help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z0-9_.-]+:.*?## / {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ── Environment ──────────────────────────────────────────────────────────────
.PHONY: podman-start
podman-start: ## Start the Podman VM if not running (macOS)
	@podman machine list --format '{{.LastUp}}' 2>/dev/null | head -1 | grep -q 'ago\|Currently running' \
		|| podman machine start

.PHONY: venv
venv: ## Create backend venv and install requirements
	@test -d $(VENV) || python3 -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -r $(BACKEND)/requirements.txt

# ── Infra (Postgres + Redis) ─────────────────────────────────────────────────
.PHONY: up
up: podman-start ## Start Postgres + Redis containers
	$(COMPOSE) up -d db redis

.PHONY: up-api
up-api: podman-start ## Start Postgres + Redis + API (all in containers)
	$(COMPOSE) up -d db redis api

.PHONY: down
down: ## Stop all containers (preserves volumes)
	$(COMPOSE) down

.PHONY: nuke
nuke: ## Stop containers AND delete volumes (full reset)
	$(COMPOSE) down -v

.PHONY: ps
ps: ## List running containers
	$(COMPOSE) ps

.PHONY: logs
logs: ## Tail logs for all services
	$(COMPOSE) logs -f --tail=200

.PHONY: logs-db
logs-db: ## Tail Postgres logs
	$(COMPOSE) logs -f --tail=200 db

.PHONY: logs-api
logs-api: ## Tail API container logs
	$(COMPOSE) logs -f --tail=200 api

.PHONY: psql
psql: ## Open psql shell inside the db container
	$(COMPOSE) exec db psql -U grandline -d grandline

.PHONY: redis-cli
redis-cli: ## Open redis-cli inside the redis container
	$(COMPOSE) exec redis redis-cli

# ── Migrations ───────────────────────────────────────────────────────────────
.PHONY: migrate
migrate: ## Apply all alembic migrations (against localhost DB)
	cd $(BACKEND) && source venv/bin/activate && PYTHONPATH=. alembic upgrade head

.PHONY: migrate-down
migrate-down: ## Roll back one alembic revision
	cd $(BACKEND) && source venv/bin/activate && PYTHONPATH=. alembic downgrade -1

.PHONY: migrate-status
migrate-status: ## Show current alembic revision
	cd $(BACKEND) && source venv/bin/activate && PYTHONPATH=. alembic current

# ── Backend (local dev, against containerized db+redis) ──────────────────────
.PHONY: api-dev
api-dev: ## Run FastAPI locally with uvicorn --reload
	cd $(BACKEND) && source venv/bin/activate && \
		GRANDLINE_DATABASE_URL=postgresql+psycopg://grandline:grandline@localhost:5432/grandline \
		GRANDLINE_REDIS_URL=redis://localhost:6379/0 \
		uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

.PHONY: test
test: ## Run full backend test suite
	cd $(BACKEND) && source venv/bin/activate && pytest -q

.PHONY: test-pipeline
test-pipeline: ## Run pipeline-specific tests only
	cd $(BACKEND) && source venv/bin/activate && \
		pytest -q tests/test_pipeline_api.py tests/test_pipeline_service.py tests/test_pipeline_graph.py

.PHONY: lint
lint: ## Ruff check + mypy
	cd $(BACKEND) && source venv/bin/activate && ruff check app/ tests/ && mypy app/

.PHONY: fmt
fmt: ## Ruff format
	cd $(BACKEND) && source venv/bin/activate && ruff format app/ tests/

# ── Frontend ─────────────────────────────────────────────────────────────────
.PHONY: frontend-install
frontend-install: ## Install frontend deps
	cd $(FRONTEND) && npm install

.PHONY: frontend-dev
frontend-dev: ## Start Next.js dev server
	cd $(FRONTEND) && npm run dev

.PHONY: frontend-test
frontend-test: ## Run frontend tests (vitest)
	cd $(FRONTEND) && npm test

# ── Full setup + start ───────────────────────────────────────────────────────
.PHONY: setup
setup: venv up migrate ## One-shot: venv + infra + migrations
	@echo ""
	@echo "  ✓ Setup complete. Next steps:"
	@echo "    make api-dev        # run the backend locally"
	@echo "    make frontend-dev   # run the frontend (separate terminal)"

.PHONY: api-mocked
api-mocked: ## Run FastAPI with PipelineService.start mocked (for smoke test)
	@PODMAN_SOCK=$$(podman machine inspect --format '{{.ConnectionInfo.PodmanSocket.Path}}' 2>/dev/null || true); \
	cd $(BACKEND) && source venv/bin/activate && \
		DOCKER_HOST=unix://$$PODMAN_SOCK \
		GRANDLINE_DATABASE_URL=postgresql+psycopg://grandline:grandline@localhost:5432/grandline \
		GRANDLINE_REDIS_URL=redis://localhost:6379/0 \
		PYTHONPATH=. python3 -m scripts.dev_api_mocked

.PHONY: smoke
smoke: ## Run the Phase 15.4 manual-test smoke script (requires infra + api-mocked up)
	cd $(BACKEND) && source venv/bin/activate && \
		GRANDLINE_DATABASE_URL=postgresql+psycopg://grandline:grandline@localhost:5432/grandline \
		GRANDLINE_REDIS_URL=redis://localhost:6379/0 \
		PYTHONPATH=. python3 -m scripts.smoke_pipeline_api
