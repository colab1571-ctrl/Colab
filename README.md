# Colab — Monorepo

AI-powered networking and collaboration platform for creators. Quality-first build.

> **Codename**: Colab. User-facing brand name TBD before launch. Use `BRAND_NAME` env var everywhere — never hard-code the string outside `packages/i18n/`.

---

## What Is This?

Colab is a mobile-first (iOS + Android) platform that matches independent artists, musicians, designers, and creators with compatible collaborators. Core features:

- **AI-powered discovery**: Swipe-card + infinite-scroll feed matched by creative DNA, not follower count
- **Vibe Check**: Lightweight collab invite before committing to a full project
- **Collaboration workspace**: Shared chat, files, whiteboard (tldraw), and video meetings (Recall.ai)
- **AI Assistant**: In-chat commands (`/brainstorm`, `/summarize-chat`, `/mockup-image`) powered by OpenAI + Replicate
- **Identity verification**: Persona-backed Valid Profile Badge
- **Subscription billing**: RevenueCat (mobile IAP) + Stripe (web) — Free / Premium / Pro tiers + AI credit packs

Launch markets: US, Canada, Australia, New Zealand, India. 18+ platform.

---

## Monorepo Layout

```
/
├── apps/
│   ├── mobile/             # React Native / Expo SDK 53 (iOS + Android)
│   ├── marketing-web/      # Next.js 15 — static marketing site
│   ├── consumer-web/       # Next.js 15 — main app (web)
│   └── admin-web/          # Next.js 15 — internal operations console
│
├── services/               # Python FastAPI microservices (20 services)
│   ├── gateway-svc/        # API Gateway — JWT verify, rate limit, routing
│   ├── auth-svc/           # Authentication: email/phone OTP/Apple/Google OAuth, JWT
│   ├── profile-svc/        # User profiles, badges, portfolio, externals
│   ├── identity-svc/       # Persona ID verification → Valid Profile Badge
│   ├── discovery-svc/      # Feed ranking, save/hide, recommendations
│   ├── matching-svc/       # Match score computation (9×9 vocation affinity)
│   ├── invite-svc/         # Vibe Check, CollabInvite, block/unblock
│   ├── chat-svc/           # WebSocket chat, message history, presence
│   ├── moderation-svc/     # AI + human content moderation, CSAM detection
│   ├── collab-svc/         # Collaboration workspace, whiteboard (Y.js), tasks
│   ├── meeting-svc/        # Video meetings via Google Meet + Recall.ai transcripts
│   ├── ai-orchestrator-svc/# AI command intake, OpenAI + Replicate fan-out, credits
│   ├── billing-svc/        # RevenueCat + Stripe webhooks, entitlement, credit wallet
│   ├── notification-svc/   # Push (APNs/FCM), in-app, email notifications
│   ├── analytics-svc/      # PostHog event ingestion + internal metrics
│   ├── admin-svc/          # Moderation actions, feature flags, entitlement config
│   ├── support-svc/        # Support tickets, SLA timers
│   ├── geo-svc/            # Location radius matching, coarse-precision PostGIS
│   ├── media-svc/          # File upload, S3 pre-sign, virus scan, CDN
│   └── hello-svc/          # Pattern-proving sample service
│
├── packages/               # Shared libraries (pip-installable / npm workspaces)
│   ├── colab_common/       # Python: auth middleware, DB base, event schemas, logging
│   ├── ui/                 # @colab/ui — React component library (shadcn + Tailwind v4)
│   ├── design-tokens/      # @colab/design-tokens — Style Dictionary source + builds
│   ├── api-types/          # @colab/api-types — Generated TS clients (make openapi)
│   └── i18n/               # @colab/i18n — Locale catalogs (en, es, fr, hi, pt)
│
├── charts/                 # Helm charts
│   ├── svc/                # Base chart for all FastAPI services
│   ├── _template-service/  # Skeleton for new service scaffolding
│   ├── db-bootstrap/       # PostGIS + pgvector extension init job
│   ├── gateway-svc/        # Gateway-specific Helm values
│   └── hello-svc/          # Hello service Helm values
│
├── terraform/              # AWS Infrastructure as Code (IaC)
│   ├── envs/               # Per-environment tfvars (staging, prod)
│   └── modules/            # VPC, EKS, RDS, Redis, S3, MQ, SES, SNS,
│                           # Secrets, IAM-IRSA, ACM, DNS, GitHub OIDC, Budgets
│
├── loadtest/               # k6 load test scenarios
│   ├── signup-funnel.js    # 500→750 VU; Persona webhook
│   ├── feed-scroll.js      # 5k→7.5k VU; Redis cache hit rate
│   ├── chat-fanout.js      # 10k→15k VU; 100k msg/min WebSocket
│   ├── ai-commands.js      # 200→400 VU; credit idempotency
│   └── billing-webhook-storms.js # 1k→3k VU; HMAC + idempotency
│
├── docs/
│   ├── security/           # STRIDE threat model, pen-test scope, secrets runbook,
│   │                       # dependency audit, OWASP MASVS mapping
│   ├── store-submission/   # App Store Connect, Google Play, RevenueCat products
│   ├── beta/               # Recruitment plan, NDA, feedback channels, launch criteria
│   ├── ops/                # Status page config, uptime checks, incident communication
│   ├── runbooks/           # On-call rotation, paging policy, severity definitions,
│   │   │                   # incident channels, postmortem template, change mgmt SOP
│   │   └── services/       # Per-service runbooks (auth, billing, chat, moderation, AI)
│   ├── INFRA.md            # Infrastructure setup guide
│   └── adr/                # Architecture Decision Records
│
├── scripts/
│   ├── smoke/              # EKS, DB, Celery, SES, SNS smoke test scripts
│   ├── store/              # generate-screenshots.sh, upload-testflight.sh, upload-play-internal.sh
│   ├── revenuecat/         # sync-products.sh
│   └── seed_vendor_secrets.sh
│
├── tools/
│   ├── openapi-codegen/    # TypeScript client generation from OpenAPI specs
│   └── semgrep/            # Custom semgrep rules for platform-specific patterns
│
├── specs/                  # Specifications (001–019)
└── runs/                   # Pipeline state: state.json, PROJECT_LOG.md, RECONCILIATION.md
```

