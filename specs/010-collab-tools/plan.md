# 010 — Collab Tools: Implementation Plan
# Whiteboard (tldraw) + Project Plan

> Phase: **P9** — depends on P8 (collab-svc lifecycle) and P6 (chat-svc workspace).
> Date: 2026-05-11. Author: spec-detailing agent.

---

## 1. Mission Recap

**Feature goal**: Extend the collab workspace (spec §010) with two in-workspace productivity tools, both owned by `collab-svc`:

1. **Virtual Whiteboard** — a real-time, two-user collaborative drawing surface powered by tldraw, persisted to S3 + Postgres. Embedded in RN via WebView; native React component in web consumer-app.
2. **Project Plan** — a lightweight, custom-built Kanban/list tool: tasks with status, assignee, due date, and threaded comments. Task status flips emit system messages into the shared chat room.

Locked architectural decisions governing this spec (master §0):

| Ref | Decision |
|---|---|
| ARC-1 | React Native + Expo on mobile |
| ARC-2 | Next.js (consumer-web) on web |
| ARC-3 | Microservices (FastAPI); this feature lives in `collab-svc` |
| ARC-5 | REST + WebSocket via FastAPI + OpenAPI codegen → typed TS client |
| ARC-6 | Postgres + Redis |
| ARC-8 | Custom WebSocket service for realtime |
| ARC-9 | AWS S3 + CloudFront |
| ARC-10 | tldraw for whiteboard |
| ARC-11 | Custom project plan (no third-party Jira/Linear) |
| FR-C-4 | Whiteboard = COULD |
| FR-C-5 | Project plan = COULD |
| Billing | High-res whiteboard export = Premium entitlement |

---

## 2. Research Findings

### 2.1 tldraw 3.x: Next.js (React) vs React Native WebView

**tldraw 3.x is a React library** — it renders to a `<canvas>` backed by React DOM. It has no React Native target; the recommended mobile integration is a WebView wrapper.

| Concern | Next.js (consumer-web) | RN via `react-native-webview` |
|---|---|---|
| Integration | Native `<Tldraw>` React component; full API access | HTML page served locally or from CDN; RN hosts a `<WebView>` |
| tldraw store access | Direct: `editor.store`, `editor.exportAs(...)` | Indirect: all calls cross the postMessage bridge |
| Touch / gesture | Native browser pointer events | `react-native-webview` passes touch as synthetic pointer events; `allowsInlineMediaPlayback`, `scrollEnabled={false}` required |
| Pencil / stylus | Pointer-pressure API in browser | WebView PointerEvent on iOS 13.4+ / Android; hardware pressure not guaranteed on all devices |
| Performance | Full GPU-composited canvas | Extra layer: RN → WKWebView / Chrome Custom Tab; noticeable on low-end Android |
| Export | `editor.exportAs('png'|'svg'|'pdf')` in-process | Must call via postMessage; result is base64 blob sent back across bridge |
| HMR / dev | Fast | Requires webview reload on change |

**Decision (confirmed by ARC-10)**: tldraw in Next.js runs natively. In RN, the whiteboard page is a self-contained HTML bundle (`whiteboard.html`) served from S3/CloudFront (or bundled in-app via `expo-asset`); `react-native-webview` embeds it. The bridge protocol (postMessage) is defined in §4 below.

### 2.2 tldraw Sync (managed) vs Self-Hosted Collaboration

tldraw ships `@tldraw/sync` which is a managed WebSocket sync service (`tldraw.com`) — not viable for Colab because:

- Data leaves our infrastructure (privacy constraint; user data must stay in us-east-1 per ARC-9 / master §0 NFR-4).
- No self-hosted server package is available in v3 (as of 2026-05).
- The managed server does not integrate with our auth.

**Chosen approach: Y.js (CRDT) + custom y-websocket server inside `collab-svc`.**

tldraw exposes a `YjsStore` binding (`@tldraw/store` + community `tldraw-yjs-example` pattern). The binding maps the tldraw `TLRecord` store to a Y.Doc. All CRDT merge logic lives in Y.js; tldraw renders whatever the Y.Doc says.

```
tldraw editor (React/WebView)
  └─ TldrawYjsBinding (maps TLRecord ↔ Y.Map)
       └─ Y.Doc (local CRDT state)
            └─ y-websocket provider (WebSocket to our server)
                  └─ collab-svc /whiteboard/{collab_id}/ws
                       └─ yjs-server (y-websocket Node module OR Python websockets + y-crdt-python)
```

**Implementation note**: `y-websocket` is a Node.js package. To keep the stack in Python, use `ypy-websocket` (Python y-crdt implementation with asyncio WebSocket server). Alternatively, run a thin `whiteboard-relay` Node.js sidecar as part of the `collab-svc` deployment pod (discussed in §3).

### 2.3 Y.js Snapshot Strategy

Y.js keeps a full in-memory state vector. To persist without replaying every op from genesis:

