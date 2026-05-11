# 011 — Meetings + Recall.ai Bot — Implementation Plan

**Spec**: `011-meetings/spec.md`
**Phase**: P10 (after P8 collab-lifecycle, P6 chat-svc are stable)
**Service**: `meeting-svc` (FastAPI, owns its own Postgres schema)
**Last updated**: 2026-05-11

---

## 1. Mission Recap

Colab is an AI-powered networking and collaboration platform for artists and creators (18+, US/CA/AU/NZ/IN at launch). The collaboration workspace (Journey C, FR-C-6) must allow two matched participants to schedule a Google Meet video call directly from within their shared collab room, and optionally invite a Recall.ai bot to attend, record, and transcribe the session. The transcript is stored to the audit log and surfaced as a collapsible system message in the chat thread. Recording and transcription require explicit mutual consent from both participants before the bot is dispatched. Google Meet is the only video provider at v1 launch; Zoom and Microsoft Teams are deferred.

---

## 2. Research

### 2.1 Google Calendar API v3 — `events.insert` with `conferenceData`

**Endpoint**: `POST https://www.googleapis.com/calendar/v3/calendars/{calendarId}/events?conferenceDataVersion=1`

Key request body fields:
```json
{
  "summary": "Colab — {userA} × {userB}",
  "start": { "dateTime": "2026-06-01T15:00:00Z", "timeZone": "UTC" },
  "end":   { "dateTime": "2026-06-01T16:00:00Z", "timeZone": "UTC" },
  "attendees": [
    { "email": "userA@example.com" },
    { "email": "userB@example.com" }
  ],
  "conferenceData": {
    "createRequest": {
      "requestId": "<idempotency-uuid>",
      "conferenceSolutionKey": { "type": "hangoutsMeet" }
    }
  }
}
```

The API responds synchronously with a populated `conferenceData.entryPoints[].uri` — this is the Google Meet join URL. The `requestId` must be a stable, idempotent UUID stored in `Meeting.gcal_request_id` so that retries do not create duplicate calendar events.

**Quota**: Google Calendar API has a default quota of 1,000,000 requests/day and 10 requests/second per user. For a service account acting on a shared calendar this is ample at v1 scale.

**ICS**: The Calendar API returns the event in full; we derive an `.ics` attachment by serializing the `Event` object using the `icalendar` Python library and returning a signed S3 URL alongside `join_url` in the API response.

### 2.2 Google Meet Creation via `conferenceData.createRequest`

`conferenceSolutionKey.type = "hangoutsMeet"` is the standard value for Google Meet. The Calendar API automatically provisions a Meet room and attaches the conference details. No separate Meet API call is required. The provisioned Meet URL is stable for the lifetime of the calendar event.

**Caveat**: Meet rooms provisioned via `events.insert` persist even after the event is deleted. If a meeting is cancelled we **do not** attempt to invalidate the Meet URL — we simply mark `Meeting.status = cancelled` and notify attendees not to use it.

### 2.3 Domain-Wide Delegation — Service Account Pattern

For v1 we use a **single Colab-managed Google Calendar** (created under the Colab GCP service account) rather than per-user calendar access. This avoids the OAuth consent screen for calendar.events scope on every user account and eliminates the risk of users revoking tokens mid-flow.

Setup:
1. Create a GCP service account: `meeting-bot@colab-prod.iam.gserviceaccount.com`
2. Grant the service account **Calendar API scope** (`https://www.googleapis.com/auth/calendar`) on the Colab shared calendar.
3. Store the JSON key in **AWS Secrets Manager** (path: `prod/meeting-svc/google-service-account`). Load via IRSA in the EKS pod — no key file on disk.
4. Use `google-auth` Python library: `google.oauth2.service_account.Credentials.from_service_account_info(...)`.

The calendar event will appear in Colab's shared calendar. Both participants receive an email invitation from Google Calendar because their email addresses are listed in `attendees[]`. They are not required to have Google accounts; the invite is sent regardless.

**Per-user OAuth alternative** (deferred to v2): If users want meetings to appear on *their own* Google Calendars, we would implement OAuth with `calendar.events` scope per user. The complexity (refresh token storage, revocation handling, multi-account edge cases) is not worth it for v1.

### 2.4 Recall.ai — REST API, Webhook Signature, Bot Launch Model

**Base URL**: `https://api.recall.ai/api/v1/`
**Auth**: `Authorization: Token <RECALL_API_KEY>` (stored in Secrets Manager: `prod/meeting-svc/recall-api-key`).

