# DEPLOY-RESUME.md — Colab PaaS Deploy session

> Companion to `runs/RESUME.md`. This file is specifically for the in-flight PaaS deploy that paused on **2026-05-28** to install the Supabase MCP.

## tl;dr — what was happening

- Stage 3 PaaS deploy was in progress. Pivoted from Fly (now requires CC) to **Render** (no CC).
- Accounts created via GitHub OAuth as **Amay-Singh**: Render (existing), Supabase org "Colab", Supabase project `colab-dev` (us-west-2), Supabase PAT.
- Supabase MCP added to `~/.claude.json`; Claude Code must restart for it to load.
- Session memory captured at `/Users/amays/.claude/projects/-Users-amays/memory/project_colab_deploy.md`. Resume by saying "remember" in a fresh Claude Code session.

## Resume from step 4 (of 14)

1. ✅ Pick deploy target (Render)
2. ✅ Create Render account
3. ✅ Create Supabase project + PAT
4. ⏸ **Enable Postgres extensions on Supabase** — `postgis`, `vector`, `uuid-ossp`, `pg_trgm`. Use the new Supabase MCP (`mcp__supabase__execute_sql` or similar — check tool list).
5. Create Upstash Redis → grab `rediss://` URL
6. Create CloudAMQP RabbitMQ Little Lemur → grab `amqps://` URL
7. Write `render.yaml` Blueprint mapping the 3 services (gateway-svc, auth-svc, profile-svc)
8. Commit + push render.yaml
9. Create Render Blueprint from this repo
10. Set per-service env vars (`DATABASE_URL`, `REDIS_URL`, `RABBITMQ_URL`, shared `JWT_SECRET`, inter-service URLs)
11. First deploy; verify `/healthz` on all 3 services
12. Run Alembic migrations against Supabase (auth + profile)
13. Sign up Vercel; link `marketing-web`, `consumer-web`, `admin-web`; set `NEXT_PUBLIC_API_URL`
14. Smoke test: `bash scripts/smoke/demo_signup.sh` against the live Render URLs

## Key facts to look up

- **Supabase project:** ref `obtqouqjqedfosgumkxu`, region us-west-2, DB password in `.deploy/credentials.csv`.
- **DATABASE_URL for Render must be the POOLER URL (IPv4)**, not the direct 5432 (IPv6-only on free tier). Format:
  ```
  postgresql://postgres.obtqouqjqedfosgumkxu:<PASSWORD>@aws-0-us-west-2.pooler.supabase.com:5432/postgres
  ```
- **Render workspace:** `tea-d3fc2hili9vc73ee9qtg` (oregon).
- All Dockerfiles bind `0.0.0.0:8000` — Render auto-detects, no changes needed.
- Credentials log: `.deploy/credentials.csv` (gitignored).

## Open code gaps that won't bite *this* deploy

The first deploy is only gateway/auth/profile. The known gaps from `RESUME.md` (chat-svc internal endpoints, collab-svc generated columns, native iOS/Android modules, Y.js binding, MJML templates) all live in services we're NOT deploying yet. If signup email sending throws, stub it by setting `EMAIL_PROVIDER=noop` on auth-svc.
