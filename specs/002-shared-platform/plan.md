# 002 — Shared Platform — Implementation Plan

> Status: Draft v1. Owner: Platform team. Phase: P1 (per master §7). Quality-first build (per master §0). Single consolidated plan — no split research/data-model/contracts/quickstart artifacts.

---

## 1. Mission Recap

Build the **shared substrate** every other phase (003–019) consumes so feature specs never re-litigate auth plumbing, OpenAPI codegen, RN navigation shells, Next.js layouts, telemetry SDK init, error boundaries, design tokens, or CI templates. Concretely:

- `colab_common` — Python library installed into every FastAPI service.
- `gateway-svc` — first FastAPI service, demonstrates the patterns end-to-end.
- OpenAPI → typed TS client codegen pipeline (one client per service).
- React Native + Expo base app (`apps/mobile`) wired through API Gateway → gateway-svc → stub service.
- Three Next.js App Router apps: `marketing-web`, `consumer-web`, `admin-web` sharing a `@colab/ui` package.
- Shared design tokens (single source of truth across mobile + web).
- GitHub Actions CI/CD: lint/test gates, per-service build-and-push, Helm deploy, EAS mobile build.
- Helm chart base `charts/svc/` with per-service `values.yaml`.

After this phase, any spec 003+ can `pip install colab-common`, scaffold a new FastAPI service in <30 minutes, regenerate clients with `make openapi`, and ship to EKS via the existing pipeline.

---

## 2. Research Findings — Versions & Gotchas

Every choice below is locked unless flagged `[REVIEW]`. Gotchas captured so we don't trip on them in implementation.

### Backend (Python)

| Tool | Version | Biggest gotcha |
|---|---|---|
| Python | **3.12** | f-string improvements + PEP 695 generics; do NOT use 3.13 until asyncpg + uvloop wheel coverage stabilizes. |
| uv | **≥0.5** (env + lockfile) | uv replaces pip+pip-tools+venv. Lockfile (`uv.lock`) is committed; `pyproject.toml` per service; root workspace ties them together. Gotcha: `uv pip install -e ../packages/colab_common` for local dev; CI uses lockfile-pinned wheel. |
| FastAPI | **0.115.x** | `lifespan` async context manager replaces `startup/shutdown` events; remember to register `colab_common.lifespan` from every service. |
| Pydantic | **v2.9+** | v1↔v2 migration footguns: `model_config = ConfigDict(...)` not `class Config`; `model_validate` not `parse_obj`; computed fields need `@computed_field`. |
| SQLAlchemy | **2.0.x async** (`AsyncSession`) | `expire_on_commit=False` for FastAPI request scope. Async-only style — no implicit IO inside `relationship()` lazy loaders; use `selectinload` everywhere or `await session.refresh`. |
| asyncpg | **0.30** | PgBouncer compatibility — set `statement_cache_size=0` if RDS Proxy is in front. |
| Alembic | **1.13+** | Async migrations require `async_engine_from_config` + custom env.py; `colab_common.db.alembic_env` ships a copy-pasteable template. |
| structlog | **24.x** | Bind context vars per request via middleware; output JSON to stdout for CloudWatch ingestion. |
| OpenTelemetry | **opentelemetry-instrumentation-fastapi 0.48b** | Auto-instrumentation can double-instrument if FastAPI is imported before SDK init — always call `colab_common.telemetry.init()` **before** importing `FastAPI`. |
| sentry-sdk[fastapi] | **2.x** | Sentry's FastAPI integration requires `transactions_sample_rate` separate from `traces_sample_rate`; we set both to 0.1 in prod, 1.0 in dev. |
| Celery | **5.4** + kombu | Use `acks_late=True` + `task_reject_on_worker_lost=True` for at-least-once semantics; idempotency via Redis SETNX (handled in `colab_common.idempotency`). |
| celery-redbeat | **2.x** | Schedule lives in Redis — survives beat restarts; gotcha: Beat singleton lock TTL must exceed pod restart window (default 60s OK for our case). |
| RabbitMQ | Amazon MQ for RabbitMQ 3.13 | Lazy queues for high-volume topics (chat events); classic queues for low-volume. |

### Codegen

| Tool | Version | Gotcha |
|---|---|---|
| openapi-typescript | **7.x** | Produces a `paths` map + `components.schemas`; generates `fetch`-based client. We wrap with TanStack Query in `apps/mobile` and `apps/*-web`. Gotcha: schema names must be snake_case in OpenAPI → camelCase TS; we run a post-processor (`prettier` + naming script). |

### Mobile (React Native / Expo)

| Tool | Version | Gotcha |
|---|---|---|
| Expo SDK | **53+** | Expo Router optional; we chose React Navigation v7 instead because it matches the existing team mental model and supports nested stacks more flexibly. |
| React Native | **0.79+** | New architecture (Fabric + TurboModules) enabled by default; native modules must declare codegen specs. |
| React Navigation | **v7** | API renamed: `createNativeStackNavigator` (not legacy `Stack`); deep linking config moved to `linking` prop on `NavigationContainer`. |
| TanStack Query | **v5** | Query keys are tuples now; `cacheTime` renamed to `gcTime`; persistor uses `@tanstack/react-query-persist-client`. |
| Zustand | **4.5** | Use `subscribeWithSelector` middleware to drive RN re-renders without flicker. |
| NativeWind | **v4** + Tailwind **v4** | Tailwind v4 uses `@theme` + CSS-first config; NativeWind v4 reads `tailwind.config.js` plus its own JSX transformer. Gotcha: dynamic class strings break the compiler — always full literal classes. |

