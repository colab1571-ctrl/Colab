# 007 — Chat + Workspace Base

**Phase**: P6.
**Services**: `chat-svc`, `media-svc`.
**Mission**: Custom WebSocket-backed 1:1 chat room for matched profiles. Text + voice notes + file/multimedia + links. Server-side persistence (Postgres + S3). Audit log with immutability. Voice/file moderation hooks. Foundation for §010 tools, §011 meetings, §012 AI assistant, §009 lifecycle.

## In scope (master Journey C FR-C-1 through FR-C-3)

- WebSocket gateway (AWS API Gateway WebSocket APIs in front of an EKS-deployed FastAPI/Starlette `chat-svc`).
- Persistence: every message in Postgres + media on S3.
- Allowed content: text, voice note, image 10MB, audio 50MB, video 250MB, doc 25MB. Whitelisted MIME types.
- Auto-log timestamps, uploader, version (audit trail). Immutable from user UI (edits create a new revision + diff).
- Presence: per-room online status, typing indicator (Redis pub-sub).
- Pre-send moderation: every text msg through OpenAI moderation; every uploaded file through Rekognition + dup-check.
- Block respect: blocked counterparties cannot exchange messages; existing room flips to read-only.

## Dependencies

- **Hard**: 002 Platform, 003 Auth, 006 Invite (room created on `match.created`), 008 Moderation.
- **Soft**: 010 Tools, 011 Meetings, 012 AI Assistant (all embed into the chat workspace UI).

## Owned entities

- `ChatRoom`: id, collaboration_id (FK to §009 Collaboration, 1:1), participants (array of 2 profile_ids), state (open|read_only|archived), created_at.
- `ChatMessage`: id, room_id, sender_profile_id, type (text|voice|image|video|audio|doc|link|system), body (text), media_key (s3 key, nullable), mime, size_bytes, duration_ms (nullable for voice/video), reply_to (nullable), edited_at, deleted_at (nullable), created_at, moderation_score, moderation_status.
- `ChatMessageRevision`: msg_id, version, body, edited_at.
- `ChatAttachment`: msg_id, kind, s3_key, signed_url_cache_until.
- `Presence` (Redis): room_id → online uids + typing uids.

## API surface

`chat-svc` (REST + WebSocket):
- WebSocket: `wss://api.<domain>/chat/{room_id}` with bearer token. Server pushes new messages + presence; client sends `send`, `typing`, `read_ack`.
- `GET /chat/rooms` — list rooms for current user
- `GET /chat/rooms/{id}` — metadata
- `GET /chat/rooms/{id}/messages?cursor=...&limit=50` — paginated history
- `POST /chat/rooms/{id}/messages` — REST send (also reachable via WS)
- `POST /chat/rooms/{id}/messages/{msg_id}/edit` body `{body}` — text msgs only
- `POST /chat/rooms/{id}/read` body `{up_to_msg_id}` — read receipts (soft, not E2EE)

`media-svc`:
- `POST /media/upload-url` body `{room_id, kind, mime, size_bytes}` → presigned S3 PUT (5min)
- `POST /media/confirm` body `{room_id, kind, s3_key, mime, size_bytes, duration_ms?}` → server downloads, scans (mod + dup), then surfaces a message
- `GET /media/{s3_key}/signed-url` → 5min signed URL (rotated)

### Queue events

- `chat.message.sent` (consumed by §009 for last-active, §014 for notifications, §008 if moderation_status=flagged)
- `chat.media.scanned`, `chat.media.flagged`

## Acceptance criteria

- Match → room auto-created.
- WS reconnects gracefully (resume from last server-acked msg).
- Text message round-trip e2e <500ms P95 (FR-NFR-1 chat <500ms).
- Voice note recording UX: hold-to-record, send, server-side scan, deliver.
- File upload via presigned URL; client never proxies bytes through chat-svc.
- Moderation flagged content not delivered (auto-hide ≥0.9; soft-warn 0.4–0.7 with user-acknowledge).
- Block fires → both users' room state flips to `read_only`; chat history readable, no new sends.
- Audit trail returns every message + revision in chronological order via internal admin endpoint (consumed by §016 admin console + §007 chat export — see §009).

## NFRs

- WS p95 latency <500ms message round-trip.
- Server-side mod scan adds <200ms for text; <2s for image; <10s for video (async with delivery hold for ≥0.9 risk).
- 99.9% availability (chat-svc).
- Replay-safe: dropping WS during send recovers on reconnect.

## Open

- Voice-note transcription on send (for accessibility + searchability) — Phase 5 detail; likely uses Whisper-on-Replicate, gated by Premium for advanced features.
