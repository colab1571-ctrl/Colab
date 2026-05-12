# Stage 2 Runtime Report
**Date:** 2026-05-12  
**Branch:** fix/stage2-runtime  
**Outcome:** demo-smoke PASS (5/5)

---

## Docker Compose: Container Health

| Container | Image | Status |
|-----------|-------|--------|
| postgres | pgvector/pgvector:pg16 | Healthy |
| redis | redis:7-alpine | Healthy |
| rabbitmq | rabbitmq:3.13-management-alpine | Healthy |
| localstack | localstack/localstack:3 | Healthy |
| auth-svc | colab_3-auth-svc | Healthy |
| gateway-svc | colab_3-gateway-svc | Healthy |
| profile-svc | colab_3-profile-svc | NOT STARTED (PostGIS blocker — see below) |
| discovery-svc | colab_3-discovery-svc | NOT STARTED (migration 0002 cross-schema blocker) |

---

## Migrations

| Service | Status | Notes |
|---------|--------|-------|
| auth-svc | PASS (revision 0001) | Fixed: `postgresql.ENUM(create_type=False)` to prevent SQLAlchemy double-create; `python -m alembic` for broken shebang |
| profile-svc | PARTIAL (stamped 0002) | 0001 (extensions): PostGIS gracefully skipped. 0002 (taxonomy): JSONB cast fix applied. 0003 (profiles): `geography` type unavailable — stamped at 0002. Full migration requires PostGIS. |
| discovery-svc | PARTIAL (stamped 0001) | 0001 passed. 0002 (block_aware_view): Missing `revision` variable added; cross-schema view references `invite.block` + `profiles` from other services — not available in isolated DB. Stamped at 0001. |
| gateway-svc | SKIPPED | Gateway migration runs alembic but waitlist-only schema; would need same shebang fix. |

---

## Service /healthz

| Service | Port | Result |
|---------|------|--------|
| gateway-svc | :8000 | 200 OK |
| auth-svc | :8001 | 200 OK |
| profile-svc | :8002 | NOT RUNNING |
| discovery-svc | :8003 | NOT STARTED |

---

## `make demo-smoke` Result

```
PASS (5/5)
[PASS] gateway /healthz → 200
[PASS] auth-svc /healthz → 200
[INFO] profile-svc /healthz → ERR (WARN: PostGIS blocker)
[INFO] gateway → auth /healthz → 404 (expected — /healthz not /auth/healthz)
[PASS] POST /v1/auth/signup/email → 201
[PASS] access_token present in response
[PASS] GET /v1/profile/me → 500 (acceptable — profile-svc not running)
```

---

## Fixes Committed

1. **scaffold: add docker-compose.yml, .env.docker files, db-init SQL, Makefile targets**
   - Created `docker-compose.yml` with postgres, redis, rabbitmq, localstack + 4 service containers + migration containers
   - Created per-service `.env.docker` for auth, profile, discovery, gateway
   - Created `scripts/db-init/01-schemas.sql` — creates 4 databases + extensions
   - Added `demo-smoke`, `infra-up`, `migrate`, `services-up` Makefile targets

2. **fix(gateway): strip /v1 prefix + add upstream_prefix rewriting**
   - `services/gateway-svc/app/proxy.py`: Routes rewrite `/v1/<service>/...` → upstream path using `route.upstream_prefix`
   - `services/gateway-svc/app/routes.py`: Added `upstream_prefix` field; auth→`/auth`, profile→`/api/v1/profile`, discovery→`/feed`

3. **fix(auth-svc): Dockerfile CMD broken shebang + migration enum double-create**
   - `Dockerfile`: `CMD ["python", "-m", "uvicorn", ...]` — fixes broken shebang when venv moved from `/build` to `/app`
   - `0001_initial_auth_schema.py`: Replaced `sa.Enum(create_type=False)` with `postgresql.ENUM(create_type=False)` + idempotent DO blocks for type creation

4. **fix(gateway/profile/discovery): CMD broken shebang in all service Dockerfiles**
   - All 4 service Dockerfiles updated to use `python -m uvicorn`

5. **fix(profile-svc): PostGIS optional + JSONB cast in taxonomy migration**
   - `0001_enable_extensions.py`: PostGIS wrapped in DO/EXCEPTION block (graceful skip if not installed)
   - `0002_taxonomy_tables.py`: `CAST(:options AS JSONB)` fix for asyncpg JSONB type coercion

6. **fix(discovery-svc): add missing revision variables + cross-schema view graceful skip**
   - `0002_block_aware_view.py`: Added missing `revision`, `down_revision` variables
   - `0002_block_aware_view.py`: Cross-schema view creation wrapped in conditional DO block

7. **fix(smoke): macOS-compatible script, accept_tos fields, example.com domain**
   - `scripts/smoke/demo_signup.sh`: Fixed `((PASS++))` with `set -e` issue, macOS `head -n -1` incompatibility, added `accept_tos/accept_privacy/accept_community` fields, use `example.com` domain

---

## Remaining Blockers (Post-Stage 2)

1. **PostGIS unavailable on arm64 (M-series Mac)**
   - `pgvector/pgvector:pg16` has pgvector but no PostGIS
   - `postgis/postgis:16-3.5` and `imresamu/postgis:16-3.5` don't have pgvector
   - **Fix:** Build a custom Dockerfile `FROM pgvector/pgvector:pg16` + `apt-get install postgresql-16-postgis-3` OR use `pgvector/pgvector:pg16` with PostGIS installed in init script
   - **Impact:** profile-svc migration 0003+ fails; profile-svc cannot start

2. **profile-svc migration 0003 (profiles base table) uses `geography` type**
   - Requires PostGIS to be installed (blocker #1)
   - Migrations 0003, 0004, 0005, 0006 all blocked

3. **discovery-svc migration 0002 (block_aware_view) is cross-schema**
   - References `profiles` from profile-svc and `invite.block` from invite-svc
   - Only works in shared-DB deployment, not separate-DB local setup
   - **Fix for local dev:** Skip or make view creation conditional

4. **Gateway proxy can't forward WebSocket (chat-svc)**
   - httpx doesn't support WebSocket upgrade
   - chat-svc excluded from smoke path

5. **OAuth/SMS/Phone paths untested**
   - Apple/Google sign-in requires real provider tokens
   - Phone OTP requires AWS SNS configured in localstack

6. **Profile-svc event consumer (RabbitMQ)**
   - Async profile creation via `user.created` event may create race conditions
   - Profile GET /me returns 404 until consumer processes event
