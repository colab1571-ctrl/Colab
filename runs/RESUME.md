# RESUME.md — Colab pipeline state

> Last updated: 2026-05-20. Read this first, then `runs/state.json`.

## origin/main HEAD

`faae1ba` — Stage 3 merge (PR #77). All planning + implementation + build matrix + docker-compose demo + free-tier PaaS deploy configs are on `origin/main`.

## What's done (on `origin/main`)

| Layer | State |
|---|---|
| Phase 0–6 (specs, plans, reconciliation, IMPLEMENTATION_PLAN) | ✅ |
| Phase 7 P0–P18 — 19 features, ~166 commits | ✅ |
| Stage 1 — build matrix: 20/20 services compile, colab_common 32/32 tests | ✅ |
| Stage 2 — docker-compose demo: 7 healthy containers, signup smoke 5/5 | ✅ (PR #76) |
| Stage 3 — Fly+Supabase+Upstash+CloudAMQP+R2+Vercel+Expo deploy configs + docs | ✅ (PR #77) |

## What's running on the laptop right now

`docker ps` (as of last check): postgres, redis, rabbitmq, localstack, auth-svc, gateway-svc, profile-svc — all healthy. Demo signup → JWT works end-to-end via `bash scripts/smoke/demo_signup.sh`.

## What's NOT done (honest gap list)

### Code gaps flagged by implementation agents but never closed

1. **chat-svc missing 2 internal endpoints** — `POST /internal/rooms/{room_id}/messages` and `GET /internal/rooms/by-collab/{collab_id}`. Called by collab-svc, ai-orchestrator-svc, meeting-svc → they will 404 on first cross-service call.
2. **collab-svc generated columns bug** — `least_participant` / `greatest_participant` are `GENERATED ALWAYS AS ... STORED` in migration but service-layer still passes them in `pg_insert().values()`. Postgres rejects first insert.
3. **Android FLAG_SECURE Kotlin module** — RN side wired, native module never written.
4. **iOS screenshot-detect Swift module** — same.
5. **Persona / Apple Sign-In / Google Sign-In RN native bindings** — package.json declares deps; codegen specs missing.
6. **Y.js whiteboard ws server** — collab-svc has an asyncio stub, not a real ypy-websocket binding.
7. **MJML email templates** — auth-svc references templates that were deferred pending brand voice.
8. **discovery-svc 0002 cross-schema view migration** — assumes shared Postgres; will break when services split DBs.

### Services not yet booted

Only 3 of 19 backend services have ever actually run in docker-compose (gateway, auth, profile). The other 16 compile-gate clean but have never started; integration bugs will surface when they boot.

### User-side blockers (out-of-band)

- AWS account (for prod terraform apply)
- Apple Developer enrollment ($99/yr)
- Google Play Console ($25 one-time)
- Stripe live KYC
- RevenueCat prod
- Persona prod KYB
- Meta + Spotify dev app review (2–6 weeks)
- India DLT SMS registration (4–8 weeks)
- DMCA agent registration (explicitly deferred per master §0)
- Pen-test vendor procurement

## Local git status (as of session end)

Local git operations hang due to a macOS file-watch / Spotlight interaction (Windsurf IDE was a contributor, but the issue persists even closed). Workaround:
1. `cd /Users/amays/Desktop/Work/Colab_3`
2. `pkill -9 -f "git "; rm -f .git/index.lock`
3. Run command in Terminal.app (not VS Code/Windsurf integrated terminal)
4. If still hung, reboot

Or use `gh` CLI for remote ops (PRs, merges) — it bypasses the local index entirely. That's how Stage 2 + Stage 3 actually landed on origin.

## How to resume in a new session

1. Pull latest: `cd /Users/amays/Desktop/Work/Colab_3 && git pull origin main`
2. Confirm Docker state: `docker ps` (auth+gateway+profile should be running; if not, `docker compose up -d auth-svc gateway-svc profile-svc postgres redis rabbitmq localstack`)
3. Open this file (`runs/RESUME.md`) and `runs/state.json` for the full picture
4. Decide what to attack next (see "What to attack next" below)

## What to attack next (in rough priority order)

| # | Item | Effort | Why |
|---|---|---|---|
| 1 | Add the 2 missing chat-svc internal endpoints | 1 day | Unblocks collab/ai/meeting services on bring-up |
| 2 | Fix collab-svc generated-columns insert bug | 1 hour | First insert otherwise fails |
| 3 | Bring up 5 more services in docker-compose (discovery, matching, geo, invite, notification) | 2–3 days | Pushes the demo path from "signup" to "match + nudge" |
| 4 | User executes Stage 3 deploy plan (`runs/STAGE3_REPORT.md`) | 1–2 hours of user time | Public URL for sharing demo |
| 5 | Wire Expo Go mobile to local stack | 1 hour | Real phone demo |
| 6 | Native Android FLAG_SECURE module | 1 day | Required by AI mockup viewer |
| 7 | Native iOS screenshot detect | 1 day | Same |
| 8 | Y.js websocket real binding | 2–3 days | Whiteboard sync between users |
| 9 | Bring up chat + collab + ai + meeting (after #1 + #2) | 3–5 days | End-to-end collab demo |
| 10 | Vendor account creation (parallelizable, user-side) | 1–6 weeks elapsed | Required for prod features |

## Spec/plan artifacts (unchanged baseline)

- `specs/000-master/spec.md` — clarified master spec (~95 items resolved across 23 rounds)
- `specs/001-…/spec.md` through `specs/019-…/spec.md` — 19 feature specs + plans
- `runs/IMPLEMENTATION_PLAN.md` — phase order
- `runs/RECONCILIATION.md` — Phase 5b cross-feature reconciliation
- `runs/clarify_log.md` — all 23 clarify rounds with decisions
- `runs/PROJECT_LOG.md` — chronological session log
- `runs/STAGE1_REPORT.md` — build matrix outcome
- `runs/STAGE3_REPORT.md` — deploy checklist

## Locked decisions (don't re-litigate — read `specs/000-master/spec.md` §0)

- Apex domain: **colabclub.net** (registered)
- Launch geo: US, CA, AU, NZ, IN (EU/UK dropped)
- Stack: React Native + Expo / 3× Next.js / Python FastAPI 19 microservices on AWS EKS / Postgres 16 + pgvector + PostGIS / Redis / RabbitMQ
- AI: OpenAI + Replicate + Recall.ai
- Identity: Persona
- Payments: RevenueCat + Stripe
- 18+ only, WCAG 2.1 AA, English at launch, i18n-ready

## Tools that need PATH at every shell start

```bash
export PATH="$HOME/.local/bin:$PATH"   # uv
```

`pnpm` (9.15.9), `node` (v23), `python3` (3.12), `docker` (27.3.1), `gh` (2.89.0) are all on PATH by default.