**Bot creation**:
```
POST /api/v1/bot/
{
  "meeting_url": "https://meet.google.com/xxx-yyyy-zzz",
  "bot_name": "Colab Notes Bot",
  "transcription_options": { "provider": "assembly_ai" },
  "real_time_transcription": { "destination_url": null },
  "recording_mode": "speaker_view",
  "webhook_url": "https://api.colab.app/webhooks/recall"
}
```

Response includes `bot.id` — stored as `Meeting.recall_bot_id`.

**Bot lifecycle states** (polled via webhook events):
- `joining_call` → `in_call_recording` → `call_ended` → `done`
- `fatal` if bot cannot join (private room, kicked, network failure)

**Webhook delivery**: Recall.ai signs every webhook with HMAC-SHA256. Header: `X-Recall-Signature: sha256=<hex>`. Verification:
```python
import hmac, hashlib
expected = hmac.new(
    RECALL_WEBHOOK_SECRET.encode(),
    raw_body,
    hashlib.sha256
).hexdigest()
assert hmac.compare_digest(f"sha256={expected}", request.headers["X-Recall-Signature"])
```
`RECALL_WEBHOOK_SECRET` stored in Secrets Manager. FastAPI middleware verifies before any handler logic executes. Invalid signatures → 403, logged to CloudWatch.

**Transcript delivery**: When `status_changes` event type = `done`, Recall sends:
```json
{
  "event": "status_changes",
  "data": {
    "bot": { "id": "...", "status": { "code": "done" } },
    "transcript": { "url": "https://..." },
    "recording": { "url": "https://..." }
  }
}
```
We download the transcript JSON from the signed URL, store it to S3 (`artifacts/meetings/{meeting_id}/transcript.json`), and create `MeetingArtifact` rows for both transcript and recording. Then we emit `meeting.transcript_ready` to the message bus.

**Rate limits**: Recall.ai free tier: 5 concurrent bots. Production plan: 50+. No per-request rate limit documented for REST API; implement exponential backoff with jitter on 429/503.

---

## 3. Auth Flow

### 3.1 Google Calendar — Service Account (Recommended for v1)

```
meeting-svc pod
  └─ IRSA role → pulls secret from Secrets Manager
       └─ google.oauth2.service_account.Credentials
            └─ google.auth.transport.requests.AuthorizedSession
                 └─ POST calendar.googleapis.com/calendar/v3/...
```

No user-facing OAuth for calendar. The calendar event email invitation is automatically dispatched by Google to all `attendees` email addresses on event creation. Participants receive calendar invitations from `calendar-notification@google.com` on behalf of the Colab shared calendar.

### 3.2 Recall.ai Authentication

Static API key, stored in Secrets Manager, rotated quarterly. No user-facing OAuth involved.

### 3.3 Internal API Auth

All `meeting-svc` endpoints sit behind `gateway`, which validates the caller's JWT. `meeting-svc` trusts the `X-User-Id` header injected by `gateway` (never from the client directly). Webhook endpoint (`POST /webhooks/recall`) is **not** behind JWT auth — it is validated by HMAC signature as described in §2.4.

---

## 4. Data Model

### 4.1 `Meeting`

```sql
CREATE TABLE meeting (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    collab_id         UUID NOT NULL REFERENCES collaboration(id) ON DELETE CASCADE,
    organizer_profile_id UUID NOT NULL,
    scheduled_at      TIMESTAMPTZ NOT NULL,
    duration_min      SMALLINT NOT NULL DEFAULT 60 CHECK (duration_min BETWEEN 15 AND 480),
    join_url          TEXT NOT NULL,
    ics_s3_key        TEXT,
    gcal_event_id     TEXT,                     -- Google Calendar event ID
    gcal_request_id   UUID NOT NULL UNIQUE,     -- idempotency key for events.insert
    status            TEXT NOT NULL DEFAULT 'scheduled'
                          CHECK (status IN ('scheduled','started','ended','cancelled')),
    bot_enabled       BOOLEAN NOT NULL DEFAULT FALSE,
    bot_status        TEXT NOT NULL DEFAULT 'none'
                          CHECK (bot_status IN ('none','requested','joining','joined','left','failed')),
    recall_bot_id     TEXT,
    cancelled_at      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_meeting_collab ON meeting(collab_id);
CREATE INDEX idx_meeting_scheduled ON meeting(scheduled_at) WHERE status = 'scheduled';
```

### 4.2 `MeetingArtifact`

