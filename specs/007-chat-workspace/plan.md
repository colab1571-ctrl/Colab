# 007 — Chat + Workspace Base — Implementation Plan

**Date**: 2026-05-11
**Phase**: P6
**Services**: `chat-svc`, `media-svc`
**Spec ref**: `007-chat-workspace/spec.md`, `000-master/spec.md`
**Depends on**: §002 Platform, §003 Auth, §006 Invite; soft-deps §008 Moderation, §009 Collab Lifecycle

---

## 1. Mission Recap

Deliver the real-time 1:1 collaboration chat room that opens the moment two users match. The room is the centre of gravity for the entire Colab workspace: every subsequent phase (tools, meetings, AI assistant) embeds into it. This phase builds:

- A custom WebSocket gateway (`chat-svc`) backed by AWS API Gateway WebSocket APIs, fronting EKS-deployed FastAPI/Starlette pods.
- Full message persistence in Postgres; media on S3 via `media-svc` presigned-URL flow.
- Support for all five content types: text, voice notes, images, audio files, video files, documents.
- Presence and typing indicators via Redis pub/sub.
- Pre-send moderation integration with `moderation-svc` (§008) before every message is delivered.
- Immutable audit trail (revision-based edits) to satisfy the lifetime + 3-year-post-deletion retention requirement and the §009 collab-lifecycle audit log.
- Block-aware read-only room enforcement (§014 block signals).
- Offline-resilient client with optimistic updates and queued writes (master NFR-7).

All delivery must satisfy master NFR-1: P95 chat message e2e latency **< 500 ms**.

---

## 2. Research Notes

### 2.1 AWS API Gateway WebSocket APIs

| Constraint | Value | Implication |
|---|---|---|
| Idle connection timeout | **10 minutes** | Client must send a heartbeat (ping frame or app-level keepalive) every < 9 min |
| Maximum connection duration | **2 hours** | Client must reconnect pro-actively before the 2-hour mark; server should signal approaching expiry |
| Max message payload (frame) | 128 KB | Voice notes and media are never sent inline; they follow the presigned-URL path |
| Max concurrent connections per account | Adjustable via quota request | Pre-request increase before P18 load test |
| Execution timeout per route integration | 29 seconds | Fine for `send`/`typing`/`read_ack` processing |
| Cost model | $0.80/M connection-minutes + $1.00/M messages | Acceptable at 100k DAU; revisit if average session > 60 min |

**Phase 5 contingency — Native ALB + ECS path**: If the 2-hour hard limit causes unacceptable UX disruption even with a reconnect-aware client (§4), the team will evaluate replacing API Gateway WebSocket APIs with an Application Load Balancer WebSocket upgrade directly to ECS (no 2-hour cap, no idle timeout, sticky sessions). Decision gate: **P18 load test reconnect-storm results**. Document the architectural decision before P6 ships so the swap is a one-sprint change.

### 2.2 FastAPI / Starlette WebSocket Support

- Starlette's `WebSocket` class (the base of FastAPI) natively supports the WebSocket lifecycle: `accept()`, `receive_text()` / `receive_bytes()`, `send_text()` / `send_json()`, `close()`.
- Use `fastapi.WebSocket` with a `Depends(get_current_user_from_token)` that reads the bearer token passed as a query-parameter on the upgrade request (API Gateway forwards query strings).
- Each pod maintains an in-process dict `{room_id: set[WebSocket]}` for connections local to that pod. Cross-pod fanout uses Redis pub/sub (§2.3).
- Use `asyncio.gather` for concurrent `send_json` to all local connections in a room.
- Connection manager is a singleton `AsyncConnectionManager` injected via FastAPI's `app.state`.

### 2.3 Redis Pub/Sub for Cross-Pod Fanout

- Channel naming: `chat:room:{room_id}` — all pods subscribe on demand when a client joins a room.
- On message persist to Postgres, the originating pod publishes the serialized `ChatMessageOut` envelope to the Redis channel.
- All pods (including the originating pod, to reach other connections in the same room) receive the publish and fan out to their local WebSocket connections for that room.
- Presence state: `HASH chat:presence:{room_id}` keyed by `profile_id` → `{online: bool, typing: bool, last_seen_at: ISO}`. TTL 90 seconds; heartbeat from client resets TTL.
- Redis cluster: ElastiCache (same VPC, same AZ group as EKS nodes to minimize latency). Pub/sub latency target: < 10 ms p95 intra-region.

### 2.4 Python asyncio + Starlette WebSocket

- All I/O (Postgres via `asyncpg`, Redis via `aioredis`, S3 calls via `aioboto3`) must be fully async — no blocking calls on the event loop.
- Use `anyio.create_task_group` to run the subscribe-loop alongside the receive-loop per connection.
- Graceful disconnect: `websockets.exceptions.ConnectionClosedOK` / `ConnectionClosedError` caught at the connection manager level; presence updated immediately.
- Uvicorn workers: `uvicorn --workers 1 --loop uvloop` per pod (one event loop per process); scale horizontally via EKS HPA on CPU + connection count custom metric.

### 2.5 Presigned S3 PUT URL Flow

Full sequence in §8. Key notes:
- `media-svc` generates the presigned PUT URL (5-minute TTL) without touching the payload.
- The client uploads directly from device to S3 — `chat-svc` never proxies bytes.
- After upload, client calls `POST /media/confirm`; `media-svc` downloads from S3 (same VPC endpoint, free transfer), runs mod + dup scans, and only then creates the `ChatMessage` row and publishes to Redis.
- S3 bucket has `Block Public Access = true`; media is served exclusively via CloudFront signed URLs (5-minute rotating cache via `GET /media/{s3_key}/signed-url`).
- Client-side: before calling `POST /media/upload-url`, validate MIME type and file size against the per-type caps (image 10 MB, audio 50 MB, video 250 MB, doc 25 MB).

### 2.6 Voice Note Recording in React Native (expo-av)

- Use `expo-av` `Audio.Recording` API: `Audio.Recording.createAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY)`.
- Hold-to-record UX: `onPressIn` starts recording; `onPressOut` stops and triggers the upload flow.
- Output format: `.m4a` (AAC, whitelisted MIME `audio/mp4`). iOS and Android both produce this via the HIGH_QUALITY preset.
- Recording duration cap: **5 minutes** (300 s) — enforced client-side via a `setTimeout` that auto-stops.
- Waveform visualization: use `metering` mode from `expo-av` to drive a simple amplitude bar array while recording.
- Playback in the message list: `Audio.Sound.createAsync` with `progressUpdateIntervalMillis: 100` for seek-bar updates.
- `duration_ms` sent in `POST /media/confirm` body (from `recording.getStatusAsync().durationMillis`).

### 2.7 Message Ordering + Monotonic Clock

