# Plan — 019 Pre-launch Hardening (P18)

**Phase**: P18  
**Status**: Planning  
**Target**: 100k DAU peak | 99.9% availability | Zero high/critical security findings  
**Date drafted**: 2026-05-11

---

## 1. Mission Recap

P18 is the final gate before public launch. The platform (codename Colab) is an AI-powered networking and collaboration platform for rising artists and creators (18+), serving US, Canada, Australia, New Zealand, and India at launch. By this phase, all features from P0–P17 are deployed to staging minimum.

This phase delivers:
- Load validation to 100k DAU peak (10k DAU at launch → 100k DAU by M6 per NFR-2)
- Zero open high/critical security findings across all 19 microservices
- App Store Connect and Google Play submission packets accepted
- 100-creator closed beta with ≥99% crash-free sessions
- Statuspage.io live and linked from marketing site
- On-call runbook published

**Success is a signed-off green gate, not a checkbox list.** Every acceptance criterion must close before public launch is permitted.

---

## 2. Research & Tooling Recommendations

### 2.1 Load Testing: k6 vs Artillery vs Locust

#### k6 (Recommended)

| Dimension | Detail |
|---|---|
| Language | JavaScript / TypeScript test scripts |
| HTTP support | Full (REST, streaming, multipart uploads) |
| WebSocket support | Native via `k6/experimental/websockets` — critical for chat-svc |
| Protocols | HTTP/1.1, HTTP/2, WebSocket, gRPC |
| Metrics output | Prometheus-compatible; integrates with Grafana out of the box |
| CI integration | Docker image; GitHub Actions first-class |
| Threshold enforcement | Built-in pass/fail thresholds halt the pipeline on breach |
| Cloud execution | Grafana Cloud k6 for distributed 100k VU runs |
| License | AGPL-3.0 (OSS) + Grafana Cloud (managed) |

**Why k6 wins**: The combination of native WebSocket support (required for chat-svc's 10k concurrent rooms), HTTP/2 coverage, scriptable in TypeScript (matches the team's existing stack), and native Grafana dashboard integration makes it the clear choice. The threshold DSL allows the pipeline to fail automatically when P95 latency budgets are exceeded.

#### Artillery (Runner-up)

Excellent for YAML-driven HTTP scenarios. WebSocket support is plugin-based (`artillery-engine-socketio`) and less mature for raw WebSocket (chat-svc uses custom WebSocket, not Socket.IO). Ruled out for WebSocket parity.

#### Locust (Alternative)

Python-native, good for teams with Python-first instincts. No native WebSocket support without third-party libraries. Slower script iteration than k6. Ruled out.

**Decision: k6 with Grafana Cloud k6 for distributed execution.**

---

### 2.2 Container CVE Scanning: Trivy