1. On every op received, the server records a `WhiteboardOp` row (collab_id, lamport, binary Y.js update, actor, timestamp).
2. Every 10 seconds of server-side idle (no incoming updates), take a **snapshot**: call `Y.encodeStateAsUpdate(doc)` → binary blob → upload to S3 as `whiteboard/{collab_id}/snapshot-{version}.bin`. Write a `WhiteboardSnapshot` row.
3. On reconnect / initial load: server hydrates its Y.Doc from the latest snapshot S3 blob, applies any ops with lamport > snapshot.version, then sends the merged state to the joining client.
4. Old ops before the snapshot version can be pruned after 30 days (configurable).

This avoids the "replay 10,000 ops" cold-start problem while keeping full audit history.

### 2.4 Y-WebSocket Server Pattern

The standard `y-websocket` server is stateful in RAM (Y.Doc lives in the process). For two-user-max collabs (per master §0 — no group collabs), a single process is sufficient. On pod restart, the Y.Doc is re-hydrated from the S3 snapshot.

```
collab-svc pod
  ├─ FastAPI REST (gunicorn/uvicorn)
  └─ ypy-websocket asyncio server (separate asyncio task or thread)
       └─ RedisYStore (y-py Redis storage adapter) ← hot cache of Y.Doc
```

The Redis adapter keeps the live Y.Doc binary in Redis (collab_id key, 1h TTL). Pod A and Pod B both read/write the same Redis key, providing multi-replica correctness without sticky sessions.

---

## 3. Whiteboard Architecture

### 3.1 Service Placement

The whiteboard relay is an extension of `collab-svc`. A **dedicated `whiteboard-svc`** would be warranted only if:

- More than 2 concurrent users per board (not in scope — group collabs deferred).
- Whiteboard traffic forces independent scaling from task/lifecycle APIs.

For launch scope: **embed inside `collab-svc`** as an additional asyncio WebSocket endpoint. Revisit in a post-launch iteration if pod memory spikes due to many live Y.Docs.

### 3.2 Component Diagram

```
┌────────────────────────────────────────────────────────────┐
│  React Native App                                          │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  <WebView source={{ uri: WHITEBOARD_URL }}           │  │
│  │    onMessage={handleBridgeMessage}                   │  │
│  │    injectedJavaScript={bridgeBootstrap}              │  │
│  │  />                                                  │  │
│  └──────────────┬──────────────────────────────────────┘  │
│                 │ postMessage bridge                        │
└─────────────────┼──────────────────────────────────────────┘
                  │
┌─────────────────▼──────────────────────────────────────────┐
│  Whiteboard HTML (tldraw + yjs client)                     │
│  hosted: CloudFront/S3 or bundled in expo-asset            │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  <Tldraw store={yjsBoundStore} />                     │ │
│  │  TldrawYjsBinding                                     │ │
│  │  Y.Doc ──► y-websocket provider ──► WSS               │ │
│  └───────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────┘
                  │ WSS (authenticated, collab_id scoped)
┌─────────────────▼──────────────────────────────────────────┐
│  collab-svc (EKS pod)                                      │
│  ┌─────────────────────┐  ┌──────────────────────────────┐ │
│  │  FastAPI REST        │  │  ypy-websocket asyncio       │ │
│  │  /whiteboard/*      │  │  /whiteboard/{id}/ws         │ │
│  └─────────────────────┘  └────────────┬─────────────────┘ │
│                                        │                    │
│  ┌─────────────────────────────────────▼─────────────────┐ │
│  │  Redis (ElastiCache) — Y.Doc hot state per collab_id  │ │
│  └───────────────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  Postgres — WhiteboardSnapshot, WhiteboardOp tables   │ │
│  └───────────────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  S3 — snapshot blobs, export PNG/PDF                  │ │
│  └───────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────┘
```

### 3.3 Snapshot Lifecycle

```
Op arrives at ypy-websocket server
  → broadcast to other connected client (Y.js merge)
  → append WhiteboardOp row (Postgres)
  → update Y.Doc in Redis
  → reset 10s idle timer

Idle timer fires (no ops for 10s)
  → Y.encodeStateAsUpdate(doc) → binary
  → PUT to S3: whiteboard/{collab_id}/snap-{epoch}.bin
  → INSERT WhiteboardSnapshot(collab_id, s3_key, version=lamport_clock, created_at)
  → publish whiteboard.snapshot_saved event (RabbitMQ)

New client joins
  → fetch latest WhiteboardSnapshot row → download S3 blob
  → hydrate Y.Doc from blob
  → apply WhiteboardOp rows where lamport > snapshot.version
  → send full state update to joining client
```

### 3.4 Export Flow

Exports are triggered via REST (`POST /whiteboard/{collab_id}/export?format=png|pdf&resolution=basic|hi`). The server:

1. Checks entitlement: `resolution=hi` → requires Premium (billing entitlement check via `billing-svc`).
2. Sends a postMessage to the active WebView session (if any) requesting `editor.exportAs(format)`.
3. If no active session (user exports async): the server re-hydrates a headless tldraw instance in a Playwright/Puppeteer serverless function to render the snapshot and call `exportAs`. The result is uploaded to S3 and a signed URL returned.
4. Returns signed S3 URL (5-minute TTL) or 202 + polling endpoint if async.