### Web (Next.js)

| Tool | Version | Gotcha |
|---|---|---|
| Next.js | **≥15** (App Router) | Server Actions stable; we still prefer route handlers + RSC for type clarity. |
| shadcn/ui | latest | Not a package — components are copied. We vendor them into `packages/ui/src/components/...` and re-export. |
| Tailwind | **v4** | CSS-first config (`@theme`) — single tokens source shared with NativeWind through Style Dictionary outputs. |
| Sentry | `@sentry/nextjs` 8.x | Configure separate `client.config.ts`/`server.config.ts`/`edge.config.ts`. |
| PostHog | `posthog-js` + `posthog-node` | Reverse-proxy via Next route to avoid ad-blockers (`/ingest` proxy pattern). |

### Infrastructure

| Tool | Version | Gotcha |
|---|---|---|
| Helm | **≥3.14** | OCI registry support is default; we publish chart base to ECR-as-OCI. Gotcha: chart `apiVersion: v2` requires Helm 3; do NOT mix v1 `requirements.yaml`. |

---

## 3. Repo Layout (Monorepo)

**Decision: Single git repo, workspace structure** as proposed.

```
/
├── apps/
│   ├── mobile/             # RN/Expo (TypeScript strict)
│   ├── marketing-web/      # Next.js (static-export-friendly, SEO)
│   ├── consumer-web/       # Next.js (full app)
│   └── admin-web/          # Next.js (internal-only, IP-allowlisted)
├── services/
│   ├── gateway-svc/        # FastAPI (built in this phase)
│   ├── auth-svc/           # placeholder dir; built in 003
│   ├── profile-svc/        # placeholder; 003
│   ├── identity-svc/       # placeholder; 003
│   ├── discovery-svc/      # 005
│   ├── matching-svc/       # 005
│   ├── invite-svc/         # 006
│   ├── collab-svc/         # 008
│   ├── chat-svc/           # 007
│   ├── media-svc/          # 007
│   ├── ai-orchestrator-svc/# 011
│   ├── moderation-svc/     # 010
│   ├── notification-svc/   # 013
│   ├── billing-svc/        # 012
│   ├── support-svc/        # 014
│   ├── analytics-svc/      # 015
│   ├── admin-svc/          # 015
│   ├── geo-svc/            # 005
│   └── meeting-svc/        # 011
├── packages/
│   ├── colab_common/       # Python shared lib (installable, src-layout)
│   ├── ui/                 # @colab/ui — shadcn-based, shared web
│   ├── design-tokens/      # JSON tokens + Style Dictionary build
│   ├── api-types/          # generated TS clients (per service)
│   └── i18n/               # locale catalogs (en at launch; infra ready)
├── charts/
│   └── svc/                # Helm chart base
├── terraform/              # already exists
├── specs/                  # already exists
├── runs/                   # already exists
├── docs/
└── tools/
    ├── codegen/            # OpenAPI codegen scripts
    ├── Makefile
    └── Taskfile.yml
```

**Justification (4 sentences).** A monorepo gives us atomic cross-cutting refactors (e.g., changing the auth envelope is one PR that updates `colab_common` + every service + every TS client + every app simultaneously), which is critical given 12+ services that all share `colab_common`. The workspace split (`apps/` / `services/` / `packages/`) cleanly separates deployables from libraries and reflects different release cadences (mobile via EAS, web via S3+CloudFront, services via EKS). Tooling is well-supported: uv handles Python workspaces, pnpm (chosen as the JS package manager) handles JS workspaces, and Turborepo (lightweight, no remote cache initially) gives us incremental task graphs. The cost — slower CI clones — is mitigated by sparse-checkout in workflows that only need a subset.

**JS package manager: pnpm 9.x** with `pnpm-workspace.yaml` listing `apps/*`, `packages/*`. Lockfile at root.
**Python package manager: uv** with root `pyproject.toml` declaring `[tool.uv.workspace] members = ["services/*", "packages/colab_common"]`.

---

## 4. `colab_common` Python Library Design

Source layout: `packages/colab_common/src/colab_common/...`. Tested with pytest + coverage ≥80% gate. Exposed via `colab_common.__init__` for ergonomic imports.

