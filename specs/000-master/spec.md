# Master Specification — Colab (codename) / Working name TBD

> Status: **CLARIFIED — Phase 3 complete (23 rounds, ~95 items resolved)**. Source: `/Users/amays/Downloads/Main document.docx` parsed 2026-05-11.
> Codename in code: `Colab` (from repo). User-facing brand: **TBD** before launch.

---

## 0. Locked Decisions Index

### Scope
- **Milestone scope**: Full vision as written — every Journey A–G feature in scope **except ad partnerships (deferred at user direction, schema lives, ads UX not built)**.
- **Timeline posture**: Quality-first.
- **Launch geography (GEO-1)**: **US, Canada, Australia, New Zealand, India** at launch. **EU and UK dropped from the soft-launch** after the cookie-consent reconciliation. English UI only.
- **App store distribution (ARC-33)**: iOS App Store + Google Play, in all five launch regions.
- **Minimum age (COMP-2)**: **18+** globally.
- **DSR posture**: Full GDPR-grade DSRs implemented for everyone (access / rectification / erasure / portability / restriction / objection, 30-day SLA). Over-complies with CCPA, India DPDP, AU Privacy Act 1988, NZ Privacy Act 2020, Canada PIPEDA + Quebec Law 25.
- **Cookie banner**: Simple "Accept All" banner on web (sufficient for chosen launch geos; would not satisfy GDPR/UK-GDPR — drop confirmed).
- **DMCA**: Designated agent registration **deferred**; reduces US safe-harbor protection (user accepts).
- **ATT (Apple App Tracking Transparency)**: No cross-app tracking at launch; ATT prompt deferred; first-party analytics only.

### Architecture (ARC-1 … ARC-33)

| Concern | Choice |
|---|---|
| Client mobile (ARC-1) | **React Native + Expo**, ships both stores |
| Client web (ARC-2) | **Three separate Next.js apps**: marketing-static, consumer-web, admin-console |
| Backend pattern (ARC-3) | **Microservices from day 1 — 12+ FastAPI services** |
| Backend language (ARC-4) | **Python (FastAPI)** |
| API style (ARC-5) | **REST via FastAPI + OpenAPI codegen → typed TS client** for RN + web |
| Database (ARC-6) | **Postgres + Redis** (Postgres primary; Redis for sessions, rate-limit, hot feed cache, idempotency) |
| Auth (ARC-7) | **Custom auth service** in FastAPI (email+password, Apple, Google, phone SMS-OTP). Magic-link + 6-digit-OTP fallback for email verify. |
| Realtime chat (ARC-8) | **Custom WebSocket service** on AWS, behind ALB; messages persisted to Postgres |
| File storage (ARC-9) | **AWS S3 + CloudFront** (signed URLs, bucket versioning, access logs) |
| Whiteboard (ARC-10) | **Embed tldraw** via WebView in RN; persistence in S3 + Postgres |
| Project plan (ARC-11) | **Build custom** native to RN/Web |
| Meeting deep-link (ARC-12) | **Google Meet only** at launch |
| Meeting record/transcript (ARC-13) | **Recall.ai bot** joins meeting; transcript stored to audit log |
| LLM provider (ARC-14) | **OpenAI** (GPT-4.x family) for matching reasoning, in-chat assistant, content summaries |
| Image + audio generation (ARC-15, ARC-16) | **Replicate** aggregator (SDXL/FLUX/MusicGen/Stable Audio etc., webhook-async) |
| Moderation (ARC-17) | **Multi-tool layered**: OpenAI moderation API + AWS Rekognition (image/video) + perceptual-hash (pHash) image dup + Chromaprint audio dup + semantic dup via embeddings |
| Selfie/liveness (ARC-18) | **Persona** (built-in workflow, head-turn + smile) |
| Payments (ARC-19) | **RevenueCat (mobile IAP) + Stripe (web subs, partner payouts, credits)** |
| Push (ARC-20) | **Expo Push (dev) + AWS SNS Mobile Push (prod via APNs + FCM)** |
| Hosting (ARC-21) | **AWS** primary, **EKS (Kubernetes)** for the 12+ services |
| CDN (ARC-22) | CloudFront in front of S3; static web on CloudFront |
| Cache (ARC-23) | Redis (ElastiCache) for sessions, rate-limit, hot feed cache, idempotency |
| Workers (ARC-24) | **Celery** with RabbitMQ broker; Celery Beat for schedules |
| Search / vectors (ARC-25) | **Postgres + pgvector** (text-embedding-3-large); upgrade to OpenSearch later if needed |
| Geospatial (ARC-26) | **PostGIS + Mapbox geocoding** |
| OAuth integrations (ARC-27) | **Instagram Business/Creator, YouTube (Google OAuth), Spotify for Artists** at launch. TikTok deferred. |
| Analytics (ARC-28) | **PostHog** (product analytics, session replay, feature flags) |
| Errors (ARC-29) | **Sentry** (RN + Python + Next.js) |
| Logging/observability (ARC-30) | **AWS CloudWatch** Logs + Container Insights |
| Secrets (ARC-31) | **AWS Secrets Manager + Parameter Store**; EKS pods via IRSA; GitHub Actions via OIDC |
| CI/CD (ARC-32) | **GitHub Actions + EAS Build + Fastlane** |
| Message bus | **Amazon MQ for RabbitMQ** (AMQP); SNS/SQS for AWS-native fanout where simpler |
| API gateway | **AWS API Gateway** (managed); WebSocket APIs for chat |
| Tax engine | **Stripe Tax** (web) + **RevenueCat store-handled** (mobile); India GST handled through Stripe Tax / reseller registration |