**Headless render approach**: A small Node.js Lambda/ECS task runs `@playwright/test` with the whiteboard HTML page, calls `editor.exportAs(...)`, base64-encodes result, uploads to S3. This avoids shipping Chromium inside the Python service.

---

## 4. RN WebView Bridge Protocol

### 4.1 Overview

The whiteboard HTML page and the RN host communicate via `window.ReactNativeWebView.postMessage` (HTML → RN) and `webViewRef.current.injectJavaScript(...)` (RN → HTML). Messages are JSON-encoded.

### 4.2 Message Schema

All messages follow the envelope:

```typescript
interface BridgeMessage {
  type: string;      // discriminant
  requestId?: string; // for request/response pairing
  payload?: unknown;
}
```

**RN → WebView (injected JS commands)**:

| type | payload | purpose |
|---|---|---|
| `INIT` | `{ collabId, authToken, userId, resolution }` | Bootstrap: connect Y.js provider with auth |
| `EXPORT_REQUEST` | `{ requestId, format: 'png'\|'pdf', resolution: 'basic'\|'hi' }` | Trigger tldraw export |
| `SET_READONLY` | `{ readonly: boolean }` | Lock board when collab archived or blocked |
| `FOCUS_SHAPE` | `{ shapeId: string }` | Pan/zoom to a shape (for deep-link from chat) |

**WebView → RN (postMessage)**:

| type | payload | purpose |
|---|---|---|
| `READY` | `{}` | tldraw + Y.js initialized; RN can show the board |
| `EXPORT_RESULT` | `{ requestId, dataUri: string, mimeType: string }` | base64 export blob |
| `EXPORT_ERROR` | `{ requestId, error: string }` | Export failed |
| `PRESENCE_UPDATE` | `{ onlineUserIds: string[] }` | Show co-presence indicator in RN header |
| `ERROR` | `{ code: string, message: string }` | Unrecoverable error (Y.js disconnect, auth failure) |

### 4.3 Touch Event Passthrough

- Set `scrollEnabled={false}` on `<WebView>` to prevent RN ScrollView from stealing touch.
- Set `allowsInlineMediaPlayback` and `mediaPlaybackRequiresUserAction={false}`.
- Disable `bounces` on iOS: `style={{ flex: 1 }}` + `contentInset={0}`.
- tldraw's gesture handling runs entirely inside the WebView DOM — no conflict with RN gesture responder when `scrollEnabled={false}`.

### 4.4 Keyboard Avoidance

On mobile, use `KeyboardAvoidingView` wrapping the WebView container so that the tldraw text tool input is not obscured by the software keyboard. The WebView must have `keyboardDisplayRequiresUserAction={false}` (iOS).

---

## 5. Project Plan Data Model

### 5.1 Entities

```sql
-- Task
CREATE TABLE task (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  collab_id       UUID NOT NULL REFERENCES collaboration(id) ON DELETE CASCADE,
  title           VARCHAR(200) NOT NULL,
  description     TEXT,          -- max 2000 chars enforced at app layer
  assignee_profile_id UUID REFERENCES profile(id) ON DELETE SET NULL,
  due_date        DATE,
  status          VARCHAR(20) NOT NULL DEFAULT 'todo'
                    CHECK (status IN ('todo','in_progress','done','blocked')),
  order_key       VARCHAR(255) NOT NULL, -- LexoRank-style string; indexed
  created_by      UUID NOT NULL REFERENCES profile(id),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  closed_at       TIMESTAMPTZ,
  deleted_at      TIMESTAMPTZ           -- soft delete
);

CREATE INDEX idx_task_collab_order ON task (collab_id, order_key)
  WHERE deleted_at IS NULL;

CREATE INDEX idx_task_collab_due ON task (collab_id, due_date)
  WHERE deleted_at IS NULL;

-- TaskComment
CREATE TABLE task_comment (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id             UUID NOT NULL REFERENCES task(id) ON DELETE CASCADE,
  author_profile_id   UUID NOT NULL REFERENCES profile(id),
  body                VARCHAR(500) NOT NULL,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at          TIMESTAMPTZ           -- soft delete
);

CREATE INDEX idx_task_comment_task ON task_comment (task_id, created_at)
  WHERE deleted_at IS NULL;
```

### 5.2 LexoRank-Style order_key

Tasks are ordered by a **lexicographic string key** (LexoRank pattern). This avoids updating every sibling row when inserting between two items.

- Initial keys generated as base-26 balanced strings: `"i"`, `"m"`, `"a"`, etc.
- Inserting between `"a"` and `"i"` → `"e"` (midpoint). Between `"a"` and `"b"` → `"an"` (append character).
- Key space exhaustion (two adjacent keys with no midpoint) triggers a **rebalance**: new keys computed and written in a single transaction, broadcast to clients.
- Key format: uppercase A–Z + lowercase a–z + `0-9`, max 50 chars. Postgres `VARCHAR(255)` gives ample room.
- Library: use `lexorank` npm package (TS client); Python side generates initial key and validates format only — ordering logic lives in the client.