| Module | Responsibility |
|---|---|
| `settings` | `BaseSettings` (pydantic-settings) with layered loading: Secrets Manager (boto3 + LRU cache, TTL 60s) → AWS Parameter Store → process env → `.env.local`. Re-export typed sub-settings: `DatabaseSettings`, `RedisSettings`, `JWTSettings`, `SentrySettings`, `OTelSettings`, `FeatureFlagSettings`. Strict mode: fails fast if a required value is missing. |
| `db` | `engine_factory(url)` for sync + async; `AsyncSessionLocal` factory; `get_session()` FastAPI dependency that creates per-request session with begin/commit/rollback. `Base = DeclarativeBase`. RLS hooks: stub for future tenant context; today injects `current_user_id` GUC for audit triggers. Alembic env template at `colab_common/db/alembic_env.py`. |
| `auth` | JWT verify (PyJWT, RS256 with key rotation pulled from Secrets Manager JWKS). `require_user()` dependency returns `AuthUser`; `require_role("moderator")` checks claims. Service-to-service auth via short-lived JWT signed with IRSA-issued private key (audience = target svc). Bearer header parsing + cookie fallback for web. |
| `errors` | `AppError` base + concrete subclasses (`AuthError`, `ValidationError`, `NotFoundError`, `RateLimitError`, `ConflictError`). Exception handler registers with FastAPI and emits standard envelope: `{ "error": { "code": "...", "message": "...", "details": {...}, "request_id": "..." } }`. Maps to HTTP codes 4xx/5xx. Adds Sentry breadcrumb + structured log entry. |
| `events` | RabbitMQ async publish via aio-pika. Topic exchanges per domain (`auth.*`, `profile.*`, `chat.*`). `publish(event_name, payload, *, dedupe_key=None)` with idempotent send (deduped via Redis SETNX before publish, TTL 1h). Outbox pattern helper: `enqueue_outbox(session, event)` writes to `event_outbox` table; relay worker drains. |
| `rate_limit` | Redis token-bucket (Lua script atomically refills + consumes). API: `bucket(key, capacity, refill_per_sec)` decorator + FastAPI dependency. Keys typically include user_id or IP. 429 raises `RateLimitError` with `Retry-After`. |
| `idempotency` | FastAPI middleware reading `Idempotency-Key` header. Caches response body keyed by `(user_id, method, path, key)` in Redis (TTL 24h). Replays cached response if same key seen again within TTL. Skip list for GET. |
| `telemetry` | One-call `init(service_name)`: OTel TracerProvider with OTLP exporter (CloudWatch ADOT collector sidecar); structlog config with JSON renderer + request_id contextvar; FastAPI middleware that creates `request_id` + propagates `traceparent`. Sentry init from `SentrySettings`. |
| `tasks` | Celery factory: `make_celery(service_name)` returns app pre-wired with broker URL, redbeat scheduler, Sentry integration, OTel celery instrumentation, structlog hooks, base `Task` class with retry defaults (`max_retries=5`, exponential backoff). |
| `testing` | Pytest fixtures: `pg_url` (testcontainers-postgres), `redis_url` (testcontainers-redis), `rabbitmq_url`, `client` (httpx async client against ASGI app), `auth_user(role="user")` factory minting JWTs, `freeze_time` shim. |

**Versioning**: `colab_common` follows semver. Services pin to a caret range; CI ensures the workspace member is built into a wheel during service Docker build.

---

## 5. `gateway-svc` Design

Public entrypoint behind AWS API Gateway → ALB → service ClusterIP. Owns: routing, auth pre-check, rate-limit, CORS, request-id stamping, feature-flag injection. Does **not** own business logic.

### Request flow (ASCII)

```
                ┌─────────────────────────────────────────────────────────────┐
                │ AWS CloudFront (TLS, WAF, edge caching of static)            │
                └────────────────────────────┬────────────────────────────────┘
                                             ▼
                ┌─────────────────────────────────────────────────────────────┐
                │ AWS API Gateway (REST + WebSocket APIs; throttling, IP ACL) │
                └────────────────────────────┬────────────────────────────────┘
                                             ▼
                ┌─────────────────────────────────────────────────────────────┐
                │ NLB → EKS Service: gateway-svc (FastAPI, uvicorn workers)    │
                │                                                             │
                │   1. request_id middleware           (colab_common.telemetry)│
                │   2. CORS middleware                                         │
                │   3. structlog binding                                       │
                │   4. auth middleware (decode JWT, skip /health, /openapi)    │
                │   5. rate-limit middleware (per-route limits)                │
                │   6. idempotency middleware (mutating verbs)                 │
                │   7. router → http-proxy to upstream service                 │
                └────────────────────────────┬────────────────────────────────┘
                                             ▼
                ┌─────────────────────────────────────────────────────────────┐
                │ auth-svc / profile-svc / discovery-svc / … (ClusterIP)       │
                └─────────────────────────────────────────────────────────────┘
```

### Routing table (prefix per service)

| Prefix | Upstream | Auth required | Rate limit |
|---|---|---|---|
| `/v1/auth/*` | auth-svc | mixed (login/signup public) | `RATE_LIMIT_AUTH_PER_IP_PER_MIN` |
| `/v1/profile/*` | profile-svc | yes | 60/min/user |
| `/v1/identity/*` | identity-svc | yes | 30/min/user |
| `/v1/feed/*` | discovery-svc | yes | 120/min/user |
| `/v1/match/*` | matching-svc | yes | 60/min/user |
| `/v1/invite/*` | invite-svc | yes | per-tier (FR-B-8) |
| `/v1/collab/*` | collab-svc | yes | 60/min/user |
| `/v1/chat/*` | chat-svc (HTTP fallback; WS direct) | yes | 240/min/user |
| `/v1/media/*` | media-svc | yes | 30/min/user |
| `/v1/ai/*` | ai-orchestrator-svc | yes (premium gate in svc) | credit-bucketed |
| `/v1/moderation/*` | moderation-svc | yes (role) | n/a |
| `/v1/notification/*` | notification-svc | yes | n/a |
| `/v1/billing/*` | billing-svc | yes (webhooks public + signed) | n/a |
| `/v1/support/*` | support-svc | yes | n/a |
| `/v1/admin/*` | admin-svc | role=admin | n/a |
| `/v1/geo/*` | geo-svc | yes | 60/min/user |
| `/v1/meeting/*` | meeting-svc | yes | 30/min/user |
| `/v1/analytics/*` | analytics-svc | yes | n/a (proxied to PostHog) |

