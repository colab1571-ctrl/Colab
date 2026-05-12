# STRIDE Threat Model — Colab Platform

**Version**: 1.0  
**Date**: 2026-05-11  
**Owner**: Engineering Lead  
**Gate**: Zero HIGH or CRITICAL open findings before launch sign-off

Services are assessed in priority order (highest data sensitivity / attack surface first).

---

## Legend

| Rating | Definition |
|--------|-----------|
| CRITICAL | Immediate data loss, account takeover, or financial fraud |
| HIGH | Significant exploit with realistic attack path |
| MEDIUM | Exploitable under specific conditions; compensating controls exist |
| LOW | Theoretical; unlikely in practice |

---

## 1. auth-svc

**Role**: Credential handling, session tokens, Apple/Google/phone OTP OAuth flows, JWT issuance.

| STRIDE | Threat | Rating | Mitigation |
|--------|--------|--------|------------|
| Spoofing | Forged JWT used to impersonate user | CRITICAL | RS256 asymmetric JWT; public key published via JWKS endpoint; gateway verifies on every request |
| Spoofing | Phone OTP brute-force | HIGH | 6-digit OTP; 3 attempt limit per OTP; 5-min expiry; rate limit on `/auth/verify-phone` (10 req/min per IP) |
| Spoofing | OAuth `state` parameter CSRF | HIGH | Random 32-byte state per flow; verified on callback; PKCE enforced for public clients |
| Tampering | JWT `sub` or `role` claim modified | CRITICAL | Asymmetric signature; gateway rejects invalid signature |
| Tampering | Password reset link reused | HIGH | HMAC token; single-use; 1-hour expiry; used tokens stored in Redis blacklist |
| Repudiation | No audit log of login events | MEDIUM | All login, logout, token-refresh, failed-attempt events written to `audit_log` table with actor IP |
| Information Disclosure | Error message reveals user existence on login | MEDIUM | Generic error "Invalid credentials" for both bad email and bad password |
| Information Disclosure | Token leaked in URL query params | HIGH | Tokens only in `Authorization` header or `HttpOnly` cookie; never in URL |
| Denial of Service | Account lockout abuse (attacker locks victim) | MEDIUM | Lockout triggers after 10 failed attempts from same IP + user combo; email alert to victim |
| Denial of Service | OTP flood from disposable phone numbers | MEDIUM | Twilio Lookup verify phone number type before SMS send; block VoIP numbers optionally |
| Elevation of Privilege | Refresh token used after logout | HIGH | Refresh tokens stored server-side in Redis; invalidated on logout + on password change |
| Elevation of Privilege | Guest token escalated to authenticated | HIGH | Token `type` claim enforced; guest tokens rejected on all protected endpoints |

**Open issues to track**: None at spec time. First pen-test pass expected to surface token replay scenarios.

---

## 2. billing-svc

**Role**: RevenueCat + Stripe webhook ingestion, entitlement management, credit wallet, dunning.

| STRIDE | Threat | Rating | Mitigation |
|--------|--------|--------|------------|
| Spoofing | Fake RevenueCat webhook bypasses HMAC | CRITICAL | HMAC-SHA256 verification (`X-RevenueCat-Signature`); constant-time comparison; test tampered payload returns 401 |
| Spoofing | Fake Stripe webhook bypasses signature | CRITICAL | `stripe.webhooks.construct_event()` with Stripe-Signature header; event timestamp checked ≤5 min old |
| Tampering | Idempotency key collision (attacker forces credit award) | HIGH | Idempotency key = vendor-provided event ID; stored in `webhook_event_log`; duplicate check before processing |
| Tampering | Direct credit wallet top-up via API | CRITICAL | `CreditWallet` mutations only via internal Celery worker; no public endpoint for balance mutation |
| Repudiation | No record of webhook processing | HIGH | Every webhook event stored to `webhook_event_log` (idempotency key, timestamp, status, raw payload hash) |
| Information Disclosure | Full card data in logs | CRITICAL | Stripe webhooks never contain raw card data; log filtering strips `payment_method_details` |
| Information Disclosure | User subscription tier leaked to non-owner | HIGH | Entitlement queries scoped by `user_id` from JWT; no cross-user reads possible via API |
| Denial of Service | Webhook storm exhausts DB connections | HIGH | Webhook intake is async: HMAC verify → enqueue to RabbitMQ → return 200; no DB write in webhook path |
| Denial of Service | Celery worker queue unbounded | MEDIUM | Queue depth alarm at 5,000 messages; HPA scales workers automatically |
| Elevation of Privilege | Free user invokes Premium-gated endpoint | HIGH | `EntitlementSnapshot` verified per request via `billing-svc` gRPC call or Redis cache; 403 on mismatch |

---

## 3. moderation-svc

**Role**: Risk-tier routing, content scanning (OpenAI Moderation API, image hash), moderator actions.

