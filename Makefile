.PHONY: bootstrap lint test openapi openapi-check build deploy clean help \
        demo-up demo-down demo-logs demo-migrate demo-seed demo-smoke demo-build

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
# Stage-2 Demo targets
# ---------------------------------------------------------------------------
COMPOSE := docker compose

demo-build: ## Build all 5 demo service images
	$(COMPOSE) build gateway-svc auth-svc profile-svc discovery-svc chat-svc

demo-up: ## Start the full demo stack (infra + 5 services)
	$(COMPOSE) up -d
	@echo "→ Gateway available at http://localhost:8080"
	@echo "→ RabbitMQ management at http://localhost:15672 (guest/guest)"

demo-down: ## Stop and remove demo containers
	$(COMPOSE) down

demo-logs: ## Follow logs from all demo containers
	$(COMPOSE) logs -f

demo-migrate: ## Run all service migrations
	$(COMPOSE) run --rm migrate-gateway
	$(COMPOSE) run --rm migrate-auth
	$(COMPOSE) run --rm migrate-profile
	$(COMPOSE) run --rm migrate-discovery
	$(COMPOSE) run --rm migrate-chat

demo-seed: ## Seed minimal fixtures (test user + sample profiles)
	@echo "→ Seeding demo data..."
	bash scripts/smoke/demo_seed.sh

demo-smoke: ## Run signup smoke test: signup → JWT → fetch profile
	@echo "→ Running smoke test..."
	bash scripts/smoke/demo_signup.sh

# ---------------------------------------------------------------------------
clean: ## Remove all build artifacts
	$(PNPM) run clean
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