Routes are defined in `gateway-svc/app/routes.py` as a declarative list; mismatch returns 404. Healthchecks bypass everything.

### Middleware order (top of stack first)

1. `RequestIDMiddleware`
2. `CORSMiddleware` (allowed origins from `APP_DOMAIN`, `MARKETING_DOMAIN`, `ADMIN_DOMAIN`)
3. `StructlogMiddleware` (binds request_id, user_id once known)
4. `AuthMiddleware` (decodes JWT to `request.state.user`; raises 401 unless on public allowlist)
5. `RateLimitMiddleware` (consults per-route policy + user tier from JWT)
6. `IdempotencyMiddleware` (only for POST/PUT/PATCH/DELETE)
7. `RouterDispatch` (httpx async client to upstream)

### Health endpoints

- `GET /healthz` — liveness; returns `{"status":"ok"}` if process is up. Used by k8s liveness probe.
- `GET /readyz` — readiness; pings Redis + RabbitMQ + at least one upstream service `/healthz`. Used by readiness probe + ALB target group health.
- `GET /version` — image tag + git sha.
- `GET /openapi.json` — gateway's own OpenAPI (mostly empty since proxy).

---

## 6. OpenAPI Codegen Pipeline

### Goal

A single `make openapi` produces typed TS clients for every service into `packages/api-types/<service>/index.ts`, ready to consume from RN + web apps.

### Discovery

A registry file lives at `tools/codegen/services.json`:

```json
{
  "services": [
    { "name": "auth", "url": "http://localhost:8001/openapi.json", "package": "@colab/api-types-auth" },
    { "name": "profile", "url": "http://localhost:8002/openapi.json", "package": "@colab/api-types-profile" },
    ...
  ]
}
```

In CI the URLs point to a side-loaded docker-compose stack where every service runs and exports its OpenAPI document. Locally devs can run `make openapi-local` against `localhost`.

### Script (`tools/codegen/generate.ts`)

1. For each entry, `fetch(url)` → write `openapi.json` under `packages/api-types/<service>/openapi.json` (committed for diffability and for offline regen).
2. Run `openapi-typescript packages/api-types/<service>/openapi.json -o packages/api-types/<service>/schema.ts`.
3. Generate a thin wrapper `packages/api-types/<service>/client.ts` that exports a `createClient(opts)` returning a typed `fetch` wrapper with `Authorization` header injection + `X-Request-Id` + retry on 429 (honoring `Retry-After`).
4. Run `prettier --write` over outputs.
5. Emit `packages/api-types/<service>/package.json` so each is independently importable.

### Versioning strategy

- Every service tags its OpenAPI with `info.version` (semver). Breaking changes bump major.
- `packages/api-types/<service>/package.json` mirrors that version.
- Apps pin via pnpm workspace ranges. Major-bump triggers an explicit consumer-side migration PR.
- The OpenAPI doc files are committed to git so codegen is deterministic; a `make openapi-check` runs in CI and fails if regen produces a diff (forces devs to commit regenerated clients).

### Makefile (excerpt)

```make
openapi: openapi-fetch openapi-generate openapi-format
openapi-fetch:
\tnode tools/codegen/fetch.ts
openapi-generate:
\tnode tools/codegen/generate.ts
openapi-format:
\tpnpm prettier --write 'packages/api-types/**/*.ts'
openapi-check: openapi
\tgit diff --exit-code packages/api-types
```

---

## 7. RN Base App (`apps/mobile`)

### Folder layout

```
apps/mobile/
├── app.config.ts                 # Expo config — reads env via expo-constants
├── eas.json                      # EAS build profiles (development, preview, production)
├── tsconfig.json                 # strict
├── tailwind.config.js            # NativeWind v4
├── babel.config.js
├── metro.config.js
├── src/
│   ├── app/                      # entry (App.tsx + providers)
│   ├── navigation/
│   │   ├── RootNavigator.tsx
│   │   ├── AuthStack.tsx
│   │   ├── MainTabs.tsx
│   │   ├── ModalStack.tsx
│   │   └── linking.ts            # deep links
│   ├── screens/
│   │   ├── auth/                 # Welcome, SignIn, SignUp, Verify (stubs)
│   │   ├── home/                 # HomeScreen "Hello, Colab" (acceptance)
│   │   ├── profile/              # placeholder
│   │   ├── settings/             # placeholder
│   │   └── modals/               # ErrorModal, ConfirmModal
│   ├── api/
│   │   ├── client.ts             # wires generated TS clients with auth + retries
│   │   └── queries/              # TanStack Query hooks per service
│   ├── state/
│   │   ├── auth.store.ts         # Zustand: tokens + user; persisted via secure-store
│   │   ├── settings.store.ts
│   │   └── flags.store.ts        # feature flags
│   ├── components/               # platform-base shared components (Button, Text, etc.)
│   ├── theme/                    # ties design-tokens output to NativeWind
│   ├── i18n/                     # i18next + en catalog
│   ├── lib/
│   │   ├── sentry.ts
│   │   ├── posthog.ts
│   │   ├── secure-storage.ts
│   │   ├── network.ts            # offline indicator + queue
│   │   └── push.ts               # token registration scaffold
│   └── types/
└── __tests__/
```

