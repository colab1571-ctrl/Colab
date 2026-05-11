# 014 — Notifications: Implementation Plan

**Spec**: `014-notifications/spec.md`  
**Master ref**: `000-master/spec.md` §Cross-cutting FR-N-1..N-4, ARC-20  
**Phase**: P13 (after billing-svc P12, before support-svc P14)  
**Service**: `notification-svc` (FastAPI, Python)  
**Date drafted**: 2026-05-11

---

## 1. Mission Recap

`notification-svc` is the single source of truth for all user-facing signals across three channels — push (APNs/FCM via AWS SNS), email (AWS SES + MJML), and in-app banner (WebSocket fanout). It consumes domain events from every upstream service on the RabbitMQ bus, applies per-type / per-channel user preferences, executes delivery, and records state. It also manages device token registration and drives the first-needed pre-permission push-opt-in UX without requiring an OS prompt at signup.

Design principles:
- Granular control: each of the 11 notification types is independently toggleable per channel.
- Defaults are generous (all on) except marketing and weekly digest.
- Transactional and security emails are never suppressible by preference.
- Email fallback activates automatically for "key" types when push cannot be delivered.
- The in-app channel is always active while the user is connected; nothing extra to opt into.

---

## 2. Research Findings

### 2.1 AWS SNS Mobile Push (APNs + FCM)

**Platform Application creation** (one-time infra, done in Terraform):
- APNs: `CreatePlatformApplication` with `PlatformCredential` = APNs private key (.p8) + `PlatformPrincipal` = Key ID + Team ID. Set `ApplePlatformTeamID` and `ApplePlatformBundleID` attributes. Use APNs production endpoint in prod, sandbox in dev.
- FCM v1: `CreatePlatformApplication` with `Platform=GCM`, `PlatformCredential` = service-account JSON or FCM server key. FCM v1 (HTTP/2) is the required path as the legacy FCM API was deprecated in 2024.
- Store ARNs in AWS Secrets Manager (`/colab/prod/sns/apns_platform_arn`, `/colab/prod/sns/fcm_platform_arn`).

**Endpoint creation per device** (runtime, in `notification-svc`):
```
endpoint_arn = sns.create_platform_endpoint(
    PlatformApplicationArn=platform_arn,
    Token=device_token,              # raw APNs device token or FCM registration token
    CustomUserData=str(user_id),
)
```
- Re-call `create_platform_endpoint` if the token changes; SNS returns the same ARN if token matches and is enabled. If `EndpointDisabled` fault: call `set_endpoint_attributes(Enabled=True, Token=new_token)` then retry.
- Store `endpoint_arn` on the `PushDevice` row.

**Sending**:
```
sns.publish(
    TargetArn=endpoint_arn,
    MessageStructure="json",
    Message=json.dumps({
        "APNS":         json.dumps(apns_payload),
        "APNS_SANDBOX": json.dumps(apns_payload),
        "GCM":          json.dumps(fcm_payload),
        "default":      fallback_text,
    }),
)
```

APNs payload shape:
```json
{
  "aps": {
    "alert": { "title": "...", "body": "..." },
    "sound": "default",
    "badge": 1,
    "mutable-content": 1
  },
  "notif_id": "<uuid>",
  "type": "<notification_type>"
}
```

FCM v1 payload shape (inside GCM key):
```json
{
  "message": {
    "notification": { "title": "...", "body": "..." },
    "data": { "notif_id": "<uuid>", "type": "<notification_type>" },
    "android": { "priority": "high" },
    "apns": {}
  }
}
```

**Failure handling**:
- `InvalidParameter` / `EndpointDisabled` → mark `PushDevice.sns_endpoint_arn = NULL`, enqueue email fallback if type is "key".
- SNS publish throttle: Celery task with exponential back-off (max 3 retries, 2s/4s/8s).
- Bounce/complaint via SNS delivery status logging to CloudWatch — `[OPEN RISK: full bounce handler not in this milestone scope]`.

### 2.2 Expo Push Tokens vs Raw APNs/FCM

- **Development / Expo Go**: use `expo-notifications` SDK → `getExpoPushTokenAsync()` → token of the form `ExponentPushToken[xxxxxxxx]`. Send via Expo Push API (`https://exp.host/--/api/v2/push/send`). Simple, no APNs/FCM credentials required. Used only in local dev and EAS build preview.
- **Production (EAS Build, store binary)**: use `getDevicePushTokenAsync()` → raw APNs device token or FCM registration token → send via AWS SNS as above. The RN client detects the build profile and calls the correct path.
- `POST /devices/push` accepts `{ expo_push_token, platform }` in dev mode and `{ device_token, platform }` in prod mode. The service stores whichever is appropriate; in prod it immediately calls `create_platform_endpoint` and stores `sns_endpoint_arn`.

### 2.3 AWS SES — Domain Setup

**Prerequisites** (Terraform + manual DNS):
1. `ses.verify_domain_identity(Domain="mail.colab.app")` → get verification token.
2. Add TXT record `_amazonses.mail.colab.app = <token>`.
3. Enable DKIM: `ses.verify_domain_dkim(Domain="mail.colab.app")` → 3 CNAME records → add to DNS. SES auto-rotates DKIM keys; use Easy DKIM (2048-bit RSA).
4. SPF: add TXT `v=spf1 include:amazonses.com ~all` on the sending domain.
5. DMARC: add TXT `_dmarc.colab.app = "v=DMARC1; p=quarantine; rua=mailto:dmarc-reports@colab.app; pct=100"`. Start with `p=none` for the first 30 days to collect data before quarantine.
6. Bounce/complaint SNS topic: configure SES notification → SNS → Lambda/SQS → `notification-svc` bounce processor (Phase 5 / v1.1).
7. SES in `us-east-1`. Request production access (default sandbox → verified addresses only). Use `ConfigurationSet` with delivery logging to CloudWatch.

Sending from: `noreply@mail.colab.app` (transactional) and `hello@mail.colab.app` (marketing).

### 2.4 MJML for Email Templates

- All email templates authored in MJML (`*.mjml` source files), compiled to HTML at build time via `mjml` CLI (Node.js). Compiled output committed as `*.html`; Python SES client renders via Jinja2 against the compiled HTML.
- Templates stored at `notification-svc/templates/email/`:
  - `base.mjml` — master layout: header logo, body, footer with unsubscribe link.
  - One `<type>.mjml` per notification type that extends base.
  - Marketing and digest templates use `marketing_base.mjml` with list-unsubscribe header.
