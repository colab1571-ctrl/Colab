# Clarify Log — Colab/VibeMatch Master Spec

> 23 rounds, 2026-05-11. Bullets are by round; full reasoning in spec §0.

## R1 — Scope & launch reality
- SCOPE-1 Milestone scope = **Full vision as written** (later refined: ads deferred in R17).
- GEO-1 Launch = **US-only at creator hubs** (later revised in R15a → Worldwide soft-launch → revised again to US/CA/AU/NZ/IN in R22 reconciliation).
- ARC-1 Client = **React Native + Expo**, both iOS App Store + Google Play.
- TIMELINE-1 = **Quality-first**.

## R2 — Backend foundation
- ARC-3 = **Microservices from day 1** (full SOA, 12+ services).
- ARC-4 = **Python (FastAPI)**.
- ARC-5 (initial) = tRPC + REST mix → conflict surfaced.
- ARC-6 = **Postgres + Redis** day 1.

## R2b — API reconciliation + service decomposition
- ARC-5 = **REST via FastAPI + OpenAPI codegen → typed TS client**.
- ARC-3 detail = **12+ services (full SOA)**.
- Inter-service = **REST + async RabbitMQ**.
- API gateway = **Managed (AWS API Gateway)**.

## R3 — Cloud, auth, queue, storage
- ARC-21 = **AWS**.
- ARC-7 = **Custom auth in FastAPI**.
- MQ host = **Amazon MQ for RabbitMQ**.
- ARC-9 + ARC-22 = **AWS S3 + CloudFront**.

## R4 — Compute, realtime, push
- AWS compute = **EKS (Kubernetes)**.
- ARC-8 = **Custom WebSocket service** on AWS.
- ARC-20 = **Expo Push + AWS SNS Mobile Push**.

## R5 — AI stack
- ARC-14 = **OpenAI** (GPT-4.x).
- Embeddings = **OpenAI text-embedding-3-large** in pgvector.
- ARC-15+16 = **Replicate** aggregator.
- ARC-17 = **Multi-tool layered moderation** (OpenAI Moderation + AWS Rekognition + pHash + Chromaprint + semantic).

## R6 — Identity + Payments + OAuth + Age
- ARC-18 = **Persona** built-in workflow.
- ARC-19 = **RevenueCat + Stripe**.
- ARC-27 = **Instagram, YouTube, Spotify** at launch (TikTok deferred).
- COMP-2 = **18+ only** globally.

## R7 — Collab tools
- ARC-10 = **tldraw** embed.
- ARC-11 = **Build custom** project-plan.
- ARC-12 = **Google Meet only**.
- ARC-13 = **Recall.ai** bot.

## R8 — Observability
- ARC-25 = **Postgres + pgvector**.
- ARC-26 = **PostGIS + Mapbox**.
- ARC-28/29/30 = **PostHog + Sentry + CloudWatch**.
- ARC-32 = **GitHub Actions + EAS + Fastlane**.

## R9 — Web, secrets, workers, cache
- ARC-2 = **Full web app + marketing + admin** (three Next.js apps).
- ARC-31 = **AWS Secrets Manager + Parameter Store**.
- ARC-24 = **Celery** on RabbitMQ.
- ARC-23 = **Redis** for sessions + rate-limit + hot feed cache + idempotency.

## R10 — Web stack + Onboarding
- Web stack = **Three separate Next.js apps** (marketing-static + consumer-web + admin-console).
- A-2 selfie gate = **Soft block — only badge gated**.
- A-1 email verify = **Magic link + 6-digit OTP fallback**.
- A-4/A-5 signup methods = **email + Apple + Google + Phone SMS-OTP** (confirmed in R10b after conflict).

## R11 — Profile constraints
- A-3 selfie UX = **Persona built-in workflow**.
- A-6 vocations = **9 categories + curated sub-tags**.
- A-8/9/10 limits = **Bio 280ch, Obsessed 140ch, 12 portfolio items, image 10MB / audio 30MB / video 100MB**.
- A-11/12 AI-review action = **Soft warning + manual queue**.

## R12 — Feed mechanics
- B-1 feed style = **Both modes (toggle infinite-scroll vs swipeable)**.
- B-2 daily cap = **Free 30/day, Premium unlimited**.
- B-3 ranking weights = **40% embedding / 25% complementary-vocation / 15% activity / 10% health / 10% randomization**.
- B-6 profile detail = **Full profile**.