### 5.3 Status Enum

```
todo → in_progress → done
todo → blocked
in_progress → blocked
blocked → in_progress
any → done   (terminal; sets closed_at)
done → todo  (reopen; clears closed_at)
```

All transitions are allowed (no strict FSM gate) — both participants can freely move tasks. Status change writes a `CollabStatusEvent`-adjacent record (or uses the same `task_status_event` table described in §7).

---

## 6. Status Flips → System Messages in Chat

When a task's status field changes via `PATCH /tasks/{id}`, `collab-svc` publishes a `task.status_changed` event to RabbitMQ. A Celery consumer receives the event and calls `chat-svc`'s internal REST endpoint to inject a **system message** into the collab's chat room.

### 6.1 System Message Format

```
@{actor_display_name} moved "{task_title}" to {new_status_label}
```

Status label mapping:

| status | label |
|---|---|
| `todo` | To Do |
| `in_progress` | In Progress |
| `done` | Done |
| `blocked` | Blocked |

Example: `@Maya moved "Mix final stems" to Done`

### 6.2 ChatMessage row for system messages

```python
ChatMessage(
  room_id       = collab.chat_room_id,
  sender_profile_id = None,          # NULL — system sender
  type          = "system",
  body          = "@Maya moved \"Mix final stems\" to Done",
  metadata      = {
    "event":    "task.status_changed",
    "task_id":  str(task.id),
    "actor_id": str(actor_profile_id),
    "new_status": "done"
  }
)
```

The `type = "system"` variant is rendered by the chat UI as a styled pill (not a chat bubble), consistent with other system messages (e.g., "Collab started", "File shared").

### 6.3 Additional system message triggers

| Event | System message |
|---|---|
| Task created | `@{actor} added task "{title}"` |
| Task assigned | `@{actor} assigned "{title}" to @{assignee}` |
| Task due-date set | `@{actor} set due date for "{title}" to {date}` |
| Task deleted | `@{actor} deleted task "{title}"` |

All are optional / configurable per user preference (future: suppress system msgs toggle in collab settings).

---

## 7. API Contracts

### 7.1 Whiteboard Endpoints (`collab-svc`)

#### `WS /whiteboard/{collab_id}/ws`

**Auth**: Bearer token passed as query param `?token=...` (WebSocket headers not supported in `react-native-webview` provider).

**Protocol**: Raw Y.js binary frames (not JSON). The ypy-websocket server handles the y-sync v1 protocol natively.

On connect:
1. Server validates token, checks participant membership in `collab_id`.
2. Server sends full state update (hydrated Y.Doc).
3. Client sends any pending local updates.
4. Bi-directional op sync begins.

On disconnect: server waits 5s (reconnect grace), then triggers idle snapshot if no reconnect.

---

#### `GET /whiteboard/{collab_id}/snapshot`

Returns latest snapshot metadata + signed S3 URL for the binary blob.

**Response 200**:
```json
{
  "collab_id": "uuid",
  "version": 1042,
  "s3_key": "whiteboard/uuid/snap-1748000000.bin",
  "url": "https://cdn.example.com/whiteboard/...",
  "url_expires_at": "2026-05-11T12:05:00Z",
  "created_at": "2026-05-11T12:00:00Z"
}
```

**Response 404**: No snapshot yet (new board). Client initializes empty Y.Doc.

---

#### `POST /whiteboard/{collab_id}/export`

**Query params**: `format=png|pdf`, `resolution=basic|hi`

**Auth**: Bearer token. `resolution=hi` → entitlement check with `billing-svc`.

**Response 200** (sync, if active session available within 5s):
```json
{
  "url": "https://cdn.example.com/whiteboard/exports/uuid.png",
  "url_expires_at": "2026-05-11T12:05:00Z",
  "mime_type": "image/png",
  "resolution": "basic"
}
```

**Response 202** (async, headless render kicked off):
```json
{
  "export_id": "uuid",
  "status": "pending",
  "poll_url": "/whiteboard/exports/uuid"
}
```

#### `GET /whiteboard/exports/{export_id}`

Polling endpoint.

**Response**:
```json
{
  "export_id": "uuid",
  "status": "pending|generating|ready|failed",
  "url": "...",           // present when status=ready
  "url_expires_at": "...",
  "error": null           // present when status=failed
}
```

---

### 7.2 Task Endpoints (`collab-svc`)

All endpoints require Bearer auth; requester must be a participant in `collab_id` or owner of `task_id`.

#### `GET /collabs/{collab_id}/tasks`

**Query**: `?sort=order|due_date|status&status=todo|in_progress|done|blocked`