- **Tool**: [Trivy](https://github.com/aquasecurity/trivy) by Aqua Security
- **Scope**: OS packages, Python pip dependencies, npm packages inside container images; Dockerfile misconfig scanning; secrets detection
- **Integration**: GitHub Actions step after `docker build` in each service CI pipeline; gate: CRITICAL or HIGH findings block merge
- **SBOM output**: CycloneDX JSON artifact stored per build for audit trail
- **Registry scanning**: Trivy can also scan ECR images post-push for drift detection
- **License**: Apache-2.0

---

### 2.3 Software Composition Analysis (SCA): Snyk

- **Tool**: Snyk Open Source + Snyk Container
- **Scope**: Python `requirements.txt` / `pyproject.toml` across all 19 FastAPI services; npm `package.json` across three Next.js apps and the React Native app; Docker base images
- **Integration**: `snyk monitor` in CI; Snyk PR checks block high/critical findings; weekly email digest of new CVEs hitting existing deps
- **Complement to Trivy**: Trivy runs at container layer; Snyk runs at dependency manifest layer — different vulnerability databases (NVD + Snyk Intel)
- **Fix suggestions**: Snyk auto-generates fix PRs (like Dependabot but with richer context)
- **License**: Commercial (free tier for OSS; paid for org use)

---

### 2.4 SAST: semgrep + bandit

#### semgrep

- **Scope**: Python (all FastAPI services), TypeScript (Next.js, React Native), YAML/Kubernetes manifests
- **Ruleset**: `p/python`, `p/fastapi`, `p/typescript`, `p/react`, `p/secrets`, `p/owasp-top-ten`
- **Integration**: GitHub Actions; `semgrep ci` with findings uploaded to Semgrep Cloud for triage dashboard
- **Custom rules**: Write rules for platform-specific patterns (e.g., raw SQL construction, missing auth decorator on FastAPI routes, missing rate-limit check at gateway)
- **License**: OSS rules free; Semgrep Pro for org-wide dashboard

#### bandit

- **Scope**: Python only; complements semgrep with Python AST-level checks
- **Key checks**: Hardcoded passwords, SQL injection, subprocess shell=True, weak crypto, insecure deserialization
- **Integration**: `bandit -r . -ll` in CI; fail on HIGH severity
- **License**: Apache-2.0

**Combined SAST pipeline**: semgrep (broad, multi-language) → bandit (Python deep-dive) → eslint with `eslint-plugin-security` (TypeScript/React Native)

---

### 2.5 Dependabot Configuration

Dependabot covers automated dependency PRs for known CVEs and version bumps.

**`.github/dependabot.yml` strategy**:

```yaml
version: 2
updates:
  # Python — per service (one entry per service directory)
  - package-ecosystem: "pip"
    directory: "/services/auth-svc"
    schedule:
      interval: "weekly"
      day: "monday"
    open-pull-requests-limit: 5
    groups:
      production-deps:
        dependency-type: "production"
    # ... repeat for all 19 services

  # npm — Next.js apps
  - package-ecosystem: "npm"
    directory: "/apps/consumer-web"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5

  - package-ecosystem: "npm"
    directory: "/apps/marketing-static"
    schedule:
      interval: "weekly"

  - package-ecosystem: "npm"
    directory: "/apps/admin-console"
    schedule:
      interval: "weekly"

  # React Native
  - package-ecosystem: "npm"
    directory: "/mobile"
    schedule:
      interval: "weekly"

  # Docker base images
  - package-ecosystem: "docker"
    directory: "/"
    schedule:
      interval: "weekly"

  # GitHub Actions
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
```

**Policy**: Dependabot security PRs auto-merge if CI passes and severity is MODERATE or below; HIGH/CRITICAL require human review within 48h.

---

### 2.6 Secrets-Rotation Runbook

All secrets live in AWS Secrets Manager (ARC-31). EKS pods consume via IRSA; GitHub Actions via OIDC.

**Rotation cadence**:

| Secret class | Rotation interval | Rotation method |
|---|---|---|
| Database passwords (RDS Postgres) | 90 days | Secrets Manager automatic rotation Lambda |
| Redis auth token (ElastiCache) | 90 days | Manual + rolling restart |
| JWT signing key | 180 days | Blue/green with overlap window |
| OpenAI API key | 90 days | Manual; revoke old after 24h overlap |
| Stripe restricted key | 90 days | Manual; test in staging first |
| RevenueCat API key | 90 days | Manual |
| Persona API key | 90 days | Manual |
| Replicate API key | 90 days | Manual |
| Recall.ai API key | 90 days | Manual |
| AWS access key (break-glass only) | 30 days | Manual; prefer IRSA |
| Apple APNs key | Annual (Apple limit) | Coordinated with push notification test |
| FCM server key | As needed | Google Console rotation |

**Rotation drill process** (run quarterly):
1. Identify target secret.
2. Generate new credential in the provider console.
3. Add new value as a new version in Secrets Manager (do not delete old).
4. Deploy canary pod with `AWSCURRENT` pointing to new version; validate health check.
5. Promote new version to `AWSCURRENT` across all pods (rolling restart).
6. Wait 24h observation window; watch Sentry + CloudWatch for auth errors.
7. Deprecate old version; set `AWSPREVIOUS` TTL to 7 days.
8. Document in rotation log (Notion or internal wiki).

**Emergency rotation** (suspected compromise):
1. Page on-call immediately (PagerDuty P1).
2. Generate and deploy new secret within 30 minutes.
3. Revoke compromised credential at provider.
4. Open incident channel.
5. Postmortem within 72h.

---

### 2.7 Mobile Security: OWASP MASVS

Apply [OWASP Mobile Application Security Verification Standard v2](https://mas.owasp.org/MASVS/) across the React Native + Expo app.

**Applicable control families**:

| MASVS Category | Key controls for Colab RN app |
|---|---|
| MASVS-STORAGE | No sensitive data in AsyncStorage unencrypted; no credentials in logs; Keychain (iOS) / Keystore (Android) for tokens |
| MASVS-CRYPTO | No hardcoded keys; use OS-provided crypto; JWT verified server-side |
| MASVS-AUTH | Biometric re-auth for sensitive flows (payments, account deletion); token expiry enforced |
| MASVS-NETWORK | Certificate pinning for API Gateway; no HTTP in production; HSTS |
| MASVS-PLATFORM | AI mockup screen uses FLAG_SECURE (Android) + overlay warning (iOS) per FR-C-8; deep-link validation |
| MASVS-CODE | No debug code in release builds; obfuscation via Metro + Hermes; no eval() |
| MASVS-RESILIENCE | Anti-tampering checks (Expo integrity API); jailbreak/root detection advisory warning |

MASVS verification integrated into the security review checklist (Section 4).

---

## 3. Load-Test Scenarios

**Infrastructure**: Grafana Cloud k6 for distributed execution. All scenarios run against the staging environment scaled to production parity (same EKS node counts, same RDS instance class, same Redis cluster size).

**Shared ramp profile** (unless overridden per scenario):
- Stage 1: 0 → target VUs over 5 min (warm-up)
- Stage 2: Hold target VUs for 20 min (steady state)
- Stage 3: 0 → 1.5× target VUs over 5 min (spike)
- Stage 4: Hold spike for 10 min
- Stage 5: Ramp down over 5 min (cooldown)

**Global thresholds** (applied to every scenario):
- HTTP error rate < 1%
- WebSocket disconnect rate < 0.5%
- No 5xx responses during steady-state

---

### 3.1 Scenario A — Signup Funnel

**Simulates**: New user registration including email OTP verification and Persona webhook callback.

**VU count ramp**:
- Warm-up: 0 → 500 VUs over 5 min
- Steady state: 500 VUs for 20 min
- Spike: 500 → 750 VUs for 10 min

**Steps per VU iteration**:
1. `POST /auth/register` (email + password)
2. `POST /auth/verify-email` (OTP code)
3. `POST /profile/setup` (display name, location, vocations, bio)
4. `POST /media/upload` (portfolio item, simulated 2MB image)
5. Persona webhook callback (simulated inbound; hit staging webhook endpoint)

**Target latency budget**:
- Registration + OTP: P95 ≤ 200ms
- Profile setup: P95 ≤ 200ms
- Portfolio upload (media-svc + S3 pre-sign): P95 ≤ 500ms
- Persona webhook processing: P95 ≤ 300ms

**Success criteria**:
- ≥99% of registration + OTP flows complete without error
- Zero 5xx on auth-svc or profile-svc during steady state
- Throughput ≥ 400 successful signups/min at peak

---

### 3.2 Scenario B — Feed Scroll

**Simulates**: Authenticated users browsing the discovery feed (infinite-scroll mode and swipe-card mode) with ranking calls.

**VU count ramp**:
- Warm-up: 0 → 5,000 VUs over 5 min
- Steady state: 5,000 VUs for 20 min
- Spike: 5,000 → 7,500 VUs for 10 min

**Steps per VU iteration**:
1. Authenticate (JWT from pre-seeded test user pool of 50k accounts)
2. `GET /discovery/feed?page=1` (first page, 20 profiles)
3. `GET /discovery/feed?page=2` (second page)
4. `GET /discovery/profile/{id}` (profile detail view, 3 random profiles)
5. `POST /discovery/save/{id}` (save 1 profile)
6. `POST /discovery/hide/{id}` (hide 1 profile for 3 months)

**Target latency budget**:
- Feed page load (discovery-svc + Redis hot cache): P95 ≤ 300ms
- Profile detail (profile-svc): P95 ≤ 200ms
- Save/hide mutations: P95 ≤ 150ms

**Success criteria**:
- Redis cache hit rate ≥ 80% for feed pages during steady state
- discovery-svc pod CPU ≤ 70% at 5k VUs
- Zero feed pages returning empty results for non-new users

---

### 3.3 Scenario C — Chat Fanout

**Simulates**: 10,000 concurrent active chat rooms with message send/receive fanout; steady-state target of 100k messages/min.

**VU count ramp**:
- Warm-up: 0 → 10,000 VUs (each VU = one side of one chat room) over 5 min
- Steady state: 10,000 VUs for 20 min (~167 msg/sec per VU pair = 100k msg/min total)
- Spike: 10,000 → 15,000 VUs for 10 min

**Steps per VU iteration**:
1. Authenticate (pre-seeded test user pool)
2. Open WebSocket connection to `wss://api/chat/ws/{room_id}`
3. Send text message every 0.6 seconds (simulates active typing)
4. Receive and acknowledge echo from partner VU
5. Send 1 file message per VU session (simulated 500KB image)
6. Presence ping every 30 seconds

**Target latency budget**:
- Message send → receive (e2e via WebSocket): P95 ≤ 500ms
- WebSocket connection establishment: P95 ≤ 200ms
- File message processing (media-svc + moderation-svc scan): P95 ≤ 2,000ms
- Presence update propagation: P95 ≤ 1,000ms

**Success criteria**:
- WebSocket disconnect rate < 0.5% during steady state
- Message delivery rate ≥ 99.9% (no dropped messages)
- chat-svc pod memory stable (no leak) over 30-min run
- Postgres chat message write throughput ≥ 100k inserts/min

---

### 3.4 Scenario D — AI Command Invocation

**Simulates**: Premium users invoking in-chat AI commands (`/brainstorm`, `/summarize-chat`, `/mockup-image`) which fan out to ai-orchestrator-svc and Replicate.

**VU count ramp**:
- Warm-up: 0 → 200 VUs over 5 min
- Steady state: 200 VUs for 20 min
- Spike: 200 → 400 VUs for 10 min

*Note*: AI command rate is intentionally lower than chat VUs — these are premium credit-gated operations. 400 concurrent AI VUs represents heavy realistic load given credit quotas.

**Steps per VU iteration**:
1. Authenticate as premium test user
2. `POST /ai/command` with command=`/brainstorm`, context=mock chat history
3. Poll `GET /ai/job/{job_id}` status (webhook-async pattern via Replicate)
4. Wait for completion webhook (stubbed Replicate in staging returns in ≤3s)
5. `POST /ai/command` with command=`/summarize-chat`
6. `POST /ai/command` with command=`/mockup-image` (triggers Replicate image gen job)

**Target latency budget**:
- Command intake + job queue: P95 ≤ 300ms
- `/brainstorm` e2e (OpenAI GPT-4): P95 ≤ 8,000ms
- `/summarize-chat` e2e (OpenAI): P95 ≤ 5,000ms
- `/mockup-image` job queued confirmation: P95 ≤ 500ms (async; actual gen via webhook)
- Celery queue depth: ≤ 500 jobs at steady state (not backing up)

**Success criteria**:
- ai-orchestrator-svc returns 202 Accepted for all valid commands within latency budget
- Celery worker scale-out triggered automatically at queue depth > 100 (HPA)
- Credit wallet deduction idempotent (no double-charges on retry)
- Zero Replicate webhook delivery failures (staging mock)

---

### 3.5 Scenario E — Billing Webhook Storms

**Simulates**: RevenueCat and Stripe webhook storms (subscription renewals, payment failures, dunning events) at scale.

**VU count ramp**:
- Warm-up: 0 → 1,000 VUs over 2 min
- Steady state: 1,000 VUs for 15 min (each VU sends one webhook per 0.5s = 2,000 webhooks/sec)
- Spike: 1,000 → 3,000 VUs for 5 min (simulates end-of-month renewal storm)

**Webhook types distributed** (weighted):
- RevenueCat `RENEWAL` (40%)
- RevenueCat `INITIAL_PURCHASE` (20%)
- Stripe `invoice.payment_succeeded` (20%)
- RevenueCat `BILLING_ISSUE` / Stripe `invoice.payment_failed` (10%)
- Stripe dunning retry events (10%)

**Steps per VU iteration**:
1. `POST /billing/webhooks/revenuecat` with HMAC-signed payload
2. `POST /billing/webhooks/stripe` with Stripe-Signature header
3. Verify 200 OK response (idempotency key deduplication must work)
4. Send duplicate webhook (same idempotency key) — must return 200 without re-processing

**Target latency budget**:
- Webhook intake (HMAC verify + enqueue to RabbitMQ): P95 ≤ 100ms
- CreditWallet update propagation: P95 ≤ 500ms (async via worker)
- Dunning email dispatch: P95 ≤ 2,000ms (async)

**Success criteria**:
- Zero duplicate credit charges from re-delivered webhooks (idempotency verified)
- billing-svc handles 3,000 webhooks/sec without queue backup
- RabbitMQ queue depth ≤ 5,000 messages at peak (workers consuming fast enough)
- Stripe HMAC and RevenueCat HMAC validation pass on 100% of valid webhooks; 100% rejection of tampered payloads

---

## 4. Security Review Checklist

**Owner**: Engineering lead + external pen-test vendor  
**Gate**: Zero HIGH or CRITICAL open findings before launch approval

### 4.1 Per-Service Threat Model (STRIDE)

Each of the 19 microservices receives a STRIDE threat-model pass. Template:

| STRIDE Category | Questions to answer per service |
|---|---|
| **Spoofing** | How does the service verify caller identity? What happens if JWT is missing or tampered? |
| **Tampering** | Are all inputs validated and sanitized? Can a user modify data belonging to another user? |
| **Repudiation** | Are all write actions logged with actor ID + timestamp? Is the audit log tamper-evident? |
| **Information Disclosure** | Does error output leak stack traces, internal IDs, or PII? Are S3 signed URLs scoped correctly? |
| **Denial of Service** | Are rate limits enforced at gateway? Are resource-intensive operations (AI, media scan) queued? |
| **Elevation of Privilege** | Can a Free user invoke Premium-gated endpoints? Can a regular user access admin routes? |

**Services requiring priority STRIDE review** (highest data sensitivity / attack surface):

1. `auth-svc` — credential handling, session tokens, OAuth flows
2. `gateway` — rate limiting, CORS, JWT verification, routing rules
3. `chat-svc` — WebSocket authentication, message content access controls
4. `billing-svc` — payment webhook HMAC, entitlement logic, credit wallet
5. `media-svc` — file upload limits, MIME validation, virus scanning
6. `ai-orchestrator-svc` — prompt injection risk, credit exhaustion DoS
7. `moderation-svc` — moderator privilege escalation
8. `admin-svc` — admin console authentication strength
9. `identity-svc` — Persona webhook authenticity, liveness bypass risk

---

### 4.2 Dependency CVE Scan

- **Tool**: Trivy (container images) + Snyk (manifests) — see Section 2.2 and 2.3
- **Scope**: All 19 service images in ECR; all `requirements.txt`; all `package.json`
- **Gate**: No CRITICAL findings; no HIGH findings older than 14 days without accepted exception
- **Exception process**: Engineering lead + security reviewer sign off on accepted risks with compensating control documented
- **SBOM**: CycloneDX JSON stored in S3 for each release

---

### 4.3 SAST Review

- **Tools**: semgrep + bandit + eslint-plugin-security — see Section 2.4
- **Scope**:
  - All Python FastAPI services: SQL query construction, raw exec, shell injection, insecure deserialization, weak crypto, hardcoded secrets
  - All TypeScript (Next.js + RN): XSS, prototype pollution, eval usage, dangerouslySetInnerHTML
  - YAML/K8s manifests: privileged containers, host network, missing resource limits
- **Gate**: Zero HIGH/CRITICAL semgrep findings in CI; bandit baseline established and no regressions
- **Custom semgrep rules** to write:
  - Detect FastAPI routes missing `Depends(verify_jwt)` decorator
  - Detect direct Postgres queries without parameterization
  - Detect `os.system()` or `subprocess.run(shell=True)`
  - Detect logging of `password`, `token`, `secret` fields

---

### 4.4 Container Hardening Checklist

For each of the 19 service Docker images:

- [ ] Base image is official Python slim or distroless; not `latest` tag
- [ ] Runs as non-root user (`USER appuser`)
- [ ] No secrets baked into image layers (Trivy secrets scan passes)
- [ ] `COPY --chown` used; no world-writable directories
- [ ] Only required ports exposed
- [ ] Healthcheck instruction defined
- [ ] Multi-stage build: dev dependencies not in production image
- [ ] Image signed with Cosign (supply-chain integrity)
- [ ] EKS pod spec: `readOnlyRootFilesystem: true`, `allowPrivilegeEscalation: false`, `capabilities: drop: [ALL]`
- [ ] Resource requests and limits set (no unbounded memory)
- [ ] Network policy restricts pod-to-pod traffic to declared service dependencies only

---

### 4.5 Secrets Rotation

See Section 2.6 for full runbook. Pre-launch checklist:

- [ ] All secrets verified to be in AWS Secrets Manager (zero plaintext in environment variables in EKS pod specs)
- [ ] IRSA roles confirmed per service (least-privilege IAM policy per service)
- [ ] GitHub Actions OIDC confirmed (no long-lived access keys in GitHub Secrets)
- [ ] Rotation drill executed for all secret classes at least once on staging
- [ ] Dead secrets (old API keys, dev credentials) purged from Secrets Manager

---

### 4.6 Penetration Test Scope

**Vendor**: External specialist; budget approval required (Phase 5 procurement — `[OPEN RISK]`)

**Scope**:
- **API Gateway + auth-svc**: Authentication bypass, JWT attacks, OAuth flow manipulation, rate-limit bypass
- **Chat-svc WebSocket**: Unauthorized room access, message injection, presence spoofing
- **Media-svc**: Malicious file upload (polyglot files, archive bombs, SSRF via image processing)
- **Billing-svc**: HMAC bypass on webhook endpoints, entitlement manipulation, credit fraud
- **Admin-svc**: Privilege escalation, IDOR on moderation actions
- **Mobile app**: OWASP MASVS L1 verification, binary analysis, traffic interception
- **AWS infrastructure**: S3 bucket policies, ECR image access, IAM misconfigurations, public endpoint exposure

**Exclusions**: Third-party systems (Stripe, RevenueCat, Persona, Replicate, OpenAI) — tested at integration points only, not source systems.

**Timeline**: 2-week test window minimum; remediation sprint after findings delivered; retest of HIGH/CRITICAL findings before launch approval.

---

## 5. App Store Connect Submission Packet (iOS)

### 5.1 App Icon

| Asset | Specification |
|---|---|
| Marketing icon | 1024×1024 px, PNG, no alpha channel, no rounded corners (Apple rounds automatically), no transparency |
| In-app icon | Provided via Xcode asset catalog (`AppIcon.appiconset`) |
| Style | Flat design; no camera/lens effect; brand color consistent with app UI |

### 5.2 Screenshots — Required Device Classes

| Device class | Resolution (portrait) | Quantity |
|---|---|---|
| iPhone 6.9" (iPhone 16 Pro Max) | 1320×2868 px | 3–10 |
| iPhone 6.7" (iPhone 15 Plus / 16 Plus) | 1290×2796 px | 3–10 |
| iPad Pro 13" (M4) | 2064×2752 px | 3–10 |
| iPad Pro 11" | 1668×2388 px | 3–10 |

*Required minimum*: iPhone 6.9" and iPad Pro 13" are mandatory; others can be auto-scaled by App Store Connect if opted in.

**Screenshot content guidelines**:
- Screenshot 1: Discovery feed (value prop — find your creative match)
- Screenshot 2: Swipe card stack with AI match score callout
- Screenshot 3: Vibe Check send flow
- Screenshot 4: Collaboration workspace / chat + file sharing
- Screenshot 5: AI command in chat (`/brainstorm` result)
- Screenshot 6: Profile + Valid Profile Badge

All screenshots must use real in-app UI (no mockups per Apple guidelines). Use simulator with clean seed data.

### 5.3 Description Copy Outline

**App name**: [BRAND_NAME] — Creative Collab (subject to final brand lock)

**Subtitle** (30 chars max): Find Your Creative Partner

**Promotional text** (170 chars max; can be updated without review): Join [BRAND_NAME] — the AI-powered platform where artists and creators build real projects together, not just followers.

**Description structure** (4,000 chars max):
1. Opening hook (2–3 sentences): the creator loneliness problem and the platform's mission
2. Core value props (bullet list):
   - AI-matched by creative compatibility, not follower count
   - Real collaboration workspaces with file sharing, whiteboards, and AI tools
   - Verified creators only — safety-first community
3. Feature highlights: Vibe Check, AI assistant commands, credit system
4. Community promise: anti-engagement-farming, pro-creative-output
5. CTA: Sign up free. Premium unlocks unlimited matching and AI credits.

### 5.4 Keyword Strategy

**Keyword field** (100 chars, comma-separated, no spaces after commas):
`creative,collaboration,artist,musician,designer,creator,networking,AI,match,collab,portfolio,gig`

**Strategy notes**:
- Avoid brand names in keywords (Apple policy)
- Avoid words already in app name/subtitle
- Target long-tail: "find music collaborator", "artist networking app", "creative partner finder"
- Monitor via App Store Connect Analytics; iterate post-launch

### 5.5 Age Rating

**Rating**: **17+** (per Apple's age rating questionnaire)

**Rationale**:
- Infrequent/Mild: Mature/Suggestive Themes (user-generated creative content)
- User-Generated Content: Yes (chat, portfolio uploads, AI-generated mockups)
- Unrestricted Web Access: No (bounded chat; no general browser)

*Note*: The platform enforces 18+ at the application level (FR-A-3, COMP-2) but Apple's scale maxes at 17+. The ToS and age-attestation enforce the 18+ floor beyond Apple's system.

### 5.6 Privacy Questionnaire Answers

Apple's "Data Used to Track You" section:

| Category | Answer | Rationale |
|---|---|---|
| Data Used to Track You | **None** | No cross-app tracking; ATT prompt deferred per ARC-33 locked decision; first-party analytics only (PostHog) |
| Contact Info (Email) | Collected, linked to identity, used for app functionality | Account management, transactional email |
| Identifiers (User ID) | Collected, linked to identity | Account management |
| Usage Data | Collected, linked to identity | Analytics (PostHog, first-party) |
| Location (Coarse) | Collected, linked to identity | Discovery radius matching |
| Photos/Videos | Collected, linked to identity | Portfolio uploads |
| Audio | Collected, linked to identity | Portfolio audio uploads, voice notes |
| Financial Info | Collected, linked to identity | Subscription management |
| Health & Fitness | Not collected | |
| Sensitive Info | Not collected | |
| Contacts | Not collected | |
| Browsing History | Not collected | |

### 5.7 TestFlight Track Configuration

**Internal Testing Track**:
- Up to 100 Apple test accounts (engineering + QA)
- No review required
- Builds expire after 90 days
- Enable crash reporting + automatic feedback

**External Testing Track** (closed beta):
- Up to 10,000 external testers (use for 100-creator beta)
- Requires Apple review of TestFlight build (typically 24–48h)
- Invitation via email link or public TestFlight link (use private link for invite-only beta)
- Beta app description must be accurate (reviewed)
- Feedback: TestFlight in-app feedback + custom Typeform link in welcome email

---

## 6. Google Play Submission Packet (Android)

### 6.1 App Icon

| Asset | Specification |
|---|---|
| High-res icon | 512×512 px, PNG, 32-bit color, no alpha trim issues |
| Adaptive icon | Foreground layer 108×108 dp (432×432 px at 4x), background layer separate, safe zone 66×66 dp |
| Style | Match iOS icon; adaptive icon foreground must look good on any shape mask |

### 6.2 Feature Graphic

- **Size**: 1024×500 px, PNG or JPEG
- **Content**: Brand visual with platform value prop text; no device frame required
- **Safe zone**: Keep important content within the center 924×400 px (50px margin each side)
- **Note**: Displayed at top of Play Store listing and on Google Play featured placement

### 6.3 Screenshots

| Device class | Min resolution | Quantity |
|---|---|---|
| Phone (portrait) | 1080×1920 px minimum | 2–8 |
| 7-inch tablet (landscape optional) | 1200×1920 px | 1–8 |
| 10-inch tablet (landscape optional) | 1600×2560 px | 1–8 |
| Chromebook (optional) | Varies | 1–8 |

**Screenshot content**: Mirror iOS screenshot set adjusted for Android UI (back navigation, Android system UI).

### 6.4 Description

**Short description** (80 chars): Find your creative partner. AI-matched collaborations for artists.

**Full description** (4,000 chars): Mirror iOS description structure; adjust CTA to reference Google Play and mention AI credits system.

### 6.5 Content Rating Questionnaire

Proceed through IARC (International Age Rating Coalition) questionnaire in Play Console:

| Question area | Answer |
|---|---|
| Violence | None |
| Sexual content | None |
| Profanity | None |
| Controlled substances | None |
| User-generated content | Yes — users share portfolio media and chat |
| Social features | Yes — messaging between users |
| Location sharing | Yes — coarse location for discovery radius |
| Digital purchases | Yes — subscription IAP |
| Personal information collection | Yes |

**Expected rating**: PEGI 12+ or ESRB Teen at minimum; potentially ESRB Mature 17+ due to UGC + social messaging. Verify on submission. App's own 18+ enforcement is documented in ToS.

### 6.6 Data Safety Form

| Data type | Collected | Shared with third parties | Purpose |
|---|---|---|---|
| Email address | Yes | No | Account management |
| Name | Yes | No | Profile display |
| User IDs | Yes | No | Authentication |
| Profile info (bio, vocation) | Yes | No | App functionality |
| Photos & videos | Yes | No | Portfolio uploads |
| Audio files | Yes | No | Portfolio + voice notes |
| Location (approximate) | Yes | No | Discovery matching |
| App interactions | Yes | No | Analytics (PostHog) |
| Crash logs | Yes | No | Sentry error tracking |
| Financial info | Yes | No | Subscription management |
| Messages | Yes | No (E2E not claimed — persisted to Postgres per audit log requirement) | Chat functionality |

**Security practices to declare**:
- Data encrypted in transit (TLS 1.2+)
- Data encrypted at rest (RDS encryption, S3 SSE)
- Users can request data deletion (DSR — full GDPR-grade per COMP-2)
- Committed to Google Play Families Policy: No

### 6.7 Internal Testing Track Configuration

**Internal testing**:
- Up to 100 Google accounts
- No review required; instant publish
- Use for QA + smoke testing

**Closed testing (Alpha) track** (closed beta):
- Named email list of 100 invited creators
- No public availability
- Requires Play review (usually 1–3 days for new apps)
- Opt-in URL sent via invitation email

---

## 7. RevenueCat IAP Product Config Sync

RevenueCat is the entitlement layer bridging App Store IAP and Google Play Billing.

### 7.1 Products to Configure in RevenueCat

| Product ID | Type | Platform | Tier | Interval |
|---|---|---|---|---|
| `premium_monthly` | Auto-renewable subscription | iOS + Android | Premium | Monthly |
| `premium_annual` | Auto-renewable subscription | iOS + Android | Premium | Annual |
| `premium_pro_monthly` | Auto-renewable subscription | iOS + Android | Premium Pro | Monthly |
| `premium_pro_annual` | Auto-renewable subscription | iOS + Android | Premium Pro | Annual |
| `ai_credits_100` | Consumable | iOS + Android | Add-on | One-time |
| `ai_credits_500` | Consumable | iOS + Android | Add-on | One-time |
| `ai_credits_1000` | Consumable | iOS + Android | Add-on | One-time |

### 7.2 RevenueCat Entitlements Mapping

| Entitlement ID | Products that unlock it |
|---|---|
| `premium` | `premium_monthly`, `premium_annual`, `premium_pro_monthly`, `premium_pro_annual` |
| `premium_pro` | `premium_pro_monthly`, `premium_pro_annual` |
| `ai_credits` | `ai_credits_100`, `ai_credits_500`, `ai_credits_1000` (consumable — credit value added to wallet) |

### 7.3 Sync Checklist

- [ ] All App Store products created in App Store Connect and in `Submitted` status
- [ ] All Google Play products created in Play Console and `Active` status
- [ ] RevenueCat project connected to App Store Connect via API key
- [ ] RevenueCat project connected to Google Play via Service Account JSON
- [ ] Webhook URL configured: `POST /billing/webhooks/revenuecat` in RevenueCat dashboard
- [ ] Webhook HMAC secret stored in AWS Secrets Manager
- [ ] Sandbox testing passed: purchase, restore, cancel, refund flows on both platforms
- [ ] Web platform products configured in Stripe (matching SKU names/prices for cross-platform parity per FR-E-3)
- [ ] RevenueCat "Offering" configured with all products in correct Packages

---

## 8. Closed Beta Program

### 8.1 Beta Parameters

| Parameter | Value |
|---|---|
| Total invitees | 100 creators |
| Target platform | iOS (TestFlight) + Android (Play Alpha) simultaneously |
| Duration | 4 weeks |
| Target crash-free sessions | ≥ 99% |
| Target onboarding completion | ≥ 80% complete onboarding flow |
| Feedback channels | In-app feedback form + dedicated email alias |

### 8.2 Recruitment Plan

**Target profile**: Active independent creators in the platform's five launch geos (US, CA, AU, NZ, IN) across the 9 vocation categories (visual, performing, literary, design, digital, media, craft arts, plus sub-tags). Mix of experience levels; minimum 18 years old (mandatory).

**Recruitment channels**:
1. **Discord creator communities**: post in relevant servers (music producers, indie illustrators, digital artists, filmmakers)
2. **Instagram DM outreach**: search relevant hashtags; DM creators with genuine engagement (not follower-farmed accounts)
3. **Reddit**: r/WeAreTheMusicMakers, r/learnart, r/filmmakers, r/graphic_design — invite post with beta link
4. **Personal network**: founding team's creative contacts (seed credibility)
5. **Typeform application form**: short form (name, vocation, city, why interested); select 100 from applicants

**Selection criteria**:
- Vocation distribution: at least 2 per main vocation category
- Geo distribution: at least 10 from each launch country
- No more than 20 from same city (diversity of location signals)
- Mix of "would be daily user" and "occasional user" personas

### 8.3 NDA Template Summary

Beta NDA should cover:
- Confidentiality of unreleased features, UI, pricing, and platform name
- Prohibition on screenshots/recordings shared publicly (note: AI mockup screen has FLAG_SECURE / overlay warnings per FR-C-8)
- 12-month term post-beta end
- Acknowledgment that beta builds may be unstable
- Beta participant retains ownership of any creative content they upload (standard user rights from ToS)

*Legal review required before distribution.* Use DocuSign or HelloSign for e-signature.

### 8.4 Feedback Channel

- **In-app**: Shake-to-report feedback form (Sentry user feedback widget) + dedicated "Send Feedback" button in settings
- **Email**: `beta@[brand].com` alias → support-svc ticket queue with `beta` tag
- **Weekly check-in**: Async survey (Typeform) sent weekly; questions on onboarding friction, feature value, crashes encountered
- **Discord server** (private, invite-only): `#beta-general`, `#beta-bugs`, `#beta-ideas` channels; founder/PM active daily

### 8.5 Crash-Free Target

- **Target**: ≥ 99% crash-free sessions (Sentry mobile crash rate)
- **Definition**: A session is crash-free if no unhandled exception or native crash occurs during the session
- **Monitoring**: Sentry dashboard; daily check during beta; auto-alert if crash rate exceeds 1% on any single day
- **Escalation**: >1% crash rate on any day → P2 incident; >2% → P1 incident + pause new invitations

---

## 9. Status Page

### 9.1 Statuspage.io Setup

**Provider**: Statuspage.io (Atlassian)

**Plan**: Business plan minimum (required for API access and metric embedding)

**Components** (mapped to platform services + user-facing flows):

| Component Name | Underlying service(s) | User-facing description |
|---|---|---|
| API & Authentication | gateway + auth-svc | Log in / Sign up |
| Discovery Feed | discovery-svc + matching-svc | Find Creators |
| Messaging & Chat | chat-svc | Chat with Collaborators |
| File Sharing | media-svc | Share Files |
| AI Assistant | ai-orchestrator-svc | AI Commands |
| Billing & Subscriptions | billing-svc | Payments |
| Push Notifications | notification-svc + AWS SNS | Notifications |
| Media Delivery (CDN) | CloudFront + S3 | Profile Photos & Media |
| Admin & Moderation | admin-svc + moderation-svc | Safety & Trust |

**Component groups**:
- Core Platform: API & Authentication, Discovery Feed
- Collaboration: Messaging & Chat, File Sharing, AI Assistant
- Payments: Billing & Subscriptions
- Infrastructure: Push Notifications, Media Delivery

### 9.2 Uptime Checks

**Pingdom** (or AWS Route 53 Health Checks as fallback):

| Check | URL | Interval | Alert threshold |
|---|---|---|---|
| API Health | `GET /health` on API Gateway | 1 min | 2 consecutive failures |
| Auth endpoint | `POST /auth/health` | 1 min | 2 consecutive failures |
| Feed endpoint | `GET /discovery/health` | 1 min | 2 consecutive failures |
| Chat WebSocket | WS handshake to chat-svc | 2 min | 2 consecutive failures |
| Media CDN | CloudFront health check URL | 2 min | 3 consecutive failures |
| Billing webhook | `GET /billing/health` | 2 min | 2 consecutive failures |

**Alert routing**: Pingdom → PagerDuty → on-call engineer (see Section 10).

### 9.3 Status Page Integration

- **Link**: Visible in app Settings → "System Status" + in marketing site footer
- **Subscription widget**: Embed Statuspage subscriber widget on marketing site so users can subscribe to updates via email/SMS
- **Incident communication template**:
  - **Investigating**: "We are investigating reports of [component] issues. Updates every 15 minutes."
  - **Identified**: "We have identified the cause of [component] issues: [brief description]. We are working on a fix."
  - **Monitoring**: "A fix has been deployed and we are monitoring the situation."
  - **Resolved**: "The issue with [component] has been resolved. All systems are operating normally."

---

## 10. Runbook

### 10.1 On-Call Rotation

**Tool**: PagerDuty

**Rotation structure**:
- **Primary on-call**: 1 engineer; 1-week rotation; rotates every Monday 09:00 local
- **Secondary on-call** (escalation): 1 senior engineer; same rotation offset by 4 days
- **Incident commander**: Engineering lead; paged on P1 only; not in regular rotation

**Rotation members at launch** (minimum viable):
- Rotation pool: 3–4 engineers minimum to avoid unsustainable on-call burden
- If team is smaller: compress to 2-person rotation with compensatory time-off

**Quiet hours policy**: No P3/P4 pages between 23:00–07:00 local time. P1/P2 page at any hour.

---

### 10.2 Paging Policy (PagerDuty)

| Severity | Page target | Response SLA | Escalation if no ack |
|---|---|---|---|
| P1 — Critical | Primary + Secondary + IC simultaneously | Ack within 5 min | Page Engineering Lead at 10 min |
| P2 — High | Primary on-call | Ack within 15 min | Escalate to Secondary at 20 min |
| P3 — Medium | Primary on-call (business hours only) | Ack within 2h | Escalate at 4h |
| P4 — Low | Ticket created; no page | Next business day | — |

**PagerDuty integrations**:
- Pingdom → PagerDuty (uptime failures)
- Sentry → PagerDuty (crash spike alerts)
- AWS CloudWatch → PagerDuty (EKS node failures, RDS failover events)
- Manual trigger: Slack `/pd trigger` command in incident channel

---

### 10.3 Severity Definitions

| Severity | Definition | Examples |
|---|---|---|
| **P1 — Critical** | Complete service outage or data loss; all users impacted; security breach | auth-svc down (no one can log in), chat-svc total failure, database unreachable, active security incident |
| **P2 — High** | Significant degradation; majority of users impacted; revenue affected | Feed not loading for >20% of users, billing webhooks failing, push notifications not delivering |
| **P3 — Medium** | Partial degradation; subset of users impacted; workaround exists | AI commands slow (>15s), file upload failing for some MIME types, moderation queue backed up |
| **P4 — Low** | Minor issue; single user or edge case; no service impact | Typo in error message, analytics event missing, non-critical cosmetic bug |

---

### 10.4 Incident Channels

**Slack (internal team)**:
- `#incidents` — all active incidents (PagerDuty auto-posts alert here)
- `#incidents-p1` — P1 only; pings `@oncall` and `@engineering-lead`
- `#postmortems` — published postmortem docs

**Discord (if community-facing status updates needed)**:
- `#status-updates` in official Discord server (moderator-only post)
- Post when Statuspage is updated; do not post raw technical details

**External communication**:
- Statuspage.io for user-visible status updates
- Email to affected users via SES for data-related incidents (required by privacy laws for data breach notification)

---

### 10.5 Postmortem Template

```
# Postmortem — [Incident Title]

**Date**: YYYY-MM-DD  
**Severity**: P[1-4]  
**Duration**: HH:MM — HH:MM UTC (X hours Y minutes)  
**Affected services**: [list]  
**Incident commander**: [name]  
**Author**: [name]  
**Status**: Draft / In Review / Published  

## Summary
[2–3 sentence plain-English summary of what happened and impact.]

## Timeline (UTC)
| Time | Event |
|---|---|
| HH:MM | Alert fired / first report |
| HH:MM | On-call paged |
| HH:MM | Incident declared P[X] |
| HH:MM | Root cause identified |
| HH:MM | Fix deployed |
| HH:MM | Service restored |
| HH:MM | All-clear / monitoring |

## Root Cause
[Technical root cause. Be specific. No blame.]

## Contributing Factors
[List 2–5 factors that contributed (config, missing monitoring, untested edge case, etc.)]

## Impact
- Users affected: [estimate]
- Revenue impact: [estimate or N/A]
- Data loss: [Yes/No — if Yes, details + notification obligations]
- SLA breach: [Yes/No — 99.9% calculation]

## Resolution
[What was done to fix the immediate issue.]

## Follow-up Action Items
| Action | Owner | Due date | Ticket |
|---|---|---|---|
| [Specific preventative action] | [name] | YYYY-MM-DD | [GH issue link] |

## Lessons Learned
[What worked well. What could have been faster. What we didn't know before.]
```

**Postmortem SLA**: Published draft within 72h of P1 resolution; final version within 5 business days.

---

### 10.6 Change Management SOP

**Change categories**:

| Category | Definition | Approval required | Deploy window |
|---|---|---|---|
| Standard | Routine code deploy via CI/CD; covered by automated tests | None — CI/CD gates | Anytime |
| Normal | DB migration, config change, dependency upgrade | Engineering lead async approval | Weekdays 10:00–16:00 local |
| Emergency | Hotfix for P1/P2 incident | Incident commander approval (verbal OK) | Anytime; postmortem required |
| Major | EKS cluster upgrade, RDS major version, new service deploy | Engineering lead sync approval + staging soak 48h | Weekdays 10:00–14:00 local |

**Deploy checklist (Standard)**:
1. CI green (all tests pass, SAST/Trivy clean)
2. Staging deploy passes smoke tests
3. Canary deploy to 5% of production pods
4. Monitor error rate for 15 min
5. Full rollout if error rate unchanged
6. Rollback plan: `kubectl rollout undo deployment/[service]`

**Freeze windows**:
- No Normal or Major changes in the 48h before and 48h after public launch day
- No changes on Friday 17:00 – Monday 09:00 (avoid weekend incidents)

---

## 11. Implementation Tasks

| ID | Title | Outcome | Est. hours | Blocks | Blocked by |
|---|---|---|---|---|---|
| T-001 | k6 load test environment setup | Grafana Cloud k6 org created; staging env scaled to prod parity; test data seeded (50k synthetic users) | 16 | T-010 through T-015 | All P0–P17 services deployed to staging |
| T-002 | Trivy CI integration | Trivy scans in GitHub Actions for all 19 services; CRITICAL findings block merge | 8 | — | — |
| T-003 | Snyk integration | Snyk monitor in CI; PR checks active; HIGH/CRITICAL findings block merge | 8 | — | — |
| T-004 | semgrep CI integration | semgrep ci configured with rulesets; custom rules written (missing auth decorator, raw SQL, logging secrets) | 12 | — | — |
| T-005 | bandit CI integration | bandit -r . -ll in all Python service CI pipelines; baseline committed | 6 | — | — |
| T-006 | eslint-plugin-security integration | Added to all TypeScript packages; CI blocks on HIGH findings | 4 | — | — |
| T-007 | Dependabot configuration | `.github/dependabot.yml` covering all 19 services + 3 Next.js apps + RN + Docker + Actions | 6 | — | — |
| T-008 | Container hardening audit | All 19 service Dockerfiles audited against checklist (Section 4.4); remediation PRs merged | 20 | — | — |
| T-009 | STRIDE threat model per service | STRIDE doc completed for all 19 services; findings logged as GitHub issues with severity labels | 40 | T-016 | — |
| T-010 | Secrets rotation drill | Full rotation drill on staging for all secret classes; rotation log published | 16 | — | T-001 |
| T-011 | Load test — Scenario A (signup funnel) | k6 script written; passes success criteria at target VU count | 12 | T-019 | T-001 |
| T-012 | Load test — Scenario B (feed scroll) | k6 script written; Redis cache hit rate ≥80%; passes success criteria | 12 | T-019 | T-001 |
| T-013 | Load test — Scenario C (chat fanout) | k6 WebSocket script written; 10k concurrent rooms; 100k msg/min; passes success criteria | 16 | T-019 | T-001 |
| T-014 | Load test — Scenario D (AI command invocation) | k6 script written; Celery auto-scale verified; credit idempotency verified | 12 | T-019 | T-001 |
| T-015 | Load test — Scenario E (billing webhook storm) | k6 script written; idempotency verified; 3k webhooks/sec passes | 10 | T-019 | T-001 |
| T-016 | Pen-test vendor engagement | Vendor selected; SOW signed; test window scheduled; findings delivered | 40 | T-022 | T-009 (STRIDE informs scope) |
| T-017 | Pen-test findings remediation | All HIGH/CRITICAL findings resolved; retest passed | Variable (TBD post-findings) | T-022 | T-016 |
| T-018 | MASVS mobile security review | MASVS L1 checklist completed; FLAG_SECURE verified on Android; certificate pinning verified; Keychain/Keystore verified | 16 | — | — |
| T-019 | Production capacity reservation | EKS node groups right-sized for 100k DAU peak; RDS instance class confirmed; ElastiCache cluster sized; capacity reserved in AWS | 12 | T-011–T-015 | T-001 |
| T-020 | App Store Connect listing | All assets uploaded (icon, screenshots × device classes, description, keywords, age rating, privacy questionnaire) | 16 | T-023 | — |
| T-021 | Google Play Console listing | All assets uploaded (icon, feature graphic, screenshots, description, content rating, data safety form) | 16 | T-023 | — |
| T-022 | RevenueCat IAP product config sync | All 7 products created in App Store Connect + Play Console + RevenueCat; entitlements mapped; sandbox flows tested | 12 | T-020, T-021 | — |
| T-023 | TestFlight external track setup | TestFlight build submitted and approved; external track with beta email list configured | 8 | T-025 | T-020 |
| T-024 | Play Alpha track setup | Alpha track build uploaded and approved; email list configured | 8 | T-025 | T-021 |
| T-025 | Beta recruitment | Typeform live; 100 creators recruited; NDA signed; invitation emails sent with TestFlight + Play links | 20 | T-026, T-027 | T-023, T-024 |
| T-026 | Beta monitoring setup | Sentry crash alerts configured; daily crash-free session dashboard; PagerDuty alert for >1% crash rate | 8 | — | — |
| T-027 | Beta feedback channel setup | In-app shake-to-report configured; beta@[brand].com alias active; Discord private server set up; weekly Typeform survey scheduled | 8 | — | — |
| T-028 | Statuspage.io setup | Account created; components configured; uptime checks via Pingdom configured; status page linked from app + marketing site | 10 | — | — |
| T-029 | PagerDuty setup | PagerDuty org created; services configured; escalation policies set; Pingdom + Sentry + CloudWatch integrations active; on-call schedule set | 10 | — | — |
| T-030 | On-call rotation setup | PagerDuty rotation staffed; all engineers on rotation complete PagerDuty training; test page executed | 4 | — | T-029 |
| T-031 | Runbook publication | On-call runbook published to `docs/runbooks/`; postmortem template committed; change management SOP linked in engineering wiki | 8 | — | — |
| T-032 | Load test full run + sign-off | All 5 scenarios pass simultaneously against production-sized staging; P95 latencies within budget; sign-off from engineering lead | 16 | — | T-011–T-015, T-019 |
| T-033 | Security sign-off | Zero HIGH/CRITICAL findings open across SAST + CVE scan + pen-test; sign-off documented | 4 | — | T-002–T-006, T-016, T-017, T-018 |
| T-034 | iOS App Store submission | App submitted for review; first-response tracked; any rejection issues resolved | 8 | — | T-020, T-022 |
| T-035 | Android Play Store submission | App submitted for review; first-response tracked; any rejection issues resolved | 8 | — | T-021, T-022 |
| T-036 | Beta completion report | 4-week beta complete; crash-free ≥99% confirmed; onboarding ≥80% confirmed; top 10 feedback items triaged into backlog | 8 | — | T-025, T-026, T-027 |

**Total estimated hours**: ~428h (excludes pen-test remediation which is TBD post-findings)

---

## 12. Acceptance Criteria with Verifications

### AC-1 — Load test hits 100k concurrent users within latency budgets

**Criterion**: All 5 k6 scenarios (Signup Funnel, Feed Scroll, Chat Fanout, AI Command, Billing Webhooks) run simultaneously against production-parity staging, peak VU counts sustained for 10 minutes minimum, with all P95 latency thresholds passing and HTTP error rate < 1%.

**Verification**:
1. Run `k6 run --vus [target] --duration 10m scenario-[x].js` for each scenario
2. Export Grafana dashboard screenshot showing P95 latency per scenario
3. Confirm k6 threshold pass/fail summary shows all GREEN
4. Review CloudWatch Container Insights for pod CPU/memory stability (no OOM kills)
5. Engineering lead signs LGTM in the load-test PR

**Evidence artifact**: Grafana dashboard export + k6 summary JSON stored in `docs/load-tests/[date]/`

---

### AC-2 — Zero high/critical security findings open

**Criterion**: At time of launch gate review, Snyk, Trivy, semgrep, bandit, and pen-test report show zero open HIGH or CRITICAL findings. Accepted exceptions documented with compensating controls and signed off by engineering lead.

**Verification**:
1. `snyk test --severity-threshold=high` exits 0 in CI for all services
2. Trivy scan of all ECR images shows zero CRITICAL/HIGH (or all accepted with documented exceptions)
3. semgrep CI shows zero unresolved HIGH/CRITICAL findings
4. Pen-test report final version delivered; all HIGH/CRITICAL items marked Resolved or Accepted
5. Security sign-off ticket (T-033) closed with engineering lead sign-off

**Evidence artifact**: Snyk report export, Trivy SBOM JSONs, semgrep CI logs, pen-test final report — all stored in `docs/security/[date]/`

---

### AC-3 — iOS app passes Apple Review

**Criterion**: The production iOS build is approved by Apple App Review and available (gated) in the App Store or TestFlight external track.

**Verification**:
1. App Store Connect shows build status "Ready for Sale" or "Approved"
2. Metadata approved (no rejection notices outstanding)
3. TestFlight external track shows build "Active"
4. Test installation on physical iPhone confirms app launches and onboarding completes

**Evidence artifact**: App Store Connect screenshot of approval status

**Known risk**: First-submission rejection is common, especially for apps with UGC, AI, and payments. Track resubmissions in `docs/app-store/rejection-log.md`; expected iteration of 1–3 review cycles.

---

### AC-4 — Android app passes Play Console Review

**Criterion**: The production Android build is approved by Google Play Review and available in the internal/alpha/production track as configured.

**Verification**:
1. Play Console shows release status "Published" for target track
2. Content rating assigned (IARC questionnaire completed)
3. Data safety form published
4. Test installation on physical Android device confirms app launches and onboarding completes

**Evidence artifact**: Play Console screenshot of release status

---

### AC-5 — 100 beta users onboarded; onboarding ≥80%; crash-free ≥99%

**Criterion**: 100 creators have accepted beta invitations and attempted onboarding. At least 80 completed the full onboarding flow (through portfolio upload, per FR-A-13 target). Sentry crash-free session rate ≥99% over the full 4-week beta.

**Verification**:
1. PostHog funnel report: onboarding funnel showing ≥80% completion at step "portfolio upload"
2. Sentry mobile dashboard: crash-free sessions ≥99% over beta period
3. Beta completion report (T-036) authored and reviewed

**Evidence artifact**: PostHog funnel export + Sentry crash rate chart stored in `docs/beta/completion-report.md`

---

### AC-6 — Status page green; runbook published

**Criterion**: Statuspage.io is live with all components configured; all Pingdom uptime checks active and passing; status page linked from app settings and marketing site footer. Runbook is published in `docs/runbooks/` and reviewed by at least two engineers.

**Verification**:
1. Navigate to status page URL — all components show "Operational"
2. Pingdom dashboard shows all checks "Up" for ≥24h
3. `docs/runbooks/on-call.md` exists in main branch with PR approval from ≥2 engineers
4. App Settings → System Status link navigates to status page
5. Marketing site footer "Status" link navigates to status page

**Evidence artifact**: Status page URL in `docs/launch-checklist.md`; `git log docs/runbooks/` showing merged PR

---

## 13. Open Risks

### Risk-1 — Apple App Review First-Submission Rejection

**Likelihood**: High (common for new apps with UGC + AI + payments)

**Potential rejection reasons**:
- Guideline 4.3 (duplicate functionality) — mitigate by emphasizing differentiated creative niche in description
- Guideline 2.1 (app completeness) — ensure all flows function on simulator during submission
- Guideline 3.1.1 (in-app purchase) — ensure all premium features require IAP; no external payment links in app
- Guideline 5.1.1 (privacy policy) — ensure privacy policy URL is accurate and accessible without login
- Guideline 1.2 (user-generated content) — must have visible moderation, reporting, and content flagging mechanisms (all present per FR-M)

**Mitigation**:
- Submit to TestFlight external review first (faster feedback loop before production submission)
- Include detailed review notes explaining AI mockup screenshot guards, 18+ enforcement, moderation pipeline
- Prepare written responses for common rejection templates
- Allow 2–3 review cycles in launch timeline (add 2-week buffer)

---

### Risk-2 — Google Play First-Submission Rejection

**Likelihood**: Medium

**Potential rejection reasons**:
- Data safety form inaccuracies — verify every data type collected is declared
- Content rating mismatch — UGC + social features may trigger additional requirements
- Target API level (targetSdkVersion must be current year's requirement)

**Mitigation**:
- Use Play Console pre-launch report (robo test) to surface crashes before review
- Review Play Policy Center for UGC apps before submission
- Ensure targetSdkVersion = current Android requirement (35 as of 2026)

---

### Risk-3 — Pen-Test Vendor Procurement Delay

**Likelihood**: Medium

**Impact**: If vendor is not engaged early enough, pen-test findings may arrive too late to remediate before launch.

**Mitigation**:
- Begin vendor evaluation immediately (T-016 should start in week 1 of P18)
- Issue RFP to at least 3 vendors simultaneously
- Budget approval from product owner required as prerequisite — escalate if blocked
- Fallback: run internal red-team exercise using OWASP Testing Guide if vendor is delayed; defer external pen-test to 2 weeks post-launch with a commitment to remediate before public marketing push

---

### Risk-4 — 100k DAU Capacity Under-Provisioning

**Likelihood**: Low-Medium (mitigated by load test, but traffic patterns may differ from synthetic)

**Impact**: Real user behavior may generate traffic spikes (e.g., viral social sharing post-launch) that exceed modeled scenarios.

**Mitigation**:
- Configure EKS Cluster Autoscaler + HPA on all stateless services
- RDS: enable Multi-AZ + read replicas for discovery-svc and chat-svc
- CloudFront caching for static assets and feed metadata to reduce origin load
- Set AWS Service Quotas increase requests in advance for EC2, NAT Gateway, ALB targets

---

### Risk-5 — Beta NDA and Legal Review Delay

**Likelihood**: Low-Medium

**Impact**: Cannot invite beta users until NDA is reviewed and ready for e-signature.

**Mitigation**:
- Begin NDA drafting in week 1 of P18; route to legal counsel immediately
- Use standard SaaS beta NDA template as starting point to minimize drafting time
- Target legal sign-off within 1 week

---

### Risk-6 — RevenueCat / App Store IAP Review Rejection

**Likelihood**: Low-Medium

**Impact**: If IAP products are rejected (e.g., metadata doesn't match app functionality), subscription flows are blocked on mobile.

**Mitigation**:
- Submit IAP products for review in App Store Connect well before app submission (they can be reviewed independently)
- Ensure subscription descriptions are accurate and non-misleading per App Store guidelines
- Sandbox test all purchase flows thoroughly before submission

---

*End of plan — 019 Pre-launch Hardening (P18)*