```sql
CREATE TABLE meeting_artifact (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id  UUID NOT NULL REFERENCES meeting(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL CHECK (kind IN ('transcript','recording','summary')),
    s3_key      TEXT NOT NULL,
    size_bytes  BIGINT,
    ready_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_artifact_meeting ON meeting_artifact(meeting_id);
```

### 4.3 `MeetingBotConsent`

Tracks per-participant consent to bot recording. Both rows must exist before `POST /meetings/{id}/bot/start` is honoured.

```sql
CREATE TABLE meeting_bot_consent (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id   UUID NOT NULL REFERENCES meeting(id) ON DELETE CASCADE,
    profile_id   UUID NOT NULL,
    consented_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at   TIMESTAMPTZ,                   -- NULL = consent active
    UNIQUE (meeting_id, profile_id)
);

CREATE INDEX idx_consent_meeting ON meeting_bot_consent(meeting_id);
```

**Consent semantics**: A participant can revoke consent up until the moment the bot is dispatched (`bot_status = 'requested'`). Once `bot_status = 'joining'` or beyond, revocation is not possible in v1 (the bot is already in the call). This is surfaced in the UI: the "Revoke" button is disabled once the bot has joined. Future versions may support mid-meeting bot removal via `DELETE /api/v1/bot/{id}/leave_call`.

### 4.4 Entity Relationships

```
Collaboration (§009)
  └── Meeting  [1:many — one collab can have multiple scheduled meetings]
        ├── MeetingBotConsent  [0:2 — one per participant]
        └── MeetingArtifact    [0:many — transcript, recording, summary]
```

---

## 5. Recall.ai Bot Launch Flow

### 5.1 Mutual Consent Gate

The bot is never dispatched automatically. The flow is:

```
1. Organizer creates meeting with bot_enabled=true
   └─ Meeting created (status=scheduled, bot_status=none)
   └─ Notification sent to both participants:
      "A Recall.ai bot will record and transcribe this meeting.
       Both of you must approve before the bot joins."

2. Each participant visits meeting detail screen →
   clicks "Allow bot to attend" →
   POST /meetings/{id}/bot/consent  (authenticated)
   └─ MeetingBotConsent row upserted for that profile_id

3. When both rows exist and neither is revoked:
   └─ meeting-svc checks consent count
   └─ If count == 2: automatically sets bot_status = 'requested'
      and enqueues Celery task: dispatch_recall_bot(meeting_id)

4. Celery task runs at/after scheduled_at:
   └─ POST /api/v1/bot/ to Recall.ai
   └─ Store recall_bot_id
   └─ Set bot_status = 'joining'

5. Recall.ai webhook fires as bot progresses:
   └─ joining_call  → bot_status = 'joining'
   └─ in_call_recording → bot_status = 'joined'
   └─ call_ended → bot_status = 'left'
   └─ done → ingest artifacts (§5.2)
   └─ fatal → bot_status = 'failed'; notify participants
```

**Important**: If only one participant consents, `bot_status` remains `none`; the meeting proceeds without recording. The UI clearly indicates "Waiting for {name} to approve recording."

### 5.2 Artifact Ingestion

On Recall.ai webhook `status_changes` with code `done`:

```python
async def handle_recall_webhook_done(meeting: Meeting, payload: dict):
    # 1. Download transcript JSON from signed URL
    transcript_data = await http_client.get(payload["transcript"]["url"])
    
    # 2. Store to S3
    transcript_s3_key = f"artifacts/meetings/{meeting.id}/transcript.json"
    await s3.put_object(Bucket=ARTIFACTS_BUCKET, Key=transcript_s3_key, Body=transcript_data)
    
    # 3. Create MeetingArtifact rows
    await db.execute(INSERT INTO meeting_artifact (meeting_id, kind, s3_key) VALUES ...)
    # one row for 'transcript', one for 'recording'
    
    # 4. Update meeting status
    await db.execute(UPDATE meeting SET bot_status='left', status='ended' WHERE id=...)
    
    # 5. Emit queue event
    await mq.publish("meeting.transcript_ready", { "meeting_id": str(meeting.id) })
    
    # 6. Write audit log entry (§009 pattern)
    await audit_log.append(
        entity_type="meeting",
        entity_id=meeting.id,
        action="transcript_stored",
        actor="recall_webhook",
        metadata={ "s3_key": transcript_s3_key }
    )
```

### 5.3 Chat Integration (§007)

On consuming `meeting.transcript_ready` from the queue:

`chat-svc` creates a `ChatMessage` of type `system|transcript` in the collaboration's chat room:

