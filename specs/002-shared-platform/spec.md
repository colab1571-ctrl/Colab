# 002 — Shared Platform

**Phase**: P1 — Shared platform.
**Mission**: The shared libraries and base apps every downstream feature consumes. Owning this once means feature specs don't re-litigate auth-bearer-token plumbing, OpenAPI codegen, RN navigation shells, Next.js layouts, telemetry SDK init, error boundaries, design tokens, or CI templates.

## In scope

### Backend
- `colab_common` Python package (shared by all FastAPI services):
  - Settings via pydantic-settings reading Secrets Manager + env-var fallback
  - SQLAlchemy 2.x async base + session middleware + tenant-less RLS hooks
  - Pydantic v2 request/response models
  - Standard error envelope + exception → HTTP mapper
  - OpenTelemetry tracing + CloudWatch logging
  - Sentry init
  - Auth middleware: JWT bearer verification + IRSA service-to-service JWT (mTLS in cluster)
  - Rate-limit middleware (Redis token bucket)
  - Idempotency-Key middleware
  - Celery base task + Sentry integration
- `gateway-svc` FastAPI app: AWS API Gateway integration; routes per-service; CORS; rate-limit; auth-required marker.
- OpenAPI codegen pipeline: `make openapi` script that runs `openapi-typescript` against every service's `/openapi.json` and emits `clients/typescript/<service>.ts`.

### Mobile (RN/Expo)
- Expo SDK 53+ project, TypeScript strict.
- Navigation: React Navigation v7 (native stack + bottom tabs).
- State: TanStack Query v5 + Zustand for ephemeral UI state.
- API client: generated TS client from §Backend codegen.
- Design system: NativeWind (Tailwind for RN) + design tokens (`colors`, `spacing`, `typography`, `radii`).
- Sentry + PostHog wired.
- Error boundary + offline indicator + queued-writes infrastructure (hooks for FR-NFR-7).
- Push-token registration scaffolding (no opt-in prompt yet — see §014).
- Persona SDK install scaffold.
- Apple/Google sign-in SDK install scaffold.

### Web (×3 Next.js)
- `marketing-web` (Next.js App Router, static-export-friendly, SEO).
- `consumer-web` (Next.js App Router, full app mirroring RN).
- `admin-web` (Next.js App Router, internal-only, IP-allowlisted at API Gateway).
- All three share `@colab/ui` package (shadcn-based; design tokens identical to mobile).
- Sentry + PostHog init per app.

### CI/CD
- GitHub Actions workflows: `lint.yml`, `test.yml`, `build-and-push.yml` (per service), `deploy.yml` (Helm upgrade against EKS), `mobile-build.yml` (EAS).
- ECR repos created (one per service).
- Helm chart base (`charts/svc/`) + per-service `values.yaml`.

## Dependencies

- **Hard**: 001 Infrastructure.

## Owned entities

None. Only platform/library code.

## API surface

The `gateway-svc` proxies but defines nothing of its own. The `colab_common` lib exposes:
- `auth.require_user()` dependency
- `auth.require_role("moderator")` dependency
- `events.publish(event_name, payload)` for RabbitMQ fan-out
- `rate_limit.bucket(key, capacity, refill_per_sec)` decorator

## Acceptance criteria

- Every later spec's first task can `pip install colab-common` (private GitHub package or in-repo monorepo) and use the bases without re-implementing.
- `make openapi` against an empty-service template emits a working TS client.
- RN app builds via `eas build --profile development` for iOS and Android, runs on simulator, shows a "Hello, Colab" home screen wired through API Gateway → gateway-svc → a stub service.
- Each Next.js app deploys to a `next-static` S3 + CloudFront via the CI workflow.
- All deploys gated on lint + test passing.

## NFRs

- Mobile cold start <2.5s on iPhone 12 / mid-range Android.
- Web LCP <2.5s.
- Lint passes (ruff + mypy strict + eslint + typescript --noEmit) on every PR.
- Test coverage ≥80% on `colab_common`.

## Open

None — this is mostly mechanical platform work. Design-token values resolved by §018 design pass.