### Navigation tree

```
RootNavigator (NativeStack)
├── if (!authenticated) → AuthStack
│   ├── Welcome
│   ├── SignIn
│   ├── SignUp
│   └── Verify
└── if (authenticated) → MainTabs (BottomTabs)
    ├── HomeTab  → HomeScreen ("Hello, Colab")
    ├── DiscoverTab (placeholder)
    ├── ChatsTab (placeholder)
    └── MeTab (placeholder)
└── ModalStack (presented over either above)
    ├── ErrorModal
    └── ConfirmModal
```

### Platform-base screen list (this phase only)

- Welcome / SignIn stubs (no real auth; just navigation wiring).
- HomeScreen — "Hello, Colab" + a button that calls `gateway-svc /v1/auth/ping` (stub) to prove end-to-end plumbing.
- ErrorModal — global error boundary fallback.
- Settings (skeleton: theme toggle, sign out).

### Secure storage

- Refresh token stored in `expo-secure-store` (Keychain on iOS, Keystore on Android).
- Access token kept in memory only (Zustand non-persisted slice).
- On cold start: read refresh token → call `/v1/auth/refresh` → hydrate access token → mount MainTabs.

### Feature flag client

- PostHog feature flags (decided in master) consumed via `posthog-react-native`.
- `useFeatureFlag(key)` hook reads from Zustand `flags.store` which is hydrated on launch.
- Server-side flags via `gateway-svc /v1/flags` endpoint that re-emits the `FEATURE_*` env values; clients prefer PostHog and fall back to server.

### Offline + queued writes (NFR-7 hooks only)

- `lib/network.ts` watches NetInfo; pushes online/offline to Zustand.
- Optimistic mutations through TanStack Query with `onMutate` + `onError` rollback.
- Chat-message queue lives in MMKV via `react-native-mmkv`; replay on reconnect (full implementation in spec 007; this phase exposes the hook shape).

---

## 8. Next.js Base Apps

Three independent Next.js 15 App Router projects: `apps/marketing-web`, `apps/consumer-web`, `apps/admin-web`. All consume `@colab/ui`.

### `packages/ui` (`@colab/ui`) structure

```
packages/ui/
├── package.json (exports map)
├── tailwind.preset.js          # shared Tailwind v4 theme — pulls from design-tokens output
├── src/
│   ├── components/             # shadcn-vendored primitives (Button, Card, Dialog, …)
│   ├── primitives/             # layout (Container, Stack, Grid, Page)
│   ├── nav/                    # AppShell, Sidebar, TopBar
│   ├── theme/
│   │   ├── ThemeProvider.tsx
│   │   ├── tokens.css          # generated CSS vars from design-tokens
│   │   └── dark.css
│   ├── auth/
│   │   ├── AuthProvider.tsx    # next-auth-free; consumes our gateway-svc cookies
│   │   ├── useAuth.ts
│   │   └── withAuth.tsx        # HOC redirect for protected pages
│   ├── icons/                  # lucide-react re-export wrappers
│   └── index.ts
└── tsconfig.json
```

### Theme provider

- CSS variables defined in `tokens.css` (generated). Tailwind v4 references them via `@theme`.
- `ThemeProvider` toggles `data-theme` on `<html>`; persists via cookie so SSR matches.

### Auth wrapper

- All three apps mount `<AuthProvider>` at root. It reads `colab-session` cookie (set by gateway-svc); calls `/v1/auth/me` on mount; exposes `user`, `signOut`.
- `withAuth(Page)` HOC: if not authed in a protected route, redirect to login. Marketing app uses none of this; consumer-web uses it on `/app/*`; admin-web uses it on **every** route plus role check.

### Layout primitives

- `Container` — max-width 1200px, responsive padding.
- `Stack` — flex column with gap from tokens.
- `Page` — page-scaffold with `<TopBar/>` + main + footer.
- `Sidebar` — admin-web only.

### Route patterns per app

| App | Route patterns |
|---|---|
| `marketing-web` | `/` (landing), `/pricing`, `/about`, `/legal/{tos|privacy|cookies|dmca}`, `/blog/[slug]` (MDX). Static export-friendly; ISR for blog. |
| `consumer-web` | `/` (mirrors mobile home), `/auth/{sign-in|sign-up|verify}`, `/discover`, `/profile/[id]`, `/chats`, `/chats/[id]`, `/account/*`. App Router with RSC. |
| `admin-web` | `/login`, `/dashboard`, `/moderation/queue`, `/moderation/case/[id]`, `/users`, `/users/[id]`, `/billing`, `/audit`, `/flags`. IP-allowlist + admin role required. |

---

## 9. CI/CD Workflows (GitHub Actions)

All workflows live under `.github/workflows/`. AWS auth via OIDC role assumption — no long-lived secrets.

