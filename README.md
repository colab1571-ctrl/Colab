# Colab — Monorepo

AI-powered networking and collaboration platform for creators. Quality-first build.

## Entry Points

| Area | Path | Command |
|---|---|---|
| Mobile app (RN/Expo) | `apps/mobile/` | `pnpm --filter mobile start` |
| Consumer web | `apps/consumer-web/` | `pnpm --filter consumer-web dev` |
| Admin web | `apps/admin-web/` | `pnpm --filter admin-web dev` |
| Marketing web | `apps/marketing-web/` | `pnpm --filter marketing-web dev` |
| Shared UI library | `packages/ui/` | `pnpm --filter @colab/ui build` |
| Design tokens | `packages/design-tokens/` | `pnpm --filter @colab/design-tokens build` |
| Python shared lib | `packages/colab_common/` | `uv pip install -e packages/colab_common` |
| API gateway | `services/gateway-svc/` | `uv run uvicorn app.main:app --reload` |
| Hello service | `services/hello-svc/` | `uv run uvicorn app.main:app --port 8001 --reload` |

## Quick Start

```bash
# Node + Python deps
make bootstrap

# Lint
make lint

# Test (requires testcontainers-compatible Docker)
make test

# OpenAPI regen (services must be running)
make openapi

# Build all apps
make build
```

## Repo Layout

```
/
├── apps/
│   ├── mobile/             # React Native / Expo SDK 53
│   ├── marketing-web/      # Next.js 15 — static marketing site
│   ├── consumer-web/       # Next.js 15 — main app
│   └── admin-web/          # Next.js 15 — internal console
├── services/
│   ├── gateway-svc/        # FastAPI API gateway
│   └── hello-svc/          # Pattern-proving sample service
├── packages/
│   ├── colab_common/       # Python shared library (pip-installable)
│   ├── ui/                 # @colab/ui — shadcn + Tailwind v4
│   ├── design-tokens/      # Style Dictionary source + builds
│   ├── api-types/          # Generated TS clients (make openapi)
│   └── i18n/               # Locale catalogs
├── charts/                 # Helm charts (svc base + per-service)
├── terraform/              # IaC (from P0)
├── tools/                  # Codegen scripts
└── specs/                  # Specifications
```

## Package Manager

- **JS**: `pnpm 9.x` with workspaces. Run `pnpm install` at root.
- **Python**: `uv ≥0.5` with workspace. Run `uv sync --all-packages` at root.
- **Node**: `20.x` (see `.nvmrc`). Use `nvm use` to activate.
- **Python**: `3.12` (see `.python-version`). Use `pyenv` or direct install.

## Brand

Codename `Colab`. User-facing brand TBD before launch. Use `BRAND_NAME` env var everywhere — never hard-code the string outside `packages/i18n/`.