- Jinja2 context injected at send time: `{{ recipient_name }}`, `{{ action_url }}`, `{{ subject }}`, type-specific payload fields.
- `unsubscribe_url` = signed JWT link → `PATCH /notifications/preferences` (one-click per RFC 8058 List-Unsubscribe-Post).
- All emails include plain-text alternative (auto-generated via `html2text`).

### 2.5 In-App Banner via WebSocket Fanout

- `chat-svc` owns the WebSocket connections (per ARC-8). `notification-svc` does not manage WebSocket connections directly; it publishes `notification.inapp` events to RabbitMQ exchange `notifications`.
- `chat-svc` subscribes to `notifications` exchange, looks up active WebSocket sessions for `user_id`, and pushes the banner payload over the existing WS connection.
- Banner payload schema:
```json
{
  "event": "notification",
  "data": {
    "id": "<uuid>",
    "type": "new_match",
    "title": "You matched with ...",
    "body": "Tap to start collaborating.",
    "action_url": "/collabs/<collab_id>",
    "created_at": "<iso8601>"
  }
}
```
- If user is not connected, the `Notification` row exists in DB with `in_app_seen_at = NULL`; the RN app fetches unseen notifications on reconnect via `GET /notifications?unread_only=true`.
- Presence check for `chat_message` debounce: `notification-svc` checks Redis key `presence:<user_id>` (set by `chat-svc` on WS connect/disconnect) before enqueuing a push/email for `chat_message`. If user is present in the room, suppress push/email for that conversation for the next 60 seconds (debounce window).

---

## 3. Detailed Data Model

### 3.1 `Notification`

```sql
CREATE TABLE notification (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type            notification_type_enum NOT NULL,
    payload         JSONB NOT NULL DEFAULT '{}',
    in_app_seen_at  TIMESTAMPTZ,
    delivered_push_at   TIMESTAMPTZ,
    push_failed_at      TIMESTAMPTZ,
    push_failure_reason TEXT,
    delivered_email_at  TIMESTAMPTZ,
    email_failed_at     TIMESTAMPTZ,
    email_failure_reason TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_notification_user_type ON notification(user_id, type, created_at DESC);
CREATE INDEX idx_notification_unread ON notification(user_id, in_app_seen_at) WHERE in_app_seen_at IS NULL;
```

`payload` JSONB holds all type-specific fields (see §4 catalog). The column is intentionally untyped at the DB level; each notification type has a documented schema enforced in Python via Pydantic.

`notification_type_enum` (Postgres enum):
```sql
CREATE TYPE notification_type_enum AS ENUM (
    'new_match',
    'new_request',
    'request_accepted',
    'chat_message',
    'file_shared',
    'ai_mockup_ready',
    'collab_nudge',
    'collab_status_change',
    'weekly_digest',
    'support_reply',
    'marketing'
);
```

### 3.2 `NotificationPreference`

```sql
CREATE TABLE notification_preference (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type        notification_type_enum NOT NULL,
    channel     notification_channel_enum NOT NULL,  -- 'push' | 'email' | 'in_app'
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, type, channel)
);

CREATE TYPE notification_channel_enum AS ENUM ('push', 'email', 'in_app');
```

**Default seeding** (applied in `auth-svc` user-creation hook via RabbitMQ event `user.created` → `notification-svc`):
- All types, all channels → `enabled = TRUE`, **except**:
  - `marketing`, all channels → `enabled = FALSE`
  - `weekly_digest`, all channels → `enabled = FALSE`

Seed is idempotent (`INSERT ... ON CONFLICT DO NOTHING`).

### 3.3 `PushDevice`

```sql
CREATE TABLE push_device (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_id           TEXT NOT NULL,             -- client-generated stable UUID per install
    platform            TEXT NOT NULL CHECK (platform IN ('ios', 'android')),
    expo_push_token     TEXT,                      -- dev only; NULL in prod
    device_token        TEXT,                      -- raw APNs token or FCM registration token; prod
    sns_endpoint_arn    TEXT,                      -- NULL until endpoint created or if invalidated
    endpoint_enabled    BOOLEAN NOT NULL DEFAULT TRUE,
    app_version         TEXT,
    os_version          TEXT,
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, device_id)
);

CREATE INDEX idx_push_device_user ON push_device(user_id) WHERE endpoint_enabled = TRUE;
```

---

## 4. Notification Type Catalog

For each type: payload schema, push title+body templates, email subject+template, in-app banner copy, default per channel, and deliverable rules.

---

### 4.1 `new_match`

**Trigger**: `match.created` event (both users get a notification).

**Payload schema**:
```json
{
  "match_id": "<uuid>",
  "other_user_id": "<uuid>",
  "other_user_display_name": "<string>",
  "other_user_avatar_url": "<string|null>",
  "collab_id": "<uuid>"
}
```

**Push**:
- Title: `"You matched with {{other_user_display_name}}!"`
- Body: `"Start your collaboration now."`
- Deep-link: `/collabs/{{collab_id}}`

**Email**:
- Subject: `"You have a new match on Colab 🎉"`
- Template: `new_match.mjml` — shows avatar, display name, "Open Chat" CTA button.

**In-app banner**:
- `"You matched with {{other_user_display_name}}! Tap to open your workspace."`

**Defaults**: push=ON, email=ON, in_app=ON.

**Deliverable rules**:
- Email fallback applies: if push channel disabled or `sns_endpoint_arn` NULL → send email.
- Dedup: if two `match.created` events arrive for the same `match_id` within 5 seconds, process only the first (idempotency key = `match_id` in Redis, TTL 30s).

---

### 4.2 `new_request`

**Trigger**: `invite.sent` event → recipient gets notification.

**Payload schema**:
```json
{
  "invite_id": "<uuid>",
  "sender_user_id": "<uuid>",
  "sender_display_name": "<string>",
  "sender_avatar_url": "<string|null>",
  "synopsis": "<string max 250 chars>"
}
```

**Push**:
- Title: `"{{sender_display_name}} sent you a Vibe Check"`
- Body: `"{{synopsis_truncated_100}}"`

**Email**:
- Subject: `"{{sender_display_name}} wants to collaborate with you"`
- Template: `new_request.mjml` — avatar, synopsis, "View Request" CTA.

