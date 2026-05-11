# 003 — Auth + Identity Verification

**Phase**: P2.
**Services**: `auth-svc`, `identity-svc`.
**Mission**: Signup, login, session management, OAuth (Apple, Google), phone SMS-OTP, email verification, Persona-driven selfie/liveness, and the Valid Profile Badge state machine.

## In scope (master §3 Journey A FR-A-1 through FR-A-3, FR-A-9; cross-cutting auth)

- **FR-A-1** Email + password signup. Magic link + 6-digit OTP fallback.
- **FR-A-2** Apple Sign-In, Google Sign-In, Phone SMS-OTP at signup.
- **FR-A-3** Age 18+ attestation; signup blocked under 18.
- **FR-A-9** Persona selfie + liveness (built-in workflow). Soft block — only the badge is gated.
- **FR-A-12** ToS + Privacy + Community Guidelines + age attestation acceptance (logged, time-stamped, IP-stamped).
- Account-level: password reset, email change, phone change, password rotation, session list + revoke, "log out all devices".
- JWT issuance (access 15min, refresh 30d). Token rotation on refresh.
- Brute-force protection: Redis-backed login attempt counter, exponential backoff, IP + email locks.
- Persona webhook handler: `inquiry.completed` → update IdentityVerification → emit `identity.verified` event.

## Dependencies

- **Hard**: 002 Shared Platform.
- **Soft**: 004 Profile Service (Badge issuance reads from auth + identity decisions).

## Owned entities

- `User`: id, email (unique, lowercase), email_verified_at, phone (E.164, unique nullable), phone_verified_at, password_hash (argon2id), is_active, is_locked, locked_until, created_at, updated_at, last_login_at, last_active_at.
- `Identity` (OAuth federations): user_id, provider (apple|google|email|phone), provider_subject, linked_at.
- `Session`: id, user_id, refresh_token_hash, user_agent, ip, last_seen_at, revoked_at.
- `LegalAcceptance`: user_id, doc_type (tos|privacy|community_guidelines), doc_version, accepted_at, ip.
- `IdentityVerification`: user_id, persona_inquiry_id, status (pending|approved|declined|needs_review), face_age_signal, decision_at, raw_payload (jsonb).
- `LoginAttempt` (Redis-backed; not Postgres): per-IP + per-email rolling counter.

## API surface (REST per service)

`auth-svc`:
- `POST /auth/signup/email` body `{email, password, age_attestation: true, accept_tos: true, accept_privacy: true, accept_community: true}` → `{user_id, access_token, refresh_token}` (email NOT yet verified; clients still get tokens but the badge stays pending — see §004)
- `POST /auth/signup/oauth` body `{provider, id_token}` → same response
- `POST /auth/signup/phone` body `{phone}` → `{otp_sent: true}` ; `POST /auth/signup/phone/verify` body `{phone, code}` → tokens
- `POST /auth/login/email`, `/login/oauth`, `/login/phone/start`, `/login/phone/verify`
- `POST /auth/email/verify/start`, `/email/verify/finish` (link + OTP supported)
- `POST /auth/password/reset/start`, `/password/reset/finish`
- `POST /auth/token/refresh`
- `POST /auth/logout`, `/logout/all`
- `GET /auth/sessions`, `DELETE /auth/sessions/{id}`
- `POST /auth/account/email/change/start`, `/email/change/finish`
- `POST /auth/account/phone/change/start`, `/phone/change/finish`

`identity-svc`:
- `POST /identity/inquiry/start` → `{persona_inquiry_id, persona_session_token}` (RN opens Persona SDK)
- `POST /webhooks/persona/inquiry` (signed) — internal
- `GET /identity/verification` → current state for the calling user

### Queue events emitted

- `user.created`
- `user.email_verified`
- `user.phone_verified`
- `identity.verified` (Persona approved)
- `identity.declined`
- `identity.needs_review` (handed to moderator queue via §008)
- `auth.session.revoked`

## Acceptance criteria

- Signup → user record + access/refresh + email verification request issued.
- Magic link + OTP both work for email verification.
- Apple Sign-In → user record with `Identity(provider=apple)` + JWT issued.
- Google Sign-In ↑.
- Phone OTP → SNS SMS sent → 6-digit verify → tokens issued.
- Persona inquiry start → SDK opens → completion → webhook → IdentityVerification.status flips → `identity.verified` event published → §004 picks up and grants the Valid Profile Badge.
- Brute-force lockout triggers at 10 failed attempts/15min per (email + IP).
- 18+ attestation enforced; under-18 signup attempts return 400.
- ToS/Privacy/Community Guidelines acceptance stored per user, per doc version, per time.
- DSR export endpoint returns user's auth-related records on demand (delegated to §016 admin-svc).
- All endpoints documented in OpenAPI; TS client regenerates.

## NFRs

- Login P95 <150ms (excluding 3rd-party call).
- Token refresh P95 <50ms.
- 99.95% availability target for auth-svc (higher than the platform's 99.9% baseline because everything else depends on it).
- Argon2id: m=64MB, t=3, p=4.
- All tokens signed with RS256 from a rotating KMS key.

## Open

- 2FA / TOTP — not in launch scope, but data model is forward-compatible (add `mfa_enabled`, `mfa_secret` to User in v1.1).
- Passkey support — deferred.