### Microservices boundary (initial cut — to be refined in Phase 4)

User chose **12+ services / full SOA**. Proposed initial map (each is a deployable FastAPI service + its own Postgres schema in one cluster):

1. `gateway` — request routing, auth verification, rate-limit, CORS
2. `auth-svc` — signup, login, email/phone verify, OAuth (Apple/Google), session mgmt, JWT, password reset
3. `profile-svc` — profile CRUD, portfolio items, vocations, externals, AI profile review, badge issuance
4. `identity-svc` — Persona integration, selfie/liveness state machine
5. `discovery-svc` — feed assembly (swipe + infinite-scroll modes), filters, "Picked for you" recs, "hide 3mo" list
6. `matching-svc` — embedding generation, nightly ranking job, on-demand re-rank, AI match score
7. `invite-svc` — Vibe Check send/accept/reject/expire, request quotas
8. `collab-svc` — collab lifecycle, status transitions, archive, inactivity nudge, feedback
9. `chat-svc` — WebSocket gateway, message persistence, presence, file-message handling
10. `media-svc` — uploads, S3 signing, virus + moderation scanning pipeline, watermarking
11. `ai-orchestrator-svc` — Replicate webhook handling, 5-command in-chat assistant catalogue, mockup gen, mutual-consent flow
12. `moderation-svc` — risk-tiered routing, AI flag intake, mod queue, moderator actions, DMCA workflow
13. `notification-svc` — push (SNS), email (SES), in-app banner, preferences
14. `billing-svc` — RevenueCat webhooks, Stripe Customer/Subscription/Price, tax, dunning, refunds, credit wallet
15. `support-svc` — ticket intake, SLA timers, AI chatbot, CSAT
16. `analytics-svc` — event ingestion proxy (forward to PostHog), KPI rollups
17. `admin-svc` — backend for the admin/moderator console
18. `geo-svc` — Mapbox proxy, city autocomplete, radius queries
19. `meeting-svc` — Google Meet creation, Recall.ai bot orchestration

(Boundaries will be revisited in Phase 4 — the 12+ user choice is satisfied; trimming may occur where two services share too much state.)

### Compliance & legal