---

## Quick Start (New Engineer)

### Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Node.js | 20.x | `nvm install 20` (see `.nvmrc`) |
| pnpm | 9.x | `npm install -g pnpm` |
| Python | 3.12 | `pyenv install 3.12` (see `.python-version`) |
| uv | ≥ 0.5 | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Docker | 24+ | [docker.com](https://docker.com) |

### 1. Clone and bootstrap

```bash
git clone https://github.com/colab1571-ctrl/Colab.git
cd Colab

# Install all JS + Python dependencies
make bootstrap
# This runs: pnpm install + uv sync --all-packages
```

### 2. Set up environment variables

```bash
cp .env.example .env.local
# Fill in your local development values:
# - DATABASE_URL (local Postgres or Docker)
# - REDIS_URL (local Redis or Docker)
# - RABBITMQ_URL (local RabbitMQ or Docker)
# - Vendor API keys (use sandbox/test keys)
```

### 3. Start local services (Docker Compose)

```bash
# Start Postgres, Redis, RabbitMQ locally
docker compose up -d

# Apply DB migrations (once)
make db-migrate
```

### 4. Start the gateway + a service

```bash
# Terminal 1: API Gateway
uv run uvicorn app.main:app --reload --cwd services/gateway-svc

# Terminal 2: Hello service (sanity check)
uv run uvicorn app.main:app --port 8001 --reload --cwd services/hello-svc
```

### 5. Start a frontend

```bash
# Mobile (iOS/Android via Expo Go)
pnpm --filter mobile start

# Consumer web
pnpm --filter consumer-web dev

# Admin web
pnpm --filter admin-web dev
```

### 6. Run tests

```bash
# All tests
make test

# Specific service
cd services/auth-svc && uv run pytest

# Frontend lint
make lint
```

### 7. Regenerate TypeScript API clients

```bash
# Services must be running first
make openapi
```

---

## Developer Workflows

### Adding a new service

1. Copy `services/hello-svc/` as a template.
2. Add to `pnpm-workspace.yaml` and `pyproject.toml` workspace members.
3. Add a new entry in `charts/svc/values-overrides/` (Helm values).
4. Add to `terraform/modules/iam-irsa/` (IRSA role for the service).
5. Add to `.github/workflows/build-and-push.yml` and `deploy.yml`.
6. Add to `.github/dependabot.yml` (pip entry for the new service).

### Running a load test locally (against staging)

```bash
# Install k6: https://k6.io/docs/get-started/installation/
k6 run --env BASE_URL=https://api.staging.colab.test loadtest/signup-funnel.js

# Distributed run via Grafana Cloud k6
k6 cloud loadtest/chat-fanout.js
```

### Deploying to staging

Merge to `main` → GitHub Actions automatically deploys to staging via `deploy.yml`.

### Deploying to production

Production deploy requires manual approval gate in GitHub Actions. See `docs/runbooks/change-management-sop.md`.

---

## Package Manager

- **JS/TS**: `pnpm 9.x` with workspaces. Run `pnpm install` at root.
- **Python**: `uv ≥ 0.5` with workspace. Run `uv sync --all-packages` at root.
- **Node**: `20.x` (see `.nvmrc`). Use `nvm use` to activate.
- **Python**: `3.12` (see `.python-version`). Use `pyenv` or direct install.

---

## Key Architecture Decisions

See `docs/adr/` for full Architecture Decision Records. Quick reference:

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Mobile | React Native + Expo | Cross-platform; team familiarity; EAS for CI/CD |
| Backend | Python FastAPI microservices | Type safety; async; team preference |
| Database | Postgres 16 + pgvector + PostGIS | Single DB; vector search; geo queries |
| Service mesh | None at launch | Kubernetes NetworkPolicy + HS256 internal tokens; revisit v1.1 |
| WebSocket | 3 concurrent connections per client | chat-svc + collab-svc + notification-svc; consolidate in v1.1 |
| Auth | Custom JWT (RS256) | Full control; no vendor lock; JWKS endpoint |
| IAP | RevenueCat | Unified entitlement layer across iOS + Android + web |
| Analytics | PostHog (self-hosted or cloud) | First-party; no ATT required; GDPR-grade |
| AI | OpenAI + Replicate | GPT-4 for text; Replicate for image gen |
| CDN | CloudFront + S3 | Native AWS; signed URLs for private content |

---

## Security

All security documentation is in `docs/security/`:

- **Threat model**: `threat-model-stride.md` — STRIDE per service; 7 priority services fully detailed
- **Pen test**: `pen-test-scope.md` — vendor scope, in/out-of-scope, timeline
- **Secrets**: `secrets-rotation-runbook.md` — rotation cadences; emergency procedure (30 min SLA)
- **Dependency audit**: `dependency-audit.md` — Trivy + Snyk + semgrep + bandit + Dependabot
- **Mobile**: `owasp-masvs-mapping.md` — MASVS L1 control mapping for React Native

Security scan CI: `.github/workflows/security-scan.yml` runs on every PR.

---

## Ops + On-Call

- **Status page**: `docs/ops/status-page-config.yaml` (Statuspage.io)
- **Uptime checks**: `docs/ops/uptime-checks.md` (Pingdom)
- **On-call rotation**: `docs/runbooks/oncall-rotation.md` (PagerDuty)
- **Paging policy**: `docs/runbooks/paging-policy.md` — P1–P4 definitions
- **Severity**: `docs/runbooks/severity-definitions.md`
- **Postmortem template**: `docs/runbooks/postmortem-template.md`
- **Change management**: `docs/runbooks/change-management-sop.md` — freeze windows, deploy gates
- **Service runbooks**: `docs/runbooks/services/` — auth, billing, chat, moderation, AI orchestrator

---

## Pipeline Status

All 19 features from specifications 001–019 have been implemented (code, IaC, CI/CD, docs, and ops artifacts). The pipeline is **code-complete**.

Remaining work before public launch (all operator-gated, not code-gated):
1. AWS account creation + Terraform apply
2. Apple Developer enrollment ($99/yr)
3. Google Play Console enrollment ($25)
4. Vendor sign-ups: Stripe, RevenueCat, Persona, Sentry, PostHog, OpenAI, Replicate, Recall.ai
5. Apex domain name decision
6. Pen-test vendor selection + budget approval
7. Statuspage.io + PagerDuty account setup
8. Beta launch (100 invited creators, 4 weeks)

See `runs/state.json` for complete pipeline state and `docs/beta/launch-criteria.md` for the 7-gate launch checklist.

---

## Makefile Reference

```bash
make bootstrap    # Install all JS + Python dependencies
make lint         # Run all linters (eslint, ruff, mypy)
make test         # Run all tests (requires Docker for testcontainers)
make openapi      # Regenerate TS clients from running services
make build        # Build all Next.js apps
make db-migrate   # Apply Alembic migrations (all services)
make clean        # Clean build artifacts
```
