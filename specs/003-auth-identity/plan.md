# 003 — Auth + Identity Verification — Implementation Plan

> Status: **DRAFT — Phase 4 detailing**. Source spec: `specs/003-auth-identity/spec.md`. Master: `specs/000-master/spec.md`. Shared deps: `specs/002-shared-platform/spec.md`. Plan generated 2026-05-11.
>
> Codename in code: `Colab`. Services: `auth-svc` (FastAPI) + `identity-svc` (FastAPI). Phase: P2.
> Availability target: **99.95%** (one nine higher than the platform baseline; every other service depends on this).

---

## 1. Mission Recap

Auth + Identity is the floor every other Colab feature stands on. The two services under this plan have one mandate: **establish who a user is, prove it cryptographically, and gate the Valid Profile Badge state machine.** Everything else — feed, matching, chat, payments — assumes a `User` row exists, that JWTs are signed, that sessions can be revoked, and that the Persona-driven liveness check has either passed, failed, or is pending.

Scope per master §3 Journey A:
- FR-A-1: email + password signup, magic-link + 6-digit OTP fallback for verification.
- FR-A-2: Apple Sign-In, Google Sign-In, phone SMS-OTP (AWS SNS) signup + login.
- FR-A-3: 18+ age attestation, enforced server-side (`age_attestation == true` is a hard gate; signup returns 400 otherwise).
- FR-A-9: Persona selfie + liveness. **Soft block** — Persona pending/declined does **not** prevent chat, matching, or feed access; it gates only the Valid Profile Badge per master §0.
- FR-A-12: time-stamped, IP-stamped, version-stamped acceptance of ToS, Privacy, Community Guidelines.
- Account ops: password reset, email change, phone change, password rotation, session list + revoke, "log out all devices".
- JWT issuance: access 15min, refresh 30d, RS256 signed off a KMS-rotated key, JTI tracked, refresh rotates on use.
- Brute-force protection: Redis token-bucket on `(ip, route)` and counter on `(email, ip)` with exponential backoff and IP + email locks.
- Persona webhook handler: `inquiry.completed` → flips `IdentityVerification.status` → publishes `identity.verified` / `identity.declined` / `identity.needs_review` events for `profile-svc` (§004) to consume.

Non-goals this milestone: TOTP/2FA (forward-compatible columns reserved on `User`), passkeys (deferred), social-OAuth linking for Instagram/YouTube/Spotify (lives in `profile-svc` §004 — not auth login), in-cluster mTLS rotation (handled by §002 shared platform).

Hard dependencies: `colab_common` (auth middleware, idempotency middleware, rate-limit middleware, events publisher, SQLAlchemy async base, RLS hooks, settings, Sentry, OTel) per §002. Soft dependency: `profile-svc` (§004 — Badge granted there, off `identity.verified`).

---

## 2. Research Findings

### 2.1 Password hashing — argon2-cffi

- Library: `argon2-cffi==23.1.0` (`PasswordHasher` API). Backed by `libargon2.so`. Python 3.12 compatible.
- Variant: **argon2id** (master §0 lock).
- Parameters: `memory_cost=65536` (64 MiB), `time_cost=3`, `parallelism=4`, `hash_len=32`, `salt_len=16`.
- Encoded hash format: `$argon2id$v=19$m=65536,t=3,p=4$<salt>$<hash>` → store as TEXT column `password_hash`. Self-describing; no separate salt/params column.
- Verify path: `PasswordHasher.verify(stored, plaintext)` — raises `VerifyMismatchError` on bad password, `InvalidHash` on corruption. Treat both as `401 invalid_credentials`; never differentiate to the client (timing-safe, error-shape uniform).
- Re-hash path: if `ph.check_needs_rehash(stored)` after a successful verify, re-hash on the next login. Surfaces when parameters change.
- **Gotcha 1**: do **not** store the user's email or any PII in the salt; argon2-cffi generates a CSPRNG salt automatically.
- **Gotcha 2**: 64 MiB × peak-concurrent-logins drives memory budget. With pod limit 2 GiB and 30 concurrent verifies the pod will OOM. Cap verifies via a per-pod semaphore (`asyncio.Semaphore(8)`) and run argon2 work in `asyncio.to_thread` so it doesn't block the event loop.
- **Gotcha 3**: deny-list common passwords (`zxcvbn` score < 3) before hashing; reject `email` or `phone` substring inside password.
- Migration plan: write `password_hash_version` column NOT NULL DEFAULT 1; bump on parameter change.

### 2.2 JWT — pyjwt + KMS-signed RS256

- Library: `pyjwt[crypto]==2.8.0`.
- Algorithm: **RS256** (signing key in AWS KMS Customer-Managed Key, `KeyUsage=SIGN_VERIFY`, `KeySpec=RSA_2048`). The service never holds the private key in memory; it calls `kms.Sign` for issuance. **Latency tax: ~6–10ms per sign call**, so we cache the *active public key set* locally and run KMS signs in `asyncio.to_thread`.
- Verification: pull the JWKS via the service's `GET /.well-known/jwks.json` endpoint (no KMS round-trip on verify; we use the public key cached in process for 60s).
- Rotation: **two active keys at a time** (`current` + `previous`). `kid` claim carries the active key alias; verifier accepts either. KMS-alias-rotation Lambda runs monthly (key material lives for 13 months for back-compat); we expose both in JWKS so old tokens still verify until natural expiry.
- Claims (access):
  ```
  iss: "auth.colab"
  aud: ["api.colab"]
  sub: <user_id (uuid)>
  jti: <uuid v4>
  iat, nbf, exp
  sid: <session_id>
  email_verified: bool
  identity_verified: bool   # mirrors IdentityVerification.status == approved
  scope: ["user"]           # admin/moderator scopes attached by admin-svc
  ```
- Claims (refresh): no `aud`; `typ: "refresh"`; otherwise same envelope. Refresh tokens **rotate on every use**; the *previous* refresh token JTI is added to a Redis revocation set with TTL = refresh-TTL.
- Replay protection: every issued JTI for refresh is stored under `refresh:jti:<jti> → session_id, exp`. On refresh, delete-and-rotate. If a JTI is seen twice, **revoke the entire session chain** (the stolen-refresh-token detection pattern; the legitimate client has already moved on).
- Logout: revoke session row (set `revoked_at`); add the *refresh* JTI to revocation set. Access tokens are short-lived (15min) so we **do not maintain a denylist for access JTIs** to keep verify cheap; the gateway pulls session-revoked state from a Redis bitmap keyed by `session_id` on every request (one Redis GET per request — ~0.4ms).
- **Gotcha 1**: pyjwt does not call your `kid → key` resolver unless you pass `options={"verify_signature": True}` + `algorithms=["RS256"]` AND build the JWKS resolver yourself. Use `PyJWKClient` only for static JWKS; for our KMS-backed key we build a custom resolver.
- **Gotcha 2**: `aud` mismatch returns `InvalidAudienceError` not `InvalidTokenError` — handle both in the auth middleware.
- **Gotcha 3**: clock skew. Allow 30s `leeway` on `exp`/`nbf`/`iat` verification. EKS pods are NTP-synced but cross-AZ skew has been observed at 200ms+.

### 2.3 Apple Sign-In — server-side verification

- No third-party lib at launch; we verify the Apple-issued `identity_token` (a JWT) ourselves to keep the dependency surface small.
- Apple's JWKS endpoint: `https://appleid.apple.com/auth/keys`. Cache JWKS for 6h with a 5-minute negative-cache on lookup failure.
- Verification recipe:
  1. Decode JWT header → `kid` + `alg` (must be `RS256`; reject anything else).
  2. Fetch JWK by `kid` from cached JWKS; if not present, refresh JWKS once and retry.
  3. Verify signature.
  4. Validate `iss == "https://appleid.apple.com"`, `aud == APPLE_SIGN_IN_CLIENT_ID`, `exp` in future.
  5. Extract `sub` (stable Apple user id), `email` (one-time relay or real address, **email_verified** claim governs trust), `is_private_email`.