- Primary ordering key: `created_at` (server-assigned `TIMESTAMPTZ DEFAULT now()` in Postgres). Postgres `now()` within a transaction is stable; insertion order within the same millisecond resolved by `id` (UUIDv7 — time-ordered).
- UUIDv7 chosen for `ChatMessage.id`: embeds 48-bit Unix epoch milliseconds in the most-significant bits, making lexicographic ordering consistent with temporal ordering. No separate `sequence_number` column needed.
- Client optimistic messages use a client-generated `client_nonce` (UUID4) echoed back in the server ack; client deduplicates on `client_nonce` to avoid double-rendering.
- `since_msg_id` resume parameter (§4) uses UUIDv7 byte-comparison for correct ordering even across pod restarts.
- Clock skew: server timestamp always wins; client display time uses server `created_at`.

---

## 3. WebSocket Protocol

### 3.1 Wire Format

All frames: UTF-8 JSON. Binary frames not used (media travels via S3, not WS).

```
Envelope:
{
  "type": "<message_type>",
  "payload": { ... },
  "request_id": "<client_uuid4>",   // echo'd in ack (client→server only)
  "ts": "<ISO8601>"                  // sender wall-clock (informational)
}
```

### 3.2 Client → Server Message Types

| `type` | Payload fields | Description |
|---|---|---|
| `send` | `body` (str, ≤4000 ch), `reply_to?` (msg_id), `client_nonce` (uuid4) | Send a text message. Server validates, runs moderation, persists, then broadcasts |
| `typing` | `state` (`start` \| `stop`) | Typing indicator. Rate-limited: max 1 `start` per 3 s per connection |
| `read_ack` | `up_to_msg_id` (uuid7) | Mark all messages up to this ID read for the sender |
| `ping` | _(empty)_ | Application-level keepalive. Server responds with `pong`. Use every 8 min to beat the 10-min API GW idle timeout |
| `reconnect` | `since_msg_id` (uuid7) | Sent immediately after WS `accept` if client has a stored last-ack'd ID (§4) |

### 3.3 Server → Client Message Types

| `type` | Payload fields | Description |
|---|---|---|
| `message` | Full `ChatMessageOut` object (see §5.1) | New message delivered to room |
| `message_ack` | `client_nonce`, `msg_id`, `created_at` | Ack to the sender's `send` frame; allows optimistic dedup |
| `presence` | `profile_id`, `online` (bool), `last_seen_at` | Presence update for a participant |
| `typing` | `profile_id`, `state` (`start`\|`stop`) | Typing indicator from other participant |
| `read` | `profile_id`, `up_to_msg_id`, `read_at` | Read receipt update |
| `replay` | `messages` (array of `ChatMessageOut`), `has_more` (bool) | Response to `reconnect` — replays missed messages |
| `room_state` | `state` (`open`\|`read_only`\|`archived`) | Room state change (e.g., block fires) |
| `error` | `code` (str), `message` (str), `request_id?` | Protocol or business logic error |
| `pong` | _(empty)_ | Response to client `ping` |
| `connection_expiry_warning` | `expires_in_seconds` (int) | Sent 5 min before the 2-hour API GW connection limit. Client should reconnect |

### 3.4 Error Codes

| `code` | Meaning |
|---|---|
| `AUTH_INVALID` | Bearer token missing or expired |
| `ROOM_NOT_FOUND` | Room does not exist or user is not a participant |
| `ROOM_READ_ONLY` | Room is in read-only state (block or archive) |
| `MESSAGE_TOO_LONG` | `body` exceeds 4000 characters |
| `MODERATION_HOLD` | Message held pending mod review (0.7–0.9 band) |
| `MODERATION_REJECTED` | Message auto-hidden (≥ 0.9); user temporarily muted |
| `RATE_LIMITED` | Too many frames |
| `INTERNAL_ERROR` | Unexpected server error |

---

## 4. Reconnect + Resume Protocol

### 4.1 Client-Side State

The RN client persists to AsyncStorage:
- `last_ack_msg_id`: the UUIDv7 of the last message for which the client received a `message` or `message_ack` frame.
- `pending_sends`: a queue of unsent `send` payloads (offline writes, master NFR-7).

### 4.2 Reconnect Sequence

```
1. WS disconnect detected (error or intentional close)
2. Client enters exponential-backoff retry loop:
     attempt 1: 1s, attempt 2: 2s, attempt 3: 4s … cap 60s
3. On new WS connection accepted:
   a. If last_ack_msg_id exists → send { type: "reconnect", since_msg_id: last_ack_msg_id }
   b. Server responds with { type: "replay", messages: [...], has_more: bool }
      - Server fetches messages WHERE id > since_msg_id AND room_id = ? ORDER BY id ASC LIMIT 200
      - If has_more=true, client fetches additional pages via REST GET /chat/rooms/{id}/messages?cursor=...
4. Client de-duplicates replay messages against its local cache using msg_id.
5. Client drains pending_sends queue (in order). Each is sent as a normal `send` frame.
6. If no last_ack_msg_id → full initial load via REST pagination (first-open scenario).
```

### 4.3 Connection Expiry Handling (2-Hour API GW Limit)

- Server tracks connection start time. At t = 115 min (5 min before expiry), server sends `connection_expiry_warning { expires_in_seconds: 300 }`.
- Client performs a clean reconnect: opens a new WS, sends `reconnect` with `since_msg_id`, waits for `replay`, then closes the old connection.
- This ensures zero message loss across the mandatory reconnect.

### 4.4 Offline Write Queue (NFR-7)

- When client has no active WS connection and user sends a message, it is appended to `pending_sends` in AsyncStorage with `client_nonce` and `timestamp`.
- UI shows a "pending" indicator (clock icon) on the optimistic bubble.
- On reconnect + replay complete, the queue is drained in FIFO order.
- Each queued message is sent as a normal `send` frame; the server assigns a real `created_at` and returns `message_ack`. Client updates the bubble from pending → delivered.

---

## 5. Detailed Data Model

### 5.1 ChatRoom

```sql
CREATE TABLE chat_room (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    collaboration_id UUID NOT NULL REFERENCES collaboration(id) ON DELETE CASCADE,
    participant_ids  UUID[2] NOT NULL,              -- [profile_id_a, profile_id_b]
    state           TEXT NOT NULL DEFAULT 'open'   -- open | read_only | archived
                    CHECK (state IN ('open','read_only','archived')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    archived_at     TIMESTAMPTZ,
    CONSTRAINT chk_two_participants CHECK (cardinality(participant_ids) = 2)
);

CREATE INDEX idx_chat_room_collaboration ON chat_room(collaboration_id);
CREATE INDEX idx_chat_room_participants  ON chat_room USING GIN(participant_ids);
```

### 5.2 ChatMessage