**Response 200**:
```json
{
  "tasks": [
    {
      "id": "uuid",
      "collab_id": "uuid",
      "title": "Mix final stems",
      "description": "...",
      "assignee_profile_id": "uuid|null",
      "due_date": "2026-05-20|null",
      "status": "in_progress",
      "order_key": "i",
      "created_by": "uuid",
      "created_at": "...",
      "updated_at": "...",
      "closed_at": null,
      "comment_count": 3
    }
  ],
  "total": 12
}
```

---

#### `POST /collabs/{collab_id}/tasks`

**Body**:
```json
{
  "title": "Mix final stems",
  "description": "Optional, max 2000 chars",
  "assignee_profile_id": "uuid|null",
  "due_date": "2026-05-20|null",
  "order_key": "i"   // client provides; server validates uniqueness within collab
}
```

**Response 201**: Full task object.

**Errors**:
- `422` if `order_key` conflicts → client should rebalance and retry.
- `403` if requester not a participant.

---

#### `PATCH /tasks/{id}`

Partial update. Any combination of fields.

**Body** (all optional):
```json
{
  "title": "...",
  "description": "...",
  "assignee_profile_id": "uuid|null",
  "due_date": "date|null",
  "status": "todo|in_progress|done|blocked",
  "order_key": "..."
}
```

**Response 200**: Updated task object.

**Side effect**: if `status` changed → emit `task.status_changed` event → system message in chat.

---

#### `DELETE /tasks/{id}`

Soft delete (`deleted_at = now()`).

**Response 204**.

**Side effect**: emit `task.deleted` → system message in chat.

---

#### `POST /tasks/{id}/comments`

**Body**:
```json
{ "body": "...(max 500 chars)" }
```

**Response 201**:
```json
{
  "id": "uuid",
  "task_id": "uuid",
  "author_profile_id": "uuid",
  "body": "...",
  "created_at": "..."
}
```

---

#### `GET /tasks/{id}/comments`

**Query**: `?cursor=uuid&limit=20` (cursor = last comment id)

**Response 200**:
```json
{
  "comments": [ ...comment objects... ],
  "next_cursor": "uuid|null"
}
```

---

### 7.3 Queue Events

| Event | Exchange | Producer | Consumers |
|---|---|---|---|
| `task.status_changed` | `collab.tasks` | `collab-svc` | Celery worker → `chat-svc` (system msg), `notification-svc` (push) |
| `task.created` | `collab.tasks` | `collab-svc` | Celery worker → `chat-svc` (system msg) |
| `task.assigned` | `collab.tasks` | `collab-svc` | Celery worker → `chat-svc` (system msg), `notification-svc` (push to assignee) |
| `task.deleted` | `collab.tasks` | `collab-svc` | Celery worker → `chat-svc` (system msg) |
| `whiteboard.snapshot_saved` | `collab.whiteboard` | `collab-svc` | `analytics-svc` |
| `whiteboard.export_ready` | `collab.whiteboard` | `collab-svc` | `notification-svc` (push if async export) |

**Event payload for `task.status_changed`**:
```json
{
  "event": "task.status_changed",
  "collab_id": "uuid",
  "task_id": "uuid",
  "task_title": "Mix final stems",
  "actor_profile_id": "uuid",
  "actor_display_name": "Maya",
  "prev_status": "in_progress",
  "new_status": "done",
  "occurred_at": "2026-05-11T10:00:00Z"
}
```

---

## 8. Implementation Tasks

> Format: `id | title | outcome | est_hours | blocks | blocked_by`

### 8.1 Backend — Whiteboard

| ID | Title | Outcome | Est hrs | Blocks | Blocked by |
|---|---|---|---|---|---|
| WB-BE-1 | DB schema: WhiteboardSnapshot + WhiteboardOp | Alembic migration, indexes, FK to Collaboration | 3 | WB-BE-2, WB-BE-4 | P8 Collaboration table |
| WB-BE-2 | ypy-websocket server integration in collab-svc | asyncio WS server on `/whiteboard/{id}/ws`; Y.Doc lifecycle (create/hydrate/destroy); Redis Y.Doc caching | 12 | WB-BE-3, WB-BE-5 | WB-BE-1 |
| WB-BE-3 | Op persistence + 10s idle snapshot | WhiteboardOp insert on every op; idle timer; snapshot to S3; WhiteboardSnapshot row | 8 | WB-BE-6 | WB-BE-2 |
| WB-BE-4 | `GET /whiteboard/{collab_id}/snapshot` endpoint | Latest snapshot metadata + signed S3 URL; 404 on empty board | 3 | WB-FE-1 | WB-BE-1 |
| WB-BE-5 | WS auth + participant guard | Token validation; collab participant check; 4003 close code on fail | 4 | WB-BE-2 | WB-BE-2 |
| WB-BE-6 | Snapshot hydration on WS connect | Load latest snapshot from S3 → hydrate Y.Doc → apply delta ops → send state to client | 6 | WB-BE-2, WB-BE-3 | |
| WB-BE-7 | Export REST endpoint + entitlement check | `POST /whiteboard/{id}/export`; billing-svc entitlement call for hi-res; 202 async path | 5 | WB-BE-8 | WB-BE-1 |
| WB-BE-8 | Headless export worker (Playwright Lambda/ECS task) | Node.js task: hydrate tldraw in Playwright, exportAs, upload to S3, signal completion | 16 | WB-FE-3 | WB-BE-7 |
| WB-BE-9 | `GET /whiteboard/exports/{id}` polling endpoint | Status + signed URL when ready | 2 | — | WB-BE-7 |
| WB-BE-10 | `whiteboard.snapshot_saved` event publish | RabbitMQ publish after snapshot write | 2 | — | WB-BE-3 |

