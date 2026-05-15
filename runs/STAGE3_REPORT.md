# Stage 3 — PaaS Deploy Report

**Date:** 2026-05-11
**Branch:** feat/stage3-paas-deploy
**Base commit:** cafb85d

---

## Accounts to Create (blocking — do these first)

- [ ] **Fly.io** — https://fly.io/app/sign-up (free, no credit card)
- [ ] **Supabase** — https://supabase.com (free, no credit card)
- [ ] **Upstash** — https://upstash.com (free, no credit card)
- [ ] **CloudAMQP** — https://cloudamqp.com → plan: Little Lemur (free)
- [ ] **Cloudflare** — https://cloudflare.com (R2 free tier — no credit card needed for 10 GB)
- [ ] **Resend** — https://resend.com (free: 100 emails/day)
- [ ] **Persona sandbox** — https://withpersona.com/sign-up (sandbox is free)
- [ ] **Sentry** — https://sentry.io (free: 5k errors/mo)
- [ ] **PostHog** — https://posthog.com (free: 1M events/mo)
- [ ] **OpenAI** — https://platform.openai.com (pay-as-you-go; load $5 credit)
- [ ] **Replicate** — https://replicate.com (pay-as-you-go)
- [ ] **Expo** — https://expo.dev (free; needed for `expo publish`)
- [ ] **Vercel** — https://vercel.com (Hobby tier is free)

---

## Step-by-Step Deploy Checklist

### Phase 1: Install CLIs

```bash
brew install flyctl
npm i -g vercel
# Verify
fly version
vercel --version
```

### Phase 2: Supabase — Database

- [ ] Create project `colab-dev` in US East region.
- [ ] Note your DB password and `<project-ref>`.
- [ ] In SQL Editor, run:
  ```sql
  CREATE EXTENSION IF NOT EXISTS postgis;
  CREATE EXTENSION IF NOT EXISTS vector;
  CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
  CREATE EXTENSION IF NOT EXISTS pg_trgm;
  ```
- [ ] Get connection string: Settings → Database → URI → copy.
- [ ] Set env var locally:
  ```bash
  export SUPABASE_DB_URL="postgresql://postgres:<pw>@db.<ref>.supabase.co:5432/postgres"
  ```
- [ ] Run migrations:
  ```bash
  make migrate-supabase
  ```

### Phase 3: Upstash — Redis

- [ ] Create database `colab-redis` in US-East-1, TLS enabled.
- [ ] Copy `rediss://` URL from Details tab.
- [ ] Save as `REDIS_URL` for Fly secrets below.

### Phase 4: CloudAMQP — RabbitMQ

- [ ] Create instance `colab-dev` on Little Lemur plan in AWS US-East-1.
- [ ] Copy AMQP URL from Details tab (format: `amqps://user:pw@host/vhost`).
- [ ] Save as `RABBITMQ_URL` for Fly secrets below.

### Phase 5: Cloudflare R2 — Object Storage

- [ ] Create buckets: `colab-portfolio-prod`, `colab-chat-files-prod`, `colab-mockup-assets-prod`.
- [ ] Create R2 API token with Object Read & Write.
- [ ] Save `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ENDPOINT`.

### Phase 6: Resend — Email

- [ ] Create account, add and verify domain `colabclub.net`.
- [ ] Create API key. Save as `RESEND_API_KEY`.

### Phase 7: Fly.io — Create Apps

```bash
fly auth login

# gateway
fly launch --no-deploy --copy-config \
  --name colab-gateway-prod --region iad \
  --dockerfile services/gateway-svc/Dockerfile \
  --config services/gateway-svc/fly.toml

# auth
fly launch --no-deploy --copy-config \
  --name colab-auth-prod --region iad \
  --dockerfile services/auth-svc/Dockerfile \
  --config services/auth-svc/fly.toml

# profile
fly launch --no-deploy --copy-config \
  --name colab-profile-prod --region iad \
  --dockerfile services/profile-svc/Dockerfile \
  --config services/profile-svc/fly.toml
```

### Phase 8: Fly.io — Set Secrets

See `docs/deploy/fly.md` for the full `fly secrets set` commands for each service.
Also see `docs/deploy/env-var-mapping.md` for the complete variable mapping.

```bash
# Minimum viable secrets for gateway:
fly secrets set --app colab-gateway-prod \
  AUTH_SVC_URL="https://colab-auth-prod.fly.dev" \
  PROFILE_SVC_URL="https://colab-profile-prod.fly.dev" \
  REDIS_URL="<upstash-rediss-url>" \
  JWT_SECRET="<run: openssl rand -hex 32>"

# auth-svc minimum:
fly secrets set --app colab-auth-prod \
  DATABASE_URL="$SUPABASE_DB_URL" \
  REDIS_URL="<upstash-rediss-url>" \
  RABBITMQ_URL="<cloudamqp-amqps-url>" \
  JWT_SECRET="<same-value-as-gateway>" \
  RESEND_API_KEY="<resend-key>"

# profile-svc minimum:
fly secrets set --app colab-profile-prod \
  DATABASE_URL="$SUPABASE_DB_URL" \
  REDIS_URL="<upstash-rediss-url>" \
  RABBITMQ_URL="<cloudamqp-amqps-url>" \
  R2_ACCOUNT_ID="<cf-account-id>" \
  R2_ACCESS_KEY_ID="<r2-key>" \
  R2_SECRET_ACCESS_KEY="<r2-secret>" \
  R2_ENDPOINT="https://<account-id>.r2.cloudflarestorage.com"
```

