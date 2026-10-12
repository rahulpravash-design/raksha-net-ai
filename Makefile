# RAKSHA NET AI — common development tasks.
#
#   make help
.DEFAULT_GOAL := help
.PHONY: help bootstrap up down logs migrate seed dev-backend dev-citizen \
        dev-control check test test-backend test-frontend lint format clean

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "} {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

bootstrap: ## Prepare a fresh checkout for development
	./scripts/bootstrap.sh

up: ## Start the full stack in Docker
	docker compose up -d

down: ## Stop the stack
	docker compose down

logs: ## Follow the stack logs
	docker compose logs -f

migrate: ## Apply database migrations
	./scripts/migrate.sh

seed: ## Load synthetic development data
	./scripts/seed.sh --reset

dev-backend: ## Run the API with reload
	./scripts/dev_backend.sh

dev-citizen: ## Run the citizen web app
	npm run dev:citizen

dev-control: ## Run the control centre
	npm run dev:control

check: ## Run the full quality gate, as CI does
	./scripts/check.sh

test: test-backend test-frontend ## Run every test suite

test-backend: ## Run the backend and AI test suites
	cd backend && .venv/bin/pytest -q
	PYTHONPATH=. backend/.venv/bin/pytest ai/tests -q

test-frontend: ## Run the frontend test suites
	npm run test --workspaces --if-present

lint: ## Lint everything
	backend/.venv/bin/ruff check backend
	cd backend && .venv/bin/mypy app
	npm run lint --workspaces --if-present

format: ## Format the backend
	backend/.venv/bin/black backend
	backend/.venv/bin/ruff check --fix backend

clean: ## Remove build artefacts and caches
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
	find . -type d -name .ruff_cache -prune -exec rm -rf {} +
	find . -type d -name .mypy_cache -prune -exec rm -rf {} +
	rm -rf apps/*/.next