```json
{
  "type": "system",
  "subtype": "transcript",
  "content": "Meeting transcript is ready.",
  "metadata": {
    "meeting_id": "<uuid>",
    "meeting_scheduled_at": "2026-06-01T15:00:00Z",
    "artifact_kind": "transcript",
    "collapse": true
  }
}
```

The client renders this as a collapsible system card: "Meeting on Jun 1, 2026 — Transcript Available [Expand]". Expanding shows the full transcript inline (pulled from a signed S3 URL via `GET /meetings/{id}/artifacts/{artifact_id}/download`).

---

## 6. Timezone Handling

**Storage**: All `TIMESTAMPTZ` columns store UTC. The Postgres driver (asyncpg) enforces UTC on insert.

**Input**: `scheduled_at` in API requests must be ISO 8601 with explicit UTC offset (e.g. `2026-06-01T15:00:00Z` or `2026-06-01T10:00:00-05:00`). The service normalizes to UTC before persisting.

**Rendering**: The client (React Native + Next.js) receives UTC timestamps and renders them in the user's device/browser locale using the `Intl.DateTimeFormat` API with `timeZoneName: 'short'`. No timezone conversion is performed server-side.

**ICS file**: The `.ics` generated server-side uses `DTSTART;TZID=UTC:` with the raw UTC value. Clients (Google Calendar, Apple Calendar, Outlook) honour the user's local timezone when displaying the event.

**Conflict detection**: When creating a meeting, `meeting-svc` checks for overlapping meetings in the same collab (same `collab_id`, `status != 'cancelled'`, overlapping time window). If a conflict exists, return 409 with `conflicting_meeting_id`.

---

## 7. API Contracts

All routes are prefixed `/v1` and sit behind the `gateway`. Auth via JWT (`X-User-Id` injected by gateway). All timestamps ISO 8601 UTC.

### 7.1 `POST /v1/collabs/{collab_id}/meetings`

**Auth**: Either participant of the collab.

Request:
```json
{
  "scheduled_at": "2026-06-01T15:00:00Z",
  "duration_min": 60,
  "bot_enabled": true
}
```

Response `201`:
```json
{
  "id": "uuid",
  "collab_id": "uuid",
  "organizer_profile_id": "uuid",
  "scheduled_at": "2026-06-01T15:00:00Z",
  "duration_min": 60,
  "join_url": "https://meet.google.com/xxx-yyy-zzz",
  "ics_url": "https://cdn.colab.app/signed/artifacts/meetings/.../invite.ics",
  "status": "scheduled",
  "bot_enabled": true,
  "bot_status": "none",
  "bot_consent": {
    "participant_a": false,
    "participant_b": false
  }
}
```

Errors: `400` (validation), `409` (conflicting meeting), `502` (Google API failure).

### 7.2 `PATCH /v1/meetings/{id}`

**Auth**: Either participant.

Request (all fields optional):
```json
{
  "scheduled_at": "2026-06-01T16:00:00Z",
  "duration_min": 90,
  "status": "cancelled"
}
```

- Rescheduling updates the Google Calendar event (`events.patch`). If Google fails, the Colab meeting is **not** updated — return 502.
- Cancelling sets `status = 'cancelled'`, `cancelled_at = NOW()`, emits `meeting.cancelled`. Does not delete the Google Calendar event (the Meet URL remains valid but we inform users it is cancelled).
- Cannot modify a meeting with `status = 'ended'` or `status = 'cancelled'` → 422.

Response `200`: full `Meeting` object.

### 7.3 `POST /v1/meetings/{id}/bot/consent`

**Auth**: Must be one of the two collab participants.

Request: empty body (consent is the act of calling the endpoint).

Response `200`:
```json
{
  "profile_id": "uuid",
  "consented_at": "2026-05-11T10:00:00Z",
  "both_consented": false
}
```

When `both_consented` becomes `true`, `meeting-svc` internally sets `bot_status = 'requested'` and schedules the Celery task.

### 7.4 `DELETE /v1/meetings/{id}/bot/consent`

**Auth**: The consenting participant (own consent only).

Allowed only when `bot_status IN ('none', 'requested')`. If bot has already been dispatched (`bot_status = 'joining'` or later), returns 422 with message "Bot has already been dispatched and cannot be recalled."

Sets `revoked_at` on the `MeetingBotConsent` row. If the other participant's consent was already given, `bot_status` reverts to `none` and the Celery task is revoked (if not yet started).

### 7.5 `POST /v1/meetings/{id}/bot/start`

**Auth**: Either participant.