| STRIDE | Threat | Rating | Mitigation |
|--------|--------|--------|------------|
| Spoofing | Attacker impersonates moderator to approve own content | CRITICAL | Moderator role in JWT; self-moderation blocked in service logic (moderator cannot action own content) |
| Spoofing | Fake `moderation.action_taken` event injected into RabbitMQ | HIGH | RabbitMQ connections are internal-only (VPC); not exposed to internet |
| Tampering | Moderator action log edited after write | HIGH | `ModerationAuditLog` is append-only; update/delete disabled at DB level (row-level trigger) |
| Tampering | CSAM image hash bypass via minor modification | CRITICAL | PhotoDNA + perceptual hash; multiple hash algorithms (pHash + dHash + aHash) combined |
| Repudiation | Moderator denies action taken | HIGH | Every moderation decision stored with moderator JWT `sub`, timestamp, reason; irreversible |
| Information Disclosure | Moderation queue leaks flagged content to wrong moderator | MEDIUM | Queue items scoped to moderator assignment; no cross-assignment reads |
| Information Disclosure | OpenAI moderation API receives PII | MEDIUM | Content is pseudonymized before API call; no user IDs sent to OpenAI |
| Denial of Service | Flood of AI-generated content exhausts moderation queue | MEDIUM | AI-generated content rate-limited by credit quota; moderation queue HPA |
| Elevation of Privilege | Regular user accesses `/moderation/admin/*` routes | HIGH | Admin routes require `role=moderator` or `role=admin` in JWT; gateway enforces |

---

## 4. chat-svc

**Role**: WebSocket message delivery, room access control, presence.

| STRIDE | Threat | Rating | Mitigation |
|--------|--------|--------|------------|
| Spoofing | Unauthenticated WebSocket connection | CRITICAL | JWT required in WS handshake query param or `Authorization` header; connection rejected without valid JWT |
| Spoofing | User sends messages as another user | CRITICAL | Message `sender_id` set server-side from JWT `sub`; client-supplied sender is ignored |
| Tampering | Message content modified in transit | HIGH | TLS in transit; messages stored with hash in DB; no E2E encryption claim (documented in data safety form) |
| Tampering | Room access via guessed `room_id` | HIGH | Room IDs are UUIDs (v4); access check: user must be participant of the room |
| Repudiation | User denies sending a message | MEDIUM | All messages persisted with `sender_id` + timestamp + IP hash; audit trail for legal holds |
| Information Disclosure | Chat messages readable by non-participant | CRITICAL | Room participant check on every WebSocket connection and REST API call |
| Information Disclosure | Presence status leaked to non-participant | MEDIUM | Presence updates broadcast only to room participants |
| Denial of Service | 10k concurrent WS connections overwhelm API Gateway | HIGH | AWS API Gateway WS: 10k concurrent connection limit per region; EKS HPA on chat-svc |
| Denial of Service | Message flood from single user | MEDIUM | 10 messages/second per connection rate limit; exponential backoff on violation |
| Elevation of Privilege | Blocked user re-enters room after block | HIGH | Block check on WS connection + on message send; room membership re-validated on reconnect |

---

## 5. media-svc

**Role**: File upload (portfolio, chat attachments, AI mockups), pre-signed S3 URLs, virus scanning.

| STRIDE | Threat | Rating | Mitigation |
|--------|--------|--------|------------|
| Spoofing | Upload to another user's S3 prefix | HIGH | Pre-signed URL scoped to `user_id` prefix; S3 bucket policy enforces key prefix match |
| Tampering | MIME type spoofing (e.g., executable disguised as image) | HIGH | Server-side MIME detection via `python-magic`; rejects mismatch between declared and detected type |
| Tampering | Archive bomb (zip bomb) | HIGH | Max file size 50MB hard limit; decompression not performed server-side |
| Tampering | Polyglot file (valid image + embedded payload) | HIGH | ClamAV scan post-upload before file is made accessible; image re-encoding via Pillow strips metadata |
| Tampering | SSRF via image processing library | HIGH | Pillow processes files in isolated subprocess with network disabled; no URL fetch from image content |
| Repudiation | Upload attribution disputed | MEDIUM | Upload event logged with `user_id`, timestamp, SHA-256 hash of file |
| Information Disclosure | Pre-signed URL shared beyond intended recipient | MEDIUM | Pre-signed URLs expire in 1 hour; CloudFront signed cookies for long-lived access |
| Information Disclosure | S3 bucket public read misconfiguration | CRITICAL | S3 bucket ACL = private; public access block enabled; Terraform enforces; Trivy checks Dockerfile/IaC |
| Denial of Service | Upload flood exhausts S3 PUT rate limits | MEDIUM | Per-user upload rate limit: 10 uploads/min; daily storage quota enforced per subscription tier |
| Elevation of Privilege | Free user uploads video (Pro feature) | MEDIUM | Media type + duration checked against `EntitlementSnapshot`; 403 on violation |

---

## 6. profile-svc

**Role**: Profile display data, badge state machine, portfolio, vocation/external links.

