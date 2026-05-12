# Stage 2 Compose Demo — Report

**Branch:** `feat/stage2-compose-demo`
**Date:** 2026-05-11
**Commits:** 1 (scaffold commit)

---

## Deliverables Produced

### Files Created/Modified

| File | Status |
|------|--------|
| `docker-compose.yml` | Created |
| `Makefile` (demo-* targets) | Updated |
| `scripts/db-init/01-schemas.sql` | Created |
| `scripts/smoke/demo_signup.sh` | Created |
| `scripts/smoke/demo_seed.sh` | Created |
| `services/gateway-svc/.env.docker` | Created |
| `services/auth-svc/.env.docker` | Created |
| `services/profile-svc/.env.docker` | Created |
| `services/discovery-svc/.env.docker` | Created |
| `services/chat-svc/.env.docker` | Created |
| `services/auth-svc/Dockerfile` | Fixed (removed missing `templates/` COPY) |
| `services/gateway-svc/Dockerfile` | Fixed (added `migrations/` + `alembic.ini` COPY) |

---

## Docker Build Status

**BLOCKED:** Docker daemon was not running at time of execution.
`docker ps` returns: "Cannot connect to the Docker daemon."

Docker Desktop must be started before running `make demo-up`.

**To build manually once Docker Desktop is running:**
```bash
docker build -t colab/gateway-svc:dev -f services/gateway-svc/Dockerfile .
docker build -t colab/auth-svc:dev -f services/auth-svc/Dockerfile .
docker build -t colab/profile-svc:dev -f services/profile-svc/Dockerfile .
docker build -t colab/discovery-svc:dev -f services/discovery-svc/Dockerfile .
docker build -t colab/chat-svc:dev -f services/chat-svc/Dockerfile .
```

---

## Migration Status (Expected — not run due to Docker daemon down)

| Service | Migration Dir | Versions |
|---------|--------------|---------|
| gateway-svc | `services/gateway-svc/migrations/` | `0001_create_waitlist_emails.py` |
| auth-svc | `services/auth-svc/alembic/` | `0001_initial_auth_schema.py` |
| profile-svc | `services/profile-svc/alembic/` | 0001–0006 |
| discovery-svc | `services/discovery-svc/alembic/` | 0001–0002 |
| chat-svc | `services/chat-svc/alembic/` | `20260511_0001_initial_chat_schema.py` |

All migrations use `postgresql+asyncpg://colab:colab@postgres:5432/colab_dev`.

---

## Smoke Test Path

The smoke test (`scripts/smoke/demo_signup.sh`) tests:
1. `GET http://localhost:8080/healthz` → 200
2. `GET http://localhost:8001/healthz` → 200 (auth-svc direct)
3. `POST http://localhost:8001/auth/signup/email` → 201 + JWT
4. `GET http://localhost:8002/api/v1/profile/me` with JWT → 200 or 404

**Known routing mismatch (Stage-3 fix):** Gateway routes `ROUTES` use prefix `/v1/auth` but auth-svc
router prefix is `/auth` (no `/v1`). Proxy forwards full path as-is, so `/v1/auth/signup/email`
is forwarded to `http://auth-svc:8000/v1/auth/signup/email` which 404s. Smoke test bypasses
gateway and hits auth-svc directly on port 8001.

---

## Top 5 Blockers for Stage 3 (PaaS Deploy)

1. **Gateway prefix mismatch**: Gateway `ROUTES` use `/v1/auth`, `/v1/profile`, etc. but upstream
   services use `/auth`, `/api/v1/profile`. Either strip prefix in proxy or align route tables.
   Affects all 5 in-scope services.

2. **Real credentials required**: SES email, Twilio OTP, Apple/Google OAuth all need real keys
   for auth flows. LocalStack handles SES in dev but Twilio/OAuth need proper staging secrets.

3. **Event-driven profile creation**: `profile-svc` creates profiles on `user.created` RabbitMQ
   event. If RabbitMQ consumer startup order is wrong, profile won't exist after signup. Needs
   retry/backoff or synchronous profile creation endpoint in smoke path.

4. **pgvector/PostGIS on shared DB**: All 5 services share `colab_dev`. Profile and discovery
   migrations use `vector` and `postgis` extensions. `pgvector/pgvector:pg16` image must be
   verified to include PostGIS (may need `postgis/postgis:16-3.5` fallback with pgvector plugin).

5. **chat-svc WebSocket**: chat-svc uses uvloop and WebSocket connections. Gateway's httpx proxy
   cannot upgrade HTTP to WebSocket. Chat WS endpoints need a dedicated WebSocket-aware proxy
   (e.g., Nginx, Traefik) or direct connection bypass for Stage 3.