- **Gotcha 1**: Apple emails the relay address (`@privaterelay.appleid.com`) only on first sign-in unless the user re-grants. Persist it; subsequent sign-ins may not include `email`.
- **Gotcha 2**: Apple's "Hide my email" produces a unique relay per app — that's fine; we still treat it as the user's verified email.
- **Gotcha 3**: `nonce` parameter for replay protection — client generates per sign-in, server stores in a short-lived Redis cell, must match claim on verify. Reject if missing.

### 2.4 Google Sign-In — server-side verification

- Library: `google-auth==2.30.0` — `from google.oauth2 import id_token; from google.auth.transport import requests`.
- Call: `id_token.verify_oauth2_token(token, requests.Request(), audience=<one of GOOGLE_CLIENT_ID_{IOS,ANDROID,WEB}>)`.
- Library handles JWKS fetch, signature verify, exp/iat/iss/aud all in one. Returns dict with `sub`, `email`, `email_verified`, `aud`.
- Audience handling: accept token only if `aud` is one of the three configured client IDs. Reject anything else (cross-project token injection).
- **Gotcha 1**: the library caches Google's JWKS by default for 1h via `requests.Request` adapter — fine; we don't override.
- **Gotcha 2**: if a user signs in with both Apple and Google on the same email, we get **two Identity rows** linked to one User. Email match is our merge signal but only when `email_verified == true` on both sides.

### 2.5 Phone OTP — AWS SNS SMS

- API: `boto3.client('sns').publish(PhoneNumber=<E.164>, Message=<text>, MessageAttributes={AWS.SNS.SMS.SenderID, AWS.SNS.SMS.SMSType: "Transactional"})`.
- Sender ID: `SNS_SMS_SENDER_ID=Colab` (supported in IN, AU, NZ; US/CA fall back to long codes — registered through Pinpoint 10DLC for US per AWS SMS guidance).
- Message format (single SMS, <160 chars): `Colab: Your verification code is 482913. Expires in 5 minutes. Reply STOP to opt out.`
- OTP: 6 digits, generated via `secrets.randbelow(900_000) + 100_000`, stored in Redis `otp:phone:<phone>` with 5-min TTL and `attempt_count` (max 5). After 5 wrong attempts the key is deleted and a 30-minute cool-down lock is set on `(phone, ip)`.
- Opt-out: SNS auto-handles STOP/QUIT/CANCEL keywords (returns the number to the opt-out list). On opt-in failure (recipient previously opted out) `Publish` returns 200 but the message is dropped. We poll the SNS opt-out list before issuing a new OTP and surface a clear error: "This number has opted out of texts. Reply START to resume or use a different number."
- Cost ceiling: SNS SMS spend caps via `SMSPreferences.MonthlySpendLimit`. Default our account to $200/mo; alert at 80%.
- **Gotcha 1**: India SMS requires DLT registration of the template and sender (TRAI rule). Coordinate with infra in §001. Until registered, India phone signup falls back to email signup; we soft-disable phone signup when `country_code == IN AND DLT_REGISTERED != true` (feature flag).
- **Gotcha 2**: avoid sending OTP to a number that already has a pending OTP; re-use the live one or short-circuit with 429.

### 2.6 Persona — Inquiry API + webhook signature

- Library: none. Plain `httpx` against `https://withpersona.com/api/v1/`.
- Inquiry-template approach: pre-built workflow in Persona dashboard (`PERSONA_TEMPLATE_ID`) with selfie + head-turn + smile prompts (matches §0 ARC-18 decision).
- Create inquiry: `POST /inquiries { data: { attributes: { inquiry-template-id, reference-id: <user_id> } } }` with `Persona-Version: 2023-01-05`. Returns `inquiry_id`.
- SDK session token: `POST /inquiries/{id}/generate-one-time-link` returns a short-lived link OR call `POST /inquiries/{id}/resume?session-token=true` (the RN SDK opens the session). We pass the `session_token` to the client; SDK opens the camera flow.
- Webhook URL: `POST /webhooks/persona/inquiry` (path on identity-svc, exposed via gateway).
- Webhook signature header: `Persona-Signature: t=<ts>,v1=<hmac>`.
- Verification: `hmac.new(PERSONA_WEBHOOK_SECRET.encode(), f"{ts}.{raw_body}".encode(), hashlib.sha256).hexdigest()` compared in constant time to `v1`. Reject if `|now - ts| > 300s`.
- Idempotency: Persona sends the same `inquiry.completed` more than once; we key idempotency on `event_id` from the payload (also stored as the webhook event id). Inserts into `persona_webhook_events` with `event_id UNIQUE`; duplicates 200-OK no-op.
- **Gotcha 1**: Persona delivery has at-least-once semantics with retries on 5xx. Our handler must be idempotent and respond fast (return 200 within 5s; queue heavy work).
- **Gotcha 2**: the `face_age_signal` is in `data.attributes.fields["age-estimate-signal"]` (varies by template); if it's `< 18` even when liveness passed, flip the status to `needs_review` (master §0).
- **Gotcha 3**: in dev, Persona webhooks can be redirected via their dashboard "Webhook URL" override. Per-env secrets are mandatory.

### 2.7 Magic-link patterns

- Single-use signed token, exp ≤ 15 min, **opaque to clients**.
- Implementation: `token = base64url(secrets.token_bytes(32))`. SHA-256 hash stored in `magic_links` table with `purpose ∈ {email_verify, password_reset, email_change, phone_change}`, `user_id`, `exp_at`, `consumed_at`, `nonce`.
- Email body link: `https://app.colab.com/auth/verify?t=<token>` — opens RN via Universal Links / Android App Links → mobile screen calls `POST /auth/email/verify/finish { token }` → server hashes & lookups; consume → set `consumed_at`. Constant-time compare on hash.
- **Single use**: any second attempt with same token returns 410 Gone.
- **Bind to device**: optional. We do NOT bind by default — that breaks the "request on phone, click on laptop" UX. We DO bind for password reset (token cookie set on email open if web; otherwise `client_id` claim).
- OTP fallback: 6-digit code generated parallel to the magic-link token; both consume the same row. User can use either. OTP entered in-app → same `verify/finish` endpoint with `code` instead of `token`.
- Rate limit: max 3 start-requests per email per 10 minutes (429 with retry-after).

### 2.8 Email — AWS SES + MJML templates

- SES region us-east-1; production identity verified, DKIM enabled, DMARC `p=reject` aligned with the `MARKETING_DOMAIN`.
- Sender: `SES_FROM_ADDRESS=no-reply@colab.com`. Reply-to: `support@colab.com`.
- Templates authored in MJML (`templates/email/*.mjml`); compiled to HTML at build time and registered as SES templates via the deploy pipeline (one SES template per email type, with `{{var}}` placeholders).
- Send pattern: `SendTemplatedEmail` with structured `TemplateData`. Tracks `MessageId` for bounce/complaint linkage.
- Bounce/complaint: SES → SNS → `auth.email.bounce` / `auth.email.complaint` topics → handler in notification-svc (§014) flags address; auth-svc updates `email_status` column (`active|bounced|complained`). Hard-bounced emails are blocked from re-sending.
- **Gotcha**: SES sandbox-mode allows sending only to verified addresses. Production-access request must be filed in §001 infra.

### 2.9 Rate limit — Redis token bucket

