# 010 — Collab Tools (Whiteboard + Project Plan)

**Phase**: P9.
**Services**: `collab-svc` extension.
**Mission**: Two in-workspace tools: a tldraw-embedded virtual whiteboard with server-side persistence, and a native lightweight project-plan tool (tasks/owners/due dates/comments) modeled in Postgres and rendered in RN + Web.

## In scope (master Journey C FR-C-4, FR-C-5)

### Whiteboard
- tldraw embedded via WebView in RN; native React-tldraw in Web.
- Persistence: snapshot to S3 on idle (10s); diff stream stored in Postgres for replay.
- Two-user concurrent edit (Yjs-on-tldraw recommended; Phase 5 confirms).
- Export to PNG/PDF (Premium for high-res; basic for free).

### Project plan
- Tasks: title (200ch), description (2000ch), assignee (one of two participants), due_date (nullable), status (todo|in_progress|done|blocked), order.
- Comments: per-task threaded (500ch each).
- Activity log: task created/edited/closed events shown in a sidebar; mirrored to chat as system messages when status flips.
- Sort: order (manual) + due_date + status.

## Dependencies

- **Hard**: 007 Chat (rendered inside the collab workspace), 009 Collab Lifecycle (Collaboration owns the tools).
- **Soft**: 013 Billing (high-res whiteboard export = Premium feature).

## Owned entities

- `WhiteboardSnapshot`: collab_id, s3_key, version, created_at.
- `WhiteboardOp` (or yjs doc binary): collab_id, lamport, op (jsonb), actor_profile_id, applied_at.
- `Task`: id, collab_id, title, description, assignee_profile_id (nullable), due_date (nullable), status, order_key, created_by, created_at, closed_at.
- `TaskComment`: id, task_id, author_profile_id, body (500ch), created_at.

## API surface

Whiteboard:
- `WS /whiteboard/{collab_id}` — op stream
- `GET /whiteboard/{collab_id}/snapshot` → latest snapshot
- `POST /whiteboard/{collab_id}/export?format=png|pdf&resolution=basic|hi`

Tasks:
- `GET /collabs/{collab_id}/tasks`
- `POST /collabs/{collab_id}/tasks` body `{title, description?, assignee_profile_id?, due_date?}`
- `PATCH /tasks/{id}` body `{status?, title?, description?, assignee_profile_id?, due_date?, order_key?}`
- `DELETE /tasks/{id}`
- `POST /tasks/{id}/comments` body `{body}`
- `GET /tasks/{id}/comments?cursor=...`

### Queue events

- `task.status_changed` (system message into chat: "{actor} moved {task} to Done")
- `whiteboard.snapshot_saved` (analytics)

## Acceptance criteria

- Whiteboard concurrent edits converge.
- Snapshot every 10s of idle; reloadable on app restart.
- Export PNG free / PDF hi-res Premium.
- Tasks CRUD + reorder + assignee toggle works.
- Status flip mirrors a system msg into the chat.

## NFRs

- Whiteboard op delivery <250ms.
- Task list P95 <150ms.

## Open

- tldraw Yjs binding maturity in RN-WebView vs custom CRDT — Phase 5 detail / research.