### 8.2 Frontend Web — Whiteboard

| ID | Title | Outcome | Est hrs | Blocks | Blocked by |
|---|---|---|---|---|---|
| WB-FE-1 | tldraw + Y.js integration in consumer-web (Next.js) | `<Tldraw>` with `TldrawYjsBinding`; y-websocket provider connecting to `collab-svc`; auto-reconnect | 14 | WB-FE-2 | WB-BE-2, WB-BE-4 |
| WB-FE-2 | Co-presence indicator | Show partner's cursor color + display name on board; online/offline pill in header | 6 | — | WB-FE-1 |
| WB-FE-3 | Export UI (web) | Export button with format + resolution selector; entitlement gate for hi-res; download trigger | 5 | — | WB-BE-7 |
| WB-FE-4 | Read-only mode (web) | Disable tldraw tools when board is locked (archived/blocked collab) | 3 | — | WB-FE-1 |

### 8.3 Frontend Mobile — Whiteboard (RN WebView)

| ID | Title | Outcome | Est hrs | Blocks | Blocked by |
|---|---|---|---|---|---|
| WB-RN-1 | Whiteboard HTML bundle | Self-contained HTML + tldraw + yjs + y-websocket; served from CloudFront or bundled | 8 | WB-RN-2 | WB-FE-1 (shared tldraw logic) |
| WB-RN-2 | `<WebView>` host component in RN | Render whiteboard HTML; `scrollEnabled={false}`; touch passthrough; keyboard avoidance | 6 | WB-RN-3, WB-RN-4 | WB-RN-1 |
| WB-RN-3 | postMessage bridge — INIT + READY | Inject INIT payload (auth token, collab_id) after WebView load; handle READY message to show board | 5 | WB-RN-5 | WB-RN-2 |
| WB-RN-4 | postMessage bridge — presence, read-only, errors | Handle PRESENCE_UPDATE, SET_READONLY, ERROR messages from WebView | 4 | — | WB-RN-3 |
| WB-RN-5 | postMessage bridge — export | EXPORT_REQUEST → WebView → EXPORT_RESULT (base64) → upload to S3 via media-svc or direct presign | 8 | — | WB-RN-3, WB-BE-7 |
| WB-RN-6 | Entitlement gate for hi-res export in RN | Check billing entitlement; show upsell sheet if Free tier | 3 | — | WB-RN-5 |

### 8.4 Backend — Project Plan

| ID | Title | Outcome | Est hrs | Blocks | Blocked by |
|---|---|---|---|---|---|
| PP-BE-1 | DB schema: Task + TaskComment | Alembic migration; indexes (collab_id + order_key, collab_id + due_date); FK guards | 4 | PP-BE-2 | P8 Collaboration table |
| PP-BE-2 | Task CRUD endpoints | `GET /collabs/{id}/tasks`, `POST`, `PATCH /tasks/{id}`, `DELETE` with soft-delete | 10 | PP-BE-4, PP-BE-5 | PP-BE-1 |
| PP-BE-3 | TaskComment endpoints | `POST /tasks/{id}/comments`, `GET` with cursor pagination | 5 | PP-FE-3 | PP-BE-1 |
| PP-BE-4 | order_key generation + rebalance | Server-side LexoRank midpoint calc; conflict detection; rebalance endpoint `POST /collabs/{id}/tasks/rebalance` | 8 | PP-FE-2 | PP-BE-2 |
| PP-BE-5 | task.status_changed event + system message | On status change: emit RabbitMQ event; Celery consumer calls chat-svc `/system-message`; also emit task.created, task.assigned, task.deleted | 8 | PP-BE-6 | PP-BE-2, chat-svc system message endpoint |
| PP-BE-6 | chat-svc: `POST /chat/rooms/{id}/system-message` internal endpoint | Accept `{body, metadata}`; insert ChatMessage(type=system); broadcast via WS | 4 | — | §007 chat-svc |
| PP-BE-7 | Assignee push notification | On task.assigned: notify-svc push to assignee | 3 | — | PP-BE-5, §013 notify-svc |

### 8.5 Frontend Web — Project Plan