- Pattern: token bucket per `(ip, route)` AND per `(user_id, route)` (whichever exists). Bucket key: `rl:<scope>:<key>:<route>`.
- Storage: Redis `HSET` with fields `tokens`, `last_refill_ts`. Refilled lazily on read by `min(capacity, tokens + elapsed * refill_rate)`.
- Buckets:
  - `auth_signup`: 5 attempts/min/IP, capacity 5, refill 0.083/s.
  - `auth_login`: 10/min/IP, capacity 10, refill 0.167/s.
  - `auth_otp_send`: 1 per 60s per `(phone OR email)`, capacity 1, refill 0.0167/s, additional **daily cap 10 per phone**.
  - `auth_password_reset_start`: 3 per 10min per email, capacity 3, refill 0.005/s.
  - `auth_oauth`: 30/min/IP (clients can retry).
  - `auth_refresh`: 60/min/user, capacity 60, refill 1/s.
  - `persona_webhook`: not rate-limited (signed) but bounded at 100 rps via API Gateway.
- 429 response: `Retry-After: <seconds>` header. JSON body: `{ "error":"rate_limited", "retry_after_seconds": N }`.
- All gates also enforced at the gateway (master §0: gateway IP + user+route) as defense-in-depth.

---

## 3. Valid Profile Badge State Machine

```
                       ┌─────────────────┐
                       │   unverified    │  (signup just landed; no email yet verified)
                       └────────┬────────┘
                                │ email magic-link clicked OR OTP entered
                                ▼
                       ┌─────────────────┐
                       │ email_verified  │  (User.email_verified_at set; can use product)
                       └────────┬────────┘
                                │ user starts Persona inquiry (RN opens SDK)
                                ▼
                       ┌─────────────────┐
                       │identity_pending │  (Persona inquiry created; waiting on webhook)
                       └────────┬────────┘
                                │
       ┌────────────────────────┼──────────────────────────┐
       │                        │                          │
       │ webhook: declined      │ webhook: approved        │ webhook: needs_review
       ▼                        ▼                          ▼  (age-signal <18 OR Persona escalation)
┌─────────────────┐    ┌─────────────────┐        ┌─────────────────────┐
│ identity_held    │    │identity_approved│        │ identity_held       │
│ (declined)       │    └────────┬────────┘        │ (manual_review)     │
└────────┬─────────┘             │ profile-svc     └─────────┬───────────┘
         │ user resubmits        │ kicks off AI            │ moderator
         │ Persona inquiry       │ profile review          │ approves OR rejects
         │                       ▼                          │
         │             ┌─────────────────────┐               │
         │             │ ai_review_pending   │               │
         │             └─────────┬───────────┘               │
         │                       │                            │
         │       ┌───────────────┼─────────────────┐          │
         │       │               │                 │          │
         │       │ AI approved   │ AI flagged      │          │
         │       ▼               ▼                 ▼          │
         │ ┌──────────────┐ ┌──────────────────┐              │
         └▶│ unverified    │ │ badge_held        │◀────────────┘
           │ (back to start)│ │ (mod_review)      │
           └──────────────┘ └─────────┬─────────┘
                                      │ moderator approves
                                      ▼
                            ┌─────────────────┐
                            │ badge_granted   │  ← VALID PROFILE BADGE issued
                            └─────────────────┘
                                      │
                                      │ user reported / found in violation
                                      ▼
                            ┌─────────────────┐
                            │ badge_revoked   │  (moderation-svc action)
                            └─────────────────┘
```

Notes:
- States *up to and including* `email_verified` live in `auth-svc.User`.
- States `identity_*` live in `identity-svc.IdentityVerification`.
- States `ai_review_pending` → `badge_granted` live in `profile-svc.ProfileReview` (§004).
- Soft-block rule: **every state except `badge_granted` still allows full product use**. Only the badge UI affordance is gated.
- `badge_revoked` is reachable from `badge_granted` only via moderator action (§008 moderation-svc).

---

## 4. Detailed Data Model

All tables in schema `auth` (auth-svc) or `identity` (identity-svc). Single Postgres cluster; per-service schemas isolate ownership. SQLAlchemy 2.x async models in `apps/auth_svc/models.py` and `apps/identity_svc/models.py`.

### 4.1 `auth.users`

| column | type | nullable | default | notes |
|---|---|---|---|---|
| `id` | uuid | NO | `gen_random_uuid()` | PK |
| `email` | citext | YES | — | lowercased; uniqueness conditional |
| `email_verified_at` | timestamptz | YES | — | when magic-link/OTP succeeded |
| `email_status` | text | NO | `'active'` | `active|bounced|complained` |
| `phone` | text | YES | — | E.164 |
| `phone_verified_at` | timestamptz | YES | — | |
| `password_hash` | text | YES | — | argon2id-encoded; NULL when only OAuth |
| `password_hash_version` | smallint | NO | `1` | bump on parameter change |
| `password_updated_at` | timestamptz | YES | — | last rotation |
| `age_attestation_at` | timestamptz | NO | — | 18+ attestation timestamp |
| `is_active` | boolean | NO | `true` | global kill switch (admin) |
| `is_locked` | boolean | NO | `false` | lockout state |
| `locked_until` | timestamptz | YES | — | brute-force cooldown |
| `last_login_at` | timestamptz | YES | — | |
| `last_active_at` | timestamptz | YES | — | refreshed by gateway |
| `mfa_enabled` | boolean | NO | `false` | v1.1 forward-compat |
| `mfa_secret_ciphertext` | bytea | YES | — | v1.1 forward-compat (KMS-wrapped) |
| `created_at` | timestamptz | NO | `now()` | |
| `updated_at` | timestamptz | NO | `now()` | trigger-bumped |

Indexes:
- `users_email_uniq` UNIQUE `(email) WHERE email IS NOT NULL` — partial because phone-only users have NULL email.
- `users_phone_uniq` UNIQUE `(phone) WHERE phone IS NOT NULL` — partial.
- `users_last_active_idx` BRIN `(last_active_at)` — supports activity-based discovery rank.
- `users_is_active_idx` `(is_active) WHERE is_active = false` — partial for admin sweep.

Row-Level Security: enabled. Policy `users_self_select`: `USING (id = current_setting('app.user_id', true)::uuid OR current_setting('app.role', true) IN ('admin','moderator'))`. Service-to-service traffic sets `app.role = 'service'` and bypasses via a separate `users_service_select` policy.

### 4.2 `auth.identities`

OAuth federation rows; 1 user → many identities (apple, google, email, phone).

| column | type | nullable | default | notes |
|---|---|---|---|---|
| `id` | uuid | NO | `gen_random_uuid()` | PK |
| `user_id` | uuid | NO | — | FK users.id ON DELETE CASCADE |
| `provider` | text | NO | — | `apple|google|email|phone` |
| `provider_subject` | text | NO | — | apple `sub` / google `sub` / email itself / phone E.164 |
| `provider_email` | citext | YES | — | snapshot at link time |
| `linked_at` | timestamptz | NO | `now()` | |
| `unlinked_at` | timestamptz | YES | — | soft delete |

Indexes:
- `identities_provider_subject_uniq` UNIQUE `(provider, provider_subject) WHERE unlinked_at IS NULL`.
- `identities_user_provider_idx` `(user_id, provider)`.

RLS: same self-select pattern as `users`.

### 4.3 `auth.sessions`

| column | type | nullable | default | notes |
|---|---|---|---|---|
| `id` | uuid | NO | `gen_random_uuid()` | PK; embedded in JWT `sid` claim |
| `user_id` | uuid | NO | — | FK users.id ON DELETE CASCADE |
| `refresh_token_hash` | bytea | NO | — | sha256 of opaque refresh token (we still issue JWT refresh; this hash secures revocation lookup) |
| `current_refresh_jti` | uuid | NO | — | latest issued refresh JTI |
| `user_agent` | text | YES | — | truncated 512 |
| `ip` | inet | YES | — | |
| `device_id` | text | YES | — | optional client fingerprint |
| `created_at` | timestamptz | NO | `now()` | |
| `last_seen_at` | timestamptz | NO | `now()` | |
| `revoked_at` | timestamptz | YES | — | NULL = active |
| `revoke_reason` | text | YES | — | `user_logout|logout_all|admin|stolen_refresh|password_change` |