| File | Trigger | Purpose |
|---|---|---|
| `lint.yml` | push, pull_request | `ruff check`, `ruff format --check`, `mypy --strict` (services + colab_common), `pnpm lint`, `tsc --noEmit` (all TS packages), `prettier --check`. |
| `test.yml` | push, pull_request | Python: pytest with testcontainers (postgres, redis, rabbitmq). JS: `pnpm test` (Vitest for packages, RN testing-library for mobile). Coverage uploaded; gate ≥80% on `colab_common`. |
| `openapi-check.yml` | pull_request | Spins service containers, runs `make openapi`, fails if `git diff --exit-code` shows drift. |
| `build-and-push.yml` | push to main, version tags | Matrix over `services/*`: build Docker image, push to ECR with tag `<sha>` + `latest`. Uses BuildKit cache. |
| `deploy.yml` | manual (workflow_dispatch) + auto after build-and-push on main | OIDC-assume `colab-deployer` role → `helm upgrade --install <service> charts/svc -f services/<service>/values.yaml --set image.tag=<sha>`. One job per service in a matrix; concurrency group per env. |
| `web-build-and-deploy.yml` | push to main | For each `apps/*-web`: `pnpm build` → sync `out/` to S3 bucket (`S3_BUCKET_WEB_STATIC`) → CloudFront invalidation. |
| `mobile-build.yml` | manual + nightly | EAS Build: dev profile for PR previews, preview for staging, production for tagged releases. Uses `EXPO_TOKEN`. Submits to TestFlight + Internal Testing via `eas submit` on `production`. |
| `terraform.yml` | pull_request on `terraform/**` | `terraform fmt -check`, `validate`, `plan` (comment-bot to PR). Apply requires manual `workflow_dispatch`. |
| `release.yml` | tag push `v*` | Cuts a release: ensures all services build, deploys to staging, runs smoke suite, opens production approval gate. |

### OIDC role assumption pattern

Every workflow that touches AWS includes:

```yaml
permissions:
  id-token: write
  contents: read
jobs:
  job:
    steps:
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/colab-gha-${{ github.ref_name == 'main' && 'prod' || 'staging' }}
          aws-region: us-east-1
```

Roles are pre-provisioned in `terraform/iam/gha.tf` (created in spec 001) with environment-scoped trust policies on GitHub's OIDC issuer + `repo:colab/* :ref:refs/heads/main` conditions.

---

## 10. Design Tokens

Source of truth: `packages/design-tokens/tokens/*.json` (W3C DTCG-ish shape). Style Dictionary builds them into platform outputs.

### Input shape

```json
{
  "color": {
    "brand": {
      "primary":   { "value": "#5B5BD6", "type": "color" },
      "secondary": { "value": "#FFB454", "type": "color" }
    },
    "neutral": { "0":  { "value": "#FFFFFF" }, "900": { "value": "#0B0B0F" } }
  },
  "space":  { "1": { "value": "4",  "type": "spacing" }, "2": { "value": "8" }, "4": { "value": "16" } },
  "radius": { "sm": { "value": "4" }, "md": { "value": "8" }, "lg": { "value": "16" } },
  "font": {
    "family": { "sans": { "value": "Inter" } },
    "size":   { "sm": { "value": "14" }, "md": { "value": "16" }, "lg": { "value": "20" } },
    "weight": { "regular": { "value": "400" }, "bold": { "value": "700" } }
  }
}
```

### Output channels

| Channel | Path | Consumed by |
|---|---|---|
| CSS variables | `packages/design-tokens/build/css/tokens.css` | `@colab/ui` Tailwind v4 theme; loaded once in root layout. |
| Tailwind preset | `packages/design-tokens/build/tailwind/preset.js` | All web apps + RN NativeWind config. |
| RN/NativeWind theme | `packages/design-tokens/build/rn/theme.ts` | `apps/mobile/src/theme/index.ts`. |
| JSON (docs) | `packages/design-tokens/build/json/tokens.json` | Documentation site (`docs/`) + design handoff. |

### Build command

`pnpm --filter @colab/design-tokens build` runs Style Dictionary. CI runs it before any app build so generated files are always fresh. Outputs are gitignored EXCEPT a snapshot copy of `tokens.json` for doc previewing.

### Accessibility scaffolding

- All color tokens carry an `a11y.contrast` annotation in source JSON; a build-time linter fails if the brand pair drops below 4.5:1 on the default background (WCAG 2.1 AA target — full audit in spec 018).
- Spacing scale is 4-pt aligned to support 44pt min tap targets in RN.

---

## 11. Implementation Task List

Tasks are ordered with `blocked_by` to drive a DAG-aware executor. Estimates are calendar-hours of solo work; parallelization handled at the phase-run level. Total: **42 tasks**.

### A. colab_common

| id | title | outcome | hrs | blocks | blocked_by |
|---|---|---|---|---|---|
| C1 | Scaffold `packages/colab_common` with src-layout + pyproject + uv workspace entry | `uv pip install -e packages/colab_common` works | 2 | C2 | — |
| C2 | `settings` module + Secrets Manager loader + Parameter Store fallback | services can `from colab_common.settings import Settings` | 4 | C3,C4 | C1 |
| C3 | `db` module: engine factory, async session dep, alembic env template | sample service can run a migration | 5 | C7,G1 | C2 |
| C4 | `errors` module + handler + envelope | unit tests on FastAPI test app | 3 | C5,C8 | C2 |
| C5 | `telemetry` module: OTel + structlog + Sentry init | request_id propagation verified in logs | 5 | C8,G1 | C4 |
| C6 | `auth` module: JWT verify + role dep + service-to-service signer | unit tests with fake JWKS | 6 | C8,G1 | C2 |
| C7 | `events` module: aio-pika publish + outbox helper | publish to test rabbit + observe | 5 | G1 | C3 |
| C8 | `rate_limit` + `idempotency` middlewares (Redis-backed) | unit tests with testcontainers-redis | 5 | G1 | C5,C6 |
| C9 | `tasks` module: Celery factory + redbeat + Sentry wiring | sample task runs locally | 4 | — | C5 |
| C10 | `testing` module: pytest fixtures + JWT mint | downstream tests import successfully | 3 | C11 | C6,C3 |
| C11 | colab_common unit-test suite to ≥80% coverage | CI gate green | 6 | — | C1–C10 |