Idempotent manual trigger (in addition to the automatic dispatch after double-consent). Returns 422 if consent from both participants is not present, or if `bot_status` is not `none` or `requested`.

Response `202`:
```json
{ "bot_status": "requested", "recall_bot_id": null }
```

### 7.6 `GET /v1/collabs/{collab_id}/meetings`

**Auth**: Either participant.

Returns paginated list of meetings for the collab, sorted by `scheduled_at DESC`. Supports `?status=scheduled|ended|cancelled`.

Response `200`:
```json
{
  "items": [ { ...Meeting... } ],
  "cursor": "...",
  "has_more": false
}
```

### 7.7 `GET /v1/meetings/{id}/artifacts`

**Auth**: Either participant.

Response `200`:
```json
{
  "items": [
    {
      "id": "uuid",
      "kind": "transcript",
      "download_url": "https://cdn.colab.app/signed/...",
      "ready_at": "2026-06-01T16:05:00Z"
    }
  ]
}
```

Signed URLs expire in 1 hour. Client must re-fetch for fresh URL.

### 7.8 `POST /webhooks/recall`

**Auth**: HMAC-SHA256 signature verification (no JWT).

Processes Recall.ai lifecycle events. Returns `200` immediately after signature verification to avoid Recall.ai timeout; processing is handed off to a Celery task.

### 7.9 Queue Events

| Event | Producer | Consumers |
|---|---|---|
| `meeting.scheduled` | `meeting-svc` | `notification-svc` (push + email to both participants) |
| `meeting.cancelled` | `meeting-svc` | `notification-svc` |
| `meeting.bot_consent_pending` | `meeting-svc` | `notification-svc` (nudge to non-consenting participant) |
| `meeting.transcript_ready` | `meeting-svc` | `chat-svc` (create system message), `collab-svc` (update `last_activity_at`) |

---

## 8. Implementation Tasks

### 8.1 Infrastructure / Secrets (P0 prerequisite)

- [ ] **MEET-INFRA-1**: Create GCP project `colab-prod`. Enable Google Calendar API + Google Meet API. Create service account `meeting-bot@colab-prod.iam.gserviceaccount.com`. Grant service account Editor access on a dedicated Colab shared calendar. Download JSON key. Store in Secrets Manager at `prod/meeting-svc/google-service-account`. Rotate annually.
- [ ] **MEET-INFRA-2**: Create Recall.ai account. Generate API key. Store in Secrets Manager at `prod/meeting-svc/recall-api-key`. Generate HMAC webhook secret. Store at `prod/meeting-svc/recall-webhook-secret`.
- [ ] **MEET-INFRA-3**: Create S3 bucket `colab-meeting-artifacts-prod` in `us-east-1`. Apply bucket policy: private, server-side encryption (AES-256), versioning enabled, lifecycle rule to Glacier after 90 days (audit retention).
- [ ] **MEET-INFRA-4**: Register Recall.ai webhook URL: `https://api.colab.app/webhooks/recall`. Configure in Recall.ai dashboard to send all bot events.

### 8.2 Service Skeleton

- [ ] **MEET-SVC-1**: Scaffold `meeting-svc` FastAPI app. Add to EKS deployment. Configure IRSA role with Secrets Manager read access.
- [ ] **MEET-SVC-2**: Write Alembic migration for `meeting`, `meeting_artifact`, `meeting_bot_consent` tables.
- [ ] **MEET-SVC-3**: Implement `GoogleCalendarClient` wrapper using `google-auth` + `httpx`. Methods: `create_event(...)` → `(gcal_event_id, join_url)`, `patch_event(...)`, `delete_event(...)`. Include retry with exponential backoff (max 3 retries, 502 on final failure).
- [ ] **MEET-SVC-4**: Implement `RecallClient` wrapper. Methods: `create_bot(meeting_url, webhook_url)` → `recall_bot_id`, `get_bot_status(bot_id)`. Include retry + circuit breaker (if Recall.ai is down, `bot_status = 'failed'`, notify participants).
- [ ] **MEET-SVC-5**: Implement HMAC webhook signature middleware (`verify_recall_signature`). Reject before handler if invalid.
- [ ] **MEET-SVC-6**: Implement `ics_generator.py` using `icalendar` library. Generates `.ics` bytes from `Meeting` object. Upload to S3 on meeting creation. Return signed 1-hour URL.

### 8.3 API Endpoints