Indexes:
- `sessions_user_idx` `(user_id) WHERE revoked_at IS NULL` — partial; fast "list active sessions".
- `sessions_last_seen_idx` BRIN `(last_seen_at)`.

RLS: `sessions_self`: `user_id = current_setting('app.user_id')::uuid`.

### 4.4 `auth.legal_acceptances`

| column | type | nullable | default | notes |
|---|---|---|---|---|
| `id` | uuid | NO | `gen_random_uuid()` | PK |
| `user_id` | uuid | NO | — | FK |
| `doc_type` | text | NO | — | `tos|privacy|community_guidelines|age_attestation` |
| `doc_version` | text | NO | — | semver of the published doc |
| `accepted_at` | timestamptz | NO | `now()` | |
| `ip` | inet | YES | — | |
| `user_agent` | text | YES | — | |

Indexes: composite `(user_id, doc_type, doc_version)` UNIQUE — one row per (user, doc, version). Used by DSR exports.

### 4.5 `auth.magic_links`

| column | type | nullable | default | notes |
|---|---|---|---|---|
| `id` | uuid | NO | `gen_random_uuid()` | PK |
| `user_id` | uuid | NO | — | FK |
| `purpose` | text | NO | — | `email_verify|password_reset|email_change|phone_change` |
| `token_hash` | bytea | NO | — | sha256 of opaque token; UNIQUE |
| `otp_hash` | bytea | YES | — | sha256 of 6-digit code (zero-padded) |
| `target_email` | citext | YES | — | for email_change |
| `target_phone` | text | YES | — | for phone_change |
| `created_at` | timestamptz | NO | `now()` | |
| `exp_at` | timestamptz | NO | — | exp_at <= created_at + 15min |
| `consumed_at` | timestamptz | YES | — | |
| `attempt_count` | smallint | NO | `0` | OTP wrong-entry counter |

Indexes:
- `magic_links_token_uniq` UNIQUE `(token_hash)`.
- `magic_links_user_purpose_idx` `(user_id, purpose) WHERE consumed_at IS NULL`.
- `magic_links_exp_idx` BRIN `(exp_at)` — cleanup sweep.

### 4.6 `identity.identity_verifications`

| column | type | nullable | default | notes |
|---|---|---|---|---|
| `id` | uuid | NO | `gen_random_uuid()` | PK |
| `user_id` | uuid | NO | — | FK users.id (cross-schema) |
| `persona_inquiry_id` | text | NO | — | UNIQUE |
| `status` | text | NO | `'pending'` | `pending|approved|declined|needs_review` |
| `face_age_signal` | smallint | YES | — | estimated age from Persona; <18 forces needs_review |
| `decision_at` | timestamptz | YES | — | |
| `raw_payload` | jsonb | YES | — | full Persona webhook envelope (KMS-encrypted at-rest via column-level pgcrypto) |
| `created_at` | timestamptz | NO | `now()` | |
| `updated_at` | timestamptz | NO | `now()` | |

Indexes:
- `iv_user_idx` `(user_id)`.
- `iv_persona_uniq` UNIQUE `(persona_inquiry_id)`.
- `iv_status_idx` `(status) WHERE status IN ('pending','needs_review')` — partial for the manual-review queue.

RLS: self-select; service role for `profile-svc` reads.

### 4.7 `identity.persona_webhook_events`

| column | type | notes |
|---|---|---|
| `event_id` | text PK | from Persona payload (idempotency key) |
| `inquiry_id` | text | indexed |
| `event_type` | text | `inquiry.completed | inquiry.approved | inquiry.declined | ...` |
| `received_at` | timestamptz default now() | |
| `processed_at` | timestamptz | NULL until handled |
| `raw_payload` | jsonb | |
| `signature_valid` | boolean | for forensic logs |

Index: `(processed_at) WHERE processed_at IS NULL` (work queue).

### 4.8 Ownership boundaries vs §004 profile-svc

- `User` lives in **auth-svc**. `Profile` lives in **profile-svc**. Relationship is 1:1, joined on `user_id`. Neither service holds a FK across schemas at the DB level (microservice boundary); referential integrity is enforced at the application layer.
- `auth-svc` publishes `user.created` containing `{ user_id, email, phone }` → `profile-svc` listens and creates the matching empty `Profile` row.
- Badge issuance lives in `profile-svc.ProfileReview` (§004), driven by `identity.verified` from identity-svc + AI-profile-review outcome. `auth-svc` is **not** the badge owner.
- DSR export for a user joins across `auth.*`, `identity.*`, `profile.*` via the `user_id` key, orchestrated by `admin-svc` (§016).

### 4.9 Redis schema

```
otp:phone:<E.164>           → { code_hash, attempts, exp_at }   TTL 300s
otp:email_verify:<email>    → { code_hash, attempts, exp_at }   TTL 900s
rl:ip:<ip>:<route>          → { tokens, last_refill_ts }        TTL refill-time
rl:user:<user_id>:<route>   → { tokens, last_refill_ts }        TTL refill-time
lock:login:<email>:<ip>     → { fails, locked_until }           TTL 900s
refresh:jti:<jti>           → { session_id, exp }               TTL = refresh-TTL
revoked:session:<sid>       → 1                                  TTL = refresh-TTL
oauth:nonce:<nonce>         → user_id                            TTL 600s
jwks_cache:apple            → JSON                               TTL 6h
```

---

## 5. API Contracts

> Compact block form. Every response shape carries `error_code` + `message` on non-2xx. All endpoints emit Server-Timing headers. All endpoints behind gateway-svc enforce IP rate-limit; per-route bucket cited.

### 5.1 `POST /auth/signup/email`
```
auth: none
rate: auth_signup (5/min/IP)
idempotency: optional via Idempotency-Key (24h replay window)
body:
  email: str (RFC5322; lowercased server-side)
  password: str (min 12; zxcvbn >=3; cannot contain email substring)
  age_attestation: bool (MUST be true; else 400 age_attestation_required)
  accept_tos: bool, accept_privacy: bool, accept_community: bool (all true)
  doc_versions: { tos: str, privacy: str, community: str }
200 { user_id, access_token, refresh_token, access_exp_at, refresh_exp_at }
400 invalid_input | weak_password | age_attestation_required | docs_not_accepted
409 email_already_registered
429 rate_limited
500 server_error
```
Side effects: insert User, insert email Identity, insert 4× LegalAcceptance rows, write Session, publish `user.created`, kick off email verify (magic-link + OTP).

### 5.2 `POST /auth/signup/oauth`
```
auth: none
rate: auth_oauth (30/min/IP)
body:
  provider: "apple" | "google"
  id_token: str   # Apple/Google JWT
  nonce: str      # for apple replay protection (must match stored)
  age_attestation: bool   # MUST be true
  accept_tos/privacy/community: bool
  doc_versions: {...}
200 { user_id, access_token, refresh_token, is_new_user }
400 invalid_token | nonce_mismatch | age_attestation_required
401 token_signature_invalid
409 oauth_account_already_linked_to_other_user
429 rate_limited
```
Behavior: verify token per §2.3 / §2.4; if `(provider, sub)` exists → login; else if `email_verified` matches an existing email → 409 (require explicit "link" via account settings); else create User + Identity.

### 5.3 `POST /auth/signup/phone` + `/verify`
```
POST /auth/signup/phone
rate: auth_otp_send (1/60s/phone)
body: { phone: E.164, age_attestation: bool, accept_*: bool, doc_versions }
200 { otp_sent: true, resend_after_seconds: 60 }
400 invalid_phone | age_attestation_required
429 rate_limited
503 sms_provider_unavailable

POST /auth/signup/phone/verify
rate: auth_login (10/min/IP) + per-phone attempt cap (5)
body: { phone, code }
200 { user_id, access_token, refresh_token, is_new_user }
400 invalid_code | code_expired
429 too_many_attempts
```

