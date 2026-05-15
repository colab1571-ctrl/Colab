# Secrets Checklist — Where Every Env Var Goes

Every variable from `.env.example` mapped to its Stage 3 destination.

Legend:
- **Fly/gateway** = `fly secrets set --app colab-gateway-prod`
- **Fly/auth** = `fly secrets set --app colab-auth-prod`
- **Fly/profile** = `fly secrets set --app colab-profile-prod`
- **Vercel/marketing** = `vercel env add ... --cwd apps/marketing-web`
- **Vercel/consumer** = `vercel env add ... --cwd apps/consumer-web`
- **Vercel/admin** = `vercel env add ... --cwd apps/admin-web`
- **Expo** = `apps/mobile/.env.local` (prefix `EXPO_PUBLIC_` for client-side)
- **Supabase** = set in Supabase project dashboard (not exposed to services)
- **N/A-stage3** = not needed until later services are deployed

## Application

| Variable | gateway | auth | profile | Vercel | Expo | Notes |
|---|---|---|---|---|---|---|
| `NODE_ENV` | set `production` in fly.toml | same | same | framework default | — | |
| `ENV` | `prod` in fly.toml | same | same | — | — | |
| `LOG_LEVEL` | `info` in fly.toml | same | same | — | — | |
| `APP_DOMAIN` | ✓ | ✓ | ✓ | — | — | |
| `API_DOMAIN` | ✓ | ✓ | — | `NEXT_PUBLIC_API_URL` | `EXPO_PUBLIC_API_URL` | |

## Database

| Variable | gateway | auth | profile | Notes |
|---|---|---|---|---|
| `DATABASE_URL` | — | ✓ Fly secret | ✓ Fly secret | Supabase connection string |
| `DATABASE_REPLICA_URL` | — | N/A-stage3 | N/A-stage3 | Not available on free Supabase |
| `DATABASE_POOL_MIN` | — | 2 (free tier) | 2 (free tier) | Lower for free tier |
| `DATABASE_POOL_MAX` | — | 10 (free tier) | 10 (free tier) | Supabase free = max 60 connections |

## Redis

| Variable | gateway | auth | profile | Notes |
|---|---|---|---|---|
| `REDIS_URL` | ✓ Fly secret | ✓ Fly secret | ✓ Fly secret | Upstash `rediss://` URL |
| `REDIS_TLS` | `true` | `true` | `true` | Upstash requires TLS |

## Storage (Cloudflare R2)

| Variable | profile | Notes |
|---|---|---|
| `S3_BUCKET_PORTFOLIO` | ✓ Fly secret | `colab-portfolio-prod` |
| `S3_BUCKET_CHAT_FILES` | ✓ Fly secret | `colab-chat-files-prod` |
| `S3_BUCKET_MOCKUP_ASSETS` | ✓ Fly secret | `colab-mockup-assets-prod` |
| `R2_ACCOUNT_ID` | ✓ Fly secret | Cloudflare account ID |
| `R2_ACCESS_KEY_ID` | ✓ Fly secret | R2 API token |
| `R2_SECRET_ACCESS_KEY` | ✓ Fly secret | R2 API secret |
| `R2_ENDPOINT` | ✓ Fly secret | `https://<account-id>.r2.cloudflarestorage.com` |
| `CLOUDFRONT_DISTRIBUTION_ID` | N/A-stage3 | Not used with R2 |

## RabbitMQ

| Variable | auth | profile | Notes |
|---|---|---|---|
| `RABBITMQ_URL` | ✓ Fly secret | ✓ Fly secret | CloudAMQP `amqps://` URL |

## Email

| Variable | auth | Notes |
|---|---|---|
| `SES_FROM_ADDRESS` | ✓ Fly secret | `no-reply@colabclub.net` |
| `RESEND_API_KEY` | ✓ Fly secret | Replaces SES for Stage 3 |

## Auth / JWT

| Variable | gateway | auth | Notes |
|---|---|---|---|
| `JWT_SECRET` | ✓ Fly secret | ✓ Fly secret | **Must be identical** in both services |
| `JWT_ACCESS_TTL_SECONDS` | fly.toml env | fly.toml env | 900 |
| `JWT_REFRESH_TTL_SECONDS` | fly.toml env | fly.toml env | 2592000 |

