# 014 — Notifications

**Phase**: P13.
**Services**: `notification-svc`.
**Mission**: Multi-channel notification delivery (push, email, in-app banner). Granular per-type / per-channel preferences. First-needed pre-permission UX for push opt-in. Transactional emails always sent (legal/transactional override).

## In scope (master Cross-cutting Notifications FR-N-1..N-4)

- Notification types: new match, new request, request accepted, chat message, file shared, AI mockup ready, collab nudge, collab status change, weekly digest, support reply, marketing.
- Channels: push, email, in-app banner.
- Defaults: all on except marketing + weekly digest.
- First-needed pre-permission card for push (per Apple/Google best practice).
- Email always for receipts + security events (regardless of preference).
- Email vendor: AWS SES; templates in code (MJML → HTML).
- Push: APNs + FCM via AWS SNS Mobile Push. Expo Push during development.
- In-app banner: stored as a `Notification` row + delivered via WS when the user is connected.

## Dependencies

- **Hard**: 002, 003.
- **Soft**: every emitting service (`match.created`, `invite.*`, `chat.message.sent`, `ai.mockup_generated`, `collab.*`, support.*, etc.).

## Owned entities

- `Notification`: id, user_id, type, payload (jsonb), in_app_seen_at (nullable), delivered_push_at, delivered_email_at, created_at.
- `NotificationPreference`: user_id, type, channel, enabled. (Default-fill on user creation.)
- `PushDevice`: user_id, device_id, platform (ios|android), expo_push_token, sns_endpoint_arn, last_seen_at.

## API surface

- `GET /notifications?cursor=...&unread_only=`
- `POST /notifications/{id}/read`
- `GET /notifications/preferences`
- `PATCH /notifications/preferences` body `{type, channel, enabled}` (bulk)
- `POST /devices/push` body `{expo_push_token, platform}`
- `DELETE /devices/push/{device_id}`

### Queue events consumed (just a few examples)
- `match.created` → `new_match` notification
- `invite.sent` → `new_request` to recipient
- `chat.message.sent` → `chat_message` to other party (debounced if user is active)
- `ai.mockup_generated` → `ai_mockup_ready`
- `collab.nudge_due` → `collab_nudge`
- `support.ticket_replied` → `support_reply`

## Acceptance criteria

- New user gets default preferences seeded.
- Push token registered via Expo on first launch; SNS endpoint created server-side.
- Pre-permission card UI appears the first time a notification would be useful (managed in RN via a flag set by `notification-svc` `/devices/push` response).
- Per-type per-channel toggle in app settings; live takes effect.
- Email-fallback: if push channel disabled or undelivered for collab_nudge / new_match → email sent.
- Transactional (receipts, security) emails always send.

## NFRs

- Push fanout P95 <2s from event.
- Email send P95 <5s.

## Open

- Quiet hours per user (default off) — Phase 5 detail (could ship in v1.1).
- Bulk-send rate-limits to avoid SNS throttling — Phase 5 capacity plan.