### 5.4 `POST /auth/login/email`
```
rate: auth_login (10/min/IP); brute-force lock 10 fails/15min/(email,ip)
body: { email, password }
200 { user_id, access_token, refresh_token, email_verified, identity_verified }
401 invalid_credentials  # uniform for unknown email + bad password
403 account_locked  # body: { unlock_at }
429 rate_limited
```

### 5.5 `POST /auth/login/oauth`
Same shape as 5.2 minus age_attestation/docs (only on signup; ToS bumps separately enforced by middleware: if user has not accepted current doc versions, 200 with `requires_doc_acceptance: true`).

### 5.6 `POST /auth/login/phone/start` + `/verify`
Mirrors 5.3 but on existing user.

### 5.7 `POST /auth/email/verify/start`
```
auth: bearer (access)
rate: auth_otp_send (3/10min/email)
body: {}  # uses caller's email
200 { sent: true }
409 already_verified
429 rate_limited
```

### 5.8 `POST /auth/email/verify/finish`
```
auth: optional bearer; can be called unauth (link from email)
rate: auth_login bucket
body: { token: str (opaque) }  OR  { email, code }
200 { verified: true, user_id }
400 invalid | expired | already_consumed
410 link_expired
```

### 5.9 `POST /auth/password/reset/start`
```
auth: none
rate: auth_password_reset_start (3/10min/email)
body: { email }
200 { sent: true }   # always 200 to avoid email enumeration
```

### 5.10 `POST /auth/password/reset/finish`
```
body: { token, new_password }   # token from email
200 { reset: true }
400 invalid_token | weak_password
410 link_expired
```
Side effect: revoke ALL active sessions; user re-logs in.

### 5.11 `POST /auth/token/refresh`
```
auth: refresh token (bearer)
rate: auth_refresh (60/min/user)
body: {}  # token in Authorization header
200 { access_token, refresh_token, access_exp_at, refresh_exp_at }
401 invalid_refresh | replayed_refresh  # replayed → entire session chain revoked
403 session_revoked
```
Behavior: verify refresh, check JTI in `refresh:jti:<jti>`, delete-and-rotate, re-issue both tokens. If JTI missing AND session is active → **stolen-refresh detection**: revoke session, return 401, publish `auth.session.revoked` with reason `stolen_refresh`.

### 5.12 `POST /auth/logout`
```
auth: bearer (access)
body: {}
204
```
Revokes current session (`session_id` from access claim).

### 5.13 `POST /auth/logout/all`
```
auth: bearer
204
```
Revokes all of the user's sessions.

### 5.14 `GET /auth/sessions`
```
auth: bearer
200 [{ id, user_agent, ip, created_at, last_seen_at, is_current: bool }]
```

### 5.15 `DELETE /auth/sessions/{id}`
```
auth: bearer
204
404 not_found
403 not_owner
```

### 5.16 `POST /auth/account/email/change/start`
```
auth: bearer
body: { new_email, current_password }
200 { sent: true }   # email goes to NEW address
401 invalid_password
409 email_taken
```

### 5.17 `POST /auth/account/email/change/finish`
```
auth: bearer
body: { token }  OR  { code }
200 { email: <new> }
```
Side effects: revoke all sessions except current; notify old email.

### 5.18 `POST /auth/account/phone/change/start` + `/finish`
Mirrors 5.16/5.17 with phone OTP path.

### 5.19 `POST /identity/inquiry/start`
```
auth: bearer (access; user must be email_verified)
rate: 5/min/user
body: {}
200 { persona_inquiry_id, persona_session_token, expires_at }
403 email_not_verified
409 inquiry_already_in_progress  # returns existing inquiry instead (idempotent)
```

### 5.20 `POST /webhooks/persona/inquiry`
```
auth: HMAC via Persona-Signature header
rate: 100rps gateway cap
body: full Persona event envelope
200 { received: true }
401 signature_invalid | timestamp_skew
202 duplicate_event   # idempotent replay
```

### 5.21 `GET /identity/verification`
```
auth: bearer
200 { status, decision_at, face_age_signal: int|null }
```

### 5.22 `GET /.well-known/jwks.json`
```
auth: none
200 { keys: [...] }   # current + previous active keys
cache: public, max-age=300
```

---

## 6. Email Flows

| Email type | Subject | Template | Trigger event | Link / OTP semantics |
|---|---|---|---|---|
| Email verify | "Verify your Colab email" | `email-verify.mjml` | `POST /auth/signup/email` OR `/email/verify/start` | magic-link + 6-digit OTP; 15min exp; single-use |
| Welcome | "Welcome to Colab" | `welcome.mjml` | `user.email_verified` | no link; product CTA |
| Password reset | "Reset your Colab password" | `password-reset.mjml` | `POST /auth/password/reset/start` | magic-link only; 15min exp; single-use; revokes all sessions on finish |
| Email change confirm (new) | "Confirm your new Colab email" | `email-change-confirm.mjml` | `email/change/start` | sent to NEW address; 15min exp; magic-link + OTP |
| Email change notice (old) | "Your Colab email was changed" | `email-change-notice.mjml` | `email/change/finish` | sent to OLD address; no action link; support-revoke link valid 7d |
| New device login | "New sign-in to your Colab account" | `login-alert.mjml` | unrecognized device (fingerprint mismatch) | revoke-session link valid 7d |
| Password changed | "Your Colab password was changed" | `password-changed.mjml` | password/reset/finish OR account/password rotate | revoke-session link valid 7d |
| Account locked | "Your Colab account is temporarily locked" | `account-locked.mjml` | brute-force lockout fired | self-unlock link (1h exp) + support contact |
| Persona declined | "We couldn't verify your identity" | `persona-declined.mjml` | `identity.declined` | retry CTA; no expiring link |
| Magic-link signup (OAuth merge) | "Confirm linking your Google account" | `oauth-link-confirm.mjml` | sign-in with new OAuth provider on existing email | one-time 15min link |

All emails are SES-templated, MJML-compiled. Address-list bounces flow to `email_status`.

---

## 7. OAuth Flow Sequences

### 7.1 Apple Sign-In

```
RN client                          auth-svc                        Apple
   │                                  │                              │
   │  open Apple SDK with nonce       │                              │
   │  (nonce generated client-side    │                              │
   │   and sent to /signup/oauth)     │                              │
   ├──────────────────────────────────┼──── Sign in with Apple ─────▶│
   │                                  │                              │
   │◀──── id_token, authorizationCode ┼──────────────────────────────│
   │                                                                 │
   │  POST /auth/signup/oauth                                        │
   │  { provider:"apple", id_token, nonce, age_attestation, ... }    │
   ├─────────────────────▶│                                          │
   │                      │  decode header.kid                       │
   │                      ├──────── GET /auth/keys ────────────────▶│
   │                      │◀────────── JWKS ────────────────────────│
   │                      │  verify sig, iss, aud, exp, nonce       │
   │                      │  upsert User + Identity(provider=apple) │
   │                      │  insert Session, sign JWT pair          │
   │◀───── 200 tokens ────│                                          │
   │  store tokens, route to onboarding                              │
```

### 7.2 Google Sign-In

```
RN/Web client                      auth-svc                       Google
   │                                  │                              │
   │  open Google SDK                 │                              │
   ├──────────────────────────────────┼─── OAuth (PKCE) ────────────▶│
   │◀───────── id_token ──────────────┼──────────────────────────────│
   │                                                                 │
   │  POST /auth/signup/oauth                                        │
   │  { provider:"google", id_token, age_attestation, ... }          │
   ├─────────────────────▶│                                          │
   │                      │  google.oauth2.id_token.verify_oauth2_token
   │                      │   (handles JWKS fetch, sig, aud, exp)   │
   │                      │  upsert User + Identity(provider=google)│
   │                      │  insert Session, sign JWT pair          │
   │◀───── 200 tokens ────│                                          │
```

### 7.3 Phone SMS-OTP