**In-app banner**:
- `"New Vibe Check from {{sender_display_name}}"`

**Defaults**: push=ON, email=ON, in_app=ON.

**Deliverable rules**:
- No email fallback (push preferred; email still gated on preference).
- If push channel disabled, rely on in-app only (this type is not "key" for email fallback purposes).

---

### 4.3 `request_accepted`

**Trigger**: `invite.accepted` event → original sender gets notification.

**Payload schema**:
```json
{
  "invite_id": "<uuid>",
  "acceptor_user_id": "<uuid>",
  "acceptor_display_name": "<string>",
  "acceptor_avatar_url": "<string|null>",
  "collab_id": "<uuid>"
}
```

**Push**:
- Title: `"{{acceptor_display_name}} accepted your Vibe Check!"`
- Body: `"Your collaboration workspace is ready."`
- Deep-link: `/collabs/{{collab_id}}`

**Email**:
- Subject: `"Your Vibe Check was accepted — time to create!"`
- Template: `request_accepted.mjml`.

**In-app banner**:
- `"{{acceptor_display_name}} accepted your Vibe Check! Open workspace →"`

**Defaults**: push=ON, email=ON, in_app=ON.

**Deliverable rules**:
- Email fallback applies (treated as "key" type).

---

### 4.4 `chat_message`

**Trigger**: `chat.message.sent` event → other party in the collab chat.

**Payload schema**:
```json
{
  "collab_id": "<uuid>",
  "message_id": "<uuid>",
  "sender_user_id": "<uuid>",
  "sender_display_name": "<string>",
  "message_preview": "<string max 100 chars>",
  "message_type": "text|voice|file|link"
}
```

**Push**:
- Title: `"{{sender_display_name}}"`
- Body (text): `"{{message_preview}}"`
- Body (voice): `"Sent a voice note"`
- Body (file): `"Sent a file"`
- Body (link): `"{{message_preview}}"`
- Deep-link: `/collabs/{{collab_id}}/chat`

**Email**: None by default (in-app + push sufficient; email would be noisy for chat).

**In-app banner**:
- `"{{sender_display_name}}: {{message_preview}}"`

**Defaults**: push=ON, email=OFF, in_app=ON.

**Deliverable rules**:
- **Debounce**: check Redis key `presence:<user_id>` + `chat_active:<user_id>:<collab_id>`. If user is actively in the room, suppress push for 60 seconds (sliding window). After window expires without re-send, send one consolidated push.
- **Batching**: if 3+ messages arrive within the debounce window, the eventual push reads `"3 new messages from {{sender_display_name}}"`.
- No email fallback for `chat_message`.
- Frequency cap: maximum 1 push per conversation per minute to the same recipient.

---

### 4.5 `file_shared`

**Trigger**: `chat.file.sent` event (file message in chat) → other party.

**Payload schema**:
```json
{
  "collab_id": "<uuid>",
  "message_id": "<uuid>",
  "sender_user_id": "<uuid>",
  "sender_display_name": "<string>",
  "file_name": "<string>",
  "file_type": "image|audio|video|document",
  "file_size_bytes": 1234567
}
```

**Push**:
- Title: `"{{sender_display_name}} shared a file"`
- Body: `"{{file_name}} ({{file_type}})"`
- Deep-link: `/collabs/{{collab_id}}/chat`

**Email**: None by default.

**In-app banner**:
- `"{{sender_display_name}} shared {{file_name}}"`

**Defaults**: push=ON, email=OFF, in_app=ON.

**Deliverable rules**:
- Same presence debounce as `chat_message` (60s window).
- If chat-message and file-shared occur within 10s of each other in the same conversation, collapse into a single push.

---

### 4.6 `ai_mockup_ready`

**Trigger**: `ai.mockup_generated` event (Replicate webhook processed by `ai-orchestrator-svc`). Both collab parties receive.

**Payload schema**:
```json
{
  "collab_id": "<uuid>",
  "mockup_id": "<uuid>",
  "mockup_type": "image|audio",
  "preview_url": "<string|null>",
  "consent_set_id": "<uuid>",
  "expires_at": "<iso8601>"
}
```

**Push**:
- Title: `"Your AI Collab Preview is ready!"`
- Body: `"Tap to view before it expires {{expires_relative}}."`
- Deep-link: `/collabs/{{collab_id}}/mockup/{{mockup_id}}`

**Email**:
- Subject: `"Your AI Collab Preview is ready — expires {{expires_date}}"`
- Template: `ai_mockup_ready.mjml` — shows mockup type, expiry countdown, "View Now" CTA.

**In-app banner**:
- `"AI Collab Preview ready! View before {{expires_relative}}."`

**Defaults**: push=ON, email=ON, in_app=ON.

**Deliverable rules**:
- Email fallback applies (key type — time-sensitive).
- Push and email both send regardless of debounce (urgency override).

---

### 4.7 `collab_nudge`

**Trigger**: `collab.nudge_due` event from `collab-svc` Celery Beat job (14 days of collab inactivity per FR-C-13).

**Payload schema**:
```json
{
  "collab_id": "<uuid>",
  "other_user_display_name": "<string>",
  "inactive_days": 14,
  "auto_archive_at": "<iso8601>"
}
```

**Push**:
- Title: `"Your collab with {{other_user_display_name}} is going quiet"`
- Body: `"No activity in {{inactive_days}} days. Say something before it archives."`
- Deep-link: `/collabs/{{collab_id}}`

**Email**:
- Subject: `"Your collaboration with {{other_user_display_name}} needs attention"`
- Template: `collab_nudge.mjml` — shows collab context, "Reopen Workspace" CTA.

**In-app banner**:
- `"{{other_user_display_name}} collab is inactive — {{days_until_archive}} days until auto-archive."`

**Defaults**: push=ON, email=ON, in_app=ON.

**Deliverable rules**:
- Email fallback applies (key type).
- Send at most once per collab per nudge cycle (idempotency key = `collab_id + nudge_cycle_date`, TTL 48h in Redis).

---

### 4.8 `collab_status_change`

**Trigger**: `collab.status_updated` event when status transitions to `in_progress`, `completed`, or `didnt_work_out`.

**Payload schema**:
```json
{
  "collab_id": "<uuid>",
  "other_user_display_name": "<string>",
  "new_status": "in_progress|completed|didnt_work_out",
  "changed_by_user_id": "<uuid>"
}
```