```sql
CREATE TABLE chat_message (
    id                  UUID PRIMARY KEY,           -- UUIDv7 (time-ordered)
    room_id             UUID NOT NULL REFERENCES chat_room(id),
    sender_profile_id   UUID NOT NULL,
    type                TEXT NOT NULL               -- text|voice|image|video|audio|doc|link|system
                        CHECK (type IN ('text','voice','image','video','audio','doc','link','system')),
    body                TEXT,                       -- text content or NULL for media-only
    media_key           TEXT,                       -- S3 object key, NULL for text
    mime                TEXT,
    size_bytes          BIGINT,
    duration_ms         INTEGER,                    -- voice/video only
    reply_to            UUID REFERENCES chat_message(id),
    client_nonce        UUID,                       -- for dedup
    edited_at           TIMESTAMPTZ,
    deleted_at          TIMESTAMPTZ,                -- soft-delete (immutable from user UI)
    moderation_score    REAL,
    moderation_status   TEXT NOT NULL DEFAULT 'pending'
                        CHECK (moderation_status IN ('pending','allowed','soft_warn','hidden','auto_hidden')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_chat_msg_room_id    ON chat_message(room_id, id);       -- primary query pattern
CREATE INDEX idx_chat_msg_sender     ON chat_message(sender_profile_id);
CREATE INDEX idx_chat_msg_nonce      ON chat_message(client_nonce) WHERE client_nonce IS NOT NULL;
```

**Retention**: rows are never hard-deleted for the account lifetime + 3 years. `deleted_at` set for user-initiated soft-deletes; body redacted to `[deleted]`, media_key nulled after user requests deletion. Pseudonymised after account deletion (sender_profile_id replaced with a stable hash). Backup purge at 3-year mark triggered by `collab-svc` lifecycle events.

### 5.3 ChatMessageRevision

```sql
CREATE TABLE chat_message_revision (
    id          BIGSERIAL PRIMARY KEY,
    msg_id      UUID NOT NULL REFERENCES chat_message(id),
    version     SMALLINT NOT NULL,
    body        TEXT NOT NULL,
    edited_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_revision_msg_version ON chat_message_revision(msg_id, version);
```

Edit flow: `POST /chat/rooms/{id}/messages/{msg_id}/edit` inserts a new revision row, updates `chat_message.body` and `edited_at`. Original body preserved in revision v1.

### 5.4 ChatAttachment

```sql
CREATE TABLE chat_attachment (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    msg_id                UUID NOT NULL REFERENCES chat_message(id),
    kind                  TEXT NOT NULL,            -- image|audio|video|doc|voice
    s3_key                TEXT NOT NULL,
    signed_url_cache_until TIMESTAMPTZ,
    signed_url_cache      TEXT
);
```

Signed URL cache: refreshed lazily when `signed_url_cache_until < now() + 30s`. CloudFront signed URLs with 5-minute TTL; cache in this column to avoid redundant KMS calls.

### 5.5 Presence (Redis)

```
Key:   chat:presence:{room_id}:{profile_id}
Type:  Hash
Fields:
  online       "1" | "0"
  typing       "1" | "0"
  last_seen_at "<ISO8601>"
TTL:   90 seconds (reset on every ping/message from client)

Pub/sub channel per room: chat:room:{room_id}
Published envelope matches server→client wire format.
```

### 5.6 Read Receipt Model

One row per (room, participant) tracking the high-water mark:

```sql
CREATE TABLE chat_read_receipt (
    room_id        UUID NOT NULL REFERENCES chat_room(id),
    profile_id     UUID NOT NULL,
    last_read_msg_id UUID,           -- UUIDv7; NULL = nothing read
    last_read_at   TIMESTAMPTZ,
    PRIMARY KEY (room_id, profile_id)
);
```

`POST /chat/rooms/{id}/read` with `{up_to_msg_id}` upserts this row using `ON CONFLICT DO UPDATE SET last_read_msg_id = EXCLUDED.last_read_msg_id WHERE EXCLUDED.last_read_msg_id > chat_read_receipt.last_read_msg_id` (monotonic — never move the pointer backward).

Server broadcasts a `read` WS event to the room after upsert so the other participant's UI updates in real time.

Unread count query:
```sql
SELECT count(*) FROM chat_message
WHERE room_id = $1
  AND id > COALESCE((SELECT last_read_msg_id FROM chat_read_receipt WHERE room_id=$1 AND profile_id=$2), '00000000-0000-0000-0000-000000000000'::uuid)
  AND sender_profile_id <> $2
  AND deleted_at IS NULL
  AND moderation_status IN ('allowed','soft_warn');
```

---

## 6. Block-Aware Behavior

| Event | Trigger | `chat_room.state` | User-visible behaviour |
|---|---|---|---|
| `block.created` published by auth/profile-svc | Either participant blocks the other | `open` → `read_only` | Both users see a banner: "This conversation is now read-only." No new messages can be sent. History fully readable. |
| Room in `read_only` | Any `send` frame received | — | Server returns `{ type: "error", code: "ROOM_READ_ONLY" }` |
| +30 days post-block | Celery Beat job in `collab-svc` | `read_only` → `archived` | Room disappears from active list; accessible only via history |
| Block lifted (unblock) | `block.removed` event | `archived` stays archived (cannot un-archive via unblock); `read_only` → `open` if not yet 30 days | Banner removed; sends re-enabled |
| Chat export during block | Either participant, Premium | — | Still allowed. `GET /collabs/{id}/export` checks entitlement, not room state |

`chat-svc` subscribes to `block.created` and `block.removed` RabbitMQ events (published by `auth-svc`). On receipt, it:
1. Updates `chat_room.state` in Postgres.
2. Publishes a `{ type: "room_state", state: "read_only" }` event to the Redis pub/sub channel for the room, which all connected pods fan out to active WS clients.

---

## 7. Read Receipts Model (Detailed)

- **Granularity**: per-room high-water mark (not per-message). Chosen for simplicity and to avoid O(messages) rows.
- **Delivery**: `read_ack` WS frame from client triggers upsert; server broadcasts `read` event to room.
- **Auto-read**: when the chat screen is focused and messages arrive, the client automatically sends `read_ack` for the newest visible message (after a 2-second debounce to avoid spamming on fast scroll).
- **Badge count**: `notification-svc` uses the unread count query (§5.6) to drive the push badge number. Subscribed to `chat.message.sent` and `chat.read_ack` events.
- **Privacy**: read receipts are soft / non-E2EE. They indicate the server delivered and the client likely viewed, not cryptographic confirmation. This is documented in the UX (no "blue ticks" promise).
- **Blocked rooms**: read receipts frozen at block time. No new `read_ack` processed while `state = read_only`.

---

## 8. Media Upload Flow

### 8.1 Sequence Diagram (ASCII)