- [ ] **MEET-API-1**: `POST /v1/collabs/{collab_id}/meetings` — validate collab membership, check for overlap, call `GoogleCalendarClient.create_event`, persist `Meeting`, emit `meeting.scheduled`, generate + upload ICS.
- [ ] **MEET-API-2**: `PATCH /v1/meetings/{id}` — reschedule (call `GoogleCalendarClient.patch_event`) or cancel. Validate state transitions.
- [ ] **MEET-API-3**: `POST /v1/meetings/{id}/bot/consent` — upsert `MeetingBotConsent`. After upsert, query count of non-revoked consents; if == 2, schedule Celery task `dispatch_recall_bot`.
- [ ] **MEET-API-4**: `DELETE /v1/meetings/{id}/bot/consent` — validate bot_status, set `revoked_at`, revoke Celery task if pending.
- [ ] **MEET-API-5**: `POST /v1/meetings/{id}/bot/start` — manual idempotent trigger. Check consent count == 2. Dispatch Celery task.
- [ ] **MEET-API-6**: `GET /v1/collabs/{collab_id}/meetings` — paginated list.
- [ ] **MEET-API-7**: `GET /v1/meetings/{id}/artifacts` — list artifacts with signed S3 URLs.
- [ ] **MEET-API-8**: `POST /webhooks/recall` — verify HMAC, parse event, enqueue `process_recall_webhook` Celery task, return 200.

### 8.4 Celery Tasks

- [ ] **MEET-TASK-1**: `dispatch_recall_bot(meeting_id)` — scheduled to run at `Meeting.scheduled_at`. Calls `RecallClient.create_bot`. Updates `bot_status = 'joining'` + `recall_bot_id`. On failure: `bot_status = 'failed'`, emit error notification.
- [ ] **MEET-TASK-2**: `process_recall_webhook(meeting_id, payload)` — handles Recall.ai event payload. On `done`: download transcript, upload to S3, create `MeetingArtifact` rows, update `meeting.status = 'ended'`, `bot_status = 'left'`, emit `meeting.transcript_ready`.
- [ ] **MEET-TASK-3**: `send_consent_nudge(meeting_id)` — triggered 30 min before `scheduled_at` if `bot_status = 'requested'` and not both consented. Sends push notification to non-consenting participant.

### 8.5 Queue Consumers

- [ ] **MEET-CONS-1**: `chat-svc` subscribes to `meeting.transcript_ready` → creates `ChatMessage(type='system', subtype='transcript')` in the collab room.
- [ ] **MEET-CONS-2**: `collab-svc` subscribes to `meeting.transcript_ready` → updates `Collaboration.last_activity_at`.
- [ ] **MEET-CONS-3**: `notification-svc` subscribes to `meeting.scheduled`, `meeting.cancelled`, `meeting.bot_consent_pending`.

### 8.6 Client (React Native + Web)

- [ ] **MEET-CLIENT-1**: "Schedule Meeting" entry point in collab workspace header/toolbar.
- [ ] **MEET-CLIENT-2**: Meeting scheduling modal — date/time picker (device locale aware), duration selector (15/30/45/60/90 min), "Enable recording bot" toggle with explanatory copy.
- [ ] **MEET-CLIENT-3**: Meeting card in collab room — shows scheduled time (user locale), "Join Meeting" deeplink button, countdown, bot status badge.
- [ ] **MEET-CLIENT-4**: Bot consent UI — "Allow bot to attend" / "Revoke" button. Shows status of both participants' consent. Disabled once bot_status is 'joining' or beyond.
- [ ] **MEET-CLIENT-5**: Transcript system message in chat — collapsible card. "Meeting on {date} — Transcript Available". Inline transcript render. "Download" button for recording (if available).
- [ ] **MEET-CLIENT-6**: Meeting history tab in collab detail — list of past and upcoming meetings with status badges.

### 8.7 Tests

- [ ] **MEET-TEST-1**: Unit tests for `GoogleCalendarClient` (mock `httpx`). Cover: success, 409 conflict idempotency, 502 retry exhaustion.
- [ ] **MEET-TEST-2**: Unit tests for `RecallClient`. Cover: bot creation success, 429 backoff, circuit-open behaviour.
- [ ] **MEET-TEST-3**: Unit tests for `verify_recall_signature` — valid, invalid, missing header.
- [ ] **MEET-TEST-4**: Integration tests (pytest + testcontainers Postgres): full meeting creation → consent → dispatch → webhook → artifact ingestion lifecycle.
- [ ] **MEET-TEST-5**: Integration test: single-consent → meeting proceeds without bot.
- [ ] **MEET-TEST-6**: Integration test: consent revocation before dispatch.
- [ ] **MEET-TEST-7**: Integration test: overlapping meeting conflict 409.