## R13 — Request mechanics
- B-7/B-8 request shape = **250-char synopsis, no attachments**.
- B-12/B-13 free quota = **5/wk, Premium unlimited**.
- B-9 TTL (revised) = **30 days then archive (not delete)**.
- B-14 direction = **Two-way, premium can hide from non-premium**.

## R14 — Filters + recs + mockup timing
- B-4 radius = **Auto-locale 50mi/80km default, max 500mi/800km or Anywhere**.
- B-5 health filter = **No filter exposure — internal ranking only**.
- B-10 AI recs = **Top-of-feed row + dedicated tab**.
- B-11 mockup timing = **Post-match only with mutual consent**.

## R15 — Collab workspace
- B-12 mockup quota = **Premium-only feature** (no free mockups).
- C-1/C-2 file caps = **Image 10MB, audio 50MB, video 250MB, doc 25MB**; whitelist common types.
- C-3 AI commands = **5 launch commands** (`/mockup-image`, `/mockup-audio`, `/summarize-chat`, `/brainstorm`, `/palette`), Premium-only.
- C-5 screenshot = **Android FLAG_SECURE + iOS overlay warning**.

## R15a — Worldwide compliance follow-ups
- Data residency = **US-only with SCCs** at launch.
- Stores = **All US/EU/UK/CA/AU/NZ + IN** (later revised in R22 cookie reconcile to drop EU/UK).
- Tax engine = **Stripe Tax + RevenueCat store-handled**.
- DSR = **Full GDPR-grade for everyone**.

## R16 — Chat export + feedback + archive
- C-6/C-7 export = **PDF + ZIP, Premium-only**.
- C-8 rating = **Thumbs up/down + tag chips** (revises source's 1–5).
- C-9 inactivity = **14d nudge / 30d auto-archive**.
- C-10 nudge = **Push + in-app banner; email fallback**.

## R17 — Ads + Premium structure
- D-1 ads at launch = **No ads at launch** (schema lives, UI deferred).
- D-2 attribution = **Per-user unique coupon code** (when ads ship).
- D-3 Premium vs ads = **Per-user toggle in settings**.
- E-1 tiers = **Free + Premium + Premium Pro**.

## R18 — Pricing detail
- E-2 prices = **Lock values later; build tier-flexible billing**.
- E-3 SKUs = **Both monthly + annual at launch**.
- E-4 credits = **Lock values later; build credit-flexible billing**.
- E-5/E-6 dunning + refund = **Standard dunning + 14-day no-questions refund**.

## R19 — Entitlements, moderation, DMCA, support
- E-1 detail = **Lock values later; spec entitlement axes** (invites, AI credits, ads, export, visibility, support priority, mockup fidelity, portfolio PDF, see-who-saved-you).
- MOD-1 = **Risk-tiered (<0.4/0.4-0.7/0.7-0.9/≥0.9)** with IP+harassment-threat always human.
- MOD-2 DMCA agent = **Deferred** (US safe-harbor not claimed — open risk).
- F-1 SLAs = **Standard tiered** (harassment 4h/24h; IP 24h/7d; payment 24h/72h; technical 24h/5d; other 48h/7d; Pro 2× faster ack).

## R20 — NFRs
- NFR-1/3 = **P95 API <200ms, feed <300ms, chat <500ms; 99.9% availability**.
- NFR-5/6 = **WCAG 2.1 AA + English at launch + i18n-ready**.
- G-1 search = **Titles + descriptions + collaborator names + file names**.
- PQ-1 = **Optional quiz at onboarding + matching signal weight**.

## R21 — Scale, offline, KPI, name
- NFR-2 scale = **10k DAU launch → 100k DAU by M6**.
- NFR-7 offline = **Read-cache + queued writes**.
- METRIC-1 = **Defer targets; track metrics only**.
- LEGAL-1 = **Codename 'Colab'**, brand TBD at launch (BRAND_NAME constant).

## R22 — Data model, retention, push, cookie
- D-MODEL-1 = **Full data-model rewrite by Phase 5 detailing agents**.
- Chat retention = **Lifetime + 3 years archived after deletion**.
- Push opt-in = **First-needed pre-permission card**.
- Cookie = **'Accept All' banner only** → conflict with GDPR → user dropped EU/UK from launch (revised GEO-1 = **US/CA/AU/NZ/IN**).

## R23 — Final residuals
- Notifications = **Granular per-type** with sensible defaults (all on except marketing + weekly digest).
- Blocking = **Hard mutual block**; collabs read-only then auto-archive at +30d.
- Save visibility = **Premium-only feature** (anonymous count for free; saver names visible to Premium).
- ATT = **Defer to launch — no cross-app tracking at launch**, hooks ready.