```
RN Client          chat-svc         media-svc         S3              moderation-svc
    |                  |                |              |                     |
    |--- (1) WS open, join room ------->|              |                     |
    |                  |                |              |                     |
    | User picks file  |                |              |                     |
    |--- (2) POST /media/upload-url ------------------->|                     |
    |       {room_id, kind, mime, size_bytes}           |                     |
    |                  |                |-- validate caps & mime              |
    |                  |                |-- gen presigned PUT URL (5min TTL) |
    |<-- (3) { upload_url, s3_key } ------|              |                     |
    |                  |                |              |                     |
    |--- (4) PUT {upload_url} + file body (direct to S3)----------->|         |
    |<-- (5) 200 OK -------------------------------------------------|         |
    |                  |                |              |                     |
    |--- (6) POST /media/confirm ------->|              |                     |
    |       {room_id, kind, s3_key, mime, size_bytes, duration_ms?}           |
    |                  |                |-- HEAD s3_key (verify upload)       |
    |                  |                |-- download bytes (VPC endpoint)     |
    |                  |                |              |                     |
    |                  |                |--- (7) POST /internal/scan -------->|
    |                  |                |       {subject_id=s3_key, kind}     |
    |                  |                |<-- (8) { score, status } ----------|
    |                  |                |              |                     |
    |                  |           if score < 0.9:     |                     |
    |                  |                |-- INSERT chat_message (moderation_status=allowed|soft_warn)
    |                  |                |-- publish to Redis chat:room:{room_id}
    |<-- (9) WS "message" frame --------|              |                     |
    |   (other participant receives too)|              |                     |
    |                  |                |              |                     |
    |                  |           if score >= 0.9:    |                     |
    |                  |                |-- INSERT chat_message (moderation_status=auto_hidden)
    |                  |                |-- publish moderation.action_taken event
    |                  |                |-- DO NOT broadcast to room          |
    |<-- (10) WS "error" {code:"MODERATION_REJECTED"} (to sender only)       |
    |                  |                |              |                     |
    |   [async] moderator reviews case (1h SLA) -------------------------------->
```

### 8.2 Signed URL Rotation

CloudFront signed URLs expire in 5 minutes. `media-svc` caches the generated URL in `chat_attachment.signed_url_cache` with `signed_url_cache_until`. On `GET /media/{s3_key}/signed-url`, if `signed_url_cache_until > now() + 60s`, return cached URL; else generate a new one.

CloudFront key pair stored in AWS Secrets Manager. `media-svc` uses boto3 CloudFront signer.

### 8.3 File Size + MIME Whitelist Enforcement

| Kind | Max size | Allowed MIME types |
|---|---|---|
| image | 10 MB | `image/jpeg`, `image/png`, `image/gif`, `image/webp`, `image/heic` |
| audio | 50 MB | `audio/mp4`, `audio/mpeg`, `audio/wav`, `audio/ogg`, `audio/aac` |
| video | 250 MB | `video/mp4`, `video/quicktime`, `video/webm` |
| doc | 25 MB | `application/pdf`, `application/msword`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `text/plain` |
| voice | 10 MB | `audio/mp4` (m4a from expo-av) |

Executables, scripts, and archives are rejected. `media-svc` validates on `POST /media/upload-url` (before issuing presigned URL) and on `POST /media/confirm` (after upload, comparing S3 object Content-Type header to submitted mime).

---

## 9. Moderation Integration

### 9.1 Text Message Flow

Every `send` frame from the client triggers an inline moderation check before persisting or broadcasting:

```python
async def handle_send(ws: WebSocket, payload: SendPayload, room: ChatRoom):
    # 1. Validate body length, room state
    if room.state != 'open':
        await ws.send_json(error('ROOM_READ_ONLY'))
        return

    # 2. Call moderation-svc internal scan (HTTP to moderation-svc, <50ms P95 budget)
    scan = await moderation_client.scan_text(payload.body, subject_type='chat_message')

    # 3. Route by score
    if scan.score >= 0.9:
        # Insert as auto_hidden; temp-mute user; do NOT broadcast
        await persist_message(room, payload, moderation_status='auto_hidden', score=scan.score)
        await publish_moderation_event(scan, action='auto_hide_temp_mute')
        await ws.send_json(error('MODERATION_REJECTED'))
        return

    if 0.7 <= scan.score < 0.9:
        # Insert as hidden; queue for mod review; DO NOT broadcast yet
        msg = await persist_message(room, payload, moderation_status='hidden', score=scan.score)
        await publish_moderation_event(scan, action='hold_for_review')
        # Soft-warn sender
        await ws.send_json(error('MODERATION_HOLD'))
        return

    if 0.4 <= scan.score < 0.7:
        # Insert as soft_warn; broadcast; notify sender with inline warning UI
        msg = await persist_message(room, payload, moderation_status='soft_warn', score=scan.score)
        await broadcast(room, message_envelope(msg))
        await ws.send_json(ack_with_warning(msg, 'This message may have violated community guidelines.'))
        return

    # score < 0.4: clean
    msg = await persist_message(room, payload, moderation_status='allowed', score=scan.score)
    await broadcast(room, message_envelope(msg))
    await ws.send_json(message_ack(msg, payload.client_nonce))
```

**Latency budget for text mod**: `moderation-svc` scan must return in < 200 ms P95 (spec NFR). `chat-svc` calls `moderation-svc` via internal Kubernetes service (ClusterIP), not through the public API Gateway, to minimise latency.

### 9.2 Media Moderation (Async)

As shown in §8.1 steps 7–8, media scanning is synchronous within the `POST /media/confirm` handler but async from the perspective of the WS message delivery. The client sees the upload succeed (step 6 returns 202), and only receives the WS `message` frame (step 9) once scanning passes. This adds up to 10 s for video (per spec NFR); client shows a "processing…" spinner on the optimistic bubble.

For ≥ 0.9 risk media: message is persisted as `auto_hidden`; sender receives `error { code: "MODERATION_REJECTED" }`; no WS broadcast to recipient. A `moderation.action_taken` event is published; moderator queue receives the case with 1h SLA.

### 9.3 IP/DMCA + Harassment Escalation

Per §008 spec: these categories always route to human moderators regardless of score. `moderation-svc` exposes category classification alongside the numeric score. `chat-svc` treats any `scan.categories` containing `harassment_threat` or `dmca` the same as score ≥ 0.9 (hold + mute) and adds the `ESCALATE_HUMAN` flag to the moderation event.

### 9.4 Moderation Events Published to RabbitMQ

| Event | Exchange | Consumer |
|---|---|---|
| `chat.message.sent` | `chat` | §009 collab-svc (last_activity_at update), §014 notification-svc (push) |
| `chat.media.scanned` | `chat` | §009 collab-svc (asset tracking) |
| `chat.media.flagged` | `chat` | §008 moderation-svc (case creation) |
| `moderation.action_taken` (emitted by §008) | `moderation` | §007 chat-svc (room_state update, temp-mute enforcement) |

---

## 10. API Contracts

### 10.1 REST — chat-svc

All endpoints require `Authorization: Bearer <jwt>` header. Validated by `gateway` service before forwarding.

#### Room Endpoints