---

## 9. Acceptance Criteria

### AC-1 — Meeting Creation
- **Given**: Two matched participants in an active collab.
- **When**: Either participant calls `POST /v1/collabs/{collab_id}/meetings` with a valid future `scheduled_at`.
- **Then**:
  - Response 201 contains a valid `join_url` (format: `https://meet.google.com/[a-z]{3}-[a-z]{4}-[a-z]{3}`).
  - A Google Calendar event exists in the Colab shared calendar with both participants' emails in `attendees`.
  - Both participants receive a Google Calendar invitation email within 2 minutes.
  - `Meeting` row persisted with `status = 'scheduled'`.
  - `meeting.scheduled` event on RabbitMQ observable within 1 second.
  - `notification-svc` sends push + email notification to both participants within 30 seconds.
- **Verification**: Integration test + manual QA with live GCP service account.

### AC-2 — ICS Download
- **Given**: A scheduled meeting.
- **When**: Client fetches `ics_url`.
- **Then**: Downloaded file is valid `.ics` (RFC 5545); DTSTART matches `scheduled_at` (UTC); DTEND = `scheduled_at + duration_min`; LOCATION contains the Google Meet URL.
- **Verification**: Import `.ics` into Apple Calendar and Google Calendar; verify event details.

### AC-3 — Meeting Reschedule
- **Given**: A meeting with `status = 'scheduled'`.
- **When**: `PATCH /v1/meetings/{id}` with new `scheduled_at`.
- **Then**: Google Calendar event is updated (verified via `events.get`); `Meeting.scheduled_at` updated; new `ics_url` generated; both participants notified.
- **Verification**: Integration test + manual GCal check.

### AC-4 — Meeting Cancellation
- **Given**: A meeting with `status = 'scheduled'`.
- **When**: `PATCH /v1/meetings/{id}` with `status = 'cancelled'`.
- **Then**: `Meeting.status = 'cancelled'`, `cancelled_at` populated; `meeting.cancelled` event emitted; push + email notification sent to both participants; Google Calendar event is **not** deleted (Meet URL remains technically accessible, but UI shows "Cancelled").
- **Verification**: Integration test.

### AC-5 — Bot Consent — Mutual Required
- **Given**: A meeting with `bot_enabled = true`.
- **When**: Only one participant calls `POST /v1/meetings/{id}/bot/consent`.
- **Then**: `MeetingBotConsent` row created; `bot_status` remains `'none'`; nudge notification sent to the non-consenting participant; Celery bot dispatch task NOT scheduled.
- **Verification**: Unit + integration tests.

### AC-6 — Bot Dispatch After Mutual Consent
- **Given**: A meeting with `bot_enabled = true`; both participants have called consent.
- **When**: Second consent is recorded.
- **Then**: `bot_status = 'requested'`; Celery task `dispatch_recall_bot` scheduled for `scheduled_at`; response `both_consented = true`.
- **Verification**: Integration test with mocked Recall.ai.

### AC-7 — Recall.ai Bot Joins and Records
- **Given**: `dispatch_recall_bot` Celery task executes.
- **When**: `RecallClient.create_bot` succeeds.
- **Then**: `Meeting.recall_bot_id` stored; `bot_status = 'joining'`; Recall.ai webhook events received and processed in order: joining → joined → left → done.
- **Verification**: Recall.ai sandbox environment end-to-end test.

### AC-8 — Webhook Signature Verification
- **Given**: A POST to `POST /webhooks/recall`.
- **When**: The `X-Recall-Signature` header is missing, malformed, or contains an invalid HMAC.
- **Then**: Response is 403; event is not processed; security event logged to CloudWatch.
- **When**: Signature is valid.
- **Then**: Response is 200 immediately; event processing delegated to Celery.
- **Verification**: Unit tests with valid/invalid signatures.

### AC-9 — Transcript Ingestion
- **Given**: Recall.ai webhook `done` event received and verified.
- **When**: `process_recall_webhook` Celery task completes.
- **Then**:
  - `MeetingArtifact` rows created for `transcript` and `recording` kinds.
  - Transcript JSON stored to S3 at `artifacts/meetings/{meeting_id}/transcript.json`.
  - `Meeting.status = 'ended'`, `bot_status = 'left'`.
  - `meeting.transcript_ready` event on queue.
  - `ChatMessage(type='system', subtype='transcript')` created in collab chat room within 10 seconds.
  - Audit log entry written.
- **Verification**: Integration test with mocked Recall.ai payload.