```
RN client                          auth-svc                        SNS
   │                                  │                              │
   │  POST /auth/signup/phone         │                              │
   │  { phone, age_attestation, ... } │                              │
   ├──────────────────▶│              │                              │
   │                   │ generate 6-digit code                      │
   │                   │ hash → redis otp:phone:<E.164> TTL 5min    │
   │                   ├──────────── publish(SMS) ──────────────▶│
   │                   │                                          │
   │◀── 200 { otp_sent } ─┤                                       │
   │                                                                 │
   │  user reads SMS, types code                                     │
   │                                                                 │
   │  POST /auth/signup/phone/verify { phone, code }                 │
   ├──────────────────▶│                                              │
   │                   │ redis GET otp:phone:<E.164>                  │
   │                   │ constant-time compare hashes                 │
   │                   │ on match: del key, upsert User + Identity    │
   │                   │  (provider=phone), sign JWT pair              │
   │◀── 200 tokens ────│                                               │
```

---

## 8. Security Review (OWASP Top 10)

| OWASP Top 10 (2021) | Mitigation in this service |
|---|---|
| A01 Broken Access Control | RLS policies on all auth.* and identity.* tables, app.user_id session var set by `colab_common.auth.require_user()`. Service-to-service uses dedicated IRSA role + `app.role='service'` policy. Session-revocation Redis bitmap consulted on every gateway request. |
| A02 Cryptographic Failures | Argon2id @ m=64MB/t=3/p=4 per master §0. JWTs RS256 with KMS-stored private key (never on disk). TLS 1.2+ enforced at ALB; HSTS 1y preload at marketing/consumer-web. `persona_webhook_events.raw_payload` is pgcrypto-encrypted at rest. JWKS rotated monthly with two-key window. |
| A03 Injection | SQLAlchemy 2.x parameterized queries; raw SQL banned by lint. Pydantic v2 validation on all inputs; reject any field not in schema. citext for case-insensitive email lookups with built-in normalization. |
| A04 Insecure Design | Threat-modeled per-endpoint (above). Brute-force throttling, replay protection, stolen-refresh detection, session-list UX, password-change → revoke-all are designed-in, not bolted on. Soft-block default keeps service degradation graceful. |
| A05 Security Misconfiguration | Settings via `pydantic-settings` from AWS Secrets Manager (§002). Pods read via IRSA; no creds in env files. CSP at gateway. HSTS, X-Content-Type-Options, Referrer-Policy strict-origin-when-cross-origin set on every response. SES/SNS use IAM least-privilege role bound to namespace. |
| A06 Vulnerable & Outdated Components | Dependabot daily; `pip-audit` in CI gating merges; SBOM generated per build. Argon2-cffi, pyjwt, google-auth pinned with renovate-bot upgrades. |
| A07 Identification & Auth Failures | Per spec — strong password policy, MFA columns reserved, account lockout, session listing, full logout-all, no security questions. OAuth nonce replay protection on Apple. Uniform 401 error message. |
| A08 Software & Data Integrity Failures | Persona webhook HMAC-SHA256 verified. Magic-link tokens are random 32-byte secrets; stored as sha256 hashes; constant-time compare. Refresh JTI rotation. SES templates registered server-side (no template injection from request data). |
| A09 Logging & Monitoring Failures | CloudWatch structured logs include `request_id, user_id, route, ip, ua, latency_ms, status`. Sentry captures auth exceptions. Auth audit log: `auth_audit_events` table for high-signal events (signup, login, password change, session revoke, lockout fire, OAuth link, ToS accept) — append-only, S3 mirror nightly. PostHog tracks funnels (drop-off per signup step). Alarms: lockout rate spike, 5xx rate, refresh-replay events. |
| A10 SSRF | Outbound HTTP only to: Apple JWKS, Google JWKS (via google-auth), Persona API, SES, SNS, KMS, Mapbox (in geo-svc, not here). All hardcoded; not user-supplied URLs. |

Additional non-OWASP controls:
- **Refresh-token rotation on use** with stolen-refresh chain-revoke.
- **JTI tracking** in Redis for refresh tokens.
- **Brute-force lockout**: 10 fails/15min/(email,ip); 30-min lock; email + push notification on trigger.
- **CSRF**: API is bearer-token; no cookies; CSRF is N/A for REST. The one cookie-bearing surface (web sign-out from a stolen tab) is handled by session-revocation rather than CSRF tokens — the web client posts to `/auth/logout` with bearer.
- **Audit logging**: every state-changing endpoint emits an entry to `auth_audit_events` with reversible reasoning fields.
- **Secrets handling**: AWS Secrets Manager via IRSA; secrets never printed to logs; Sentry data scrubbers strip headers `Authorization`, `Cookie`, and body fields `password`, `code`, `token`, `id_token`.
- **Age 18+**: enforced server-side at every signup endpoint (`age_attestation == true` AND, if Persona returns `face_age_signal < 18`, status flips to needs_review).

---

## 9. Persona Integration — Exact Call Sequence

```
1. (client) RN screen "Verify your identity"
2. (client → identity-svc) POST /identity/inquiry/start
3. (identity-svc → Persona)
   POST https://withpersona.com/api/v1/inquiries
     headers:
       Authorization: Bearer ${PERSONA_API_KEY}
       Persona-Version: 2023-01-05
       Idempotency-Key: <user_id>:<short-window>  # 24h window
     body:
       { data: { attributes: { inquiry-template-id: ${PERSONA_TEMPLATE_ID},
                               reference-id: <user_id>,
                               fields: { email: <user.email> } } } }
4. (Persona → identity-svc) 201 { data: { id: "inq_...", attributes: { status: "created" } } }
5. (identity-svc → Persona)
   POST /inquiries/inq_.../resume?session-token=true
   → { meta: { session-token: "..." } }
6. (identity-svc → DB) INSERT identity_verifications (user_id, persona_inquiry_id, status='pending')
7. (identity-svc → client) 200 { persona_inquiry_id, persona_session_token, expires_at }
8. (client) Persona RN SDK opens, runs head-turn + smile + selfie capture
9. (Persona → backend, async) Inquiry processed by Persona's pipeline
10. (Persona → identity-svc) POST /webhooks/persona/inquiry
    headers:
      Persona-Signature: t=<ts>,v1=<hmac>
      Content-Type: application/json
    body: { data: { id: <event_id>, type: "event",
                    attributes: { name: "inquiry.completed",
                                  payload: { data: { id: "inq_...",
                                                     attributes: { status: "approved",
                                                                   fields: {...},
                                                                   ... } } } } } }
11. (identity-svc) verify HMAC; reject if invalid
12. (identity-svc) idempotency check: INSERT INTO persona_webhook_events (event_id, ...) ON CONFLICT DO NOTHING; if rowcount==0 → return 200 (duplicate)
13. (identity-svc) map Persona status:
      approved + face_age_signal>=18 → status=approved
      approved + face_age_signal<18  → status=needs_review (escalate)
      declined                        → status=declined
      else                            → status=needs_review
14. (identity-svc → DB) UPDATE identity_verifications SET status, decision_at, face_age_signal, raw_payload
15. (identity-svc → bus) publish identity.verified | identity.declined | identity.needs_review
                              with { user_id, inquiry_id, status }
16. (identity-svc → Persona) 200 { received: true }
17. (profile-svc, async, §004) consumes identity.verified → ProfileReview kickoff → badge state machine advances
```

Webhook idempotency key: **`event_id` from the Persona payload**, stored in `persona_webhook_events.event_id` UNIQUE.

---

## 10. Implementation Task List

> Ids `AUTH-NN` and `IDV-NN`. Estimates are eng-hours for one developer (no review). Dependencies via `blocked_by`. "Blocks" listed only when downstream tasks block on the upstream output. RN tasks prefixed `RN-NN`.

### 10.1 Data model + migrations