- **Worldwide soft-launch** rolled back to **US/CA/AU/NZ/IN** only.
- **DSR**: 30-day SLA, full set, machine-readable export (JSON + media ZIP), hard-delete primary + 90-day backup purge, audit-log retention exemption documented.
- **Chat + audit-log retention**: lifetime of account + **3 years archived after deletion** (pseudonymized IDs).
- **DMCA agent**: deferred (US safe-harbor not claimed).
- **Cookie consent**: simple "Accept All" banner on web; mobile collects no cookies.
- **18+ only**: ToS-enforced via age-attestation at signup; selfie verification cross-checks face age signals (Persona) flagging visibly-under-18 for manual review.
- **Data residency**: US (us-east-1) with SCCs in DPA. India DPDP-localization addressed via Stripe processor + audit log (residency requirements still being refined — `[NEEDS CLARIFICATION at Phase 5]` for India-specific localization).

---

## 1. Vision & Problem (verbatim from source)

**Mission**: Build the leading AI-powered networking and collaboration platform for rising artists and creators in the gig economy. Low-friction, anti-engagement-farming, productive-partnerships-first.

**Primary user**: Gen Z / Gen Alpha (constrained to 18+ at launch) artis-preneurs across visual, performing, literary, design, digital, media, and craft arts.

**Core anti-pattern**: time-on-app maximization, content farming, engagement metrics. Optimize instead for *real creative output*.

---

## 2. In Scope / Out of Scope (this milestone)

### In scope
All of Journeys A, B, C, E, F, G. Plus moderation, IP-safe audit logging, multi-region rollout.

### Out of scope **this milestone** (locked deferrals)
- **Journey D (Ads + course partnerships)** — schema lives, UI deferred (user decision in R17). Coupon/attribution model recorded for resurrection later.
- **Personality matching as a standalone screen** — quiz is optional at onboarding and feeds matching signal weight; the dedicated screen is deferred.
- **Group collaborations (>2 users)** — verbatim from source.
- **Group chat** — verbatim from source.
- **Multiple projects with the same collaborator** — verbatim from source.
- **Chat translation** — verbatim from source.
- **VibeMatch as production house / label** — verbatim from source.
- **B2B / scouting tools** — verbatim from source.
- **EU + UK go-to-market** — dropped from soft-launch.

---

## 3. Functional Requirements

> Each FR carries the locked MoSCoW tag. **Removed** clarifications are listed in the Decision Index above; remaining `[NEEDS CLARIFICATION]` markers (if any) defer to Phase 5 detailing agents.

### Journey A — Onboarding (auth-svc, profile-svc, identity-svc)

- **FR-A-1 (MUST)** Email + password signup. Magic-link + 6-digit-OTP fallback for verification.
- **FR-A-2 (MUST)** Apple Sign-In, Google Sign-In, Phone (SMS OTP via AWS SNS) — all available at signup screen alongside email.
- **FR-A-3 (MUST)** Age attestation 18+; signup blocked under 18.
- **FR-A-4 (MUST)** Profile setup capture: display name, location (PostGIS lat/long + city via Mapbox autocomplete), radius (auto-locale 50mi/80km default, 'Anywhere' max), vocations (9 categories + curated sub-tags; free-text 'other' flagged), bio (280ch), "obsessed with" (140ch), open-to-remote toggle.
- **FR-A-5 (SHOULD)** OAuth connection: Instagram Business/Creator, YouTube, Spotify for Artists. All optional.
- **FR-A-6 (MUST)** Portfolio upload: up to 12 items; image 10MB, audio 30MB, video 100MB. Whitelisted MIME types.
- **FR-A-7 (COULD)** Optional fields: notable past experience, "what I'm looking for".
- **FR-A-8 (COULD)** Personality quiz (5–7 questions). Optional. Result = `personality_archetype` on Profile; feeds matching with minor weight.
- **FR-A-9 (SHOULD)** Selfie + liveness via Persona built-in workflow. **Soft block — only the Valid Profile Badge is gated**; matching + chat work without it.
- **FR-A-10 (SHOULD)** AI profile review (OpenAI + Rekognition + dup-detection). On flag: **soft warning + manual review queue**. Onboarding proceeds; badge withheld until cleared.
- **FR-A-11 (SHOULD)** Valid Profile Badge granted when (a) email verified, (b) Persona verified, (c) AI profile review passed.
- **FR-A-12 (MUST)** ToS + Privacy + Community Guidelines + age attestation acceptance at signup, click-through, time-stamped.
- **FR-A-13 (SHOULD)** Onboarding analytics (PostHog): drop-off per step. Target ≥70% completion in <8 min.