```
GET  /chat/rooms
  Query: ?cursor=<uuid7>&limit=20
  Response 200: {
    rooms: [ChatRoomSummary],
    next_cursor: str | null
  }

ChatRoomSummary: {
  id: uuid,
  collaboration_id: uuid,
  state: "open"|"read_only"|"archived",
  participants: [ProfileStub],
  last_message: ChatMessageOut | null,
  unread_count: int,
  created_at: ISO8601
}

GET  /chat/rooms/{room_id}
  Response 200: ChatRoomDetail (full, includes read_receipts for both participants)

GET  /chat/rooms/{room_id}/messages
  Query: ?cursor=<uuid7>&limit=50&direction=before|after
  Response 200: {
    messages: [ChatMessageOut],
    next_cursor: str | null
  }
  Note: ordered by id DESC (newest first) by default; direction=after for replay.

POST /chat/rooms/{room_id}/messages
  Body: { body: str, reply_to?: uuid, client_nonce: uuid4 }
  Response 201: ChatMessageOut
  Note: Equivalent to WS `send`; moderation applied synchronously.

POST /chat/rooms/{room_id}/messages/{msg_id}/edit
  Body: { body: str }
  Response 200: ChatMessageOut (updated)
  Constraint: sender only; text messages only; creates revision row.

POST /chat/rooms/{room_id}/read
  Body: { up_to_msg_id: uuid7 }
  Response 204
```

#### ChatMessageOut Schema

```json
{
  "id": "uuid7",
  "room_id": "uuid",
  "sender_profile_id": "uuid",
  "sender": { "display_name": "str", "avatar_url": "str?" },
  "type": "text|voice|image|video|audio|doc|link|system",
  "body": "str?",
  "media_key": "str?",
  "media_url": "str?",              // signed CloudFront URL, 5-min TTL
  "mime": "str?",
  "size_bytes": "int?",
  "duration_ms": "int?",
  "reply_to": "uuid?",
  "reply_preview": { ... }?,        // embedded stub of replied-to message
  "moderation_status": "allowed|soft_warn|hidden|auto_hidden",
  "edited_at": "ISO8601?",
  "created_at": "ISO8601"
}
```

Note: `moderation_status` of `hidden` or `auto_hidden` messages is only visible to the sender (so they know why delivery failed). The recipient never receives these messages.

### 10.2 REST — media-svc

```
POST /media/upload-url
  Body: {
    room_id: uuid,
    kind: "image"|"audio"|"video"|"doc"|"voice",
    mime: str,
    size_bytes: int
  }
  Response 200: {
    upload_url: str,       // presigned S3 PUT, 5-min TTL
    s3_key: str
  }
  Errors: 400 (mime not whitelisted), 413 (size exceeds cap), 403 (room not found or not participant)

POST /media/confirm
  Body: {
    room_id: uuid,
    kind: str,
    s3_key: str,
    mime: str,
    size_bytes: int,
    duration_ms?: int
  }
  Response 202: { status: "processing", pending_msg_id: uuid }
  Note: Scanning async from client perspective; WS delivers message when ready.

GET /media/{s3_key}/signed-url
  Query: ?room_id=<uuid>  (auth: must be participant of the room containing this key)
  Response 200: { url: str, expires_at: ISO8601 }
```

### 10.3 WebSocket Endpoint

```
WSS wss://api.<domain>/chat/{room_id}?token=<jwt>

Connection lifecycle:
  - API Gateway authenticates token via Lambda authorizer before upgrade
  - chat-svc receives $connect event → validates room membership → subscribes to Redis channel
  - $disconnect → unsubscribes → updates presence
  - $default → routes by frame `type` field

Rate limits (enforced in chat-svc):
  - max 30 `send` frames / minute / connection
  - max 1 `typing` start / 3 seconds / connection
  - max 60 `read_ack` / minute / connection
  - max 5 `reconnect` frames per connection lifetime (prevent resume-loop abuse)
```

### 10.4 Internal Scan API (chat-svc → moderation-svc)

```
POST /internal/scan/text
  Body: { subject_id: str, body: str, context: "chat_message" }
  Response 200: { score: float, status: str, categories: [str] }

POST /internal/scan/media
  Body: { subject_id: str, s3_key: str, kind: str, mime: str }
  Response 200: { score: float, status: str, categories: [str] }
```

These are ClusterIP-only endpoints (not exposed through API Gateway). Authenticated via mutual service-account JWT (IRSA).

---

## 11. Implementation Tasks

### Legend

- **Services**: `CS` = chat-svc, `MS` = media-svc, `RN` = React Native client, `INF` = infrastructure
- **Blocks**: task cannot start until listed tasks are complete
- **Est**: rough engineering-hours estimate per task (single engineer)

---

### Cluster A — Infrastructure & Scaffold

| ID | Title | Outcome | Est (h) | Blocks | Blocked By |
|---|---|---|---|---|---|
| T-01 | EKS namespace + Helm chart for chat-svc | `chat-svc` deployable to EKS with HPA on CPU + custom `ws_connections` metric | 8 | T-02, T-03 | §002 Platform complete |
| T-02 | EKS namespace + Helm chart for media-svc | `media-svc` deployable with S3 + Rekognition IAM via IRSA | 6 | T-10 | §002 Platform complete |
| T-03 | API Gateway WebSocket API provisioned (Terraform) | WS endpoint live at `wss://api.<domain>/chat/{room_id}`; Lambda authorizer wired | 10 | T-04 | T-01 |
| T-04 | Lambda authorizer for API Gateway WS | JWT validated before `$connect`; `profile_id` injected into connection context | 6 | T-05 | T-03, §003 Auth JWT |
| T-05 | RabbitMQ exchanges declared | `chat` exchange with `chat.message.sent`, `chat.media.scanned`, `chat.media.flagged` routing keys | 4 | — | §002 Platform RabbitMQ |
| T-06 | Postgres schema migrations for chat tables | `chat_room`, `chat_message`, `chat_message_revision`, `chat_attachment`, `chat_read_receipt` created with indexes | 6 | — | §002 Postgres |
| T-07 | Redis presence key design + helper library | `AsyncPresenceManager` with get/set/expire; pub/sub subscribe/publish helpers | 6 | T-08 | §002 Redis |
| T-08 | Cross-pod fanout integration test | Two pods, two WS clients in same room; message sent by one reaches the other via Redis pub/sub | 8 | — | T-07, T-11 |

---

### Cluster B — chat-svc Backend

