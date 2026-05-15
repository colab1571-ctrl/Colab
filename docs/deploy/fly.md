# Fly.io Deploy Guide

Three services in Stage 3 scope: **gateway-svc**, **auth-svc**, **profile-svc**.
Each runs as a free-tier `shared-cpu-1x` (256 MB) Fly Machine in `iad` (Virginia).

## Prerequisites

```bash
brew install flyctl
fly auth login          # opens browser — sign up at fly.io first (free)
```

## 1. Create the apps (once per service)

Run from the **repo root**. `--no-deploy` creates the app record without building.

```bash
# gateway
fly launch --no-deploy --copy-config \
  --name colab-gateway-prod \
  --region iad \
  --dockerfile services/gateway-svc/Dockerfile \
  --config services/gateway-svc/fly.toml

# auth
fly launch --no-deploy --copy-config \
  --name colab-auth-prod \
  --region iad \
  --dockerfile services/auth-svc/Dockerfile \
  --config services/auth-svc/fly.toml

# profile
fly launch --no-deploy --copy-config \
  --name colab-profile-prod \
  --region iad \
  --dockerfile services/profile-svc/Dockerfile \
  --config services/profile-svc/fly.toml
```

## 2. Set secrets (fly secrets set)

Fly secrets are injected as environment variables at runtime — never baked into the image.

### gateway-svc
```bash
fly secrets set --app colab-gateway-prod \
  AUTH_SVC_URL="https://colab-auth-prod.fly.dev" \
  PROFILE_SVC_URL="https://colab-profile-prod.fly.dev" \
  REDIS_URL="rediss://<upstash-endpoint>:6380" \
  JWT_SECRET="<32-byte-random>" \
  SENTRY_DSN_API="<sentry-dsn>" \
  POSTHOG_API_KEY_WEB="<posthog-key>"
```

### auth-svc
```bash
fly secrets set --app colab-auth-prod \
  DATABASE_URL="postgresql://postgres:<password>@db.<supabase-ref>.supabase.co:5432/postgres" \
  REDIS_URL="rediss://<upstash-endpoint>:6380" \
  RABBITMQ_URL="amqps://<cloudamqp-url>" \
  JWT_SECRET="<same-32-byte-random>" \
  APPLE_TEAM_ID="<team-id>" \
  APPLE_BUNDLE_ID="net.colabclub.colab" \
  APPLE_KEY_ID="<key-id>" \
  APPLE_PRIVATE_KEY="<p8-contents-newline-escaped>" \
  APPLE_SIGN_IN_CLIENT_ID="<client-id>" \
  GOOGLE_CLIENT_ID_IOS="<google-ios-client-id>" \
  GOOGLE_CLIENT_ID_WEB="<google-web-client-id>" \
  GOOGLE_CLIENT_SECRET_WEB="<google-web-secret>" \
  RESEND_API_KEY="<resend-key>" \
  SES_FROM_ADDRESS="no-reply@colabclub.net" \
  PERSONA_API_KEY="<persona-sandbox-key>" \
  PERSONA_TEMPLATE_ID="<template-id>" \
  PERSONA_WEBHOOK_SECRET="<webhook-secret>" \
  SENTRY_DSN_API="<sentry-dsn>"
```

### profile-svc
```bash
fly secrets set --app colab-profile-prod \
  DATABASE_URL="postgresql://postgres:<password>@db.<supabase-ref>.supabase.co:5432/postgres" \
  REDIS_URL="rediss://<upstash-endpoint>:6380" \
  RABBITMQ_URL="amqps://<cloudamqp-url>" \
  S3_BUCKET_PORTFOLIO="colab-portfolio-prod" \
  S3_BUCKET_CHAT_FILES="colab-chat-files-prod" \
  S3_BUCKET_MOCKUP_ASSETS="colab-mockup-assets-prod" \
  R2_ACCOUNT_ID="<cloudflare-account-id>" \
  R2_ACCESS_KEY_ID="<r2-access-key>" \
  R2_SECRET_ACCESS_KEY="<r2-secret-key>" \
  R2_ENDPOINT="https://<account-id>.r2.cloudflarestorage.com" \
  OPENAI_API_KEY="<openai-key>" \
  REPLICATE_API_TOKEN="<replicate-token>" \
  MAPBOX_SECRET_TOKEN="<mapbox-token>" \
  SENTRY_DSN_API="<sentry-dsn>"
```

## 3. Deploy

Each deploy builds from your local Docker context (monorepo root) and pushes to Fly's registry.

```bash
# Deploy all three (run from repo root)
fly deploy --app colab-gateway-prod \
  --dockerfile services/gateway-svc/Dockerfile.fly \
  --config services/gateway-svc/fly.toml

fly deploy --app colab-auth-prod \
  --dockerfile services/auth-svc/Dockerfile \
  --config services/auth-svc/fly.toml

fly deploy --app colab-profile-prod \
  --dockerfile services/profile-svc/Dockerfile \
  --config services/profile-svc/fly.toml
```

> **Tip:** gateway-svc uses `Dockerfile.fly` (1 uvicorn worker, uvloop) to avoid OOM on 256 MB.

## 4. Verify

```bash
curl https://colab-gateway-prod.fly.dev/healthz
curl https://colab-auth-prod.fly.dev/healthz
curl https://colab-profile-prod.fly.dev/healthz
```

All should return `{"status": "ok"}`.

## 5. Custom domain (optional — colabclub.net)

```bash
fly certs add api.colabclub.net --app colab-gateway-prod
```

Then add a CNAME at your DNS provider:
```
api.colabclub.net  CNAME  colab-gateway-prod.fly.dev
```

Fly auto-provisions a TLS certificate via Let's Encrypt within ~60 seconds.

## 6. View logs

```bash
fly logs --app colab-gateway-prod
fly logs --app colab-auth-prod
fly logs --app colab-profile-prod
```

## Free tier limits

| Resource | Limit |
|---|---|
| Machines | 3 shared-cpu-1x included free |
| Bandwidth | 160 GB/mo outbound |
| Machine RAM | 256 MB each |
| Auto-stop | Machines sleep when idle (cold start ~1-2 s) |