| ID | Title | Outcome | Est hrs | Blocks | Blocked by |
|---|---|---|---|---|---|
| PP-FE-1 | Task list / board view (web) | Column-per-status or flat list; virtualized; status chips; due date display; overdue highlight | 12 | PP-FE-2, PP-FE-3 | PP-BE-2 |
| PP-FE-2 | Drag-and-drop reorder (web) | `@dnd-kit/sortable` for list reorder; update order_key on drop via PATCH; optimistic UI | 8 | — | PP-FE-1, PP-BE-4 |
| PP-FE-3 | Task detail panel (web) | Title edit, description, assignee toggle, due-date picker, status select, comments thread | 10 | — | PP-FE-1, PP-BE-3 |
| PP-FE-4 | System messages rendering in chat (web) | Styled pill component for type=system messages; linkable to task (tap to open task panel) | 5 | — | PP-BE-5 |

### 8.6 Frontend Mobile — Project Plan (RN)

| ID | Title | Outcome | Est hrs | Blocks | Blocked by |
|---|---|---|---|---|---|
| PP-RN-1 | Task list screen (RN) | FlatList with status filter tabs; swipe-to-change-status; assignee avatar; due-date badge; overdue tint | 14 | PP-RN-2, PP-RN-3 | PP-BE-2 |
| PP-RN-2 | Drag-to-reorder (RN) | `react-native-draggable-flatlist`; update order_key on drop; optimistic UI | 8 | — | PP-RN-1, PP-BE-4 |
| PP-RN-3 | Task detail bottom sheet (RN) | Title, description, assignee toggle, due-date picker, status picker, comments list | 12 | PP-RN-4 | PP-RN-1, PP-BE-3 |
| PP-RN-4 | Task comment input + list (RN) | InfiniteScroll comment list (cursor); keyboard-aware input; 500ch limit counter | 6 | — | PP-RN-3 |
| PP-RN-5 | System messages rendering in chat (RN) | Pill component for type=system; tap → navigate to task detail | 5 | — | PP-BE-5 |

### 8.7 Cross-Cutting

| ID | Title | Outcome | Est hrs | Blocks | Blocked by |
|---|---|---|---|---|---|
| CC-1 | OpenAPI spec update for §010 endpoints | Regenerate TS client with new whiteboard + task routes | 3 | All FE | PP-BE-2, WB-BE-4, WB-BE-7 |
| CC-2 | Integration tests: whiteboard op + snapshot | Two-client Y.js convergence test; snapshot-on-idle; hydration on reconnect | 10 | — | WB-BE-6 |
| CC-3 | Integration tests: task CRUD + system messages | Task lifecycle; reorder; system message appears in chat room | 8 | — | PP-BE-5, PP-BE-6 |
| CC-4 | E2E tests (Detox/Playwright): whiteboard basic draw | Open board, draw shape, switch to other user, verify shape appears | 8 | — | WB-RN-2, WB-FE-1 |
| CC-5 | E2E tests: task flow | Create task, change status, verify system msg in chat | 6 | — | PP-RN-1, PP-FE-1 |
| CC-6 | Load test: 500 concurrent whiteboard sessions | Confirm Redis Y.Doc cache holds; no pod OOM; snapshot latency < 2s | 8 | — | WB-BE-2, WB-BE-3 |

---

## 9. Acceptance Criteria

### 9.1 Whiteboard

| # | Criterion | Verification |
|---|---|---|
| WB-AC-1 | Two participants drawing concurrently see each other's strokes within 250ms P95. | Integration test: two y-websocket clients, measure round-trip. |
| WB-AC-2 | A snapshot is written to S3 within 12 seconds of the last drawing op (10s idle + 2s write). | Test: draw op → wait 12s → assert `WhiteboardSnapshot` row exists with correct `s3_key`. |
| WB-AC-3 | On app restart (new WebSocket connection), the board rehydrates from the snapshot and any subsequent ops. | Test: client A draws, disconnects. Client B draws. Client A reconnects → assert A sees B's shapes. |
| WB-AC-4 | Free user can export PNG at basic resolution (max 1920px on longest side). | API test: `POST /whiteboard/{id}/export?format=png&resolution=basic` → 200 with PNG URL. |
| WB-AC-5 | Premium user can export PDF at hi-res. Free user receives `403 ENTITLEMENT_REQUIRED`. | API test with Free token → 403. Premium token → 200/202. |
| WB-AC-6 | Archived or blocked collab → board renders read-only; no ops accepted by server. | Test: archive collab → WS op rejected with close code 4009. |
| WB-AC-7 | RN WebView bridge: INIT→READY handshake completes within 3s on slow 3G (throttled). | Manual + Detox test. |
| WB-AC-8 | Touch drawing in RN WebView does not trigger parent ScrollView scroll. | Manual test: draw gesture does not scroll the workspace tab bar. |

### 9.2 Project Plan