## Apple Sign-In

| Variable | auth | Notes |
|---|---|---|
| `APPLE_TEAM_ID` | ✓ Fly secret | |
| `APPLE_BUNDLE_ID` | ✓ Fly secret | `net.colabclub.colab` |
| `APPLE_KEY_ID` | ✓ Fly secret | |
| `APPLE_PRIVATE_KEY` | ✓ Fly secret | `.p8` contents, newlines as `\n` |
| `APPLE_SIGN_IN_CLIENT_ID` | ✓ Fly secret | |

## Google Sign-In

| Variable | auth | Vercel/consumer | Expo | Notes |
|---|---|---|---|---|
| `GOOGLE_CLIENT_ID_IOS` | ✓ Fly secret | — | `EXPO_PUBLIC_GOOGLE_CLIENT_ID_IOS` | |
| `GOOGLE_CLIENT_ID_ANDROID` | ✓ Fly secret | — | `EXPO_PUBLIC_GOOGLE_CLIENT_ID_ANDROID` | |
| `GOOGLE_CLIENT_ID_WEB` | ✓ Fly secret | `NEXT_PUBLIC_GOOGLE_CLIENT_ID` | — | |
| `GOOGLE_CLIENT_SECRET_WEB` | ✓ Fly secret | — | — | Server-only |

## Identity (Persona)

| Variable | auth | Notes |
|---|---|---|
| `PERSONA_API_KEY` | ✓ Fly secret | Use **sandbox** key for Stage 3 |
| `PERSONA_TEMPLATE_ID` | ✓ Fly secret | |
| `PERSONA_WEBHOOK_SECRET` | ✓ Fly secret | |

## AI Providers

| Variable | profile | gateway | Notes |
|---|---|---|---|
| `OPENAI_API_KEY` | ✓ Fly secret | ✓ Fly secret | Pay-as-you-go, ~$5 covers testing |
| `OPENAI_ORG_ID` | ✓ Fly secret | — | |
| `REPLICATE_API_TOKEN` | ✓ Fly secret | — | |
| `REPLICATE_WEBHOOK_SECRET` | ✓ Fly secret | — | |

## Payments (N/A Stage 3 — billing-svc not deployed yet)

| Variable | Notes |
|---|---|
| `STRIPE_SECRET_KEY` | N/A-stage3 |
| `STRIPE_PUBLISHABLE_KEY` | N/A-stage3 — add to consumer-web when billing-svc deployed |
| `REVENUECAT_*` | N/A-stage3 |

## Observability

| Variable | Fly services | Vercel apps | Expo | Notes |
|---|---|---|---|---|
| `SENTRY_DSN_API` | ✓ all 3 Fly secrets | — | — | Single DSN for all API services |
| `SENTRY_DSN_CONSUMER_WEB` | — | Vercel/consumer | — | |
| `SENTRY_DSN_ADMIN` | — | Vercel/admin | — | |
| `SENTRY_DSN_MARKETING` | — | Vercel/marketing | — | |
| `SENTRY_DSN_RN` | — | — | ✓ Expo env | |
| `POSTHOG_API_KEY_WEB` | ✓ gateway | Vercel/consumer + marketing | — | |
| `POSTHOG_API_KEY_MOBILE` | — | — | ✓ Expo env | |
| `POSTHOG_HOST` | — | Vercel/consumer + marketing | ✓ Expo env | `https://us.i.posthog.com` |

## Geo / Maps

| Variable | profile | Vercel/consumer | Expo | Notes |
|---|---|---|---|---|
| `MAPBOX_SECRET_TOKEN` | ✓ Fly secret | — | — | Server-side only |
| `MAPBOX_PUBLIC_TOKEN` | — | `NEXT_PUBLIC_MAPBOX_TOKEN` | `EXPO_PUBLIC_MAPBOX_TOKEN` | |

## Social OAuth (N/A Stage 3)

| Variable | Notes |
|---|---|
| `META_APP_*` | N/A-stage3 |
| `SPOTIFY_*` | N/A-stage3 |
| `YOUTUBE_API_KEY` | N/A-stage3 |