| STRIDE | Threat | Rating | Mitigation |
|--------|--------|--------|------------|
| Spoofing | Claim another user's username | HIGH | Username uniqueness enforced at DB (unique constraint); no transfer mechanism |
| Tampering | Bypass badge state machine (claim verified without Persona) | CRITICAL | Badge state written by `identity-svc` only; `profile-svc` validates source via internal service token |
| Tampering | IDOR on profile update (update another user's profile) | HIGH | All PATCH/PUT endpoints verify `profile.user_id == jwt.sub` |
| Repudiation | Profile data deletion disputed | MEDIUM | DSR (data subject request) deletion logged with timestamp + request_id |
| Information Disclosure | Private profile fields returned to unauthenticated caller | MEDIUM | Public profile endpoint strips `email`, `phone`, internal metadata; schema-level projection |
| Information Disclosure | Location (city) returned when user disables discovery | MEDIUM | `discovery_hidden` flag suppresses location in API response |
| Denial of Service | Profile search with expensive regexes | LOW | Profile search uses pg_trgm index; timeout 1s query limit |
| Elevation of Privilege | Profile-svc bypassed to write badge directly to DB | CRITICAL | Badge column has row-level security; only `identity_svc_role` Postgres role can update |

---

## 7. ai-orchestrator-svc

**Role**: AI command intake, Replicate/OpenAI fan-out, credit deduction, mockup consent.

| STRIDE | Threat | Rating | Mitigation |
|--------|--------|--------|------------|
| Spoofing | Prompt injection via chat context | HIGH | System prompt pinned; user-supplied context passed as data, not instruction; OpenAI `user` role enforced |
| Spoofing | Replicate webhook forged | HIGH | Replicate webhook HMAC verified; replay protection via timestamp check (≤5 min) |
| Tampering | Credit quota bypass (send AI command without credits) | CRITICAL | Credit check + reserve before job queued; debit on completion; refund on failure — all in single Celery transaction |
| Tampering | Mockup generation without consent | HIGH | Consent flag required in request; stored in `MockupConsent` record; generation blocked without record |
| Repudiation | AI interaction log not stored | MEDIUM | `AIInteraction` entity stores command, prompt hash, model, cost, output hash per FR-C-6 |
| Information Disclosure | Prompt contains PII leaked to OpenAI | HIGH | Prompt sanitization strips email, phone patterns before API call; documented in privacy policy |
| Information Disclosure | Other user's AI job result returned | HIGH | Job scoped by `user_id`; poll endpoint verifies ownership before returning result |
| Denial of Service | Celery queue flood via rapid AI command sends | HIGH | Per-user rate limit: 10 AI commands/min; credit quota is natural DoS mitigation |
| Denial of Service | Runaway Replicate job costs | HIGH | Replicate timeout 120s; max cost per job enforced in Replicate API call params |
| Elevation of Privilege | Free user invokes `/mockup-image` (Pro-only) | HIGH | Command gated by `premium_pro` entitlement check before job queued |

---

## Gateway (Cross-Cutting)

| STRIDE | Threat | Rating | Mitigation |
|--------|--------|--------|------------|
| Spoofing | JWT from foreign issuer accepted | CRITICAL | Gateway validates `iss` claim = `https://auth.colab.test`; rejects all other issuers |
| Denial of Service | API abuse / scraping | HIGH | Rate limiting: 1,000 req/min per authenticated user; 100 req/min per IP unauthenticated |
| Information Disclosure | Internal service paths exposed | MEDIUM | Gateway is sole ingress; internal service hostnames unreachable from internet (VPC-only) |
| Elevation of Privilege | CORS wildcard origin | HIGH | CORS restricted to `*.colab.test` + app origins; no wildcard |

---

## Remaining Services (Lower Priority — Summary)

| Service | Top Risk | Mitigation |
|---------|----------|-----------|
| identity-svc | Persona webhook forgery | HMAC + replay protection |
| discovery-svc | IDOR on saved/hidden profiles | User-scoped queries |
| matching-svc | Score manipulation via profile bombing | Rate limit on score recalculation |
| invite-svc | Block bypass | Reciprocal block enforced at invite + chat layer |
| collab-svc | Unauthorized workspace access | Collaboration membership check on all reads |
| notification-svc | Push notification spoofing | Notification payload signed; no user-injectable fields |
| analytics-svc | Event injection | Events accepted from internal services only |
| admin-svc | Admin console open to internet | Admin routes restricted to VPN CIDR (Tailscale) |
| support-svc | Ticket IDOR | Ticket scoped by user_id or moderator role |
| meeting-svc | Recall.ai webhook forgery | HMAC verification |
| geo-svc | Precise location leak | City-level only; PostGIS ST_SnapToGrid(0.1 degree) |

---

## Action Items

All HIGH/CRITICAL items above must be verified as implemented before security sign-off (T-033). Open findings tracked as GitHub issues with label `security:stride`.

**Next step**: Pen-test vendor receives this document as pre-engagement briefing (T-016).