| id | title | outcome | hours | blocks | blocked_by |
|---|---|---|---|---|---|
| AUTH-01 | Alembic migration: create `auth.users` + indexes + RLS policies | DB schema in place | 4 | AUTH-02..05, AUTH-10..18 | 002 colab_common |
| AUTH-02 | Migration: `auth.identities` + indexes + RLS | OAuth linkage table ready | 2 | AUTH-12 | AUTH-01 |
| AUTH-03 | Migration: `auth.sessions` + indexes + RLS | Session store ready | 2 | AUTH-15 | AUTH-01 |
| AUTH-04 | Migration: `auth.legal_acceptances` UNIQUE composite | ToS audit ready | 1 | AUTH-10 | AUTH-01 |
| AUTH-05 | Migration: `auth.magic_links` + cleanup job | Magic-link store ready | 2 | AUTH-13, AUTH-14 | AUTH-01 |
| AUTH-06 | Migration: `auth.auth_audit_events` append-only | Audit surface ready | 1 | AUTH-20 | AUTH-01 |
| IDV-01 | Migration: `identity.identity_verifications` + RLS | Persona state row | 2 | IDV-02..05 | 002 |
| IDV-02 | Migration: `identity.persona_webhook_events` idempotency table | Webhook idempotency | 1 | IDV-04 | IDV-01 |

### 10.2 auth-svc REST endpoints

| id | title | outcome | hours | blocks | blocked_by |
|---|---|---|---|---|---|
| AUTH-10 | `POST /auth/signup/email` end-to-end (incl. argon2id, age check, doc acceptance, event emit, email verify kickoff) | Working email signup | 8 | RN-10 | AUTH-01..06, AUTH-30 |
| AUTH-11 | `POST /auth/login/email` (incl. lockout, audit, email_status check) | Working email login | 6 | RN-11 | AUTH-10 |
| AUTH-12 | `POST /auth/signup/oauth` + `/login/oauth` (Apple + Google) | OAuth signup/login | 10 | RN-12 | AUTH-02, AUTH-40, AUTH-41 |
| AUTH-13 | `POST /auth/signup/phone` + verify (SNS SMS, OTP) | Phone signup/login | 8 | RN-13 | AUTH-05, AUTH-42 |
| AUTH-14 | `POST /auth/email/verify/start` + `/finish` (link + OTP both paths) | Email verification works | 4 | — | AUTH-30 |
| AUTH-15 | `POST /auth/token/refresh` with rotation + stolen-refresh detection | Token refresh | 6 | RN-14 | AUTH-03 |
| AUTH-16 | `POST /auth/logout` + `/logout/all` + `GET/DELETE /auth/sessions` | Session mgmt API | 4 | RN-50, RN-51 | AUTH-03 |
| AUTH-17 | Password reset start + finish (+ revoke-all on finish) | Reset flow | 4 | RN-15 | AUTH-05, AUTH-30 |
| AUTH-18 | Email/phone change endpoints (start + finish, both purposes) | Account mgmt | 6 | RN-52 | AUTH-05 |
| AUTH-19 | Brute-force lockout middleware (Redis token bucket + counter + email send on lock) | Locks fire as designed | 4 | — | AUTH-30, AUTH-43 |
| AUTH-20 | Auth audit log writer (decorator + sink) | Audit events flowing | 3 | AUTH-60 (load test) | AUTH-06 |
| AUTH-21 | `GET /.well-known/jwks.json` endpoint | JWKS served | 2 | gateway verify | AUTH-44 |

### 10.3 identity-svc REST endpoints

| id | title | outcome | hours | blocks | blocked_by |
|---|---|---|---|---|---|
| IDV-10 | `POST /identity/inquiry/start` (Persona create + session-token) | Inquiry creation | 6 | RN-30 | IDV-01, IDV-50 |
| IDV-11 | `POST /webhooks/persona/inquiry` (HMAC verify, idempotency, status mapping, event emit) | Webhook handler live | 8 | profile-svc badge | IDV-02, IDV-50 |
| IDV-12 | `GET /identity/verification` | Status read | 2 | RN-31 | IDV-01 |

### 10.4 Email templates + SES integration

| id | title | outcome | hours |
|---|---|---|---|
| AUTH-30 | MJML templates (10 emails per §6) compiled & registered as SES templates via deploy step | Templates deployable | 8 |
| AUTH-31 | Email sender wrapper (`SendTemplatedEmail` boto3, bounce/complaint SNS subscriber → email_status updater) | Delivery + lifecycle | 4 |

### 10.5 SMS integration

| id | title | outcome | hours |
|---|---|---|---|
| AUTH-42 | SNS SMS sender with sender-ID, opt-out list precheck, monthly cap alarm | SMS sending production-ready | 6 |

### 10.6 Apple / Google verifiers

| id | title | outcome | hours |
|---|---|---|---|
| AUTH-40 | Apple identity-token verifier (JWKS cache, nonce check, claim validation) | Apple verify pluggable | 6 |
| AUTH-41 | Google identity-token verifier (google-auth wrapper, multi-aud handling) | Google verify pluggable | 3 |

### 10.7 JWT + KMS

| id | title | outcome | hours |
|---|---|---|---|
| AUTH-43 | KMS RSA-2048 sign key provisioned + Terraform; rotation alias | Sign key live | 3 |
| AUTH-44 | JWT issuer/verifier module (RS256 via KMS Sign; JWKS publication; rotation-tolerant verify) | JWT ops in code | 6 |

### 10.8 Persona integration

| id | title | outcome | hours |
|---|---|---|---|
| IDV-50 | Persona API client (`httpx`, idempotency keys, retries with backoff) | Persona calls reliable | 5 |
| IDV-51 | Webhook HMAC verifier + replay window check | Inbound verified | 3 |

### 10.9 RN auth flows

| id | title | outcome | hours |
|---|---|---|---|
| RN-10 | Signup screen (email/password + age attest + docs) | Working RN signup | 8 |
| RN-11 | Login screen + forgot password link | Working login | 4 |
| RN-12 | Apple/Google buttons + SDK wiring + nonce gen | OAuth signup/login | 8 |
| RN-13 | Phone signup screen + OTP screen + resend timer | Phone flow | 8 |
| RN-14 | Token storage + auto-refresh + 401 retry interceptor | Tokens survive across launches | 6 |
| RN-15 | Password reset flow (request → email → app open via Universal Link → new password) | Reset flow | 6 |
| RN-30 | Persona kickoff screen + RN SDK launch | Verification flow | 6 |
| RN-31 | Identity status badge component (reads `/identity/verification`) | Status visible | 2 |

### 10.10 Session + account management UI

| id | title | outcome | hours |
|---|---|---|---|
| RN-50 | Sessions list screen (current device marker, last seen, revoke button) | Session mgmt UX | 6 |
| RN-51 | "Log out all devices" entry point | One-tap revoke-all | 2 |
| RN-52 | Account settings: change email, change phone, change password | Account UX | 8 |

### 10.11 Tests

| id | title | outcome | hours |
|---|---|---|---|
| AUTH-60 | Unit tests: argon2 wrapper, JWT issue/verify, magic-link gen/consume, OAuth verifiers (mocked JWKS), SMS sender (moto stubbed) | ≥90% line coverage on libs | 12 |
| AUTH-61 | Integration tests via testcontainers: full signup+login+refresh+revoke flows for all 4 modalities | green CI gate | 12 |
| AUTH-62 | Contract tests: OpenAPI schemas regression-tested against TS client generator | TS client always compiles | 4 |
| AUTH-63 | Security tests: replay refresh, replay magic-link, replay OAuth nonce, brute-force lockout fires, JWT alg-confusion attempt, JWT with old kid | red on regression | 8 |
| AUTH-64 | Load test (Locust): 500 logins/sec sustained, P95 <150ms; refresh 2000/sec, P95 <50ms | NFR-validated | 8 |
| IDV-60 | Persona webhook contract test (replayed fixture payloads) + signature negative tests | Webhook proven | 6 |

