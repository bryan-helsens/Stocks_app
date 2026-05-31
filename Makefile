# =============================================================================
# DivTrack — developer & ops convenience commands.
# =============================================================================
.DEFAULT_GOAL := help
COMPOSE := docker compose
BACKEND := backend

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ----- Environment -----------------------------------------------------------
.PHONY: env
env: ## Create .env from the template if missing
	@test -f .env || (cp .env.example .env && echo "Created .env from template")

# ----- Docker lifecycle ------------------------------------------------------
.PHONY: up
up: env ## Build and start the full stack (detached)
	$(COMPOSE) up -d --build

.PHONY: down
down: ## Stop and remove containers
	$(COMPOSE) down

.PHONY: logs
logs: ## Tail logs for all services
	$(COMPOSE) logs -f --tail=100

.PHONY: ps
ps: ## Show running services
	$(COMPOSE) ps

.PHONY: restart
restart: down up ## Restart the stack

# ----- Database --------------------------------------------------------------
.PHONY: migrate
migrate: ## Apply database migrations inside the api container
	$(COMPOSE) exec api alembic upgrade head

.PHONY: revision
revision: ## Autogenerate a new migration (msg="...")
	$(COMPOSE) exec api alembic revision --autogenerate -m "$(msg)"

.PHONY: seed
seed: ## Seed reference data (brokers, demo assets)
	$(COMPOSE) exec api python -m scripts.seed_db

.PHONY: psql
psql: ## Open a psql shell
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-divtrack} -d $${POSTGRES_DB:-divtrack}

# ----- Backend dev (local venv) ----------------------------------------------
.PHONY: install
install: ## Install backend deps into a local venv
	cd $(BACKEND) && python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"

.PHONY: test
test: ## Run the backend test suite
	cd $(BACKEND) && . .venv/bin/activate && PYTHONPATH=. pytest

.PHONY: lint
lint: ## Lint & type-check the backend
	cd $(BACKEND) && . .venv/bin/activate && ruff check app tests && mypy app

.PHONY: fmt
fmt: ## Auto-format / fix lint issues
	cd $(BACKEND) && . .venv/bin/activate && ruff check --fix app tests

.PHONY: run
run: ## Run the API locally with autoreload
	cd $(BACKEND) && . .venv/bin/activate && uvicorn app.main:app --reload

# ----- Frontend --------------------------------------------------------------
.PHONY: app
app: ## Run the Flutter app (requires Flutter SDK)
	cd frontend && flutter run

.PHONY: app-build
app-build: ## Build the Flutter web/desktop bundle
	cd frontend && flutter build web
