# Stage 1 — Build Matrix Report

> Branch: `fix/stage1-build-matrix`. Status as of the final commit on 2026-05-12.

## What passes

| Check | Result |
|---|---|
| `pnpm install` at root | ✓ (after fixing `@tanstack/async-storage-persister` → `@tanstack/query-async-storage-persister` in `apps/mobile/package.json`) |
| `uv sync --all-packages` | ✓ (after expanding `[tool.uv.workspace].members` to all 19 services + adding `[tool.hatch.build.targets.wheel]` to each service `pyproject.toml`) |
| `uv run pytest packages/colab_common/tests` | **✓ 32/32 passed** |
| `from app.main import app` per service | **✓ 20/20 services** (all of: gateway, auth, identity, profile, discovery, matching, geo, invite, chat, media, collab, moderation, notification, billing, support, ai-orchestrator, meeting, admin, analytics, hello) |

## Fixes landed on `fix/stage1-build-matrix`

1. `fix(mobile): correct @tanstack/query-async-storage-persister package name`
2. `fix(js-workspace): fix pnpm install + typecheck for web apps and packages`
3. `fix(py-workspace): expand uv workspace to all 19 services + per-service dep fixes`
4. `fix(colab_common): rename 'message' extra key in logger.warning to avoid LogRecord KeyError`
5. `fix(models): add __allow_unmapped__ to DeclarativeBase + colab_common.db exports` (incl. `async_session_factory` added to `colab_common.db` per RECONCILIATION known integration gap)
6. `fix(py-services): add hatch wheel config so uv workspace can install each service`
7. `fix(services): resolve last 3 compile-gate failures (auth/collab/support)`

## Known follow-ups (deferred — not blocking Stage 2)

### Deprecation noise

Every `uv` invocation prints a warning that `[tool.uv.dev-dependencies]` is deprecated and should use `[dependency-groups.dev]`. This is a multi-file rename across 21 `pyproject.toml` files; doesn't affect functionality. Defer.

### JWT key length warnings

`colab_common.testing.mint_jwt` test helper uses an 11-byte HMAC key which is below RFC 7518's 32-byte minimum recommendation. Test-only — production uses RS256 + KMS-signed keys. Defer (or raise to 32 bytes in the test helper if you want clean warning output).

### What's NOT validated yet (Stage 2 territory)

- `pnpm typecheck` across web apps (TS errors likely exist)
- `pnpm build` for each Next.js app
- `pnpm --filter=mobile typecheck` (RN)
- `uv run pytest services/<svc>/tests` per service (tests reference fixtures that need Postgres/Redis/RabbitMQ — needs docker-compose)
- `docker build` per service Dockerfile
- `helm template` per chart
- `terraform validate` per env
- Cross-service contract tests (auth emits `user.created` → profile consumes; etc.)
- End-to-end smoke against running services

### Known architectural risks the agents flagged (still standing)

1. **collab-svc Postgres generated columns**: `least_participant` / `greatest_participant` defined as `GENERATED ALWAYS AS ... STORED` but service-layer code passes them in `pg_insert().values()` — will be rejected by Postgres at first insert.
2. **WebSocket multiplicity**: 3 concurrent WS connections per mobile client (chat, whiteboard, in-app banners). Accepted at launch; v1.1 consolidation deferred.
3. **API Gateway WebSocket 2-hour limit**: reconnect storm risk at 100k DAU near 2-hour mark.
4. **Postgres partitioned tables can't be FK targets**: `chat_message_revision` / `chat_attachment` reference `chat_message.id` via app-layer integrity only.
5. **DMCA agent not registered**: reduced US safe-harbor; accepted per master §0.
6. **India DLT SMS**: blocks phone OTP in IN until telco approval (4–8 weeks).

## Recommended next step

Stage 2: docker-compose stack (Postgres + Redis + RabbitMQ + LocalStack) → run real services → fix integration bugs that surface during boot. The compile-gate passing means the worst structural bugs are behind us; integration bugs (DB session factory shapes, RabbitMQ routing key alignment, internal API contracts between services) come next.