| ID | Title | Outcome | Est (h) | Blocks | Blocked By |
|---|---|---|---|---|---|
| T-09 | FastAPI app skeleton + Starlette WS router | `/chat/{room_id}` WS endpoint; connection manager singleton | 8 | T-10 | T-01 |
| T-10 | JWT-authenticated WS connection + room membership check | Only participants can join a room; error frame sent + connection closed otherwise | 6 | T-11 | T-09, T-04 |
| T-11 | `send` handler — text messages | Receives `send` frame, validates, persists to Postgres, publishes to Redis, broadcasts `message` + `message_ack` | 12 | T-17, T-18 | T-10, T-06, T-07 |
| T-12 | `typing` handler + presence | Updates Redis presence hash; broadcasts `typing` frame to room; rate-limited | 4 | — | T-11 |
| T-13 | `read_ack` handler | Upserts `chat_read_receipt`; broadcasts `read` frame | 4 | — | T-11 |
| T-14 | `ping`/`pong` + keepalive | Responds to `ping` with `pong`; server-side idle ticker resets on any frame | 3 | — | T-09 |
| T-15 | `reconnect` handler + replay | Fetches messages since `since_msg_id`, returns `replay` frame; handles `has_more` | 8 | — | T-11 |
| T-16 | Connection expiry warning (2hr limit) | Background task per connection; sends `connection_expiry_warning` at t=115min | 4 | — | T-14 |
| T-17 | Moderation integration — text | Calls `moderation-svc` `/internal/scan/text`; routes by score; returns correct error frames | 10 | — | T-11, §008 scan endpoint |
| T-18 | Block event subscriber | Consumes `block.created` / `block.removed` from RabbitMQ; updates `chat_room.state`; broadcasts `room_state` WS frame | 8 | — | T-11 |
| T-19 | `chat.message.sent` publisher | After successful persist + broadcast, publishes event to RabbitMQ | 4 | — | T-11, T-05 |
| T-20 | REST endpoints — rooms + messages | `GET /chat/rooms`, `GET /chat/rooms/{id}`, `GET /chat/rooms/{id}/messages` with cursor pagination | 10 | — | T-06 |
| T-21 | REST endpoint — send message | `POST /chat/rooms/{id}/messages` (same moderation logic as WS `send`) | 4 | — | T-17 |
| T-22 | REST endpoint — edit message | `POST /chat/rooms/{id}/messages/{msg_id}/edit`; revision row insert; WS broadcast of updated message | 6 | — | T-20 |
| T-23 | REST endpoint — read receipt | `POST /chat/rooms/{id}/read`; monotonic upsert; WS broadcast | 4 | — | T-13 |
| T-24 | Room auto-creation on `match.created` | Subscribes to `match.created` RabbitMQ event; creates `chat_room` row + emits `collab.created` | 6 | — | T-06, T-05, §006 Invite |
| T-25 | Internal audit-log endpoint | `GET /internal/rooms/{id}/messages/all` (admin-svc + collab-svc export); returns all messages + revisions in chronological order | 6 | — | T-20 |

---

### Cluster C — media-svc Backend

| ID | Title | Outcome | Est (h) | Blocks | Blocked By |
|---|---|---|---|---|---|
| T-26 | FastAPI app skeleton + S3 client | IRSA-authenticated boto3 client; S3 bucket name from env | 4 | T-27 | T-02 |
| T-27 | `POST /media/upload-url` | Validates MIME + size; generates presigned PUT URL (5-min TTL); returns `{upload_url, s3_key}` | 8 | T-28 | T-26 |
| T-28 | `POST /media/confirm` + async scan pipeline | HEAD verify → download → scan (moderation + dup) → persist `chat_message` + `chat_attachment` → publish to Redis | 16 | T-29 | T-27, T-17, §008 scan endpoint |
| T-29 | `GET /media/{s3_key}/signed-url` | CloudFront signed URL; cached in `chat_attachment.signed_url_cache`; auth: participant check | 8 | — | T-28 |
| T-30 | pHash dup-check integration | Download image bytes; compute pHash via `imagehash` library; query `media_phash` index; flag if distance < threshold | 8 | — | T-28 |
| T-31 | Chromaprint audio dup integration | Shell out to `fpcalc`; query `media_fingerprint` index; flag near-duplicates | 6 | — | T-28 |
| T-32 | `chat.media.scanned` + `chat.media.flagged` events | Published to RabbitMQ after every confirm; flagged event if score >= 0.4 | 4 | — | T-28, T-05 |

---

### Cluster D — RN Chat Screen

| ID | Title | Outcome | Est (h) | Blocks | Blocked By |
|---|---|---|---|---|---|
| T-33 | WS connection manager (RN) | `useChatSocket` hook; connects on mount; reconnects with expo backoff; stores `last_ack_msg_id` in AsyncStorage | 12 | T-34 | T-11, §003 Auth token in RN |
| T-34 | Message list — virtualized | `FlashList` (Shopify) with inverted layout; renders `ChatMessageOut`; groups by date; sticky date headers | 12 | T-35 | T-33 |
| T-35 | Optimistic send + pending state | Message bubble added immediately; `client_nonce` used for dedup; updated to confirmed state on `message_ack` | 8 | — | T-34 |
| T-36 | Offline write queue | `usePendingQueue` hook; AsyncStorage persistence; drains on reconnect | 8 | — | T-35, T-33 |
| T-37 | Typing indicator UI | Animated 3-dot bubble appears when `typing { state: "start" }` received; hides on `stop` or 5s timeout | 4 | — | T-34 |
| T-38 | Presence indicator | Online/offline dot on the other user's avatar in the header; sourced from WS `presence` frames | 3 | — | T-34 |
| T-39 | Read receipts UI | Tick marks (single = delivered, double = read) below sender's own bubbles | 4 | — | T-13, T-34 |
| T-40 | Reply-to threading UI | Tap-to-reply shows inline preview bar in composer; `reply_to` sent in `send` frame; message bubble shows quoted preview | 6 | — | T-35 |
| T-41 | Edit message UI | Long-press menu → Edit; pre-fills composer; sends `PATCH`; bubble shows "(edited)" label | 4 | — | T-22 |
| T-42 | Read-only room UI | Banner at top: "This chat is read-only." Composer hidden/disabled. | 3 | — | T-18 |
| T-43 | Report button | Long-press on any message → "Report" → `POST /reports` to moderation-svc → confirmation toast | 4 | — | §008 report endpoint |

---

### Cluster E — Message List Virtualization

| ID | Title | Outcome | Est (h) | Blocks | Blocked By |
|---|---|---|---|---|---|
| T-44 | Infinite scroll (older messages) | On scroll to top, fetch next page via `GET /chat/rooms/{id}/messages?cursor=...&direction=before`; prepend to list without scroll-jump | 8 | — | T-34, T-20 |
| T-45 | Auto-scroll to bottom | On new incoming message: if user is near bottom → auto-scroll; else show "N new messages ↓" badge | 5 | — | T-34 |
| T-46 | Jump-to-message | From reply-preview tap; smooth animated scroll via `FlashList.scrollToIndex`; handles out-of-viewport messages with REST fetch | 6 | — | T-34, T-44 |

---

### Cluster F — Voice Note Recorder