### AC-10 — Transcript in Chat
- **Given**: `meeting.transcript_ready` event consumed by `chat-svc`.
- **When**: A participant opens the chat room.
- **Then**: A collapsible system card appears: "Meeting on {formatted date/time in user's locale} — Transcript Available". Expanding the card shows the full transcript text. A signed download URL for the recording is accessible.
- **Verification**: Manual QA + screenshot-based client test.

### AC-11 — Timezone Correctness
- **Given**: Meeting scheduled at `2026-06-01T15:00:00Z` (UTC).
- **When**: Participant in UTC−5 (CDT) views the meeting.
- **Then**: UI displays "Jun 1, 2026 at 10:00 AM CDT" (or equivalent per device locale). The UTC value in the database is unchanged.
- **Verification**: Manual test with device timezone changed to UTC−5, UTC+5:30 (IST), AEST (UTC+10).

### AC-12 — Consent Revocation
- **Given**: Participant A has consented; `bot_status = 'requested'`; Celery task not yet started.
- **When**: Participant A calls `DELETE /v1/meetings/{id}/bot/consent`.
- **Then**: `MeetingBotConsent.revoked_at` set; `bot_status` reverts to `'none'`; Celery task revoked; Participant B notified that recording has been disabled.
- **Given**: `bot_status = 'joining'` (bot already dispatched).
- **When**: Participant A calls `DELETE /v1/meetings/{id}/bot/consent`.
- **Then**: 422 returned with message "Bot has already been dispatched and cannot be recalled."
- **Verification**: Integration tests.

### AC-13 — Schedule API Latency
- **Given**: Google Calendar API is healthy.
- **When**: 50 concurrent `POST /v1/collabs/{collab_id}/meetings` requests issued.
- **Then**: P95 response time < 500ms (excluding Google API round-trip which is measured separately and not included in the SLA).
- **Verification**: k6 load test in staging with GCP service account.

---

## 10. Open Risks

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| **RISK-MEET-1** | Google Calendar API quota exhaustion | Low at v1 scale | Medium | Monitor via GCP Console quotas; at 80% daily quota emit CloudWatch alarm. Request quota increase before launch. |
| **RISK-MEET-2** | Google Meet URL instability / format change | Low | High | Do not parse or manipulate the `join_url` — store and return verbatim. Pin Google API client library version. |
| **RISK-MEET-3** | Recall.ai bot kicked from private/moderated Meet rooms | Medium | Medium | On `fatal` webhook: `bot_status = 'failed'`; send in-app + push notification to both participants; do not retry automatically (requires participant re-consent). |
| **RISK-MEET-4** | Recall.ai downtime during scheduled meeting | Low–Medium | Medium | Implement circuit breaker in `RecallClient`. If Recall is down at dispatch time, retry up to 3× with 60s backoff. On final failure: `bot_status = 'failed'`, notify participants, meeting proceeds without recording. |
| **RISK-MEET-5** | Webhook delivery failure (network / timeout) | Low | High | Recall.ai retries webhook delivery up to 10× with exponential backoff. Our endpoint returns 200 immediately (processing in Celery), so we do not time out. Implement idempotency key on webhook handler: store `recall_event_id` in Redis with 24h TTL; skip duplicate events. |
| **RISK-MEET-6** | Participant consent UX confusion | Medium | Medium | Clear UI copy: "Both you and {name} must approve before the bot joins." Run usability test with 3–5 creator-persona users pre-launch. |
| **RISK-MEET-7** | Legal / consent in AU/NZ/IN (recording laws) | Medium | High | Recording consent is captured by the `MeetingBotConsent` mechanism; both participants explicitly approve. Bot name is "Colab Notes Bot" — visible to all Meet participants. Review with legal counsel before launch in each geo. Audit log retains consent timestamps per DSR requirements. |
| **RISK-MEET-8** | Transcript S3 storage costs at scale | Low at v1 | Low | Average transcript ~50–200KB; recording links are Recall.ai-hosted (not stored in Colab S3). Cost negligible at v1. Revisit at 50k DAU. |
| **RISK-MEET-9** | Pre-meeting agenda generator (GPT) scope creep | Low | Low | Explicitly deferred to §012 in-chat AI assistant as `/agenda` command. Not in scope for P10. |
| **RISK-MEET-10** | Service account key compromise | Very Low | Critical | JSON key stored in Secrets Manager only; never in code, env files, or logs. Rotation policy: annual + immediate on suspected exposure. IRSA access scoped to `meeting-svc` pod only. |
