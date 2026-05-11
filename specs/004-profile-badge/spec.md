# 004 — Profile + AI Review + Valid Badge

**Phase**: P2 + P3.
**Services**: `profile-svc`.
**Mission**: Profile CRUD (display name, location, vocations, portfolio, externals, optional personality quiz), AI profile review (text + image), Valid Profile Badge state machine.

## In scope (master Journey A FR-A-4 through FR-A-8, FR-A-10, FR-A-11, FR-A-13)

- Profile setup wizard data: display name, location (lat/long + city), radius (50mi/80km default per locale), vocations (9 categories + curated sub-tags), bio (280ch), "obsessed with" (140ch), open-to-remote toggle.
- Portfolio: up to 12 items; image 10MB, audio 30MB, video 100MB. Upload via signed S3 URLs from `media-svc` (§007).
- Optional fields: notable past experience, "what I'm looking for".
- Optional personality quiz (5–7 questions). Result: `personality_archetype` enum.
- External OAuth links: Instagram Business/Creator, YouTube (Google), Spotify for Artists. Tokens encrypted at rest (AWS KMS).
- AI profile review pipeline (text + image): OpenAI moderation, AWS Rekognition image moderation, pHash dup, embedding dup. On flag: soft warning + mod queue (§008). Profile completes; badge withheld.
- Valid Profile Badge state machine:
  - States: `unverified → email_verified → identity_pending → identity_approved → ai_review_pending → badge_granted` (or `→ badge_held` on AI flag).
  - Issuance event: `profile.badge_granted`.
- Onboarding telemetry: PostHog events at every step. Drop-off measured.

## Dependencies

- **Hard**: 002 Shared Platform; 003 Auth+Identity (consumes `user.created`, `identity.verified`).
- **Soft**: 007 Chat+Workspace (media upload uses media-svc); 008 Moderation (AI review hands flags into mod queue); 016 Admin (mod console reviews held badges).

## Owned entities

- `Profile`: id, user_id (FK), display_name (citext, unique-case-insensitive), bio (text 280), obsessed_with (text 140), location_point (postgis), location_city, radius_value, radius_unit (mi|km), open_to_remote (bool), experience_level (1–5), personality_archetype (nullable enum), profile_health_score (float, computed), badge_state (enum), badge_granted_at (nullable), is_visible_to_non_premium (bool, default true), created_at, updated_at, last_active_at.
- `ProfileVocation`: profile_id, category, subtag.
- `ProfileSkill`: profile_id, label (free-text + normalization queue).
- `PortfolioItem`: id, profile_id, position, type (image|video|audio|link), s3_key, mime, size_bytes, caption (200ch), metadata (jsonb), created_at, ai_review_status, ai_review_score, ai_review_payload (jsonb).
- `ExternalLink`: profile_id, provider (instagram|youtube|spotify), provider_handle, provider_id, encrypted_access_token, encrypted_refresh_token, scopes, linked_at, last_synced_at.
- `PersonalityAnswer`: profile_id, question_key, answer_key.
- `ProfileReview`: id, profile_id, kind (text|image|video|audio), score, reasons (jsonb), status (passed|flagged|escalated), created_at.

## API surface

- `GET/POST/PATCH /profile/me` — own profile
- `GET /profile/{handle}` — public profile (subject to visibility rules + block list)
- `POST /profile/me/portfolio` (multipart→signed S3) ; `DELETE /profile/me/portfolio/{id}` ; reorder
- `POST /profile/me/externals/{provider}/connect` (OAuth start) ; `/callback` ; `DELETE /profile/me/externals/{provider}`
- `POST /profile/me/personality` — submit quiz answers
- `POST /profile/me/badge/recheck` — request AI re-review (rate-limited)
- `GET /profile/me/badge` — current state + held reasons
- `GET /profile/{id}/embedding` (internal) — used by matching-svc

### Queue events

- `profile.created`, `profile.updated`, `profile.health_recomputed`, `profile.badge_granted`, `profile.badge_held`, `profile.portfolio_added`, `profile.portfolio_flagged` (to §008).

## Acceptance criteria

- Profile setup wizard completes in <8 minutes (onboarding telemetry baseline).
- Bio + obsessed-with text length enforced server-side.
- Portfolio upload caps enforced server-side; rejected uploads return 413.
- City autocomplete works via geo-svc (Mapbox proxy).
- IG/YouTube/Spotify OAuth round-trip persists encrypted tokens.
- AI profile review runs async; on pass, badge progresses to `badge_granted`; on flag, status flips to `badge_held` + mod queue entry created.
- `user.created` → empty profile shell auto-created (idempotent).
- `identity.verified` → badge_state advances to `ai_review_pending` and review fires.
- Profile health score recomputed nightly + on update; weights configurable.

## NFRs

- Profile read P95 <100ms (cached).
- Profile update P95 <200ms.
- AI review pipeline P95 e2e <60s (asynchronous).

## Open

- Exact pHash + audio-fingerprint thresholds for duplicate detection — Phase 5 detailing.
- Personality quiz question set + scoring — Phase 5 content task.
- Vocation taxonomy (9 categories + sub-tags) full list — Phase 5 content task (already promised in spec).
