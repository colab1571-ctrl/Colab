# STUB AUDIT — Stage 3 Pre-Launch

> Generated 2026-06-11. Inventory of every stub, placeholder, and unwired UI across the codebase, cross-referenced against the 000-master spec promises.
>
> Method: full grep of `apps/`, `packages/`, and `services/` for `implemented in P`, `Coming soon`, `TODO`, `FIXME`, `NotImplementedError`, `mock`, `stub`, `placeholder`, plus eyeball-read of every Next.js page + every mobile screen + every backend router.

---

## Executive summary

- **Total backend services: 20** (19 spec'd + `hello-svc`).
  - **Fully functional + DB-wired (models + routers + migrations):** 17
    - `auth-svc`, `profile-svc`, `discovery-svc`, `matching-svc`, `invite-svc`, `chat-svc`, `collab-svc`, `moderation-svc`, `notification-svc`, `billing-svc`, `support-svc`, `ai-orchestrator-svc`, `meeting-svc`, `admin-svc`, `analytics-svc`, `identity-svc`, `gateway-svc` (proxy-only, by design)
  - **Compiles but routes/migrations incomplete:** 3
    - `media-svc` (no migrations file; only 3 endpoints)
    - `geo-svc` (no alembic dir; stateless Mapbox proxy — OK by design)
    - `analytics-svc` (only 3 endpoints, mostly proxy)
  - **Booted in docker-compose ever:** 2 of 20 (`auth-svc`, `gateway-svc`). `profile-svc` only stamped at migration 0002 due to PostGIS unavailability on arm64 dev box.
  - **Deployed to PaaS today:** 0. Render Blueprint exists for gateway+auth+profile; Fly configs exist for the same 3 only. The other 16 services have **no deploy config**.
- **Total frontend pages (Next.js):** 18 web pages + ~57 mobile screens.
  - **Web pages wired to API:** 14 of 18.
    - marketing-web: 10/10 pages render real content (some have explicit Coming-soon copy by design; waitlist API has DB+SES "stub" path)
    - consumer-web: 3 of 5 wired (home, signup, login); 2 are explicit "implemented in PN" stubs (`/discover`, `/settings`). NO global nav, NO authed shell.
    - admin-web: 13 of 13 pages wired to admin-svc via `admin-api.ts`. `/login` is a non-functional UI shell (no onSubmit).
  - **Mobile screens that exist as files: ~57.** **Wired into navigation: 8** (Welcome, SignIn, SignUp, Verify, PhoneOTP, ForgotPassword, Home, Feed/Discover). The other ~49 screens exist on disk but the Chats and Me tabs both render `PlaceholderScreen` ("Coming soon"). There is no path from the UI to ChatRoomScreen, ProfileViewScreen, MockupViewerScreen, any billing/support/collab screen.
- **E2E user flows that work right now:**
  - Marketing site browse + waitlist submission (with `WAITLIST_LIST_NAME`/`DATABASE_URL` env vars unset, falls back to logging — never persists)
  - consumer-web signup → JWT in localStorage → `/v1/auth/me` succeeds (when gateway+auth deployed)
  - consumer-web login → JWT → `/v1/auth/me`
  - Mobile signup → JWT → tab nav to Home/Feed
  - `docker compose` demo signup (gateway → auth-svc) per `scripts/smoke/demo_signup.sh`
- **E2E user flows that DON'T work:**
  - Profile creation after signup (profile-svc not deployed; consumer-web has no profile wizard)
  - Discover feed in consumer-web (page is a stub)
  - Sending a Vibe Check from any client
  - Chat: no chat UI is reachable in mobile (Chats tab = Placeholder); chat-svc has 2 missing internal endpoints per RESUME.md
  - File upload / portfolio (PortfolioUploadScreen is a stub timer)
  - OAuth (Instagram/YouTube/Spotify) connect — `OAuthConnectScreen` is a stub timer
  - AI mockups (mockup screens not wired in nav; native ScreenshotGuard module missing on both platforms)
  - Whiteboard real-time sync (`ypy_websocket` dependency missing; collab-svc `whiteboard_ws.py` is asyncio stub)
  - Meeting deep-link (no Google Meet OAuth flow)
  - Billing subscription / refund / credit purchase from mobile (screens exist but not in nav)
  - Push notifications (`apps/mobile/src/lib/push.ts` is a stub)
  - Persona liveness (native binding missing — `expo-persona-sdk` is a placeholder package name; real SDK is `@persona-kyc/rn-sdk`)
  - Apple Sign-In / Google Sign-In on mobile (RN native bindings missing)
  - Android FLAG_SECURE / iOS screenshot-detect for mockup viewer (native modules never written)

---

## Per-service backend status

### gateway-svc
- Routes implemented: 4 endpoints (`/healthz`, `/ready`, `/version`, `/v1/flags`) + proxy for 19 prefixes.
- Stubs/TODOs: none in routers.
- DB calls: only `waitlist_emails` migration exists (`migrations/versions/0001_create_waitlist_emails.py`). Gateway itself is stateless proxy.
- Deployed?: configs in `render.yaml` + `services/gateway-svc/fly.toml`. Not actually deployed.
- Critical gaps: **WebSocket proxying (chat-svc) not supported** — `httpx` has no WS upgrade; chat-svc must be called directly from client. Mobile will need a separate WS host.

### auth-svc
- Routes implemented: 22 endpoints — signup (email/OAuth/phone), login (email/OAuth/phone), email verify, password reset, sessions, /me, logout, account email/phone change.
- Stubs/TODOs: none in router code.
- DB calls real?: yes — `User`, `Session`, etc. with `__tablename__`; 1 alembic migration.
- Deployed?: render.yaml + fly.toml.
- Critical gaps: **MJML email templates not implemented** (RESUME.md gap #7) — emails reference templates that were deferred. **OAuth requires real provider tokens** (Apple/Google client secrets). **Phone OTP requires India DLT registration (4–8 weeks)** — blocks IN launch.

### profile-svc
- Routes implemented: 18 endpoints across profile, portfolio, vocations, taxonomy, badge, oauth (externals), internal.
- Stubs/TODOs: none in router code.
- DB calls real?: yes — 6 migrations including PostGIS extensions, profiles, taxonomy, OAuth externals.
- Deployed?: render.yaml + fly.toml.
- Critical gaps: **PostGIS not available on arm64 dev images** (STAGE2_REPORT) — migration 0003 fails; service won't boot locally. Production Supabase has PostGIS so this is a dev-only blocker, but **profile-svc has never actually run end-to-end against a real DB.** AI profile review (FR-A-10/11) requires OpenAI + Rekognition; OPENAI_API_KEY is `sk-local-placeholder` per render.yaml.

### identity-svc
- Routes implemented: 3 endpoints — identity router + Persona webhook.
- Stubs/TODOs: none.
- DB calls real?: yes — `IdentityVerification` model + 1 migration.
- Deployed?: **no fly.toml, no render entry.**
- Critical gaps: requires Persona sandbox key + Persona Mobile SDK on RN; mobile screen `PersonaLaunchScreen` notes "expo-persona-sdk is a placeholder; the real SDK is @persona-kyc/rn-sdk". **Cannot do liveness check today.**

### discovery-svc
- Routes implemented: 8 — feed (scroll/swipe), saved, picked-for-you, profile detail.
- Stubs/TODOs: `_get_user_id` comment says "(JWT sub claim, stub)" but routes also read `X-User-Id` header set by gateway — functional.
- DB calls real?: yes; 2 migrations. **Migration 0002 (`block_aware_view`) references cross-schema tables** (`invite.block`, `profile.profiles`) — only works in shared-DB deployments; Supabase shared DB OK, but isolated-DB local Postgres breaks (STAGE2_REPORT blocker #3).
- Deployed?: no.
- Critical gaps: depends on pgvector + populated profile embeddings. No data → empty feed → user sees nothing.

### matching-svc
- Routes implemented: 4 — match score + nightly job triggers.
- Stubs/TODOs: none.
- DB calls real?: yes; 2 migrations.
- Deployed?: no.
- Critical gaps: requires OpenAI embeddings for portfolio similarity. **Nightly ranking job (Celery Beat) not actually scheduled anywhere — no Celery worker container in docker-compose or fly config.**

### geo-svc
- Routes implemented: 3 — city autocomplete, radius queries, geocoding.
- Stubs/TODOs: none.
- DB calls real?: **no alembic dir** — stateless Mapbox proxy by design.
- Deployed?: no.
- Critical gaps: requires `MAPBOX_API_KEY`; not in env-var-mapping doc.

### invite-svc
- Routes implemented: 9 — vibe-check send/accept/reject/list, blocks.
- Stubs/TODOs: `profile_client.py` notes "Returns a stub on any error to avoid cascading failures" — graceful degradation, not a missing feature.
- DB calls real?: yes; 1 migration.
- Deployed?: no.
- Critical gaps: requires profile-svc up + notification-svc up to emit "Match!" event.

### chat-svc
- Routes implemented: 6 (rooms, messages, edit, read) + 1 internal endpoint (`/internal/rooms/{room_id}/messages/all`).
- Stubs/TODOs: **2 INTERNAL ENDPOINTS MISSING per RESUME.md gap #1:** `POST /internal/rooms/{room_id}/messages` (used by ai-orchestrator-svc to post system messages, e.g. mockup-ready) and `GET /internal/rooms/by-collab/{collab_id}` (used by collab-svc to look up the chat room for a collab). Cross-service calls will 404.
- DB calls real?: yes; 1 migration.
- Deployed?: no.
- Critical gaps: WebSocket gateway design conflicts with API Gateway WS 2-hour limit (Stage 1 risk #3). No native WS connect path in mobile app today.

### media-svc
- Routes implemented: 3 — presigned PUT, finalize, delete.
- Stubs/TODOs: none.
- DB calls real?: **NO migrations dir** — `services/media-svc/alembic/` exists but `alembic/versions/` is empty. Models reference tables that have never been created.
- Deployed?: no.
- Critical gaps: requires R2 / S3 creds; **DB tables for media metadata don't exist** — first POST will 500.

### collab-svc
- Routes implemented: 19 — collabs, tasks, whiteboard (WS endpoint), mockup consent.
- Stubs/TODOs: `whiteboard.py` comment "real auth done by gateway JWT decode … query param stub" — auth is delegated to gateway. `workers/whiteboard_tasks.py` `render_snapshot()` is a stub ("Real implementation calls Node.js Playwright"). `services/whiteboard_ws.py` "Falls back gracefully if ypy_websocket is not installed (dev env stub)" — production whiteboard real-time sync is **not implemented** (RESUME.md gap #6).
- DB calls real?: yes; 2 migrations.
- Deployed?: no.
- Critical gaps: **`least_participant` / `greatest_participant` GENERATED columns bug** (Stage 1 risk #1, RESUME.md gap #2) — first INSERT will fail. Whiteboard rendering for export/preview returns mock blob.

### moderation-svc
- Routes implemented: 18 — reports, DMCA, cases, internal AI flag ingestion.
- Stubs/TODOs: none in routers.
- DB calls real?: yes; 1 migration.
- Deployed?: no.
- Critical gaps: needs OpenAI Moderation API + AWS Rekognition keys. DMCA agent **not registered** (master spec §0 accepts this risk). pHash / Chromaprint / embedding-dup pipelines depend on Celery worker — not deployed.

### notification-svc
- Routes implemented: 3 router files: notifications, preferences, devices.
- Stubs/TODOs: none in routers.
- DB calls real?: yes; 1 migration.
- Deployed?: no.
- Critical gaps: depends on AWS SNS (push) + SES (email). Resend is configured in deploy docs but `channels/email.py` likely targets SES. Expo Push fallback exists but `apps/mobile/src/lib/push.ts` is a stub.

### billing-svc
- Routes implemented: 18 — billing, webhooks, internal (entitlements), admin (refunds/credits).
- Stubs/TODOs: `services/refunds.py` line 116 "stub with 0 and flag for admin" — graceful default when invoice amount missing.
- DB calls real?: yes — `Customer`, `Subscription`, `EntitlementSnapshot`, `CreditWallet`, `CreditTransaction`, `Invoice`, `RefundRequest`, `WebhookEventLedger`, `DunningCase`. 1 migration.
- Deployed?: no.
- Critical gaps: Stripe + RevenueCat live keys not set. India GST registration deferred. Marketing pricing page is a stub ("implemented in P12") — even if billing-svc worked, **the public can't see prices.**

### support-svc
- Routes implemented: 9 — faq, chatbot, tickets, status page.
- Stubs/TODOs: `status.py` line 110 "Statuspage.io fetch failed: returning stub" — fallback when external monitor down. `config.py` line 37 "STATUSPAGE_PUBLIC_URL stub". Both are graceful, not gaps.
- DB calls real?: yes; 2 migrations.
- Deployed?: no.
- Critical gaps: AI chatbot needs OpenAI key. **No support UI in consumer-web; mobile support screens not wired in nav.**

### ai-orchestrator-svc
- Routes implemented: 5 — slash commands, consent, webhooks (Replicate).
- Stubs/TODOs: none in router code.
- DB calls real?: yes; 1 migration.
- Deployed?: no.
- Critical gaps: Replicate credentials. **Watermarking depends on `mutagen` lib for audio ID3 tagging** — installed in pyproject? Need to verify. **Cross-service post to chat-svc will fail** until `POST /internal/rooms/{room_id}/messages` is added (RESUME.md gap #1).

### meeting-svc
- Routes implemented: 8 — meetings list/create, Recall.ai bot orchestration, Google OAuth callback.
- Stubs/TODOs: none in routers.
- DB calls real?: yes; 1 migration.
- Deployed?: no.
- Critical gaps: Google OAuth client + Recall.ai key. **Mobile meeting screens not wired into nav.**

### admin-svc
- Routes implemented: 25 — moderation, support, billing, users, flags, kpi, audit.
- Stubs/TODOs: none.
- DB calls real?: yes; 1 migration.
- Deployed?: no.
- Critical gaps: depends on every other service for the cross-service reads. **IP allowlist middleware enforces — needs admin IPs in env.**

### analytics-svc
- Routes implemented: 3 — event ingestion + KPI rollups.
- Stubs/TODOs: none.
- DB calls real?: yes; 1 migration.
- Deployed?: no.
- Critical gaps: requires PostHog project key for forwarding.

### hello-svc
- 1 sanity-check endpoint. Used by mobile HomeScreen "Ping Gateway" test. Working.

---

## Per-page frontend status

### marketing-web (apps/marketing-web)

| Path | Status | Notes |
|---|---|---|
| `/` | **Wired** | Hero, value props, how-it-works steps, FAQ teaser, waitlist form. "Testimonials placeholder" copy block at line 186 reads `[Testimonials — populated at Phase 5 design pass and launch]`. |
| `/about` | **Mostly wired** | Substantive content, but section at line 113-128 is `{/* Team placeholder */}` with copy `[Team bios — populated at Phase 5 design pass and launch]`. |
| `/blog` | **STUB — "Coming soon"** | Full-page "The {BRAND_NAME} Blog … We're writing — check back soon." `robots: noindex,nofollow`. |
| `/faq` | **Wired** | 14 FAQ items (`./data.ts`) + filter component + JSON-LD FAQPage schema. |
| `/how-it-works` | **Wired** | Substantive, references the 5 slash commands. "Animated diagram placeholder" comment at line 148 (decorative). |
| `/pricing` | **STUB — "implemented in P12"** | Single line: `<p>Pricing tiers implemented in P12 (billing-svc). Full copy in spec 017.</p>` — public-facing pricing page is a one-liner. |
| `/legal/community-guidelines` | **Wired** | MDX page. |
| `/legal/cookies` | **Wired** | MDX page. |
| `/legal/dmca` | **Wired** | MDX page. |
| `/legal/privacy` | **Wired** | MDX page. |
| `/legal/tos` | **Wired** | MDX page. |
| API route `/api/waitlist` | **Half-wired** | SES path conditional on `WAITLIST_LIST_NAME`; DB path is a `console.log` stub with `TODO(infra): replace with actual DB insert via gateway-svc internal API`. Confirmation email TODO `(spec-017)`. Without env vars, **waitlist emails are dropped on the floor — only logged.** |

### consumer-web (apps/consumer-web)

| Path | Status | Notes |
|---|---|---|
| `/` | **Wired (static)** | 3 feature cards (Discover/Connect/Create) with hardcoded copy + Get Started/Discover buttons → links to /login + /discover. Functional landing but no auth-aware UI; no nav bar; no "you are signed in" state. |
| `/login` | **WIRED** | Real `useAuth().signIn({email,password})` call → `/v1/auth/login/email`, error state, redirect to `/discover` on success. (The "implemented in P2" footer note was removed at some point — current code has full client form.) |
| `/signup` | **WIRED** | Full form with 4 acceptance checkboxes (TOS / privacy / community / 18+), real `signUp()` call to `/v1/auth/signup/email`, error state. |
| `/discover` | **STUB** | Literally `<p>Feed assembly implemented in P4 (discovery-svc).</p>`. Authenticated user lands here from login → sees a placeholder. |
| `/settings` | **STUB** | Literally `<p>Settings UI implemented in P2+.</p>` |
| (no other routes) | | No `/profile`, `/inbox`, `/chat`, `/collab`, `/billing`, `/support`, `/onboarding`, `/forgot-password`. The `/login` page links to `/forgot-password` but the route does not exist → 404. |

**Critical:** No app shell, no global navigation, no signed-in vs signed-out layout, no profile setup wizard. After signup, the user is dumped on `/discover` which is a stub line of text. There is no path to anything else in the web app.

### admin-web (apps/admin-web)

| Path | Status | Notes |
|---|---|---|
| `/` | **Wired** | Redirects to `/dashboard`. |
| `/dashboard` | **Half-wired** | Static 3-card link grid with `count: "—"` placeholder. Footer text: "Dashboard metrics wired in P15 (admin-svc + analytics-svc)." No real fetch of metrics. |
| `/login` | **STUB UI** | No form element, no onSubmit handler, no state. Static `<Input>`s + `<Button type="submit">` with no enclosing `<form>`. Clicking Sign In does nothing. |
| `/audit` | **Wired** | Server-side `requireRole(["super_admin","auditor"])` + `getAuditLog`. |
| `/billing` | **Wired (redirect)** | Redirects to `/billing/tiers`. |
| `/billing/tiers` | **Wired** | Server fetch `getTiers()`. |
| `/billing/refunds` | **Wired** | Real server actions calling `decideRefund()`. |
| `/flags` | **Wired** | `getFlags()` + `upsertFlag()` server actions. |
| `/kpis` | **Wired** | `getKpiRollups()`. |
| `/moderation/queue` | **Wired** | `getModerationQueue()` with SLA badges + table. |
| `/moderation/case/[id]` | **Wired** | Case detail + action form. |
| `/support/queue` | **Wired** | `getSupportQueue()`. |
| `/support/ticket/[id]` | **Wired** | `getTicketDetail()` + reply form. |
| `/users/[id]` | **Wired** | `getUser360()` + reveal toggle. |

**Critical:** admin-web is the most complete of the three web apps. **But you cannot log in** — the `/login` page is a non-functional UI shell. There is no admin auth endpoint wired and no cookie set. Every other page calls `requireRole(...)` which `redirect("/login")` → infinite loop the moment you visit anything.

### Mobile app (apps/mobile)

- **Files on disk:** ~57 screens covering every Journey A–G feature.
- **Actually reachable from navigation:**
  - Auth stack: Welcome, SignIn, SignUp, Verify, PhoneOTP, ForgotPassword — 6 screens, wired to auth-svc.
  - Main tabs: Home (gateway ping placeholder), Discover (FeedScreen, real), Chats (`PlaceholderScreen` — "Coming soon"), Me (`PlaceholderScreen` — "Coming soon").
- **Screens that exist on disk but are NOT reachable from navigation:**
  - All 6 profile screens (ProfileSetupWizardScreen, ProfileViewScreen, PortfolioUploadScreen, VocationPickerScreen, PersonalityQuizScreen, OAuthConnectScreen)
  - All 5 invite screens (Inbox, SentHistory, MatchCelebration, SendVibeCheckModal, BlocksScreen)
  - All 11 chat screens (ChatRoomScreen + 7 components + MatchCelebrationHandoff + SlashCommandPicker)
  - All 10 collab screens (Active/Past Projects, CollabDetail, TaskList/Detail, Kanban, Search, Whiteboard, ExportStatus, FeedbackPromptModal)
  - All 4 billing screens (Paywall, Subscription, CreditPurchase, RefundRequest)
  - All 6 support screens (Faq, Chatbot, TicketList, TicketForm, TicketDetail, CSATPrompt)
  - All 3 meeting screens
  - All 2 AI screens (MockupConsent, MockupViewer)
  - Both account screens (EmailChange, Sessions)
  - PersonaLaunchScreen (identity verification)
- **Known stub patches inside the existing screens:**
  - `profile/OAuthConnectScreen.tsx` line 56-63: connect handler returns `@stub_${provider}` after 1.5s setTimeout — no real OAuth flow.
  - `profile/PortfolioUploadScreen.tsx` line 53-86: `// For now: stub the upload flow` — `setTimeout` simulates upload, no real S3 presigned PUT.
  - `profile/ProfileViewScreen.tsx` line 89-119: hardcoded stub user with `id: "stub-id"`, fake bio, fake portfolio.
  - `profile/VocationPickerScreen.tsx` line 31: "Static taxonomy stub — loaded from `/api/v1/vocations/taxonomy` in production" — 9 hardcoded vocations.
  - `profile/PersonalityQuizScreen.tsx` line 129-131: `// TODO: const res = await profileApi.submitPersonality(payload);` — result is hardcoded.
  - `profile/ProfileSetupWizardScreen.tsx` line 110: `// TODO: call profile API PATCH /api/v1/profile/me` — wizard never persists.
  - `collab/TaskListScreen.tsx` line 127: `const authToken = ''; // placeholder` — every API call sends empty auth.
  - `ai/MockupConsentModal.tsx`: `fetch("/collabs/...")` with no base URL — hits `localhost:port/collabs/...` rather than gateway.
  - `ai/MockupViewerScreen.tsx` line 49-58: `MockupScreenshotGuard` native module declared but Android Kotlin + iOS Swift implementations missing (RESUME.md gaps #3 #4).
  - `chat/MatchCelebrationHandoff.tsx` line 72: `{/* Confetti placeholder — production uses lottie-react-native */}` — no animation.
  - `identity/PersonaLaunchScreen.tsx` line 13: `expo-persona-sdk is a placeholder; the real SDK is @persona-kyc/rn-sdk` — wrong package, won't compile against device.
  - `lib/network.ts` line 8-11: NetInfo stub `// TODO P2: wire NetInfo listener` — offline detection not real.
  - `lib/push.ts` line 17: `// TODO spec 013: implement with expo-notifications + SNS registration` — push notifications no-op.

**Ship-readiness for TestFlight tomorrow: NO. PRE-ALPHA.**
- The Chats tab and Me tab both show "Coming soon" — App Store reviewers will reject under §4.2 Design "minimum functionality."
- No way to view your own profile, edit your profile, or upload a portfolio item from the live app.
- No way to send a vibe check, accept a match, or open a chat.
- Persona SDK has wrong package name; build will fail or Persona screen will crash.
- Apple Sign-In / Google Sign-In RN native bindings declared in package.json but codegen specs missing (RESUME.md gap #5) — buttons on Welcome screen will throw at runtime if pressed.

---

## packages/* shared code

### @colab/ui
- Real React components (Button, Card, Input, …) — used by both web apps and admin-web.
- `AuthProvider.tsx` — REAL: calls `/v1/auth/signup/email`, `/v1/auth/login/email`, `/v1/auth/me`, `/v1/auth/logout`. Stores tokens in localStorage. Used by consumer-web `signup` + `login` pages.
- `withAuth` HOC — wired.

### @colab/api-types
- Generated `openapi-typescript` clients exist only for **gateway-svc** (84 lines: `/healthz`, `/ready`, `/version`, `/v1/flags`) and **hello-svc** (48 lines).
- **No generated types for auth-svc, profile-svc, discovery-svc, chat-svc, billing-svc, or any other 17 services.** Mobile + web apps roll their own request bodies/responses by hand. Drift risk is real (mobile already hits `/auth/...` directly without the gateway `/v1` prefix in `apps/mobile/src/api/auth.ts`).

### @colab/design-tokens
- `build/css/tokens.css`, `build/tailwind/preset.js`, `build/rn/theme.ts`, `build/json/tokens.json` all exist — Style Dictionary build output is real.

### @colab/i18n
- `locales/en/*.json` — 13 catalog files, 965 lines total covering common, auth, profile, discovery, invite, chat, collab, moderation, notifications, billing, support, admin, errors.
- `locales/qps-ploc/*.json` — pseudo-locale generated for testing.
- `src/init.ts`, `src/loader.ts`, `src/useLocale.ts`, `src/init-rn.ts` — real.
- Catalogs are populated, not stubs.

---

## Spec promises NOT implemented (cross-referenced to specs/000-master)

### Journey A — Onboarding
| FR | One-line | Implementation status |
|---|---|---|
| FR-A-1 | Email+password signup | ✓ auth-svc; ✓ mobile; ✓ consumer-web /signup |
| FR-A-2 | Apple/Google/Phone signup | Partial — auth-svc endpoints exist; **RN native bindings missing**; phone OTP needs India DLT |
| FR-A-3 | Age attestation 18+ | ✓ signup forms enforce |
| FR-A-4 | Profile setup wizard | Mobile screen exists but **NOT wired into navigation; submit handler is a TODO**; consumer-web has no profile wizard |
| FR-A-5 | OAuth externals (IG/YT/Spotify) | **Stub timer** in OAuthConnectScreen; no real OAuth flow |
| FR-A-6 | Portfolio upload | **Stub timer** in PortfolioUploadScreen; no real S3 PUT |
| FR-A-7 | Optional bio fields | UI exists; **doesn't persist** |
| FR-A-8 | Personality quiz | UI exists; **doesn't persist** |
| FR-A-9 | Persona liveness | **Wrong SDK package name; native binding missing** |
| FR-A-10 | AI profile review | profile-svc supports endpoint; **needs OpenAI/Rekognition keys** |
| FR-A-11 | Valid Profile Badge | profile-svc badge router exists; depends on FR-A-9, FR-A-10 |
| FR-A-12 | ToS acceptance at signup | ✓ both clients enforce |
| FR-A-13 | Onboarding analytics | PostHog integration in `lib/posthog.ts`; events not consistently fired |

### Journey B — Discover & Match
| FR | One-line | Implementation status |
|---|---|---|
| FR-B-1 | Scroll + swipe feed | ✓ mobile FeedScreen; **consumer-web /discover is a stub** |
| FR-B-2 | Daily 30/day cap | discovery-svc enforces; mobile UI shows banner |
| FR-B-3 | Ranking signals | matching-svc code exists; **nightly Celery job not deployed** |
| FR-B-4 | Hide 3 months | mobile UI present; backend endpoint exists |
| FR-B-5 | Filters | mobile FiltersDrawer present |
| FR-B-6 | Profile detail | mobile screen exists but **not wired in nav from main tabs** |
| FR-B-7 | Save profile | mobile SavedListScreen exists but **not in nav** |
| FR-B-8 | Send Vibe Check | mobile SendVibeCheckModal exists but **not in nav** |
| FR-B-9 | Accept/reject | mobile InboxScreen exists but **not in nav (Chats tab = Placeholder)** |
| FR-B-10 | "Match!" celebration | mobile MatchCelebrationScreen exists but **unreachable** |
| FR-B-11 | "Picked for you" | mobile tab in FeedScreen wired |
| FR-B-12 | Premium hide-from-non-premium | Settings UI not built |
| FR-B-13 | Two-way discovery | enforced at invite-svc; UI not wired |

### Journey C — Collaboration Workspace
| FR | One-line | Implementation status |
|---|---|---|
| FR-C-1 | 1:1 chat room | chat-svc exists; **2 internal endpoints missing**; mobile ChatRoomScreen **not in nav** |
| FR-C-2 | Chat content types | components exist (VoiceRecorder, MediaImage, MessageComposer) but **unreachable** |
| FR-C-3 | Auto-log + timestamps | chat-svc persists; ✓ |
| FR-C-4 | Whiteboard (tldraw) | mobile WhiteboardScreen exists; **ypy_websocket not installed; collab-svc ws is asyncio stub** |
| FR-C-5 | Project plan | TaskList/Detail/Kanban exist; **unreachable; auth token is `''` placeholder** |
| FR-C-6 | Meeting scheduling | meeting-svc + mobile screens exist; **unreachable; no Google OAuth keys** |
| FR-C-7 | 5 AI slash commands | SlashCommandPicker exists; **unreachable; chat-svc internal POST missing** |
| FR-C-8 | AI mockup with consent | MockupConsentModal + MockupViewerScreen exist; **fetch URLs broken; native screenshot guard missing on both platforms** |
| FR-C-9 | Project status states | collab-svc supports |
| FR-C-10 | Chat export PDF + ZIP | collab-svc ExportStatusScreen exists; **unreachable** |
| FR-C-11 | Collab feedback | FeedbackPromptModal exists; **unreachable** |
| FR-C-12 | Report button | reports endpoints exist; UI hooks missing |
| FR-C-13 | Auto-archive 14d/30d | collab-svc Celery worker code; **worker not deployed** |
| FR-C-14 | Block / unblock | BlocksScreen exists but **not in nav** |

### Journey D — Ads (deferred per master §0)
- Out of scope. Not audited.

### Journey E — Payments
| FR | One-line | Implementation status |
|---|---|---|
| FR-E-1 | Free/Premium/Pro tiers | billing-svc supports; **marketing-web /pricing is a one-line stub** |
| FR-E-2 | Entitlement axes | EntitlementSnapshot table + service code; admin-web tier admin wired |
| FR-E-3 | RevenueCat + Stripe | code exists; **no live keys; no PaaS deploy** |
| FR-E-4 | Credit wallet | tables + service code; mobile CreditPurchaseScreen **unreachable** |
| FR-E-5 | Billing screen | mobile SubscriptionManagementScreen exists; **unreachable** |
| FR-E-6 | Dunning state machine | tables exist; Celery worker not deployed |
| FR-E-7 | 14-day refund | mobile RefundRequestScreen + admin-web /billing/refunds wired |
| FR-E-8 | Stripe Tax | billing-svc code exists; needs Stripe Tax enabled |

### Journey F — Help & Support
| FR | One-line | Implementation status |
|---|---|---|
| FR-F-1 | FAQ | marketing-web /faq + mobile FaqListScreen; **mobile FAQ not in nav** |
| FR-F-2 | Legal pages | ✓ marketing-web /legal/* |
| FR-F-3 | Outage status page | support-svc /status endpoint; **no public status page UI** |
| FR-F-4 | AI support chatbot | support-svc /chatbot + mobile ChatbotScreen; **unreachable** |
| FR-F-5 | Ticket SLAs | tickets router exists; **mobile screens unreachable** |
| FR-F-6 | CSAT | CSATPromptScreen exists; **unreachable** |

### Journey G — Activity & History
- ActiveProjectsScreen, PastProjectsScreen, SearchScreen, BlocksScreen, SentHistoryScreen all exist as files but **none are reachable from the Main tabs.** Backend collab-svc + invite-svc support the queries.

### Cross-cutting — Notifications
| FR | One-line | Implementation status |
|---|---|---|
| FR-N-1 | Notification types | notification-svc supports all 11 types |
| FR-N-2 | Per-channel preferences | preferences router + tables; **mobile preferences UI not in nav** |
| FR-N-3 | Push opt-in | mobile push lib is a **stub** (`apps/mobile/src/lib/push.ts`) |
| FR-N-4 | Email for receipts/security | notification-svc supports; **MJML templates never written** (RESUME gap #7) |

### Cross-cutting — Moderation
| FR | One-line | Implementation status |
|---|---|---|
| FR-M-1 | AI moderation pipeline | moderation-svc + workers; **needs OpenAI + Rekognition keys**; Celery not deployed |
| FR-M-2 | Risk-tiered routing | code supports thresholds |
| FR-M-3 | Moderator actions catalog | admin-web /moderation/case/[id] wired |
| FR-M-4 | Action log | tables exist; admin-web /audit page wired |
| FR-M-5 | DMCA workflow | DMCA router + tables; **agent not registered (master §0)** |
| FR-M-6 | Mockup watermark + screenshot guard | watermark service exists; **native screenshot guard missing on Android + iOS** |

### NFRs
- **NFR-1 Performance**: not load-tested.
- **NFR-2 Scale**: not load-tested.
- **NFR-3 Availability**: 0 services in production.
- **NFR-4 US Residency**: configs target Render Oregon / Fly iad — OK.
- **NFR-5 WCAG 2.1 AA**: marketing-web + admin-web have a11y attributes; mobile screens have a11y labels per spot-check; not audited end-to-end. Pseudo-locale rig exists.
- **NFR-6 i18n**: catalogs populated for EN; pseudo-locale generated. Not gated on the UI yet (consumer-web pages don't use `<Trans>`).
- **NFR-7 Offline**: NetInfo stub; not implemented.

---

## Recommended launch-day scope

The codebase is **pre-alpha for a public consumer launch tomorrow**. Recommend hard-pivoting from "Colab v1.0" to "Colab waitlist + early-access beta." Concretely, what can credibly work in the next 24 hours:

1. **marketing-web only** for the public URL. It's ~95% real (signup waitlist captures emails as long as `WAITLIST_LIST_NAME` + `DATABASE_URL` are set; the blog stub already `noindex`s itself; the team + testimonials placeholders are inline `[…]` notes you can either populate or hide).
2. **Hide the /pricing page from the public nav** (or replace its one-line content with "Pricing announced at launch — join the waitlist"). The current page literally says "implemented in P12 (billing-svc). Full copy in spec 017."
3. **Do NOT publish consumer-web at colabclub.net.** The signup/login work but after auth the user lands on a page that says "Feed assembly implemented in P4." Soft-launching this would be embarrassing.
4. **Do NOT submit mobile to TestFlight.** Chats + Me tabs are "Coming soon"; profile wizard, portfolio, vibe check, chat, mockups, billing, support are all unreachable.
5. **admin-web is internal-only and the /login form is broken** — until login is wired, admin staff cannot access the moderation queue. Either fix /login (small task) or proxy through CloudFlare Access / IP allowlist + service token.
6. **Backend deploy: only ship gateway+auth+profile.** That's the only Render Blueprint that exists. profile-svc requires PostGIS in Supabase (already there) but has never been booted end-to-end — verify with a manual smoke after deploy.
7. **Move communication about timeline now.** Tell stakeholders "early-access beta opens X, full app Y" so tomorrow's release is "we're live in waitlist mode" rather than "we're live and broken."

---

## Recommendations

### Hide from nav / unreleased
- consumer-web: remove links to `/discover`, `/settings` from any nav you build (currently there's no nav at all, which is actually a blessing).
- marketing-web: remove `/pricing` from header/footer (or rewrite the page to say "Pricing announced at launch"). Confirm `/blog` is already noindex'd (it is).
- mobile: do not ship anything; navigation only reaches stub tabs.

### Ship with explicit "Coming Soon" / early-access disclaimers
- The whole consumer app — gate at the marketing site with "Join the waitlist; we open early access at $DATE."
- Status page (`/status`) — wire a static "All systems nominal" until support-svc is up.

### Fix tonight (highest-leverage)
1. **admin-web /login** — wire a real `<form>` with onSubmit calling `/v1/admin/login` (admin-svc has the endpoint; just need the client glue). Without this, no one can moderate.
2. **`apps/marketing-web/src/app/pricing/page.tsx`** — replace the one-liner with real pricing copy from spec 017 OR a "Pricing announced at launch" banner.
3. **`apps/consumer-web/src/app/discover/page.tsx` and `/settings/page.tsx`** — same: convert to "Coming soon — your account is on the waitlist for early access."
4. **`apps/consumer-web/src/app/page.tsx`** — add a "Join the waitlist" CTA pointing to marketing-web (or embed the WaitlistForm). The current homepage's CTAs point to /login + /discover which lead nowhere useful.
5. **Verify the marketing waitlist API actually persists** — `WAITLIST_LIST_NAME` and `DATABASE_URL` must be set on Vercel, or every waitlist submission is silently dropped to console.log.
6. **chat-svc — add the 2 missing internal endpoints** (`POST /internal/rooms/{room_id}/messages`, `GET /internal/rooms/by-collab/{collab_id}`) — even if chat is hidden, these block ai-orchestrator + collab-svc from any future smoke test.
7. **collab-svc — drop `least_participant`/`greatest_participant` from the insert values** — known DB-rejecting bug from Stage 1.

### Defer to post-launch (1–6 weeks)
- Mobile TestFlight build (need: wire all ~49 orphan screens into nav; replace Persona SDK package; write Android FLAG_SECURE Kotlin + iOS screenshot Swift modules; fix Apple/Google native bindings).
- Whiteboard real-time sync (ypy-websocket integration; 2–3 days).
- 5 AI slash commands (depends on chat-svc internal endpoints + Replicate keys).
- Phone OTP for India (4–8 week DLT registration).
- DMCA agent registration (legal/cost decision).
- Stripe Tax + RevenueCat live keys + IAP product setup.

### Deferred and at-risk for v1.0
- Email templates: MJML files never written; transactional emails will render as plain JSON or fail silently.
- Push notifications: `lib/push.ts` is a stub; no APNs/FCM device registration code; no Expo Push token capture.
- Notification preferences UI: not in mobile nav, no consumer-web settings page beyond the stub line.
- Celery workers: notification-svc digest, collab-svc auto-archive, moderation-svc dup-detection — no Celery container in docker-compose; no Fly machine config; no Render worker.

---

## Migration follow-ups (added 2026-06-11)

After per-service `version_table` patch + schema pre-creation, **9 of 19 services migrated successfully** to Supabase:
- auth, profile (stamped — were already at head)
- chat, collab, discovery, ai, meeting (full DDL applied; schemas live)
- admin, analytics (full DDL applied; schemas live)

**10 services NOT yet migrated due to real migration-file bugs** (each needs an individual fix; track as P0 follow-ups):

| Service | Error | Likely fix |
|---|---|---|
| matching-svc | `invalid input syntax for type json` on 0001 | Migration's `server_default` for a JSON column passes a bad literal — wrap in `text("'[]'::jsonb")` instead of raw `"[]"` |
| billing-svc | `invalid input syntax for type json` on 0001 | Same JSON server_default issue |
| invite-svc | `column "published" does not exist` | CHECK constraint or trigger references a column not yet declared in the same migration. Reorder or drop the constraint. |
| moderation-svc | `column cannot have more than 2000 dimensions for ivfflat index` | Vector column is >2000 dims; pgvector IVFFlat caps at 2000. Switch to `USING hnsw` (caps at 16k) or reduce embedding dim. |
| support-svc | Same 2000-dim ivfflat issue | Same fix: switch to hnsw |
| notification-svc | `type "notification_type_enum" already exists` | Leftover from earlier partial run; drop in correct schema first (`DROP TYPE notification.notification_type_enum CASCADE;`) then re-run |
| identity-svc | `Can't find Python file env.py` from `script_location=.` | alembic.ini's `script_location` should point to versions dir, not `.` |
| gateway-svc | `No 'script_location' key found in configuration` | migrations/alembic.ini missing the `script_location` setting |
| media-svc | (intentional — by design has no migrations, writes to chat schema) | None |
| geo-svc | (intentional — stateless Mapbox proxy) | None |

Schemas currently live in Supabase: admin, ai, analytics, chat, collab, discovery, meeting (7). 