**Push**:
- `in_progress`: `"{{other_user_display_name}} marked your collab as In Progress 🚀"`
- `completed`: `"Collab with {{other_user_display_name}} marked Completed. Share your feedback!"`
- `didnt_work_out`: `"Collab with {{other_user_display_name}} has ended."`

**Email**:
- `completed`: Subject `"Congrats! Your collaboration is complete — leave feedback"`. Template `collab_completed.mjml`.
- `didnt_work_out`: No email by default (opt-in in future).
- `in_progress`: No email.

**In-app banner**:
- Mirrors push body.

**Defaults**: push=ON, email=ON (completed only), in_app=ON.

**Deliverable rules**:
- `completed` status → email always sent if email channel enabled (not a transactional override, but high-value).
- Notify only the other party (not the user who made the status change).

---

### 4.9 `weekly_digest`

**Trigger**: Celery Beat schedule every Monday 09:00 user-local timezone (approximated to user's city timezone from `profile.location`; fallback UTC).

**Payload schema**:
```json
{
  "period_start": "<iso8601 date>",
  "period_end": "<iso8601 date>",
  "new_matches": 2,
  "messages_exchanged": 47,
  "active_collabs": 1,
  "profile_views": 12
}
```

**Push**: None (digest is email-native).

**Email**:
- Subject: `"Your Colab week in review — {{period_start_formatted}}"`
- Template: `weekly_digest.mjml` — stats block, "View your workspace" CTA.

**In-app banner**: None.

**Defaults**: push=OFF, email=OFF, in_app=OFF (user must opt in).

**Deliverable rules**:
- Skip users with 0 activity in the period (no matches, no messages, no collabs).
- Respect email preference explicitly — this is marketing-adjacent and defaults off.

---

### 4.10 `support_reply`

**Trigger**: `support.ticket_replied` event from `support-svc` (agent or AI reply on a ticket).

**Payload schema**:
```json
{
  "ticket_id": "<uuid>",
  "ticket_subject": "<string>",
  "reply_preview": "<string max 150 chars>",
  "replied_by": "agent|ai"
}
```

**Push**:
- Title: `"Update on your support request"`
- Body: `"{{reply_preview}}"`
- Deep-link: `/support/tickets/{{ticket_id}}`

**Email**:
- Subject: `"Re: {{ticket_subject}}"`
- Template: `support_reply.mjml` — reply text, "View Ticket" CTA.

**In-app banner**:
- `"Support replied: {{reply_preview}}"`

**Defaults**: push=ON, email=ON, in_app=ON.

**Deliverable rules**:
- Email always sent for support replies (treated as transactional for UX purposes, but still user-preference-gated because it's not a receipt/security event).
- Frequency: one push per ticket reply; no debounce.

---

### 4.11 `marketing`

**Trigger**: Admin broadcast via `admin-svc` → RabbitMQ `marketing.broadcast` event.

**Payload schema**:
```json
{
  "campaign_id": "<uuid>",
  "title": "<string>",
  "body": "<string>",
  "action_url": "<string|null>",
  "segment": "all|premium|free"
}
```

**Push**:
- Title: from `payload.title`
- Body: from `payload.body`

**Email**:
- Subject: from `payload.title`
- Template: `marketing.mjml` — full campaign layout with unsubscribe footer.
- From: `hello@mail.colab.app`
- Must include `List-Unsubscribe` and `List-Unsubscribe-Post` headers (RFC 8058).

**In-app banner**: None (marketing push only).

**Defaults**: push=OFF, email=OFF, in_app=OFF.

**Deliverable rules**:
- Only delivered to users who explicitly enabled the `marketing` preference on each channel.
- Never email-fallback (marketing should never be forced).
- Throttle: max 1 marketing push per user per 24h regardless of campaign count.

---

## 5. First-Needed Pre-Permission Card Pattern

### Rationale

Asking for push permission at signup has poor conversion (Apple guidelines also discourage it). Instead, permission is requested the first time a push notification would actually be useful to the user.

### Server-Side Logic (`POST /devices/push` response)

When the RN app calls `POST /devices/push` on first launch (before any OS permission is granted, sending `{ expo_push_token: null, platform: "ios"|"android" }`):

```python
def handle_push_registration(user_id, expo_push_token, device_id, platform):
    device = get_or_create_push_device(user_id, device_id, platform)
    
    has_token = bool(device.sns_endpoint_arn or device.expo_push_token)
    has_queued = notification_queued_for_user(user_id)  # check Notification table
    
    should_prompt = not has_token and has_queued
    
    if expo_push_token:
        # Token provided = user already granted permission; register with SNS
        register_with_sns(device, expo_push_token)
        should_prompt = False
    
    return {
        "device_id": str(device.id),
        "should_prompt_push": should_prompt,
        "queued_count": count_undelivered_push(user_id) if should_prompt else 0,
    }
```

`notification_queued_for_user` returns `True` if there exists a `Notification` row for the user with `delivered_push_at IS NULL AND push_failed_at IS NULL AND type NOT IN ('marketing', 'weekly_digest')`.

### RN Client Flow

```
App launch
  → POST /devices/push { platform, device_id, expo_push_token: null }
  ← { should_prompt_push: true, queued_count: 2 }

  → Show PrePermissionCard:
      "You have 2 new notifications — enable push to receive them instantly"
      [Yes, turn on notifications]  [Not now]

  On "Yes":
      → await Notifications.requestPermissionsAsync()
      → On grant: getDevicePushTokenAsync() → POST /devices/push { device_token, platform }
      → Server: creates SNS endpoint, marks device as active, delivers queued notifications
  
  On "Not now":
      → Store dismissal in AsyncStorage; do not show again for 7 days
      → Re-evaluate on next meaningful notification event
```

### Edge Cases

- If user taps "Not now" 3 times across 3 separate 7-day windows, suppress the card permanently (store in `push_device.prompt_dismissed_count`; threshold 3).
- If user later manually enables notifications in OS settings: next app launch `POST /devices/push` will include a token, bypassing the card.
- Android: OS push permission prompt introduced in Android 13 (API 33+). Pre-permission card still shown; the Android OS dialog is the actual OS prompt.

---

## 6. Email Fallback Rule

### "Key" Notification Types

The following types trigger email fallback if push cannot be delivered:

| Type | Key? |
|---|---|
| `new_match` | Yes |
| `new_request` | No |
| `request_accepted` | Yes |
| `chat_message` | No |
| `file_shared` | No |
| `ai_mockup_ready` | Yes |
| `collab_nudge` | Yes |
| `collab_status_change` (completed) | Yes |
| `weekly_digest` | No |
| `support_reply` | No |
| `marketing` | No |

### Fallback Logic

```python
def should_email_fallback(user_id: UUID, notif_type: str) -> bool:
    if notif_type not in KEY_NOTIFICATION_TYPES:
        return False
    
    # Check if email channel is enabled for this type
    pref = get_preference(user_id, notif_type, channel="email")
    if not pref.enabled:
        return False
    
    # Check if push would have been sent but can't be delivered
    push_pref = get_preference(user_id, notif_type, channel="push")
    has_active_device = has_enabled_push_device(user_id)
    
    push_unreachable = not push_pref.enabled or not has_active_device
    return push_unreachable
```

Fallback email is sent immediately when the push dispatch decision is made (no delay). The `Notification` row records both `delivered_push_at = NULL` (push not attempted) and `delivered_email_at` when the fallback fires.

---

## 7. Transactional Email Override

The following email types are **always sent regardless of `NotificationPreference`**:

| Event | Sent By | Override Category |
|---|---|---|
| Payment receipt (subscription, credit purchase) | `billing-svc` directly via SES | Transactional |
| Subscription cancellation confirmation | `billing-svc` | Transactional |
| Dunning emails (Day 0/3/7 payment retry) | `billing-svc` | Transactional |
| Refund confirmation | `billing-svc` | Transactional |
| Account security: password changed | `auth-svc` | Security |
| Account security: new device login | `auth-svc` | Security |
| Account security: account deactivated/banned | `moderation-svc` | Security/Legal |
| Email address verification | `auth-svc` | Transactional |
| DSR confirmation (access/erasure request received) | `auth-svc`/`admin-svc` | Legal |
| DMCA takedown notice acknowledgment | `moderation-svc` | Legal |

These emails are sent directly by the originating service using the shared `SESClient` library (not routed through `notification-svc` consumer pipeline). They do not create `Notification` rows (except for support/moderation events which have their own audit tables). They do not check `NotificationPreference`.

Implementation: shared Python library `colab_ses_client` with `send_transactional_email(to, template_id, context)` that bypasses all preference checks.

---

## 8. Queue Consumer Mapping

All events consumed from Amazon MQ (RabbitMQ) via AMQP. Exchange: `colab.events` (topic). `notification-svc` binds routing keys listed below to its queue `notification-svc.inbound`.

| Routing Key | Source Service | Notification Type(s) Created | Notes |
|---|---|---|---|
| `match.created` | `matching-svc` | `new_match` (×2 users) | Dedup on `match_id` |
| `invite.sent` | `invite-svc` | `new_request` (recipient) | |
| `invite.accepted` | `invite-svc` | `request_accepted` (sender) | |
| `chat.message.sent` | `chat-svc` | `chat_message` | Debounce + presence check |
| `chat.file.sent` | `chat-svc` | `file_shared` | Same debounce |
| `ai.mockup_generated` | `ai-orchestrator-svc` | `ai_mockup_ready` (×2 users) | Urgency override |
| `collab.nudge_due` | `collab-svc` | `collab_nudge` (×2 users) | Idempotency key |
| `collab.status_updated` | `collab-svc` | `collab_status_change` | Notify other party only |
| `support.ticket_replied` | `support-svc` | `support_reply` | |
| `marketing.broadcast` | `admin-svc` | `marketing` | Fan out to segment |
| `user.created` | `auth-svc` | — | Seed `NotificationPreference` |
| `schedule.weekly_digest` | Celery Beat internal | `weekly_digest` | Monday 09:00 local |

**Weekly digest**: not an AMQP event. Celery Beat in `notification-svc` triggers the digest job directly.

**Consumer implementation**: each routing key maps to a Celery task. The task is idempotent (uses `notification_id` or event-specific idempotency key stored in Redis with TTL). Celery worker concurrency = 4 per pod; auto-scaled via KEDA based on queue depth.

---

## 9. API Contracts

All endpoints are under `notification-svc`, registered in `gateway` as `/notifications/*` and `/devices/*`. Auth via JWT (Bearer token). All responses in JSON.

### 9.1 `GET /notifications`

List notifications for the authenticated user.

**Query params**:
- `cursor` (string, optional): opaque pagination cursor (base64-encoded `{created_at, id}`).
- `unread_only` (boolean, optional, default `false`): filter to `in_app_seen_at IS NULL`.
- `limit` (integer, optional, default 20, max 50).

**Response 200**:
```json
{
  "items": [
    {
      "id": "uuid",
      "type": "new_match",
      "payload": { ... },
      "in_app_seen_at": null,
      "delivered_push_at": "2026-05-11T10:00:00Z",
      "delivered_email_at": null,
      "created_at": "2026-05-11T10:00:00Z"
    }
  ],
  "next_cursor": "base64...",
  "has_more": true
}
```

**Errors**: 401 Unauthorized.

---

### 9.2 `POST /notifications/{id}/read`

Mark a single notification as seen in-app (sets `in_app_seen_at = NOW()`).

**Path param**: `id` (UUID).

**Response 200**:
```json
{ "id": "uuid", "in_app_seen_at": "2026-05-11T10:01:00Z" }
```

**Errors**: 401, 404 (not found or not owned by user).

---

### 9.3 `POST /notifications/read-all`

Mark all in-app unseen notifications as read for the authenticated user.

**Response 200**:
```json
{ "updated_count": 7 }
```

---

### 9.4 `GET /notifications/preferences`

Get all preferences for the authenticated user (72 rows max: 11 types × 3 channels + partial if not fully seeded).

**Response 200**:
```json
{
  "preferences": [
    {
      "type": "new_match",
      "channel": "push",
      "enabled": true,
      "updated_at": "2026-05-11T09:00:00Z"
    },
    ...
  ]
}
```

---

### 9.5 `PATCH /notifications/preferences`

Update one or more preferences.

**Request body**:
```json
{
  "updates": [
    { "type": "marketing", "channel": "push", "enabled": true },
    { "type": "chat_message", "channel": "email", "enabled": false }
  ]
}
```

**Validation**:
- `type` must be a valid `notification_type_enum`.
- `channel` must be `push | email | in_app`.
- Bulk limit: max 33 updates per request.

**Response 200**:
```json
{
  "updated": [
    { "type": "marketing", "channel": "push", "enabled": true, "updated_at": "..." }
  ]
}
```

**Errors**: 400 (invalid type/channel), 401.

---

### 9.6 `POST /devices/push`

Register or update a push device for the authenticated user.

**Request body**:
```json
{
  "device_id": "stable-client-uuid",
  "platform": "ios",
  "expo_push_token": "ExponentPushToken[...]",
  "device_token": null,
  "app_version": "1.0.0",
  "os_version": "18.0"
}
```

One of `expo_push_token` or `device_token` may be present; both may be null (pre-permission call).

**Response 200**:
```json
{
  "device_id": "stable-client-uuid",
  "registered": true,
  "should_prompt_push": false,
  "queued_count": 0
}
```

`should_prompt_push: true` when: no active SNS endpoint exists for the user AND there is at least one undelivered non-marketing notification queued.

**Errors**: 400 (invalid platform), 401.

---

### 9.7 `DELETE /devices/push/{device_id}`

Deregister a push device (e.g., on logout or app uninstall signal). Deletes the `PushDevice` row and calls `sns.delete_endpoint(endpoint_arn)`.

**Path param**: `device_id` (client-generated stable UUID).

**Response 204**: No content.

**Errors**: 401, 404.

---

### 9.8 `POST /notifications/unsubscribe` (one-click email unsubscribe)

Handles RFC 8058 `List-Unsubscribe-Post` one-click unsubscribe. Called by email clients automatically.

**Request body** (form-encoded per RFC 8058):
```
List-Unsubscribe=One-Click
```

**Query param**: `token` (signed JWT, 30-day TTL, encodes `user_id + type + channel=email`).

**Action**: Sets `enabled = false` for `(user_id, type, channel=email)` in `NotificationPreference`.

**Response 200**: Plain text `"Unsubscribed"`.

---

## 10. Implementation Tasks

Tasks are ordered by dependency. `est_hours` = engineering estimate excluding review.

| ID | Title | Outcome | Est Hours | Blocks | Blocked By |
|---|---|---|---|---|---|
| T-N-01 | Terraform: SNS platform applications (APNs + FCM) | `colab-apns-prod`, `colab-fcm-prod` platform apps in SNS; ARNs in Secrets Manager | 4 | T-N-07 | Infra bootstrap (P0) |
| T-N-02 | Terraform: SES domain identity + DKIM + SPF + DMARC | Verified `mail.colab.app`; DNS records applied; DKIM enabled; DMARC in `p=none` for 30 days | 4 | T-N-09 | Infra bootstrap (P0) |
| T-N-03 | Terraform: SES configuration set + CloudWatch delivery logging | Delivery metrics available | 2 | T-N-09 | T-N-02 |
| T-N-04 | DB schema migration: `notification_type_enum`, `notification_channel_enum`, `Notification`, `NotificationPreference`, `PushDevice` tables | Schema applied in `notification-svc` Postgres schema | 3 | T-N-05, T-N-06, T-N-07 | — |
| T-N-05 | Seed `NotificationPreference` on `user.created` event | Consumer for `user.created`; inserts 33 rows per new user with correct defaults | 3 | T-N-12 | T-N-04 |
| T-N-06 | `GET /notifications` + `POST /notifications/{id}/read` + `POST /notifications/read-all` | Paginated list with cursor; read marking; 401/404 handling | 5 | T-N-17 | T-N-04 |
| T-N-07 | `POST /devices/push` + `DELETE /devices/push/{device_id}` | Device registration; SNS endpoint creation; `should_prompt_push` logic; deregister on logout | 8 | T-N-16 | T-N-01, T-N-04 |
| T-N-08 | `GET /notifications/preferences` + `PATCH /notifications/preferences` | Read + bulk-update preferences; validation; `updated_at` tracking | 4 | T-N-12 | T-N-04 |
| T-N-09 | Shared `colab_ses_client` library: `send_transactional_email` + `send_notification_email` | Python package used by all services for SES; template rendering via Jinja2; no preference check in transactional path | 6 | T-N-10, T-N-18 | T-N-02, T-N-03 |
| T-N-10 | MJML base template + all 9 notification email templates (excluding weekly_digest + marketing) | `base.mjml`, `new_match.mjml`, `request_accepted.mjml`, `ai_mockup_ready.mjml`, `collab_nudge.mjml`, `collab_completed.mjml`, `support_reply.mjml` compiled and Jinja2-parameterized | 12 | T-N-18 | T-N-09 |
| T-N-11 | MJML `weekly_digest.mjml` + `marketing.mjml` templates | Digest and marketing email templates; List-Unsubscribe headers | 5 | T-N-18, T-N-21 | T-N-09 |
| T-N-12 | Core notification dispatch engine: preference check → channel routing → SNS publish / SES send / WS fanout event publish | The heart of `notification-svc`; reads preferences, applies channel logic, dispatches; records delivery state on `Notification` row | 16 | T-N-13..T-N-21 | T-N-04, T-N-07, T-N-08, T-N-09 |
| T-N-13 | RabbitMQ consumer: `match.created` → `new_match` (×2) | Consumes event; creates 2 `Notification` rows; dispatches; dedup on Redis | 4 | — | T-N-12 |
| T-N-14 | RabbitMQ consumers: `invite.sent` → `new_request`, `invite.accepted` → `request_accepted` | Two consumers; correct recipient routing | 4 | — | T-N-12 |
| T-N-15 | RabbitMQ consumer: `chat.message.sent` → `chat_message`, `chat.file.sent` → `file_shared` | Presence check via Redis; 60s debounce; message batching; frequency cap | 8 | — | T-N-12 |
| T-N-16 | `should_prompt_push` flag: server logic + RN pre-permission card UI | Server returns flag; RN shows card on `should_prompt_push: true`; OS prompt on "Yes"; dismissal tracking | 8 | — | T-N-07 |
| T-N-17 | In-app banner: WebSocket fanout via `chat-svc` RabbitMQ event | `notification-svc` publishes to `notifications` exchange; `chat-svc` consumes and pushes over WS; RN renders banner overlay | 8 | — | T-N-06, T-N-12 |
| T-N-18 | Email dispatch integration: preference check + email fallback rule | `send_notification_email` wrapper checks preferences; fallback logic per §6; records `delivered_email_at` | 6 | — | T-N-09, T-N-10, T-N-12 |
| T-N-19 | RabbitMQ consumers: `ai.mockup_generated` → `ai_mockup_ready`, `collab.nudge_due` → `collab_nudge`, `collab.status_updated` → `collab_status_change` | Three consumers; urgency override for mockup; idempotency for nudge | 6 | — | T-N-12 |
| T-N-20 | RabbitMQ consumer: `support.ticket_replied` → `support_reply` | Simple consumer; push + email both sent | 3 | — | T-N-12 |
| T-N-21 | Celery Beat weekly digest job + `marketing.broadcast` consumer | Monday cron; activity filter (skip 0-activity users); fan-out with per-user throttle | 8 | — | T-N-11, T-N-12 |
| T-N-22 | `POST /notifications/unsubscribe` one-click handler (RFC 8058) | JWT-signed unsubscribe link; updates preference; plain-text 200 response | 3 | — | T-N-08, T-N-09 |
| T-N-23 | SNS endpoint failure recovery: `EndpointDisabled` handler | On SNS publish failure: mark `endpoint_enabled = false`, enqueue email fallback if key type | 4 | — | T-N-12 |
| T-N-24 | OpenAPI spec + TypeScript client codegen for `notification-svc` | All 8 endpoints documented; codegen run; typed RN client available | 3 | — | T-N-06, T-N-07, T-N-08 |
| T-N-25 | Observability: CloudWatch metrics dashboard (push delivery rate, email delivery rate, queue depth, consumer lag) | Dashboard live in us-east-1; P95 latency alarms set | 4 | — | T-N-12 |
| T-N-26 | Integration tests: end-to-end notification flow (event → dispatch → delivery assertion) | Test suite covering all 11 notification types; preference filtering; fallback rule; transactional override | 12 | — | T-N-13..T-N-21 |

**Total estimate**: ~146 engineer-hours (~3.5 engineer-weeks at 40h/wk, excluding review and QA).

---

## 11. Acceptance Criteria

### AC-N-01: Default Preference Seeding
- **Given** a new user is created via `auth-svc`
- **When** `user.created` event is consumed by `notification-svc`
- **Then** 33 `NotificationPreference` rows exist for the user (11 types × 3 channels), with `enabled = false` for `marketing` and `weekly_digest` on all channels, and `enabled = true` for all others.
- **Verification**: Integration test creates user → asserts DB row count and default values.

### AC-N-02: Push Token Registration — Dev (Expo)
- **Given** RN app in dev build calls `POST /devices/push` with valid `expo_push_token` and `platform=ios`
- **When** request is processed
- **Then** `PushDevice` row created with `expo_push_token` set, `sns_endpoint_arn = NULL` (dev mode)
- **Verification**: API test + DB assertion.

### AC-N-03: Push Token Registration — Prod (SNS)
- **Given** RN app in prod build calls `POST /devices/push` with valid APNs `device_token` and `platform=ios`
- **When** request is processed
- **Then** `PushDevice.sns_endpoint_arn` is populated; `sns.create_platform_endpoint` was called with the correct `PlatformApplicationArn`
- **Verification**: Integration test with SNS mock (moto); assert endpoint ARN stored.

### AC-N-04: Pre-Permission Card Trigger
- **Given** user has no `PushDevice` with an active token AND has at least one undelivered non-marketing `Notification` row
- **When** RN app calls `POST /devices/push` with no token (pre-permission call)
- **Then** response contains `should_prompt_push: true` and `queued_count >= 1`
- **Verification**: API test with seeded notification row and no device token.

### AC-N-05: Pre-Permission Card — No Trigger When No Queue
- **Given** user has no `PushDevice` AND no queued notifications
- **When** RN app calls `POST /devices/push` with no token
- **Then** response contains `should_prompt_push: false`
- **Verification**: API test with clean user state.

### AC-N-06: Per-Type Per-Channel Toggle
- **Given** user has `chat_message / email / enabled = true`
- **When** user calls `PATCH /notifications/preferences` with `{ type: "chat_message", channel: "email", enabled: false }`
- **Then** no email is sent for subsequent `chat.message.sent` events for that user
- **Verification**: Integration test; publish `chat.message.sent`; assert no SES call.

### AC-N-07: Push Delivery — `new_match`
- **Given** user has active SNS endpoint and `new_match / push / enabled = true`
- **When** `match.created` event is published
- **Then** `sns.publish` is called within 2 seconds (P95); `Notification.delivered_push_at` is set
- **Verification**: Integration test with moto SNS mock; latency measured in 100-run loop.

### AC-N-08: Email Fallback — `new_match` (Push Unreachable)
- **Given** user has `new_match / push / enabled = false` AND `new_match / email / enabled = true`
- **When** `match.created` event is published
- **Then** no SNS publish; SES `send_email` called within 5 seconds; `Notification.delivered_email_at` set
- **Verification**: Integration test with moto SES mock.

### AC-N-09: Email Fallback — `new_match` (No Device)
- **Given** user has no `PushDevice` row AND `new_match / email / enabled = true`
- **When** `match.created` event is published
- **Then** SES `send_email` called; `delivered_email_at` set
- **Verification**: Integration test.

### AC-N-10: Transactional Email Override
- **Given** user has all email preferences disabled
- **When** `billing-svc` calls `send_transactional_email(user_id, "payment_receipt", context)`
- **Then** SES `send_email` is called regardless of preferences
- **Verification**: Unit test on `colab_ses_client`; assert SES call without preference DB query.

### AC-N-11: `chat_message` Debounce — User Present
- **Given** Redis key `presence:<user_id>` exists AND `chat_active:<user_id>:<collab_id>` exists
- **When** `chat.message.sent` event arrives
- **Then** no immediate push is dispatched; after 60-second debounce window (simulated), one consolidated push is sent
- **Verification**: Integration test with Redis mock; assert delayed single push.

### AC-N-12: `chat_message` Debounce — User Absent
- **Given** Redis key `presence:<user_id>` does NOT exist
- **When** `chat.message.sent` event arrives
- **Then** push is dispatched immediately (within P95 2s)
- **Verification**: Integration test.

### AC-N-13: In-App Banner Delivery (User Connected)
- **Given** user is connected via WebSocket (Redis presence key set)
- **When** any non-marketing notification is created
- **Then** `notification.inapp` event is published to RabbitMQ `notifications` exchange; `chat-svc` fan-out test client receives the banner payload within 1 second
- **Verification**: E2E test with test WebSocket client.

### AC-N-14: In-App Notification Fetch (User Reconnects)
- **Given** user had 3 unseen notifications while offline
- **When** user reconnects and calls `GET /notifications?unread_only=true`
- **Then** all 3 appear with `in_app_seen_at = null`; `has_more` correctly reflects pagination state
- **Verification**: API test.

### AC-N-15: `weekly_digest` Defaults Off
- **Given** a fresh user
- **When** `NotificationPreference` is seeded
- **Then** `weekly_digest` / `push`, `email`, `in_app` all have `enabled = false`
- **Verification**: DB assertion in AC-N-01 test.

### AC-N-16: Weekly Digest — Skip Zero-Activity Users
- **Given** user with 0 matches, 0 messages, 0 active collabs in the digest period, AND `weekly_digest / email / enabled = true`
- **When** Celery Beat weekly digest job runs
- **Then** no SES call for that user
- **Verification**: Unit test on digest job logic.

### AC-N-17: Marketing — Opt-In Only
- **Given** user has `marketing / push / enabled = false` (default)
- **When** `marketing.broadcast` event is published targeting segment "all"
- **Then** no push dispatched to that user
- **Verification**: Integration test; assert zero SNS calls.

### AC-N-18: SNS Endpoint Failure Recovery
- **Given** SNS `publish` call returns `EndpointDisabled` fault
- **When** push dispatch runs for a key notification type
- **Then** `PushDevice.endpoint_enabled = false`; email fallback fires if applicable; `Notification.push_failed_at` set with reason
- **Verification**: Integration test with moto SNS mock returning fault.

### AC-N-19: One-Click Unsubscribe
- **Given** valid signed unsubscribe JWT for `(user_id, new_match, email)`
- **When** `POST /notifications/unsubscribe?token=<jwt>` called with `List-Unsubscribe=One-Click` body
- **Then** `NotificationPreference(user_id, new_match, email).enabled = false`; response 200 plain text "Unsubscribed"
- **Verification**: API test.

### AC-N-20: Device Deregistration
- **Given** active `PushDevice` row with `sns_endpoint_arn`
- **When** `DELETE /devices/push/{device_id}` is called
- **Then** `PushDevice` row deleted; `sns.delete_endpoint` called with correct ARN; response 204
- **Verification**: Integration test.

---

## 12. Open Risks

### RISK-N-01: Quiet Hours (Out of Scope)
- **Description**: Users in different timezones may receive push notifications at 3 AM. Quiet hours (per-user configurable do-not-disturb windows) are not implemented in this milestone.
- **Impact**: User experience degradation; potential push opt-out increase.
- **Mitigation (deferred)**: v1.1 will add `QuietHoursPreference(user_id, start_time, end_time, timezone)` and a pre-dispatch check that queues pushes and fires at `start_time + 1m` after the quiet window.
- **Workaround (v1)**: APNs `apns-push-type: alert` with no sound for `chat_message` between 22:00–07:00 UTC; basic time-based sound suppression only.

### RISK-N-02: SNS Bounce and Complaint Handling
- **Description**: SNS/SES will accumulate invalid endpoints and email bounces over time. Without a bounce handler, delivery rates degrade and SES sending reputation may be jeopardized.
- **Impact**: Escalating bounce rate → SES account pause (AWS auto-pauses above 10% bounce rate); wasted SNS publish calls to dead endpoints.
- **Mitigation (deferred)**: v1.1 will add: (a) SES bounce/complaint SNS topic → Lambda → `notification-svc` worker that marks emails as bounced and disables email channel for that user; (b) CloudWatch alarm on SES bounce rate > 2%.
- **Workaround (v1)**: SNS `EndpointDisabled` handling (T-N-23) covers the SNS side. SES bounce monitoring via CloudWatch dashboard (T-N-25) with manual response.

### RISK-N-03: FCM v1 Migration Complexity
- **Description**: FCM legacy API was sunset June 2024. FCM v1 requires OAuth 2.0 service account credentials rather than a server key. AWS SNS FCM v1 support (via `GCM` platform application) uses the service account JSON. The exact SNS attribute mapping for FCM v1 service accounts should be validated against current AWS docs before T-N-01.
- **Impact**: Android push delivery blocked if SNS platform application is misconfigured.
- **Mitigation**: Spike T-N-01 with a test Android device in sandbox before production rollout. Fall back to Expo Push for Android in dev while investigating.

### RISK-N-04: RabbitMQ Event Schema Drift
- **Description**: `notification-svc` consumers are tightly coupled to event schemas published by upstream services (`match.created`, `invite.sent`, etc.). If upstream services change their event payload without coordinating with `notification-svc`, consumers will fail silently or raise exceptions.
- **Impact**: Silent notification gaps during deployments.
- **Mitigation**: Define event schemas as shared Pydantic models in `colab-shared-schemas` library. All services import and version schemas. Breaking changes require minor version bump and dual-emit during migration period. Consumer validation logs a `WARNING` with the raw event on schema mismatch (does not crash).

### RISK-N-05: In-App Banner Delivery Dependency on `chat-svc`
- **Description**: In-app banners depend on `chat-svc` consuming from the `notifications` RabbitMQ exchange and forwarding over WebSocket. If `chat-svc` is down, in-app banners are silently dropped (not queued for retry).
- **Impact**: In-app notification delivery unavailable during `chat-svc` outages.
- **Mitigation**: The `GET /notifications?unread_only=true` fetch on reconnect guarantees users see missed notifications once `chat-svc` recovers. Push and email channels are unaffected. No retry needed for in-app banners specifically — the DB row is the source of truth.

### RISK-N-06: DMARC `p=none` → `p=quarantine` Cutover Timing
- **Description**: Starting with DMARC in `p=none` is correct for the initial 30 days, but if the cutover to `p=quarantine` is delayed, emails may land in spam for recipients with strict DMARC policies.
- **Impact**: Email deliverability degradation.
- **Mitigation**: Calendar reminder at day 30 to review DMARC aggregate reports (`rua` inbox) and escalate to `p=quarantine`. PostHog email open-rate tracking will surface deliverability drops.
