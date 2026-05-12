.PHONY: bootstrap lint test openapi openapi-check build deploy clean help \
        infra-up infra-down migrate services-up demo-smoke

# =============================================================================
# Colab Monorepo Makefile
# =============================================================================

SHELL := /bin/bash
PYTHON := python3.12
UV := uv
PNPM := pnpm

# ---------------------------------------------------------------------------
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
bootstrap: ## Install all JS + Python deps (run after clone)
	@echo "→ Installing JS dependencies..."
	$(PNPM) install
	@echo "→ Installing Python dependencies..."
	$(UV) sync --all-packages
	@echo "→ Bootstrap complete."

# ---------------------------------------------------------------------------
lint: ## Run all linters (ruff, mypy, eslint, prettier check)
	@echo "→ Python linting..."
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run mypy --strict packages/colab_common/src services
	@echo "→ JS/TS linting..."
	$(PNPM) run lint
	$(PNPM) run format:check

# ---------------------------------------------------------------------------
test: ## Run all tests (pytest + vitest/jest)
	@echo "→ Python tests..."
	$(UV) run pytest packages/colab_common/tests -v --cov=colab_common --cov-report=term-missing --cov-fail-under=80
	@echo "→ JS/TS tests..."
	$(PNPM) run test

# ---------------------------------------------------------------------------
# OpenAPI codegen pipeline
# ---------------------------------------------------------------------------
openapi: openapi-fetch openapi-generate openapi-format ## Full OpenAPI regen pipeline

openapi-fetch: ## Fetch /openapi.json from all running services
	node tools/openapi-codegen/fetch.mjs

openapi-generate: ## Run openapi-typescript for each service
	node tools/openapi-codegen/generate.mjs

openapi-format: ## Prettier-format all generated TS
	$(PNPM) prettier --write 'packages/api-types/**/*.ts'

openapi-check: openapi ## Regen then fail if any diff (CI drift gate)
	git diff --exit-code packages/api-types

# ---------------------------------------------------------------------------
build: ## Build all apps and packages
	$(PNPM) run build

# ---------------------------------------------------------------------------
deploy: ## Deploy all services via Helm (env=staging|prod required)
	@if [ -z "$(env)" ]; then echo "Usage: make deploy env=staging"; exit 1; fi
	@echo "→ Deploying to $(env)..."
	./scripts/deploy.sh $(env)

# ---------------------------------------------------------------------------
# Stage 2 — Docker Compose targets
# ---------------------------------------------------------------------------
infra-up: ## Bring up infra (postgres, redis, rabbitmq, localstack)
	docker compose up -d postgres redis rabbitmq localstack

infra-down: ## Tear down all Stage 2 containers + volumes
	docker compose down -v

migrate: ## Run all service migrations (requires infra-up)
	docker compose up --exit-code-from migrate-auth migrate-auth
	docker compose up --exit-code-from migrate-profile migrate-profile
	docker compose up --exit-code-from migrate-discovery migrate-discovery
	docker compose up --exit-code-from migrate-gateway migrate-gateway

services-up: ## Bring up gateway, auth, profile, discovery
	docker compose up -d auth-svc profile-svc discovery-svc gateway-svc

demo-smoke: ## Run the signup smoke test against localhost:8000
	bash scripts/smoke/demo_signup.sh

# ---------------------------------------------------------------------------
clean: ## Remove all build artifacts
	$(PNPM) run clean
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