### Phase 9: Fly.io — Deploy

```bash
make deploy-fly
# or individually:
fly deploy --app colab-gateway-prod \
  --dockerfile services/gateway-svc/Dockerfile.fly \
  --config services/gateway-svc/fly.toml --remote-only

fly deploy --app colab-auth-prod \
  --dockerfile services/auth-svc/Dockerfile \
  --config services/auth-svc/fly.toml --remote-only

fly deploy --app colab-profile-prod \
  --dockerfile services/profile-svc/Dockerfile \
  --config services/profile-svc/fly.toml --remote-only
```

- [ ] Verify health checks:
  ```bash
  curl https://colab-gateway-prod.fly.dev/healthz
  curl https://colab-auth-prod.fly.dev/healthz
  curl https://colab-profile-prod.fly.dev/healthz
  ```

### Phase 10: Vercel — Web Apps

```bash
vercel login

# Link apps (run once)
cd apps/marketing-web && vercel link && cd ../..
cd apps/consumer-web  && vercel link && cd ../..
cd apps/admin-web     && vercel link && cd ../..

# Set env vars (see docs/deploy/vercel.md for full list)
vercel env add NEXT_PUBLIC_API_URL production --cwd apps/consumer-web
# value: https://colab-gateway-prod.fly.dev

# Deploy
make deploy-vercel
```

- [ ] Verify:
  ```bash
  curl https://colab-marketing.vercel.app    # → 200
  curl https://colab-consumer.vercel.app     # → 200
  ```

### Phase 11: Mobile Demo

```bash
cd apps/mobile
# Create .env.local with:
echo 'EXPO_PUBLIC_API_URL=https://colab-gateway-prod.fly.dev' > .env.local

pnpm expo start
# Scan QR with Expo Go on your phone
```

- [ ] Sign up → verify email/SMS OTP → complete profile → confirm JWT issued.

### Phase 12: CI/CD Secrets (GitHub)

In GitHub repo → Settings → Secrets and variables → Actions, add:

| Secret | Value |
|---|---|
| `FLY_API_TOKEN` | from `fly tokens create deploy -x 999999h` |
| `VERCEL_TOKEN` | from Vercel dashboard → Account Settings → Tokens |
| `VERCEL_ORG_ID` | from `vercel whoami --json` |
| `VERCEL_PROJECT_ID_MARKETING` | from `.vercel/project.json` in marketing-web |
| `VERCEL_PROJECT_ID_CONSUMER` | from `.vercel/project.json` in consumer-web |
| `VERCEL_PROJECT_ID_ADMIN` | from `.vercel/project.json` in admin-web |

Then push a tag to trigger CI:
```bash
git tag v0.3.0 && git push origin v0.3.0
```

---

## Configs Produced

| Area | Files |
|---|---|
| Fly.io | `services/gateway-svc/fly.toml`, `services/auth-svc/fly.toml`, `services/profile-svc/fly.toml`, `services/gateway-svc/Dockerfile.fly` |
| Vercel | `apps/marketing-web/vercel.json`, `apps/consumer-web/vercel.json`, `apps/admin-web/vercel.json` |
| Docs | `docs/deploy/fly.md`, `docs/deploy/managed-services.md`, `docs/deploy/vercel.md`, `docs/deploy/expo-demo.md`, `docs/deploy/env-var-mapping.md` |
| Scripts | `scripts/deploy/migrate-supabase.sh` |
| Makefile | targets: `deploy-fly`, `deploy-vercel`, `migrate-supabase` |
| CI | `.github/workflows/deploy-fly.yml`, `.github/workflows/deploy-vercel.yml` |

---

## Top 3 Things to Verify Post-Deploy

1. **JWT consistency:** `JWT_SECRET` must be identical in gateway-svc and auth-svc Fly secrets. A mismatch causes 401 on every proxied request. Verify with `fly secrets list --app colab-gateway-prod` and `fly secrets list --app colab-auth-prod`.

2. **Supabase connection pool:** Free tier caps at 60 connections total. With 3 services each using up to 10 pool connections, you're at 30/60. Watch for `too many connections` errors in `fly logs` and reduce `DATABASE_POOL_MAX` if needed.

3. **Cold-start latency:** Fly free machines sleep at min=0. First request after idle can take 2-3 s. Run `bash scripts/smoke/demo_signup.sh` against the Fly URLs to confirm the full flow completes before the 5 s health check timeout.