| ID | Title | Outcome | Est (h) | Blocks | Blocked By |
|---|---|---|---|---|---|
| T-47 | Hold-to-record button | Press-and-hold starts recording via `expo-av`; release stops; swipe-left cancels | 8 | — | T-28 |
| T-48 | Recording waveform visualization | Live amplitude bars during recording (metering from `expo-av`); max 5-minute cap | 6 | — | T-47 |
| T-49 | Voice note upload + delivery | On release: `POST /media/upload-url` → PUT to S3 → `POST /media/confirm`; WS `message` arrives with `type=voice` | 6 | — | T-47, T-28 |
| T-50 | Voice note playback UI | Play/pause button + seek bar + elapsed/total time; `Audio.Sound.createAsync` | 8 | — | T-49 |

---

### Cluster G — File Picker + Media Viewers

| ID | Title | Outcome | Est (h) | Blocks | Blocked By |
|---|---|---|---|---|---|
| T-51 | File picker (document + audio + video) | `expo-document-picker` with MIME filter; validates size client-side before upload | 6 | — | T-28 |
| T-52 | Image picker + thumbnail in message | `expo-image-picker`; shows thumbnail preview in composer before send; sends via presigned URL flow | 6 | — | T-28 |
| T-53 | Image lightbox | Full-screen modal with pinch-to-zoom; uses `react-native-zoom-toolkit` or `expo-image` full-screen mode | 6 | — | T-52 |
| T-54 | Video player in chat | Inline autoplay-muted preview; tap to expand to full-screen player using `expo-video` | 8 | — | T-51 |
| T-55 | Audio player in chat | Seekable audio player bubble (non-voice note audio files); same component as T-50 | 4 | — | T-51, T-50 |
| T-56 | Document viewer | Open PDF/doc files via `expo-sharing` → system viewer; or in-app PDF with `react-native-pdf` | 4 | — | T-51 |

---

### Cluster H — Tests

| ID | Title | Outcome | Est (h) | Blocks | Blocked By |
|---|---|---|---|---|---|
| T-57 | pytest: chat-svc unit tests | Handler logic; mock Redis + Postgres; moderation scoring paths; reconnect replay | 16 | — | T-11–T-25 |
| T-58 | pytest: media-svc unit tests | Presign, confirm, scan pipeline, dup-check; mock S3 + Rekognition | 12 | — | T-26–T-32 |
| T-59 | pytest: integration test — WS round-trip | Two clients in same room via TestClient WS; send → receive < 500ms | 8 | — | T-57 |
| T-60 | pytest: integration test — cross-pod fanout | Two FastAPI test instances sharing Redis; verify message arrives on pod 2 | 8 | — | T-08, T-57 |
| T-61 | pytest: moderation path tests | Score 0.3 → delivered; 0.5 → soft-warn; 0.8 → held; 0.95 → auto-hide; mock moderation-svc | 8 | — | T-17, T-57 |
| T-62 | pytest: block enforcement | `block.created` event → room read-only → subsequent `send` returns `ROOM_READ_ONLY` | 6 | — | T-18, T-57 |
| T-63 | pytest: read receipt monotonic constraint | Sending older `up_to_msg_id` does not move pointer backward | 4 | — | T-13, T-57 |
| T-64 | Playwright: chat web smoke (consumer-web) | Open room, send message, verify appears in message list | 6 | — | T-34 |
| T-65 | Detox: RN E2E — basic chat flow | Two simulated users match → room opens → message send → delivered to other device | 16 | — | T-35, T-39 |
| T-66 | Detox: RN E2E — voice note | Hold-record → release → playback in room | 8 | — | T-50 |
| T-67 | Detox: RN E2E — image upload | Pick image → upload → lightbox opens on tap | 6 | — | T-53 |
| T-68 | Detox: RN E2E — offline queue | Disable network → send message → re-enable → message delivered | 8 | — | T-36 |
| T-69 | k6 load test: WS latency at 1k concurrent rooms | P95 e2e < 500ms with 2000 concurrent WS connections | 12 | — | T-08, T-60 |

---

### Summary Estimates

| Cluster | Tasks | Total Est (h) |
|---|---|---|
| A — Infrastructure | T-01–T-08 | 54 |
| B — chat-svc backend | T-09–T-25 | 118 |
| C — media-svc backend | T-26–T-32 | 54 |
| D — RN chat screen | T-33–T-43 | 78 |
| E — Message list virtualization | T-44–T-46 | 19 |
| F — Voice note recorder | T-47–T-50 | 28 |
| G — File picker + viewers | T-51–T-56 | 34 |
| H — Tests | T-57–T-69 | 118 |
| **Total** | **69 tasks** | **~503 h** |

---

## 12. Acceptance Criteria

### 12.1 Core Message Delivery

| # | Criterion | Verification |
|---|---|---|
| AC-01 | Match event creates chat room within 2 seconds | pytest: publish `match.created` event; assert `chat_room` row exists within 2s |
| AC-02 | Text message e2e round-trip P95 < 500ms | k6 load test T-69; median also measured and < 200ms target |
| AC-03 | Message received by both participants (sender `message_ack` + recipient `message`) | pytest T-59; Detox T-65 |
| AC-04 | Messages persist to Postgres after WS disconnect | pytest: kill WS mid-session; query Postgres; message row exists |
| AC-05 | `client_nonce` deduplication: same nonce not double-inserted | pytest: send same frame twice; assert single row in `chat_message` |

### 12.2 Reconnect + Replay

| # | Criterion | Verification |
|---|---|---|
| AC-06 | WS disconnect + reconnect replays missed messages via `since_msg_id` | pytest T-59: disconnect client A, send 5 messages from client B, reconnect A with `since_msg_id`, assert all 5 received in `replay` frame |
| AC-07 | `has_more=true` when replay exceeds 200 messages; client fetches remainder via REST | pytest: seed 250 messages; reconnect; verify `has_more=true`; REST fetch page 2 |
| AC-08 | Offline queue drains on reconnect (NFR-7) | Detox T-68: airplane mode → 3 messages sent → reconnect → all 3 delivered in order |
| AC-09 | `connection_expiry_warning` sent at 115 minutes | pytest: mock time to t=115min; assert `connection_expiry_warning` frame sent |
| AC-10 | Client-triggered reconnect (on expiry warning) delivers no missed messages | pytest: reconnect after warning; assert smooth handoff with empty replay |

### 12.3 Media Upload

| # | Criterion | Verification |
|---|---|---|
| AC-11 | Presigned URL issued for whitelisted MIME; rejected for disallowed | pytest T-58: `image/jpeg` → 200; `application/x-sh` → 400 |
| AC-12 | File too large returns 413 before presign | pytest: `size_bytes = 11*1024*1024` for image → 413 |
| AC-13 | Client PUT direct to S3; chat-svc never proxies bytes | Architecture verified by code review; no S3 bytes pass through chat-svc handlers |
| AC-14 | After `confirm`, WS `message` frame arrives to both participants | pytest T-59 with file fixture; Detox T-67 |
| AC-15 | Voice note: hold-record → release → WS delivery within 15s (including scan) | Detox T-66 |
| AC-16 | Signed URL rotated when within 60s of expiry | pytest: mock time; `signed_url_cache_until = now+30s`; assert new URL generated |