### B. gateway-svc

| id | title | outcome | hrs | blocks | blocked_by |
|---|---|---|---|---|---|
| G1 | Scaffold `services/gateway-svc` FastAPI app + Dockerfile + uv-based image | local container responds on /healthz | 3 | G2 | C2–C8 |
| G2 | Implement middleware stack in declared order + tests | integration tests cover each middleware | 5 | G3 | G1 |
| G3 | Declarative routes config + httpx proxy to upstream | smoke test against a stub upstream | 5 | G4 | G2 |
| G4 | Health/ready/version endpoints + `/v1/flags` | probes pass; flags returned to clients | 2 | G5,M1 | G3 |
| G5 | Helm `values.yaml` for gateway-svc + ECR repo + first deploy to staging | reachable from outside | 4 | M1,W1 | G4,I3 |

### C. OpenAPI codegen

| id | title | outcome | hrs | blocks | blocked_by |
|---|---|---|---|---|---|
| O1 | `tools/codegen/services.json` registry + fetch script | dumps `openapi.json` per service | 2 | O2 | G4 |
| O2 | `openapi-typescript` runner + per-service `client.ts` wrapper | typed client compiles | 4 | O3,M2,W2 | O1 |
| O3 | `make openapi` + `openapi-check` CI workflow | drift detection works | 3 | — | O2 |

### D. RN base app

| id | title | outcome | hrs | blocks | blocked_by |
|---|---|---|---|---|---|
| M1 | Bootstrap `apps/mobile` via Expo + TS strict + NativeWind v4 | `pnpm --filter mobile start` runs | 4 | M2 | G5 |
| M2 | API client wiring (consume generated TS clients + TanStack Query) | HomeScreen calls /v1/auth/ping successfully | 4 | M3 | M1,O2 |
| M3 | Navigation tree (Auth/Main/Modal stacks) + linking config | nav e2e on simulator | 4 | M4 | M2 |
| M4 | Zustand stores (auth, settings, flags) + secure-storage refresh-token persistence | cold start hydration works | 4 | M5 | M3 |
| M5 | Sentry + PostHog + offline indicator + error boundary | crashes captured; offline banner shows | 3 | M6 | M4 |
| M6 | EAS dev/preview/production profiles + first `eas build --profile development` for iOS+Android | sims launch artifact; "Hello, Colab" visible | 5 | — | M5 |

### E. Web base apps

| id | title | outcome | hrs | blocks | blocked_by |
|---|---|---|---|---|---|
| W1 | Bootstrap `packages/ui` with Tailwind v4 + shadcn-vendored primitives | importable from any Next app | 4 | W2,W3,W4 | T1 |
| W2 | Bootstrap `apps/consumer-web` Next 15 App Router with @colab/ui + auth wrapper | landing page renders + protected route redirects | 5 | W5 | W1,O2 |
| W3 | Bootstrap `apps/marketing-web` (static export) | `pnpm build` outputs static site | 3 | W5 | W1 |
| W4 | Bootstrap `apps/admin-web` with IP-allowlist + admin role gate | unauth user sees 403 | 3 | W5 | W1 |
| W5 | Sentry + PostHog per app + proxy route for PostHog ingest | events received | 3 | — | W2,W3,W4 |

### F. Design tokens

| id | title | outcome | hrs | blocks | blocked_by |
|---|---|---|---|---|---|
| T1 | `packages/design-tokens` source JSON + Style Dictionary build → CSS/Tailwind/RN/JSON | `pnpm --filter design-tokens build` succeeds | 4 | W1,M1 | — |
| T2 | A11y contrast linter in build step | failing pair fails CI | 2 | — | T1 |

### G. CI / Helm / infra glue

| id | title | outcome | hrs | blocks | blocked_by |
|---|---|---|---|---|---|
| I1 | `charts/svc` Helm chart base (Deployment, Service, HPA, ServiceAccount/IRSA, ConfigMap, ServiceMonitor) | dry-run renders cleanly | 6 | G5,I3 | — |
| I2 | ECR repo provisioning via Terraform module (per service) | `gateway-svc` repo exists | 2 | I3 | — |
| I3 | `build-and-push.yml` workflow (matrix over services) | gateway-svc image pushed on PR merge | 4 | G5 | I1,I2 |
| I4 | `deploy.yml` workflow (helm upgrade with OIDC role) | gateway-svc deploys to staging | 3 | — | I3 |
| I5 | `lint.yml` + `test.yml` + `openapi-check.yml` | PRs gated on green | 4 | — | C11,M5,W5,O3 |
| I6 | `web-build-and-deploy.yml` (S3 + CloudFront) | consumer-web reachable on staging domain | 3 | — | W5 |
| I7 | `mobile-build.yml` (EAS) + secrets bootstrap | nightly preview build artifact lands | 3 | — | M6 |
| I8 | `terraform.yml` (fmt/validate/plan) | PR comment with plan | 2 | — | — |
| I9 | `release.yml` (tag-triggered prod gate) | dry-run on tag creates approval req | 2 | — | I4,I6,I7 |