### Journey B — Discover & Match (discovery-svc, matching-svc, invite-svc)

- **FR-B-1 (MUST)** Home feed: **toggle between infinite-scroll list and swipeable card stack**. User preference persisted.
- **FR-B-2 (MUST)** Daily profile cap: **Free 30/day, Premium unlimited**.
- **FR-B-3 (MUST)** Ranking signals (default weights): 40% portfolio embedding similarity (OpenAI text-embedding-3-large in pgvector), 25% complementary-vocation score, 15% recent activity, 10% profile health, 10% randomization. Weights admin-configurable.
- **FR-B-4 (SHOULD)** "Hide this profile for 3 months" (per-user list).
- **FR-B-5 (SHOULD)** Filters: vocation category, location radius, experience level, open-to-remote, last active, number of successful collabs. Profile health filter **not exposed** (internal ranking only).
- **FR-B-6 (MUST)** Profile detail view = full profile (name, badges, city-only, bio, "obsessed with", vocations + sub-tags, experience level, open-to-remote, portfolio carousel, collab count, last active, externals, past collab feedback up-vote count).
- **FR-B-7 (MUST)** Save profile (private — `[NEEDS CLARIFICATION post-launch]` for Premium "see who saved you").
- **FR-B-8 (MUST)** Send Vibe Check: 250-char synopsis, no attachments. Free 5/wk, Premium unlimited.
- **FR-B-9 (MUST)** Accept / reject. Rejections + unanswered silent. **30-day TTL** then auto-archive (status=expired) into recipient archive and sender's "past requests sent" history. Recoverable.
- **FR-B-10 (SHOULD)** Mutual accept → "Match!" notification (push + in-app banner; email fallback).
- **FR-B-11 (SHOULD)** AI Recommended Profiles: top-of-feed "Picked for you" row (daily 5–10) + dedicated tab.
- **FR-B-12 (PREMIUM)** Premium users can hide from non-premium users (visibility setting).
- **FR-B-13 (MUST)** Two-way discovery: anyone can send a Vibe Check unless blocked. Premium adds the hide-from-non-premium toggle.

### Journey C — Collaboration Workspace (collab-svc, chat-svc, media-svc, ai-orchestrator-svc, meeting-svc)

- **FR-C-1 (MUST)** Private 1:1 chat room opens on match. Custom WebSocket service. Persistence to Postgres.
- **FR-C-2 (MUST)** Chat content types: text, voice notes, file (image 10MB / audio 50MB / video 250MB / doc 25MB), hyperlinks. Whitelisted MIME types; reject executables/scripts.
- **FR-C-3 (MUST)** Auto-logged with timestamps + uploader + version. Immutable from user UI. Exportable per FR-C-9.
- **FR-C-4 (COULD)** Virtual whiteboard (tldraw embed, persistence in S3 + Postgres).
- **FR-C-5 (COULD)** Lightweight project plan tool (custom native, in collab-svc): tasks, owners, due dates, status, comments.
- **FR-C-6 (COULD)** Meeting scheduling (Google Meet only via Google Calendar API). Recall.ai bot optionally joins to record + transcribe; transcript stored to audit log.
- **FR-C-7 (PREMIUM)** In-chat AI assistant: **5 commands** at launch — `/mockup-image`, `/mockup-audio`, `/summarize-chat`, `/brainstorm`, `/palette`. Premium credit allowance + credit-pack overage.
- **FR-C-8 (PREMIUM)** AI Collab Preview mockup: mutual-consent doc accepted by both → Replicate generation → watermarked output → viewable only by both → consent-set lifespan (1d / 14d). Android FLAG_SECURE; iOS overlay warning + screenshot-attempt audit.
- **FR-C-9 (SHOULD)** Project status: "Still Deciding" / "In Progress" / "Completed" / "Didn't Work Out".
- **FR-C-10 (PREMIUM)** Chat export: PDF transcript + ZIP of media. Premium-only.
- **FR-C-11 (SHOULD)** Feedback at collab end: **thumbs up/down + tag chips** (one rating per collaborator). Separate feedback on the project + on the partner.
- **FR-C-12 (MUST)** Report button per chat / per profile → moderation queue.
- **FR-C-13 (SHOULD)** Auto-archive cadence: 14 days inactivity → nudge (push + in-app banner + email fallback); 30 days → auto-archive into history. "Completed" auto-archives immediately on status flip; "Didn't Work Out" archives immediately on status flip.
- **FR-C-14 (MUST)** Block + unblock semantics: hard mutual block. Blocked user invisible in feed/recs/search to both sides. Existing collabs flip to read-only, auto-archive at +30 days. Both can still export chat for IP records.