### 12.4 Moderation

| # | Criterion | Verification |
|---|---|---|
| AC-17 | Score < 0.4 → message delivered to both participants | pytest T-61 (mock score=0.3) |
| AC-18 | Score 0.4–0.7 → sender sees soft-warn; message delivered (soft_warn status) | pytest T-61 (mock score=0.5); assert `moderation_status='soft_warn'` in Postgres |
| AC-19 | Score 0.7–0.9 → message hidden; sender sees `MODERATION_HOLD`; recipient receives nothing | pytest T-61 (mock score=0.8) |
| AC-20 | Score ≥ 0.9 → message auto-hidden; sender sees `MODERATION_REJECTED`; `moderation.action_taken` event published | pytest T-61 (mock score=0.95); assert event on RabbitMQ |
| AC-21 | Moderation scan adds < 200ms P95 for text messages | k6 auxiliary test: 500 concurrent sends; measure mod scan latency percentile |
| AC-22 | Media scan: image < 2s, video async ≤ 10s before delivery | pytest T-58 with timing assertions |

### 12.5 Block Enforcement

| # | Criterion | Verification |
|---|---|---|
| AC-23 | `block.created` → both WS clients receive `room_state { state: "read_only" }` within 3s | pytest T-62 |
| AC-24 | `send` frame while room `read_only` returns `ROOM_READ_ONLY` error | pytest T-62 |
| AC-25 | Chat history remains readable (GET messages endpoint) when `read_only` | pytest: assert 200 from `GET /chat/rooms/{id}/messages` with `read_only` room |
| AC-26 | Export still works for Premium users in `read_only` room | pytest: mock Premium entitlement; `POST /collabs/{id}/export` → 202 |

### 12.6 Read Receipts

| # | Criterion | Verification |
|---|---|---|
| AC-27 | `read_ack` upserts `chat_read_receipt` with monotonic enforcement | pytest T-63 |
| AC-28 | Recipient sees double-tick after sender sends `read_ack` | Detox T-65 (assertion on tick state after read_ack) |
| AC-29 | Unread count in room summary is accurate | pytest: send 5 messages; read_ack 3; assert `unread_count=2` from `GET /chat/rooms` |

### 12.7 Audit Trail

| # | Criterion | Verification |
|---|---|---|
| AC-30 | Every message has immutable `created_at` and sender | Code review: no UPDATE on `created_at` or `sender_profile_id` |
| AC-31 | Edits create revision rows; original body preserved | pytest: edit message; assert `chat_message_revision` has v1 with original body |
| AC-32 | Internal audit endpoint returns all messages + revisions in chronological order | pytest: create messages with edits; `GET /internal/rooms/{id}/messages/all`; assert order by `id` ASC |
| AC-33 | `deleted_at` soft-delete: body redacted, media_key nulled, row retained | pytest: user-delete message; assert row exists with `body='[deleted]'` |

### 12.8 Non-Functional

| # | Criterion | Verification |
|---|---|---|
| AC-34 | P95 chat e2e < 500ms at 1k concurrent rooms | k6 load test T-69 |
| AC-35 | chat-svc availability 99.9% | EKS HPA + multi-AZ deployment; verified by chaos test (pod kill during load test) |
| AC-36 | Cross-pod fanout works when 2+ pods running | pytest T-60; Detox smoke during rolling deploy |
| AC-37 | No bytes from S3 proxied through chat-svc | Code review + network trace in integration env |

---

## 13. Open Risks

| ID | Risk | Likelihood | Impact | Mitigation / Owner |
|---|---|---|---|---|
| R-01 | **API Gateway 2-hour WS limit causes user-visible disruption** | High (any session > 2h triggers forced reconnect) | Medium (brief hiccup, potential message loss if not handled) | Implement `connection_expiry_warning` + client-side smooth reconnect (T-16, T-33). Phase 5 decision gate: evaluate ALB+ECS native WS if reconnect-storm is observed in P18 load test. |
| R-02 | **API Gateway 10-min idle timeout drops inactive connections** | Medium (users who leave app open without sending) | Low (reconnect on next send is automatic) | Client sends application-level `ping` every 8 minutes (T-14). Verified by T-59. |
| R-03 | **Redis pub/sub message loss under pod failure** | Low (Redis ElastiCache multi-AZ, replication) | Medium (in-flight messages not delivered) | `reconnect`+`since_msg_id` replay recovers all missed messages from Postgres (T-15). Redis is best-effort delivery; Postgres is source of truth. |
| R-04 | **Moderation-svc scan latency exceeds 200ms P95 under load** | Medium (OpenAI API latency is variable) | High (blocks WS send handler; chat feels slow) | Circuit-breaker in chat-svc: if mod-svc times out after 250ms, allow message through as `moderation_status='pending'` and enqueue async re-scan. Accept the < 1% slip in pre-send blocking. |
| R-05 | **S3 presigned PUT URL abused (anyone with URL can upload)** | Low (5-min TTL; room_id + kind embedded in key prefix) | Medium (storage cost; bypass MIME validation) | S3 bucket policy enforces `Content-Type` must match the presigned header parameter; `media-svc` validates on confirm step. Abuse rate monitored via S3 access logs → CloudWatch alarm. |
| R-06 | **Voice note transcription deferred** | Confirmed (Phase 5 detail) | Low-Medium (accessibility gap) | Flagged as open in spec §007. Track as backlog item for Phase 5. Whisper-on-Replicate candidate. |
| R-07 | **DMCA agent not registered** (inherited from master) | Confirmed (user decision) | High (no US safe-harbor protection) | Documented in Community Guidelines. Legal exposure accepted. |
| R-08 | **expo-av on Android produces non-m4a format on some devices** | Low | Medium (MIME validation failure at confirm) | Tested on Android API 29, 33, 34 via Detox. Fallback: accept `audio/mpeg` in addition to `audio/mp4` for voice notes. |
| R-09 | **pHash + Chromaprint false-positive dup-detection rate** | Medium | Low-Medium (legitimate files flagged) | Threshold tuned during integration testing. Dup-check result populates `moderation_status='soft_warn'` (not auto-hide) unless combined with high OpenAI score. |
| R-10 | **Postgres row count growth (3-year retention + lifetime)** | Medium (100k DAU × 50 msgs/day = 5M rows/day) | Medium (query performance degrades) | Partition `chat_message` by `created_at` (monthly). Indexes on `(room_id, id)`. Archive partitions > 18 months to S3 via pg_partman + custom Celery job; internal audit endpoint queries S3-archived partitions via Athena for DSR/export. Design decision to be confirmed in Phase 5 infra detail. |
| R-11 | **API Gateway WebSocket API connection quota (default 500k/region)** | Low at launch, Medium at 100k DAU | High if hit | Submit quota increase request in P0 infra phase. Target 2M connections. |

---

*End of plan — 007-chat-workspace/plan.md*