| # | Criterion | Verification |
|---|---|---|
| PP-AC-1 | Task CRUD: create, read, update (all fields), soft-delete works via API. | API integration tests. |
| PP-AC-2 | Reordering tasks via `order_key` updates persist and return in correct order on subsequent `GET`. | Test: create 5 tasks, reorder two, verify `GET` returns new order. |
| PP-AC-3 | Status flip to `done` sets `closed_at`; flip back to `todo` clears `closed_at`. | API integration test. |
| PP-AC-4 | Status flip emits a system message into the collab chat room within 2 seconds. | Integration test: PATCH status → poll chat history → assert system message body correct. |
| PP-AC-5 | Task comment `POST` enforces 500-char limit; returns `422` for overflow. | API test with 501-char body. |
| PP-AC-6 | Comment pagination: 20 comments per page; `next_cursor` advances correctly. | Seed 25 comments; fetch page 1 → 20 items + cursor; fetch page 2 → 5 items + null cursor. |
| PP-AC-7 | Non-participant cannot read or write tasks (`403`). | API test with unrelated profile token. |
| PP-AC-8 | `GET /collabs/{id}/tasks?sort=due_date` returns tasks with null `due_date` last. | API test: mix of null + dated tasks; verify sort. |
| PP-AC-9 | System message in chat is type=`system` and links back to `task_id` in metadata. | Assert `ChatMessage.type == "system"` and `metadata.task_id == expected_uuid`. |
| PP-AC-10 | RN: Drag-to-reorder persists after app foreground/background cycle. | Detox test: drag, background app, foreground → verify order unchanged from server. |

---

## 10. Open Risks

| Risk ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| RISK-1 | **RN WebView gesture conflicts on Android**: `react-native-webview` `onStartShouldSetResponder` may fight with tldraw's canvas gesture capture, especially on Samsung/Xiaomi skins with aggressive gesture navigation. | Medium | High | Set `scrollEnabled={false}`, `nestedScrollEnabled={false}`. Test on Android 13 + 14 on at least 3 OEM skins (Samsung One UI, Xiaomi MIUI, Pixel) during WB-RN-2. If unresolvable, wrap in a `Modal` fullscreen to eliminate parent gesture responders. |
| RISK-2 | **ypy-websocket maturity**: `ypy-websocket` (Python y-crdt) is a smaller community library compared to the canonical Node.js `y-websocket`. Bugs in the binary protocol handling could cause silent data corruption. | Low-Medium | High | Pin a specific tested version. Add a Y.js convergence integration test (CC-2) that catches divergence. Fallback: run a thin Node.js `y-websocket` sidecar in the same EKS pod (evaluated at WB-BE-2 spike). |
| RISK-3 | **tldraw 3.x + Y.js binding API stability**: tldraw frequently breaks its store API between minor versions. The `TldrawYjsBinding` is a community pattern, not an official tldraw package. | Medium | Medium | Lock tldraw to a specific minor version (e.g., `3.x.y`). Maintain an internal fork of the binding code. Add renovatebot with grouped PR + CI gate before any tldraw upgrade. |
| RISK-4 | **Headless export cold start (WB-BE-8)**: Playwright Lambda may have 5–15s cold start. Async exports with polling are fine for PDF; PNG exports expected to be synchronous by users. | Medium | Medium | Use provisioned concurrency for the export Lambda (1 warm instance). Degrade gracefully: if active WS session exists, use postMessage export (fast path); headless only when session absent. |
| RISK-5 | **LexoRank key exhaustion under heavy reordering**: Users who reorder tasks dozens of times may exhaust the midpoint space between two adjacent keys, triggering a rebalance that updates all rows. | Low | Low-Medium | Cap rebalance to single Postgres transaction. Emit `tasks.rebalanced` event so clients re-fetch. Log rebalance frequency; if > 1/week per collab, switch to fractional indexing library. |
| RISK-6 | **Y.Doc Redis cache size**: Each tldraw Y.Doc for a large board may reach several MB. At 500 concurrent boards, Redis memory usage could be ~500–2000 MB. | Low | Medium | Set `MEMORY POLICY allkeys-lru` on the Redis instance; set TTL = 1h for inactive boards. Profile Y.Doc size during load test (CC-6). If needed, compress blobs (zstd) before storing in Redis. |
| RISK-7 | **Export entitlement race**: A user downgrades from Premium to Free while an async hi-res export is generating. | Low | Low | Record entitlement at export-request time; allow in-flight export to complete. No refund/block mid-generation. Document in billing-svc changelog. |

---

## 11. Estimated Totals

| Area | Tasks | Estimated Hours |
|---|---|---|
| Backend — Whiteboard | 10 | 61 |
| Frontend Web — Whiteboard | 4 | 28 |
| Frontend Mobile — Whiteboard | 6 | 34 |
| Backend — Project Plan | 7 | 42 |
| Frontend Web — Project Plan | 4 | 35 |
| Frontend Mobile — Project Plan | 5 | 45 |
| Cross-Cutting | 6 | 43 |
| **Total** | **42** | **~288** |

At a two-engineer sprint velocity of ~80 hours/week productive (factoring reviews + overhead), this represents approximately **3.5 to 4 sprint weeks** for P9 feature completion, after P8 collab lifecycle is stable.

---

*End of plan — spec 010-collab-tools.*