### Totals
- colab_common: 11 tasks / ~48h
- gateway-svc: 5 tasks / ~19h
- codegen: 3 tasks / ~9h
- RN base: 6 tasks / ~24h
- Web base: 5 tasks / ~18h
- Design tokens: 2 tasks / ~6h
- CI/Helm: 9 tasks / ~29h
- **Grand total: 42 tasks, ~153 hours**

---

## 12. Acceptance Criteria Recap + Concrete Commands

From spec §Acceptance criteria, each mapped to a runnable check.

1. **"Every later spec's first task can `pip install colab-common`..."**
   ```bash
   uv pip install -e packages/colab_common
   python -c "from colab_common.auth import require_user; from colab_common.events import publish; print('ok')"
   ```

2. **"`make openapi` against an empty-service template emits a working TS client."**
   ```bash
   cp -r tools/codegen/templates/empty-svc services/sample-svc
   (cd services/sample-svc && uv run uvicorn app.main:app --port 8099 &) && sleep 2
   make openapi
   ls packages/api-types/sample/schema.ts packages/api-types/sample/client.ts
   pnpm --filter @colab/api-types-sample tsc --noEmit
   ```

3. **"RN app builds via `eas build --profile development` for iOS and Android, runs on simulator, shows a 'Hello, Colab' home screen wired through API Gateway → gateway-svc → a stub service."**
   ```bash
   pnpm --filter mobile eas build --profile development --platform ios --non-interactive
   pnpm --filter mobile eas build --profile development --platform android --non-interactive
   # then open simulator and verify HomeScreen calls /v1/auth/ping and renders the response
   ```

4. **"Each Next.js app deploys to S3+CloudFront via the CI workflow."**
   ```bash
   gh workflow run web-build-and-deploy.yml -f app=consumer-web -f env=staging
   curl -sf https://app-staging.example.com/ | grep -q "Colab"
   ```

5. **"All deploys gated on lint + test passing."**
   - Verified by viewing `deploy.yml` workflow: `needs: [lint, test]`.
   ```bash
   gh workflow view deploy.yml --yaml | grep -E "needs:|test:|lint:"
   ```

### NFR checks

- **Mobile cold start <2.5s** — measure via Sentry `app.start` span on iPhone 12 sim + mid-range Android (Pixel 5 emulator at 2GB RAM).
- **Web LCP <2.5s** — `npx lighthouse https://app-staging.example.com --only-categories=performance --chrome-flags="--headless"` ≥ 75 perf score.
- **Lint passes** — `pnpm lint && pnpm tsc --noEmit && uv run ruff check . && uv run mypy --strict services packages/colab_common/src` exit 0.
- **`colab_common` coverage ≥80%** — `uv run pytest --cov=colab_common --cov-fail-under=80`.

---

## 13. Open Risks

1. **Tailwind v4 + NativeWind v4 are both very recent.** Risk: edge bugs in shared theme handoff between Style Dictionary → Tailwind preset → NativeWind compiler. Mitigation: pin minor versions; smoke test a colored Button on both surfaces in CI.
2. **`openapi-typescript` v7 may not handle every FastAPI/Pydantic v2 edge case** (notably discriminated unions and `Annotated[Field(...)]`). Mitigation: minimize union usage in early API surfaces; add a codegen golden-file test per service.
3. **EAS Build minutes & queue times** in early dev could slow iteration. Mitigation: local dev client (`expo run:ios|android`) is the primary loop; EAS reserved for release builds.
4. **Service-to-service JWT signing via IRSA** requires per-service IAM roles and a key-distribution scheme. We may simplify in P1 to a shared internal-cluster shared-secret HS256 token, deferring proper RS256+IRSA to P3/P4 once we have >2 callers — flag as **[REVIEW after 003]**.
5. **Helm chart base reuse risk**: making the chart too generic vs too rigid is a known anti-pattern. We accept some duplication and start with a tight, opinionated base, splitting later if friction shows.
6. **Monorepo CI cost**: every PR could rebuild everything. Mitigation: Turborepo task-graph + Docker layer caching + uv lockfile-based service builds (only changed services rebuild).
7. **OpenAPI version drift between client and server**: an app could pin an old client and call an updated server. Mitigation: gateway-svc reads each upstream's reported version and rejects requests with `X-Client-API-Version` < advertised minimum. (Implementation deferred to spec 003 hardening, scaffolding only here.)
8. **Brand-name swap (`BRAND_NAME` env var)** must thread through every app. Risk: hard-coded "Colab" strings creep in. Mitigation: lint rule in `lint.yml` forbidding the literal `"Colab"` outside `i18n/` and `BRAND_NAME` interpolation.
9. **WCAG 2.1 AA scaffolding vs full audit**: we ship the scaffolding (token contrast lint, 4pt grid, tap targets), but the formal audit lives in spec 018. Risk: regressions accrue silently. Mitigation: enable `eslint-plugin-jsx-a11y` strict from day 1; add Storybook a11y addon in `@colab/ui`.

---
*End of plan.*