**Total estimate**: ~210 eng-hours (~5.5 dev-weeks for one engineer; ~3 calendar weeks at 2 devs in parallel given the data-model fan-out enables parallelism after AUTH-01..06 / IDV-01..02 land).

Critical path: `colab_common` (002) → AUTH-01..06 + IDV-01..02 → AUTH-44/IDV-50 → AUTH-10/IDV-10 → RN screens → AUTH-64 load test.

---

## 11. Test Strategy

### 11.1 Unit

- `argon2_wrapper.hash`, `.verify`, `.needs_rehash` — round-trip, param sanity, deny-list common passwords.
- `jwt_issuer.sign` (mock KMS) → header has `kid`, claims complete, `exp == now + 900`.
- `jwt_verifier.verify` accepts current + previous kid, rejects rotated-out kid, rejects alg `none`, alg `HS256` confusion.
- `magic_link.generate` returns 32-byte token; `.consume` is single-use; constant-time compare verified by timing harness.
- `apple_verifier` rejects: bad sig, wrong aud, expired, missing nonce, replay nonce, alg!=RS256.
- `google_verifier` rejects: wrong aud, future iat, missing email_verified.
- `sms_sender` opt-out short-circuits; sender-ID set per region.
- `persona_client.create_inquiry` retries on 5xx, idempotency key set.

### 11.2 Integration (testcontainers — Postgres + Redis + LocalStack)

- Full signup-email → email verify → login → refresh → logout flow.
- Full signup-oauth (Apple + Google with fixture JWKS) → second login → identity-row uniqueness.
- Full signup-phone → OTP verify → login.
- Persona inquiry start → simulated webhook POST → status flip → event published to RabbitMQ test container.
- Email-change flow: old-email notice, new-email confirm, sessions revoked.
- Password reset flow: all sessions revoked.

### 11.3 Contract

- OpenAPI specs versioned; PR-time check that breaking changes bump version.
- TS client regen on every spec change; consumer-web + RN both compile.
- Persona webhook payload contract pinned via fixtures from Persona docs.

### 11.4 Load (Locust)

- 500 logins/sec for 10 min — P95 latency < 150ms (excluding KMS), pod CPU < 70%.
- 2000 refreshes/sec — P95 < 50ms.
- 50 signup/sec — P95 < 200ms.
- 10 inquiry-start/sec — P95 < 250ms.

### 11.5 Specific adversarial scenarios

| Scenario | Expected behavior |
|---|---|
| Replay an old refresh token after rotation | 401 + entire session chain revoked + audit event |
| Replay a magic-link token | 410 Gone |
| Replay an Apple OAuth nonce | 400 nonce_mismatch |
| Brute force 10 wrong passwords in 15min on same (email, ip) | 11th attempt → 403 account_locked; lockout email sent |
| Submit signup with `age_attestation=false` | 400 age_attestation_required |
| Submit signup without all 3 doc acceptances | 400 docs_not_accepted |
| Persona webhook with bad HMAC | 401 signature_invalid; audit logged |
| Persona webhook delivered twice | 1st: 200 + state update; 2nd: 202 duplicate, no state change |
| JWT signed with `alg=none` | 401 invalid_token |
| JWT with kid that rotated out 14 months ago | 401 invalid_token |
| OAuth identity spoofing: send Apple token with `aud` set to attacker's bundle | 401 (aud check) |
| OAuth token for an email that already has another user's account | 409 oauth_account_already_linked_to_other_user |
| Persona returns `face_age_signal=15` with `status=approved` | service flips to `needs_review`; profile-svc holds badge |
| Submit empty body to webhook | 401 (signature check fails because body is part of HMAC) |

---

## 12. Acceptance Criteria Recap — with verifications

| Criterion | Verification |
|---|---|
| Signup creates user + tokens + email verify | `curl -X POST /auth/signup/email -d '{...}'` returns 200 + tokens; `pytest tests/integration/test_signup_email.py::test_creates_user_and_sends_verify` |
| Magic link AND OTP both work for email verify | `pytest tests/integration/test_email_verify.py::test_link_path`, `::test_otp_path` |
| Apple Sign-In flow end-to-end | `pytest tests/integration/test_oauth_apple.py::test_signup_then_login_uses_same_user` |
| Google Sign-In flow end-to-end | `pytest tests/integration/test_oauth_google.py::test_signup_then_login` |
| Phone OTP flow | `pytest tests/integration/test_phone_otp.py::test_signup_phone_flow` |
| Persona webhook flips status | `pytest tests/integration/test_persona_webhook.py::test_approved_event_publishes` (asserts RabbitMQ message + identity_verifications row) |
| Brute force triggers at 10 fails / 15min | `pytest tests/security/test_bruteforce.py::test_locks_at_10` |
| Under-18 attestation rejected | `curl -X POST /auth/signup/email -d '{"age_attestation": false, ...}'` returns 400 age_attestation_required |
| ToS acceptance stored per doc version | `psql -c "SELECT count(*) FROM auth.legal_acceptances WHERE user_id='...'"` returns 4 (tos, privacy, community, age_attestation) |
| DSR export endpoint (delegated to §016) | mock contract test exercised in admin-svc spec; this plan publishes the events admin-svc needs |
| OpenAPI doc + TS client regen | `make openapi && tsc --noEmit -p clients/typescript` exits 0 |

---

## 13. Open Risks

1. **India SMS DLT registration** — until templates are registered with TRAI through AWS Pinpoint, phone signup in IN must fall back to email. Feature flag in place; commercial pre-launch coordination required (§001 infra).
2. **Persona face-age signal reliability** — Persona's age estimate is probabilistic. Threshold (currently <18 → needs_review) may catch many legitimate users; tune in beta. Worst case: queue overflow → operational risk. Mitigation: track FP rate in dashboard; tune threshold via admin config.
3. **KMS Sign latency** — every JWT issue pays a 6–10ms KMS round-trip. At signup peaks this becomes a tail-latency contributor. Mitigation: pre-warm pods; consider in-process signing key cached from KMS Decrypt of a wrapped private key (security review needed before adopting).
4. **OAuth merge UX** — current decision returns 409 when an OAuth email matches an existing account that wasn't OAuth-linked. That's safe but yields a confusing "you already have an account" wall for users who simply forgot they signed up. Open Q: do we offer in-place "confirm to link" by sending a confirmation email? Decision deferred to UX review post-launch.
5. **Stolen-refresh detection false positives** — if a legitimate client retries an interrupted refresh (e.g., network dropped after server rotated but before response delivered), we'll see a replayed JTI and revoke the chain. Mitigation: add a 5-second grace window where the *previous* JTI is also accepted; tradeoff vs. attack window. Pending decision.
6. **DSR for auth audit log** — audit log retention is "lifetime + 3y pseudonymized" per master §0. Auth-svc emits to a long-retention store; pseudonymization on user deletion must be coordinated with §016 admin-svc — open coordination item.
7. **2FA absence at launch** — explicit master decision; risk accepted. If a high-value-account compromise occurs in beta, fast-follow 2FA work is pre-scoped in §004 v1.1.
8. **JWKS endpoint as DoS target** — public, unauthenticated. Mitigated by CloudFront cache (`max-age=300`) and gateway rate-limit `1000/min/IP`. Worth a quarterly review.
9. **Apple relay email churn** — if a user revokes their Apple ID-app authorization, Apple stops forwarding mail to our relay address. We have no signal to detect this and may continue sending to a dead address. Mitigation: pair with bounce-handling and surface "your Apple-relay email is unreachable" account warning when bounce rate ≥1.
10. **Cross-region clock drift** — leeway=30s is generous but if AWS NTP fleet degrades we'll start rejecting valid tokens. Add SLO + alarm on `jwt_clock_skew_rejection_rate`.

---

*End of plan.md (003 — Auth + Identity Verification).*