### Journey D — Advertisements (deferred to next milestone)

Schema lives (Coupon, CouponRedemption, AdImpression, AdClick, AdSnooze tables). UI surface not built this milestone. Premium toggle defined (per-user toggle in settings; ads-on for free, opt-out is premium-only) so the feature can light up post-launch without schema migration.

### Journey E — Payments (billing-svc)

- **FR-E-1 (MUST)** Tiers: Free, Premium, Premium Pro. Monthly + annual SKUs at launch. **Prices admin-configurable**.
- **FR-E-2 (MUST)** Entitlement axes (admin-configurable values per tier):
  - `invites_per_week` (Free 5, Premium ∞, Pro ∞)
  - `ai_credits_per_month` (Free 0, Premium TBD, Pro TBD higher)
  - `ads_shown` (Free yes, Premium toggleable, Pro toggleable)
  - `chat_export` (Free no, Premium yes, Pro yes)
  - `hide_from_non_premium` (Free no, Premium yes, Pro yes)
  - `picked_for_you_priority` (Free no, Premium yes, Pro higher)
  - `mockup_fidelity` (Free off, Premium basic, Pro advanced Replicate models)
  - `portfolio_pdf_export` (Free no, Premium no, Pro yes)
  - `visibility_boost` (Free no, Premium no, Pro yes)
  - `support_priority` (Free no, Premium yes, Pro higher)
  - `see_who_saved_you` (Free no, Premium yes, Pro yes)
- **FR-E-3 (MUST)** Mobile IAP via RevenueCat; web checkout via Stripe Checkout. Cross-platform entitlement parity.
- **FR-E-4 (MUST)** Credit wallet (CreditWallet, CreditTransaction). Credit bundles **admin-configurable** SKUs in Stripe + RevenueCat consumable products.
- **FR-E-5 (MUST)** Account/billing screen: usage history, current quota, active subscription + tier + renewal date, cancel subscription, refund request.
- **FR-E-6 (MUST)** Dunning state machine: Day 0/3/7 retries + email; Day 10 cancel; Day 30 grace-period reactivation.
- **FR-E-7 (MUST)** Refund: 14-day no-questions full refund; prorated thereafter only for annual SKUs; store IAP routes per Apple/Google policy.
- **FR-E-8 (MUST)** Tax via Stripe Tax (web) + store-handled (mobile). India GST: separate registration / reseller path.

### Journey F — Help & Support (support-svc)

- **FR-F-1 (SHOULD)** Self-service FAQ.
- **FR-F-2 (MUST)** Community Guidelines + ToS + Privacy + DMCA notice page.
- **FR-F-3 (COULD)** Live outage status page.
- **FR-F-4 (COULD)** Support AI chatbot (OpenAI; bounded to FAQ + ticket creation).
- **FR-F-5 (MUST)** Support ticket categories with SLAs:
  - Harassment / threats: **4h ack, 24h resolve**
  - IP / DMCA: **24h ack, 7d resolve** (+ statutory counter-notice window)
  - Payment: **24h ack, 72h resolve**
  - Technical: **24h ack, 5d resolve**
  - Other: **48h ack, 7d resolve**
  - Premium Pro: 2× faster ack.
- **FR-F-6 (SHOULD)** Post-resolution CSAT (1-5).

### Journey G — Activity & History (collab-svc + invite-svc + admin-svc)

- **FR-G-1 (SHOULD)** Active projects view.
- **FR-G-2 (SHOULD)** Past projects view (Completed / Didn't Work Out / Auto-archived).
- **FR-G-3 (SHOULD)** Requests sent + Requests received history.
- **FR-G-4 (SHOULD)** Search: titles + descriptions + collaborator names + file names. Postgres full-text. (Chat-content search out-of-scope this milestone.)

### Cross-cutting — Notifications (notification-svc)

- **FR-N-1 (MUST)** Notification types: new match, new request, request accepted, chat message, file shared, AI mockup ready, collab nudge, collab status change, weekly digest, support reply, marketing.
- **FR-N-2 (MUST)** Per-type, per-channel (push / email / in-app) preferences. Defaults: all on except marketing + weekly digest.
- **FR-N-3 (MUST)** Push opt-in: first-needed-with-pre-permission-card. Don't prompt at signup.
- **FR-N-4 (MUST)** Email always for receipts + security events regardless of preferences (legal/transactional).

### Cross-cutting — Moderation (moderation-svc)

- **FR-M-1 (MUST)** AI moderation pipeline (real-time): chat msgs, image/video uploads, portfolio uploads. OpenAI moderation (text) + AWS Rekognition (image/video) + pHash dup (image) + Chromaprint dup (audio) + embedding semantic dup.
- **FR-M-2 (MUST)** Risk-tiered routing:
  - `<0.4` → auto-allow + log
  - `0.4–0.7` → soft-warn user + mod queue (24h SLA)
  - `0.7–0.9` → hide content + mod queue (6h SLA)
  - `≥0.9` → auto-hide + temp-mute user + mod queue (1h SLA)
  - IP/DMCA + harassment-threat: always routed to humans regardless of score.
- **FR-M-3 (MUST)** Moderator actions catalog: warn, hide content, temporary mute (1h/24h/7d), permanent ban, delete account.
- **FR-M-4 (MUST)** Action log with reviewer ID + timestamp + reason.
- **FR-M-5 (MUST)** DMCA workflow: takedown intake (signed under penalty of perjury), 24h hide, counter-notice intake (10–14 day statutory window), restore on no-suit. (US safe-harbor not claimed because DMCA agent deferred — `[OPEN RISK]`.)
- **FR-M-6 (MUST)** AI mockup watermarking + screenshot guards (FR-C-8 details).

---

## 4. Data Model

Per R22 decision: **data model is rewritten by the spec-detailing agents in Phase 5** using the source's entities as a sketch. Phase 5b reconciles divergences.

Source entities to seed Phase 5: User, Profile, CollabInvite, Collaboration, ProjectAsset, Feedback, Subscription, Transaction, AdImpression, AdClick, AI Interaction Log.

Additional entities derived from Phase 3 decisions (to be confirmed by detailing agents):
Block, Notification, NotificationPreference, ModerationAction, ModerationCase, DMCANotice, CounterNotice, Coupon (deferred surface), CouponRedemption (deferred surface), CreditWallet, CreditTransaction, IdentityVerification (Persona), ProfileReview (AI), MeetingSession, MockupConsent, MockupAsset, Report, SupportTicket, SupportTicketEvent.

---

## 5. Non-Functional Requirements

- **NFR-1 Performance**: P95 API <200ms, feed <300ms, chat msg e2e <500ms.
- **NFR-2 Scale**: 10k DAU @ launch → 100k DAU by M6. Capacity plan sized accordingly.
- **NFR-3 Availability**: 99.9%.
- **NFR-4 Residency**: us-east-1 with SCCs. India localization specifics deferred to Phase 5.
- **NFR-5 Accessibility**: WCAG 2.1 AA on RN + Web.
- **NFR-6 Localization**: English at launch; i18n infra ready (all strings externalized to message catalogs from day 1).
- **NFR-7 Offline (mobile)**: Read-cache for feed + opened profiles; queued writes for sent chat messages (replay on reconnect with optimistic UI); uploads require connectivity (paused UI).

---

## 6. Success Metrics

Metrics tracked (PostHog + analytics-svc rollups). **Numeric targets deferred** — set post-launch from real data.

Tracked: onboarding completion + drop-off per step; DAU split new vs existing; profile health score distribution; time spent (instrumented but not optimization target); % profile completed; requests sent/received/accepted/rejected/expired; collab feedback up-vote ratio; tickets count + resolution time + CSAT; profiles reported; ads metrics (when ads ship).

---

## 7. Phase Order (preliminary — refined in Phase 4)

Per Roadmap Standards: Phase 0 infra → MUST → SHOULD → COULD; deps first.

- **P0 — Infrastructure Bootstrap** (AWS account, EKS, RDS, Redis, S3, RabbitMQ, Secrets Manager, GitHub Actions, Sentry, PostHog, Mapbox, Persona, RevenueCat, Stripe, OpenAI, Replicate, Recall.ai accounts + secrets)
- **P1 — Shared platform**: gateway service, base FastAPI library, auth library, OpenAPI codegen pipeline, TS client lib, RN base app + Expo, Next.js base apps × 3
- **P2 — Auth + Profile foundation**: auth-svc, profile-svc, identity-svc (Persona integration); RN signup + profile setup flows
- **P3 — Verification & Trust**: AI profile review; Valid Profile Badge issuance
- **P4 — Discovery & Matching**: matching-svc (embeddings + nightly job + on-demand re-rank), discovery-svc (feed + filters + "Picked for you"); RN feed + profile detail + save UI
- **P5 — Vibe Check**: invite-svc; RN send/accept/reject UI; "Match!" UX
- **P6 — Chat + Workspace base**: chat-svc (WebSocket + persistence); media-svc (uploads, scanning); RN chat screen; file send UI
- **P7 — Moderation & Safety**: moderation-svc (risk-tiered pipeline + queue), report flow, mod console in admin app
- **P8 — Collab Lifecycle**: collab-svc (status, feedback, archive, history); Journey G views
- **P9 — Project plan + Whiteboard**: tldraw embed; custom project-plan UI
- **P10 — Meetings**: meeting-svc + Recall.ai integration
- **P11 — AI Assistant + Mockups**: ai-orchestrator-svc + 5 commands + consent-flow mockup gen; Replicate webhook handling
- **P12 — Payments**: billing-svc (RevenueCat + Stripe), tier entitlements, credit wallet, dunning, refunds, tax
- **P13 — Notifications**: notification-svc + preferences
- **P14 — Support**: support-svc + AI chatbot + ticket SLAs
- **P15 — Admin Console + Analytics rollups**: analytics-svc, admin-svc, KPI dashboards, moderator workflow tools
- **P16 — Marketing site**: SEO landing, signup funnel, app-store badges
- **P17 — Accessibility audit + i18n infra hardening**
- **P18 — Pre-launch hardening**: load test to 100k DAU, security review, App Store + Play Store submissions, beta program

---

## 8. Open Items After Phase 3

- **D-MODEL-1** intentionally deferred to Phase 5 (full rewrite by spec-detailing agents).
- **India data localization specifics** for India DPDP — Phase 5 detailing decides whether to provision an in-region object store or rely on processor agreements.
- **Working name lock** — codename `Colab` used in code; user-facing brand TBD before launch. Single `BRAND_NAME` constant for late swap.
- **DMCA agent registration** — explicitly accepted as deferred; track as open legal risk.
- Per-feature edge cases (state-machine transitions, error copy, retry counts, off-path UX) — will surface and be answered during Phase 5 detailing.

---

## 9. Phase 3 Outcome

23 clarify rounds resolved ~95 `[NEEDS CLARIFICATION]` items including all 33 architecture decisions, all Journey-level UX choices, monetization model, moderation routing, compliance posture, accessibility commitment, scale targets. Spec is ready for Phase 3b (Infrastructure Setup) followed by Phase 4 (split into per-feature specs).
