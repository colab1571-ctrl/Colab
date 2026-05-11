# 009 — Collab Lifecycle + Feedback + History — Implementation Plan

**Spec**: `009-collab-lifecycle/spec.md`
**Phase**: P8 — Collab Lifecycle
**Service**: `collab-svc` (FastAPI, Postgres, Redis, Celery, S3)
**Plan date**: 2026-05-11
**Author**: spec-detailing agent

---

## 1. Mission Recap

`collab-svc` owns the full lifecycle of a Collaboration aggregate from the moment a mutual Vibe-Check match fires through final archival and optional export. It is the authoritative source for:

- Collaboration status and the event log of every transition.
- Inactivity-based nudge and auto-archive logic (14 d / 30 d cadence).
- End-of-collab feedback collection — **thumbs up / down + tag chips** (not 1–5 stars), with separate ratings for the *project* and the *partner*.
- Premium-only PDF-transcript + ZIP-of-media export, generated async via Celery.
- Journey G activity-history and full-text search across titles, descriptions, collaborator names, and file names — chat content is explicitly excluded from search.

Platform context (from `000-master/spec.md`):
- Architecture: FastAPI microservices on EKS; Postgres + Redis; Celery + RabbitMQ (Amazon MQ); S3 + CloudFront.
- Entitlement gate: `chat_export` is Premium+. `collab-svc` checks entitlement via `billing-svc` before accepting export requests.
- Realtime chat (spec 007) is a dependency for export content; chat messages are persisted by `chat-svc` and consumed here only for export and for `last_activity_at` updates.
- Notifications for nudges are delegated to `notification-svc` via a RabbitMQ event.

---

## 2. Research — Technology Choices

### 2.1 Full-Text Search — PostgreSQL `tsvector`

**Choice**: Native Postgres full-text search via `tsvector` column maintained by a trigger.

Rationale:
- Stack already committed to Postgres (ARC-6). Avoids a separate search cluster at this scale (10 k → 100 k DAU).
- `tsvector` supports weighted ranking (`setweight`): title carries weight `'A'`, description `'B'`, collaborator names `'C'`, file names `'D'`.
- `GIN` index on `search_vector` gives O(log N) lookup. At 100 k DAU with a ~1:3 conversion ratio (≈30 k collabs), index fits comfortably in shared_buffers.
- `plainto_tsquery` used in the query path for user-facing search (robust to raw user input; no syntax errors). `websearch_to_tsquery` considered for future advanced-search mode.
- **Chat content excluded** — `ChatMessage.body` is deliberately not indexed here (per FR-G-4 and the master spec constraint). Searching chat is out of scope this milestone.

Upgrade path: if DAU reaches 100 k and query latency degrades, the `search_vector` column can be mirrored to OpenSearch without changing the API contract.

### 2.2 PDF Transcript Generation — WeasyPrint (primary) / wkhtmltopdf (fallback)

**Primary**: **WeasyPrint** (Python-native, no headless browser, pip-installable in the Celery worker image).

| Concern | WeasyPrint | wkhtmltopdf |
|---|---|---|
| Dependency | Pure Python + Cairo | Headless Qt browser |
| Docker image delta | ~60 MB | ~250 MB |
| CSS support | CSS 2.1 + partial CSS 3 | Full CSS 3 via WebKit |
| Thread-safety | Yes | Subprocess per call |
| License | BSD | LGPL |

For the transcript use case (structured table of messages, timestamps, metadata header) WeasyPrint's CSS support is sufficient. wkhtmltopdf is available as a fallback if a richer HTML template is required post-launch.

**Template approach**: Jinja2 renders an HTML template populated with sanitized message data → WeasyPrint converts to PDF. The template carries the Colab watermark + SHA-256 content hash on the cover page for tamper evidence.

### 2.3 ZIP of Media — `aiozipstream`

**Choice**: `aiozipstream` (async streaming ZIP generation).

- Streams S3 objects into a ZIP without materializing the full archive in memory — critical for collabs with large video attachments.
- Integrates with `aiofiles` and `aiobotocore` (S3 async client) so the Celery worker can download each S3 object in chunks and pipe directly into the ZIP stream.
- Output is uploaded to S3 using S3's multipart upload API, allowing the worker to forward the stream without buffering the entire ZIP locally.
- Fallback: if `aiozipstream` encounters a stream error, the worker falls back to sequential download-and-zip via Python's built-in `zipfile` module (with a 2 GB limit enforced upstream).

### 2.4 Async Export — Celery

**Choice**: Celery with RabbitMQ broker (Amazon MQ — already in the platform stack, ARC-24).

- `collab_export_generate` task: fetches chat history from `chat-svc` internal API, renders PDF, streams ZIP, uploads both to S3, updates `CollabExport.status`.
- Task is idempotent via Redis lock keyed on `export_id` — concurrent retries skip if a lock is held.
- Celery Beat runs an hourly `inactivity_check` schedule task (see § 5).
- Result backend: Redis (existing ElastiCache cluster). Export status is also stored in `CollabExport.status` (Postgres) so the result backend is not load-bearing for the client-facing status endpoint.

---

## 3. Detailed Data Model

### 3.1 `Collaboration`

```sql
CREATE TABLE collab.collaboration (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id_a    UUID NOT NULL REFERENCES profile.profile(id),
    profile_id_b    UUID NOT NULL REFERENCES profile.profile(id),
    -- Derived convenience (either participant can act as "initiator" — no ownership)
    title           TEXT,                     -- nullable; default rendered client-side as "Collab with {name}"
    description     TEXT,                     -- nullable; set by either participant
    status          TEXT NOT NULL DEFAULT 'still_deciding'
                        CHECK (status IN (
                            'still_deciding',
                            'in_progress',
                            'completed',
                            'didnt_work_out'
                        )),
    is_read_only    BOOLEAN NOT NULL DEFAULT FALSE,   -- flipped on block.created
    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    nudge_sent_at   TIMESTAMPTZ,              -- set when 14-day nudge fires; cleared on activity
    archive_at      TIMESTAMPTZ,              -- computed by trigger / Celery; null for terminal states
    archived_at     TIMESTAMPTZ,              -- set on actual archive
    completed_at    TIMESTAMPTZ,             -- set when status → completed
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Full-text search vector (maintained by trigger)
    search_vector   TSVECTOR
);

-- Prevent duplicate collab between same pair (order-independent)
CREATE UNIQUE INDEX collaboration_participants_unique
    ON collab.collaboration (LEAST(profile_id_a, profile_id_b), GREATEST(profile_id_a, profile_id_b));

-- GIN index for full-text search
CREATE INDEX idx_collaboration_search_vector
    ON collab.collaboration USING GIN (search_vector);

-- Standard indexes
CREATE INDEX idx_collaboration_profile_a ON collab.collaboration (profile_id_a);
CREATE INDEX idx_collaboration_profile_b ON collab.collaboration (profile_id_b);
CREATE INDEX idx_collaboration_status ON collab.collaboration (status);
CREATE INDEX idx_collaboration_last_activity ON collab.collaboration (last_activity_at);
CREATE INDEX idx_collaboration_archive_at ON collab.collaboration (archive_at) WHERE archive_at IS NOT NULL;
```

**`search_vector` composition** (maintained by trigger — see § 7):

| Source field | Weight |
|---|---|
| `title` | A |
| `description` | B |
| Collaborator display names (joined at trigger time) | C |
| File names from `collab_file_name` denormalized table | D |

### 3.2 `CollabStatusEvent`

```sql
CREATE TABLE collab.collab_status_event (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    collab_id        UUID NOT NULL REFERENCES collab.collaboration(id) ON DELETE CASCADE,
    actor_profile_id UUID NOT NULL REFERENCES profile.profile(id),
    prev_status      TEXT NOT NULL,
    new_status       TEXT NOT NULL,
    note             TEXT,                 -- optional free-text reason (500 ch max)
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_collab_status_event_collab ON collab.collab_status_event (collab_id, created_at);
```

### 3.3 `CollabFeedback`

Feedback uses **thumbs up / down** (`up` | `down`) plus an array of **tag chips** (enumerated). There is **no 1–5 star rating**. This is a hard constraint from the master spec (FR-C-11) and revises the source data model which referenced a numeric rating.

Feedback targets are `project` and `partner` separately, allowing a participant to feel positively about the creative work but negatively about the collaboration experience (or vice versa).

```sql
CREATE TYPE collab.feedback_rating AS ENUM ('up', 'down');

CREATE TYPE collab.feedback_target AS ENUM ('project', 'partner');

-- Tag chip catalogue (add new values via migration; never remove without backfill)
CREATE TYPE collab.feedback_tag AS ENUM (
    -- Partner tags
    'communicative',
    'responsive',
    'professional',
    'creative',
    'reliable',
    'flexible',
    'ghosted',
    'slow_to_respond',
    'missed_deadlines',
    'scope_creep',
    -- Project tags
    'great_outcome',
    'met_goals',
    'learned_a_lot',
    'good_creative_fit',
    'incomplete',
    'unclear_direction',
    'changed_scope',
    'technical_issues'
);

CREATE TABLE collab.collab_feedback (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    collab_id        UUID NOT NULL REFERENCES collab.collaboration(id) ON DELETE CASCADE,
    from_profile_id  UUID NOT NULL REFERENCES profile.profile(id),
    to_profile_id    UUID,                  -- NULL when target = 'project'; set when target = 'partner'
    target           collab.feedback_target NOT NULL,
    rating           collab.feedback_rating NOT NULL,
    tags             collab.feedback_tag[] NOT NULL DEFAULT '{}',
    comment          TEXT CHECK (char_length(comment) <= 500),  -- optional, 500 ch
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One feedback record per (collab, from_profile, target) — idempotent upsert key
CREATE UNIQUE INDEX collab_feedback_unique
    ON collab.collab_feedback (collab_id, from_profile_id, target);

CREATE INDEX idx_collab_feedback_collab ON collab.collab_feedback (collab_id);
CREATE INDEX idx_collab_feedback_from ON collab.collab_feedback (from_profile_id);
CREATE INDEX idx_collab_feedback_to ON collab.collab_feedback (to_profile_id) WHERE to_profile_id IS NOT NULL;
```

**Constraint**: `to_profile_id` must be the other participant when `target = 'partner'`, enforced by application logic in the service layer (a CHECK constraint referencing the parent table is impractical in SQL without a trigger; handled in Pydantic validator + service).

### 3.4 `CollabExport`

```sql
CREATE TYPE collab.export_status AS ENUM ('pending', 'generating', 'ready', 'failed');

CREATE TABLE collab.collab_export (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    collab_id       UUID NOT NULL REFERENCES collab.collaboration(id) ON DELETE CASCADE,
    requested_by    UUID NOT NULL REFERENCES profile.profile(id),
    status          collab.export_status NOT NULL DEFAULT 'pending',
    pdf_s3_key      TEXT,                  -- set when ready
    zip_s3_key      TEXT,                  -- set when ready; NULL if no media
    error_detail    TEXT,                  -- populated on failure
    requested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ            -- now() + 7 days, set on transition to 'ready'
);

CREATE INDEX idx_collab_export_collab ON collab.collab_export (collab_id);
CREATE INDEX idx_collab_export_requested_by ON collab.collab_export (requested_by);
CREATE INDEX idx_collab_export_status ON collab.collab_export (status) WHERE status IN ('pending', 'generating');
```

### 3.5 `CollabFileName` (search denormalization)

File names need to be searchable (FR-G-4) but live in `chat-svc`'s `ChatAttachment`. A lightweight denormalized table avoids cross-service JOINs in the search path.

```sql
CREATE TABLE collab.collab_file_name (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    collab_id   UUID NOT NULL REFERENCES collab.collaboration(id) ON DELETE CASCADE,
    s3_key      TEXT NOT NULL,
    file_name   TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_collab_file_name_collab ON collab.collab_file_name (collab_id);
```

Populated by consuming the `chat.media.scanned` event (which includes original filename from upload metadata).

---

## 4. State Machine

### 4.1 States

| State | Meaning | Terminal? |
|---|---|---|
| `still_deciding` | Default post-match. Neither participant has committed to a project direction. | No |
| `in_progress` | Active collaboration underway. | No |
| `completed` | Work concluded successfully. Triggers immediate archive. | **Yes** |
| `didnt_work_out` | Collaboration ended without completion. Triggers immediate archive. | **Yes** |

### 4.2 Allowed Transitions

| From | To | Allowed? | Notes |
|---|---|---|---|
| `still_deciding` | `in_progress` | Yes | Either participant |
| `still_deciding` | `completed` | Yes | Either participant (edge case: short collab) |
| `still_deciding` | `didnt_work_out` | Yes | Either participant |
| `in_progress` | `completed` | Yes | Either participant |
| `in_progress` | `didnt_work_out` | Yes | Either participant |
| `in_progress` | `still_deciding` | Yes | Either participant (backtrack allowed) |
| `completed` | *(any)* | **No** | Terminal state |
| `didnt_work_out` | *(any)* | **No** | Terminal state |
| *(any)* | `still_deciding` from `in_progress` | Yes | Only backward from in_progress |

**Enforcement**: Service layer raises `HTTP 409 Conflict` with `error_code: INVALID_TRANSITION` for disallowed transitions. The full matrix above is encoded as a `TRANSITION_MAP: dict[str, set[str]]` constant in `collab_svc/domain/state_machine.py`.

### 4.3 Transition Side-Effects

| Transition | Side-effects |
|---|---|
| Any → `completed` | Set `completed_at = now()`, `archive_at = now()` (immediate), emit `collab.status_changed` |
| Any → `didnt_work_out` | Set `archive_at = now()` (immediate), emit `collab.status_changed` |
| Any → `in_progress` | Clear `nudge_sent_at`, reset `archive_at` per inactivity formula |
| Any → `still_deciding` (from in_progress) | Reset `archive_at` based on `last_activity_at` |
| `archive_at` reached (Celery Beat) | Set `archived_at = now()`, clear `archive_at`, emit `collab.archived` |
| `block.created` consumed | Set `is_read_only = true`, `archive_at = now() + 30 days` |

---

## 5. Inactivity Cadence

### 5.1 Architecture

Celery Beat fires an hourly task: `collab_svc.tasks.inactivity_check`.

The task runs a single Postgres query selecting non-terminal, non-archived collabs where inactivity thresholds are crossed, then dispatches per-collab subtasks for nudge or archive.

```sql
-- Hourly query (inactivity_check)
SELECT id, last_activity_at, nudge_sent_at, status
FROM collab.collaboration
WHERE
    status IN ('still_deciding', 'in_progress')
    AND archived_at IS NULL
    AND (
        -- Nudge window: 14d inactive, nudge not yet sent (or was sent > 14d ago and activity resumed)
        (last_activity_at < now() - INTERVAL '14 days' AND nudge_sent_at IS NULL)
        OR
        -- Archive window: 30d inactive regardless of nudge
        (last_activity_at < now() - INTERVAL '30 days')
    );
```

### 5.2 `last_activity_at` Recomputation

Updated by consuming the `chat.message.sent` event from `chat-svc`. The consumer sets `last_activity_at = now()` on the relevant `Collaboration` row and clears `nudge_sent_at` (if set), resetting the inactivity clock.

### 5.3 Nudge (14-Day)

Trigger: `last_activity_at < now() - 14 days` AND `nudge_sent_at IS NULL`.

Action:
1. Emit `collab.nudge_due` event to RabbitMQ with `{collab_id, profile_id_a, profile_id_b}`.
2. Set `nudge_sent_at = now()`.
3. `notification-svc` consumes `collab.nudge_due` and sends push + in-app banner + email fallback to both participants.

The nudge fires **once** per inactivity window. If the collab becomes active again (new chat message), `nudge_sent_at` is cleared, enabling a future nudge after another 14 d of inactivity.

### 5.4 Auto-Archive (30-Day)

Trigger: `last_activity_at < now() - 30 days`.

Action:
1. Set `archived_at = now()`, clear `archive_at`.
2. Emit `collab.archived` event.
3. The collab remains readable (history) but no new messages can be sent (chat-svc respects the `archived` state).

### 5.5 Immediate Archive (Terminal States)

When status transitions to `completed` or `didnt_work_out`:
1. Service sets `archive_at = now()` inline (not via Celery).
2. A Celery task `collab_archive_finalize` is enqueued immediately to handle any async cleanup (e.g., signing off on any open export tasks, emitting `collab.archived`).

---

## 6. Export Pipeline

### 6.1 Flow

```
Client POST /collabs/{id}/export
    ├─ Entitlement check (billing-svc): chat_export = true
    ├─ Participant check: requested_by ∈ {profile_id_a, profile_id_b}
    ├─ Insert CollabExport(status=pending)
    ├─ Enqueue Celery task collab_export_generate(export_id)
    └─ Return HTTP 202 { export_id, status: "pending" }

Celery Worker: collab_export_generate(export_id)
    ├─ Acquire Redis lock (key: export:{export_id}, TTL: 10 min)
    ├─ Set CollabExport.status = generating, started_at = now()
    ├─ Fetch chat history: internal GET chat-svc /internal/rooms/{room_id}/messages (paginated, all)
    ├─ Fetch media list: internal GET chat-svc /internal/rooms/{room_id}/attachments
    ├─ Render PDF via WeasyPrint (Jinja2 template):
    │   ├─ Cover page: collab title, participants, date range, SHA-256(all_message_ids)
    │   ├─ Message transcript: chronological, sender, timestamp, body
    │   └─ Watermark footer: "Colab — Confidential — {collab_id}"
    ├─ Upload PDF to S3: exports/{collab_id}/{export_id}/transcript.pdf
    ├─ Stream media ZIP via aiozipstream → S3 multipart upload:
    │   └─ exports/{collab_id}/{export_id}/media.zip
    │       (omitted if no media attachments)
    ├─ Set CollabExport: status=ready, pdf_s3_key, zip_s3_key, expires_at=now()+7d, completed_at=now()
    ├─ Release Redis lock
    └─ Emit collab.export_ready event

Client GET /collabs/exports/{id}
    ├─ If status=ready: generate CloudFront signed URLs (7-day TTL) for pdf_s3_key + zip_s3_key
    └─ Return { status, pdf_url?, zip_url?, expires_at }
```

### 6.2 Status Lifecycle

```
pending → generating → ready
                    ↘ failed
```

- `failed`: Worker sets `error_detail` with a sanitized message. Client sees `status: failed` and can retry (`POST /collabs/{id}/export` creates a new `CollabExport` row; no cooldown required at this stage).
- `ready` exports expire after 7 days. After expiry, signed URLs are no longer generated; client must request a new export.

### 6.3 S3 Key Schema

```
exports/{collab_id}/{export_id}/transcript.pdf
exports/{collab_id}/{export_id}/media.zip
```

Both keys live under the private S3 bucket. Access is exclusively via CloudFront signed URLs with 7-day TTL. Keys are never public.

### 6.4 Premium Entitlement Enforcement

`POST /collabs/{id}/export` calls `billing-svc` internal endpoint `GET /internal/entitlements/{profile_id}` and checks `chat_export == true`. Returns `HTTP 403 { error_code: EXPORT_REQUIRES_PREMIUM }` if the entitlement is absent.

---

## 7. Full-Text Search

### 7.1 Query Plan

```sql
-- Search query (called from GET /collabs?q={query})
SELECT
    c.id,
    c.title,
    c.status,
    c.last_activity_at,
    ts_rank_cd(c.search_vector, query) AS rank
FROM collab.collaboration c,
     plainto_tsquery('english', :query_text) AS query
WHERE
    -- Participant filter (required — user can only search their own collabs)
    (c.profile_id_a = :current_profile_id OR c.profile_id_b = :current_profile_id)
    -- Full-text match
    AND c.search_vector @@ query
    -- Optional status filter
    AND (:status_filter IS NULL OR c.status = :status_filter)
    -- Exclude hard-deleted / not yet created
    AND c.archived_at IS NULL  -- or include per ?include_archived=true
ORDER BY rank DESC, c.last_activity_at DESC
LIMIT 20
OFFSET :offset;
```

The GIN index on `search_vector` is used for the `@@` operator. The participant equality filters use the `idx_collaboration_profile_a` / `idx_collaboration_profile_b` indexes.

### 7.2 Search Vector Trigger

The trigger maintains `search_vector` on every `INSERT` or `UPDATE` to `collab.collaboration`. It also re-fires when a row is inserted into `collab.collab_file_name` for the associated collab, and when a profile's display name changes (via a `profile.display_name_changed` event consumed from RabbitMQ, which calls an internal function to refresh affected collabs).

```sql
CREATE OR REPLACE FUNCTION collab.refresh_search_vector(collab_id UUID)
RETURNS VOID AS $$
DECLARE
    v_title TEXT;
    v_description TEXT;
    v_names TEXT;
    v_file_names TEXT;
BEGIN
    SELECT c.title, c.description INTO v_title, v_description
    FROM collab.collaboration c WHERE c.id = collab_id;

    -- Collaborator display names (fetched via foreign data wrapper or materialized view;
    -- in practice, the service layer provides names and stores them in a denorm column)
    SELECT string_agg(display_name, ' ')
    INTO v_names
    FROM collab.collab_participant_name_cache
    WHERE collab_id = collab_id;

    SELECT string_agg(file_name, ' ')
    INTO v_file_names
    FROM collab.collab_file_name
    WHERE collab_id = collab_id;

    UPDATE collab.collaboration
    SET search_vector =
        setweight(to_tsvector('english', coalesce(v_title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(v_description, '')), 'B') ||
        setweight(to_tsvector('english', coalesce(v_names, '')), 'C') ||
        setweight(to_tsvector('english', coalesce(v_file_names, '')), 'D')
    WHERE id = collab_id;
END;
$$ LANGUAGE plpgsql;

-- Trigger on collaboration table
CREATE OR REPLACE FUNCTION collab.trg_collaboration_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM collab.refresh_search_vector(NEW.id);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_collaboration_search_vector
AFTER INSERT OR UPDATE OF title, description
ON collab.collaboration
FOR EACH ROW EXECUTE FUNCTION collab.trg_collaboration_search_vector();

-- Trigger on collab_file_name
CREATE OR REPLACE FUNCTION collab.trg_collab_file_name_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM collab.refresh_search_vector(NEW.collab_id);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_collab_file_name_search_vector
AFTER INSERT
ON collab.collab_file_name
FOR EACH ROW EXECUTE FUNCTION collab.trg_collab_file_name_search_vector();
```

**Collaborator name cache**: A `collab_participant_name_cache(collab_id, profile_id, display_name)` table is maintained by consuming `profile.display_name_changed` events, preventing cross-schema JOINs at trigger time.

### 7.3 Search Exclusion: Chat Content

`ChatMessage.body` is deliberately absent from the `search_vector` construction. This is both a scope constraint (FR-G-4 limits search to titles, descriptions, collaborator names, file names) and a privacy design choice. Searching private chat content is explicitly deferred to a future milestone.

---

## 8. Feedback Semantics

### 8.1 Rating Model

- **Up / Down only** — `collab.feedback_rating ENUM ('up', 'down')`. No 1–5 numeric scale.
- **Tag chips** — `collab.feedback_tag[]`. Client renders chips from the enum catalogue; backend validates against the enum. Tags are additive context, not a secondary rating axis.
- **Comment** — optional, 500-character free text. Stored in `collab.collab_feedback.comment`.

### 8.2 Separate Targets

Each participant submits up to **two** feedback records per collab: one with `target = 'project'`, one with `target = 'partner'`. The unique index on `(collab_id, from_profile_id, target)` enforces one record per combination.

- `target = 'project'`: `to_profile_id = NULL`. Reflects the creative work and outcome.
- `target = 'partner'`: `to_profile_id = <other participant's profile_id>`. Reflects the collaboration experience with the partner.

### 8.3 Idempotent Endpoint

`POST /collabs/{id}/feedback` is idempotent per `(collab_id, from_profile_id, target)`.

Logic:
1. Parse and validate the request body.
2. Attempt `INSERT INTO collab_feedback ... ON CONFLICT (collab_id, from_profile_id, target) DO UPDATE SET rating = EXCLUDED.rating, tags = EXCLUDED.tags, comment = EXCLUDED.comment, created_at = EXCLUDED.created_at`.
3. Return the upserted record with `HTTP 200`.

This allows a participant to change their mind about feedback as long as the collab is in a terminal state (feedback is only accepted post-completion — service checks `collab.status IN ('completed', 'didnt_work_out')`).

### 8.4 Feedback Availability on Profile

The `up_vote_count` visible on profile detail view (FR-B-6: "past collab feedback up-vote count") is a rollup query against `collab_feedback` filtered to `target = 'partner' AND rating = 'up'`. This rollup is computed at query time (or materialized on a 1-hour schedule) in `profile-svc` via an internal `collab-svc` endpoint.

### 8.5 Post-Completion Trigger

When a collab transitions to `completed` or `didnt_work_out`, `collab-svc` emits `collab.feedback_prompt_due` (with `{collab_id, profile_id_a, profile_id_b}`). `notification-svc` consumes this and sends the feedback prompt notification to both participants once.

---

## 9. API Contracts

All endpoints are served by `collab-svc` under the path prefix `/collabs`. Auth is enforced by the gateway (JWT bearer). Rate limits: standard tier (per gateway config).

---

### `GET /collabs`

List collaborations for the authenticated user.

**Query parameters**:

| Param | Type | Default | Description |
|---|---|---|---|
| `status` | `active \| past \| all` | `all` | `active` = non-terminal + non-archived; `past` = terminal or archived |
| `q` | `string` | — | Full-text search query |
| `cursor` | `string` | — | Opaque pagination cursor (base64-encoded last row's `(rank, last_activity_at, id)`) |
| `limit` | `integer` | `20` | Max 50 |
| `include_archived` | `boolean` | `false` | Include archived collabs in non-terminal status filter |

**Response `200 OK`**:
```json
{
  "data": [
    {
      "id": "uuid",
      "title": "string | null",
      "status": "still_deciding | in_progress | completed | didnt_work_out",
      "is_read_only": false,
      "last_activity_at": "2026-05-01T12:00:00Z",
      "archived_at": null,
      "partner": {
        "profile_id": "uuid",
        "display_name": "string",
        "avatar_url": "string | null"
      },
      "created_at": "2026-04-01T10:00:00Z"
    }
  ],
  "next_cursor": "string | null",
  "total_count": 42
}
```

---

### `GET /collabs/{id}`

Get a single collaboration.

**Response `200 OK`**:
```json
{
  "id": "uuid",
  "title": "string | null",
  "description": "string | null",
  "status": "in_progress",
  "is_read_only": false,
  "last_activity_at": "2026-05-10T08:00:00Z",
  "nudge_sent_at": null,
  "archive_at": null,
  "archived_at": null,
  "completed_at": null,
  "created_at": "2026-04-01T10:00:00Z",
  "participants": [
    { "profile_id": "uuid", "display_name": "Alice", "avatar_url": "..." },
    { "profile_id": "uuid", "display_name": "Bob", "avatar_url": "..." }
  ],
  "status_history": [
    {
      "prev_status": "still_deciding",
      "new_status": "in_progress",
      "actor_profile_id": "uuid",
      "note": null,
      "created_at": "2026-04-15T09:00:00Z"
    }
  ],
  "feedback": [
    {
      "from_profile_id": "uuid",
      "target": "partner",
      "rating": "up",
      "tags": ["communicative", "creative"],
      "comment": null,
      "created_at": "2026-05-05T14:00:00Z"
    }
  ]
}
```

**Errors**: `404` if collab not found or caller is not a participant.

---

### `PATCH /collabs/{id}`

Update mutable fields (title, description).

**Request body**:
```json
{
  "title": "Our Album Cover Project",
  "description": "Creating artwork for the summer EP"
}
```

**Response `200 OK`**: Updated collab object (abbreviated).

**Errors**: `403` if read-only (blocked or archived). `404` if not found.

---

### `POST /collabs/{id}/status`

Transition status.

**Request body**:
```json
{
  "new_status": "in_progress",
  "note": "We've agreed on the concept!"
}
```

**Response `200 OK`**:
```json
{
  "id": "uuid",
  "status": "in_progress",
  "status_event": {
    "id": "uuid",
    "prev_status": "still_deciding",
    "new_status": "in_progress",
    "actor_profile_id": "uuid",
    "note": "We've agreed on the concept!",
    "created_at": "2026-05-11T10:00:00Z"
  }
}
```

**Errors**:
- `409 Conflict` — `{ "error_code": "INVALID_TRANSITION", "message": "..." }`
- `403 Forbidden` — `{ "error_code": "COLLAB_READ_ONLY" }` (blocked or archived)
- `403 Forbidden` — `{ "error_code": "COLLAB_ARCHIVED" }` (already archived)

---

### `POST /collabs/{id}/feedback`

Submit or update feedback. Idempotent per `(collab_id, from_profile_id, target)`.

**Request body**:
```json
{
  "target": "partner",
  "rating": "up",
  "tags": ["communicative", "creative"],
  "comment": "Great to work with, very responsive."
}
```

**Validations**:
- `target` must be `project` or `partner`.
- `rating` must be `up` or `down`.
- `tags` must be a subset of the `feedback_tag` enum.
- `comment` ≤ 500 characters.
- Collab must be in terminal state (`completed` or `didnt_work_out`).
- Caller must be a participant.

**Response `200 OK`**:
```json
{
  "id": "uuid",
  "collab_id": "uuid",
  "from_profile_id": "uuid",
  "to_profile_id": "uuid | null",
  "target": "partner",
  "rating": "up",
  "tags": ["communicative", "creative"],
  "comment": "Great to work with, very responsive.",
  "created_at": "2026-05-11T10:00:00Z"
}
```

**Errors**:
- `400 Bad Request` — `{ "error_code": "INVALID_FEEDBACK_TARGET" }` or `{ "error_code": "INVALID_TAG" }`
- `403 Forbidden` — `{ "error_code": "FEEDBACK_REQUIRES_TERMINAL_STATE" }`
- `404 Not Found` — collab not found or caller not a participant

---

### `POST /collabs/{id}/export`

Request export (Premium-only).

**Request body**: empty.

**Response `202 Accepted`**:
```json
{
  "export_id": "uuid",
  "status": "pending",
  "requested_at": "2026-05-11T10:00:00Z"
}
```

**Errors**:
- `403 Forbidden` — `{ "error_code": "EXPORT_REQUIRES_PREMIUM" }`
- `403 Forbidden` — `{ "error_code": "COLLAB_NOT_ACCESSIBLE" }` (caller not a participant)
- `404 Not Found` — collab not found

---

### `GET /collabs/exports/{export_id}`

Poll export status.

**Response `200 OK`**:
```json
{
  "export_id": "uuid",
  "collab_id": "uuid",
  "status": "ready",
  "pdf_url": "https://cdn.<domain>/exports/...?signature=...&expires=...",
  "zip_url": "https://cdn.<domain>/exports/...?signature=...&expires=...",
  "expires_at": "2026-05-18T10:00:00Z",
  "requested_at": "2026-05-11T10:00:00Z",
  "completed_at": "2026-05-11T10:02:30Z"
}
```

`pdf_url` and `zip_url` are CloudFront signed URLs valid for 7 days from `expires_at`. `zip_url` is `null` if the collab had no media attachments.

**Errors**: `404` if export not found or caller did not request it.

---

### `GET /me/history/requests/sent`

Proxied from `invite-svc`. Returns paginated list of Vibe Check requests sent by the caller.

**Query params**: `status` (pending | accepted | rejected | expired | all), `cursor`, `limit`.

**Response**: paginated list of invite summaries (invite_id, recipient profile stub, synopsis excerpt, status, sent_at, responded_at).

---

### `GET /me/history/requests/received`

Proxied from `invite-svc`. Returns paginated list of Vibe Check requests received by the caller.

**Query params**: same as above.

**Response**: same shape, sender profile stub.

---

## 10. Implementation Tasks

| ID | Title | Outcome | Est Hours | Blocks | Blocked By |
|---|---|---|---|---|---|
| T-009-01 | Postgres schema migration | All tables, indexes, enums, triggers created via Alembic | 4 | T-009-02, T-009-03 | 002, 003 (platform + auth base) |
| T-009-02 | `match.created` consumer | Inserts `Collaboration` + emits `collab.created` on receipt of match event | 3 | T-009-04 | T-009-01, 006 (invite-svc match event) |
| T-009-03 | Search vector trigger + name cache | Trigger functions, `collab_participant_name_cache` table, consumer for `profile.display_name_changed` | 4 | T-009-12 | T-009-01 |
| T-009-04 | Status transition service + API | `POST /collabs/{id}/status`, state machine enforcement, `CollabStatusEvent` insert, side-effect dispatch | 5 | T-009-05, T-009-09 | T-009-01, T-009-02 |
| T-009-05 | Collab list + detail API | `GET /collabs`, `GET /collabs/{id}`, `PATCH /collabs/{id}` | 5 | T-009-12 | T-009-04 |
| T-009-06 | `chat.message.sent` consumer | Updates `last_activity_at`, clears `nudge_sent_at` | 2 | T-009-07 | T-009-01, 007 (chat-svc events) |
| T-009-07 | Celery Beat inactivity task | Hourly `inactivity_check`; dispatches nudge and archive subtasks | 4 | T-009-08 | T-009-06 |
| T-009-08 | Nudge emission | Emits `collab.nudge_due`; sets `nudge_sent_at` | 2 | — | T-009-07 |
| T-009-09 | Auto-archive logic | Sets `archived_at`, emits `collab.archived`; handles terminal-state immediate archive | 3 | — | T-009-07, T-009-04 |
| T-009-10 | `block.created` consumer | Sets `is_read_only = true`, `archive_at = now()+30d` | 2 | — | T-009-01, 008 (block events) |
| T-009-11 | Feedback API | `POST /collabs/{id}/feedback` — upsert logic, validation, `collab.feedback_prompt_due` emission | 5 | — | T-009-04 |
| T-009-12 | Full-text search | Search query, index tuning, `collab_file_name` consumer from `chat.media.scanned`, integration into `GET /collabs?q=` | 5 | — | T-009-03, T-009-05 |
| T-009-13 | Export entitlement check | Internal call to `billing-svc`; `403` if not Premium | 2 | T-009-14 | 013 (billing-svc) |
| T-009-14 | Export request API | `POST /collabs/{id}/export` → `CollabExport` insert → enqueue Celery task → `202` | 3 | T-009-15 | T-009-13 |
| T-009-15 | Celery export worker — PDF | WeasyPrint + Jinja2 template; fetches messages from `chat-svc` internal API; uploads PDF to S3 | 8 | T-009-16 | T-009-14, 007 (chat-svc internal API) |
| T-009-16 | Celery export worker — ZIP | `aiozipstream` + S3 multipart; streams media; sets `CollabExport` ready | 6 | T-009-17 | T-009-15 |
| T-009-17 | Export status API | `GET /collabs/exports/{id}` → signed CloudFront URL generation | 3 | — | T-009-16 |
| T-009-18 | Requests history proxy | `GET /me/history/requests/sent`, `/received` — proxy to `invite-svc` internal endpoint with pagination | 3 | — | T-009-05, 006 |
| T-009-19 | OpenAPI spec + TS client codegen | Finalise OpenAPI schema; run codegen; publish typed TS client to shared package | 2 | — | T-009-05, T-009-11, T-009-14, T-009-17, T-009-18 |
| T-009-20 | Unit tests — state machine | Full transition matrix coverage; invalid transitions; side-effects | 4 | — | T-009-04 |
| T-009-21 | Unit tests — feedback | Idempotency, invalid target, pre-terminal rejection, tag validation | 3 | — | T-009-11 |
| T-009-22 | Integration tests — inactivity | Celery Beat mock; 14d nudge fires once; 30d archive; activity clears nudge | 4 | — | T-009-07, T-009-08, T-009-09 |
| T-009-23 | Integration tests — export | PDF render correctness; ZIP integrity; expiry; Premium gate | 5 | — | T-009-16, T-009-17 |
| T-009-24 | Integration tests — search | FTS weights; participant isolation; archived include/exclude; no chat content leakage | 3 | — | T-009-12 |
| T-009-25 | Load test — collab list P95 | Verify `GET /collabs` P95 <200 ms at 10 k concurrent users | 3 | — | T-009-05 |
| T-009-26 | Load test — export median/P95 | Verify median <60 s, P95 <5 min under concurrent export requests | 3 | — | T-009-16 |

**Total estimated**: ~97 hours.

---

## 11. Acceptance Criteria

### AC-1 — Collaboration Created on Match

**Given** a `match.created` event is consumed by `collab-svc`  
**When** the consumer processes the event  
**Then**  
- A `Collaboration` row is inserted with `status = 'still_deciding'`, `last_activity_at = now()`, `archive_at = NULL`, `archived_at = NULL`.  
- `collab.created` event is emitted to RabbitMQ.  
- A second `match.created` event for the same pair is idempotent (no duplicate row, per unique index).

**Verification**: Integration test; also verify via `GET /collabs/{id}` returning the new collab.

---

### AC-2 — Status Transitions Enforced

**Given** a collab in state `S`  
**When** a participant calls `POST /collabs/{id}/status` with `new_status = T`  
**Then**  
- Allowed transitions succeed with `200 OK` + `CollabStatusEvent` created.  
- Disallowed transitions return `409 Conflict` with `error_code: INVALID_TRANSITION`.  
- Transitions from `completed` or `didnt_work_out` always return `409`.

**Verification**: Unit test covering all 25 cells of the transition matrix.

---

### AC-3 — Archive Side-Effects on Terminal Transition

**Given** a collab transitions to `completed` or `didnt_work_out`  
**When** the transition is applied  
**Then**  
- `archive_at = now()` is set inline.  
- `archived_at` is set by the finalize task within 5 seconds.  
- `collab.archived` event is emitted.

**Verification**: Integration test with task runner in eager mode.

---

### AC-4 — 14-Day Nudge

**Given** a collab has `last_activity_at < now() - 14 days` and `nudge_sent_at IS NULL`  
**When** the hourly Celery Beat task runs  
**Then**  
- `collab.nudge_due` event is emitted with both `profile_id_a` and `profile_id_b`.  
- `nudge_sent_at` is set to the current timestamp.  
- The nudge is emitted only **once** per inactivity window (second task run does not re-emit).

**Verification**: Integration test with mocked clock; assert exactly one event emitted across two task runs with no intervening activity.

---

### AC-5 — 14-Day Nudge Cleared on Activity

**Given** a nudge was sent (`nudge_sent_at IS NOT NULL`)  
**When** a `chat.message.sent` event is consumed for the collab  
**Then**  
- `last_activity_at` is updated to event timestamp.  
- `nudge_sent_at` is set to `NULL`.

**Verification**: Unit test on the consumer handler.

---

### AC-6 — 30-Day Auto-Archive

**Given** a collab has `last_activity_at < now() - 30 days` and `status IN ('still_deciding', 'in_progress')`  
**When** the hourly Celery Beat task runs  
**Then**  
- `archived_at` is set.  
- `collab.archived` event is emitted.  
- The collab is no longer returned in `GET /collabs?status=active`.

**Verification**: Integration test with mocked clock (advance 31 days).

---

### AC-7 — Block → Read-Only + Deferred Archive

**Given** a `block.created` event is consumed for a participant pair  
**When** the consumer processes the event  
**Then**  
- `is_read_only = true` on the collab.  
- `archive_at = now() + 30 days` is set.  
- `POST /collabs/{id}/status` returns `403 { error_code: COLLAB_READ_ONLY }`.

**Verification**: Integration test consuming a synthetic `block.created` event.

---

### AC-8 — Feedback Idempotency

**Given** a participant submits feedback for `target = 'partner'` with `rating = 'up'`  
**When** the same participant submits feedback again for the same `(collab_id, target)` with `rating = 'down'`  
**Then**  
- The existing record is updated to `rating = 'down'`.  
- Only one row exists for `(collab_id, from_profile_id, target)`.  
- HTTP `200` is returned on both calls.

**Verification**: Unit test on the upsert logic.

---

### AC-9 — Feedback Requires Terminal State

**Given** a collab with `status = 'in_progress'`  
**When** a participant calls `POST /collabs/{id}/feedback`  
**Then**  
- HTTP `403` is returned with `error_code: FEEDBACK_REQUIRES_TERMINAL_STATE`.

**Verification**: Unit test.

---

### AC-10 — Export Premium Gate

**Given** a user with `chat_export = false` (Free tier)  
**When** the user calls `POST /collabs/{id}/export`  
**Then**  
- HTTP `403` is returned with `error_code: EXPORT_REQUIRES_PREMIUM`.  
- No `CollabExport` row is created.

**Verification**: Integration test mocking billing-svc internal response.

---

### AC-11 — Export Generated Within P95 Threshold

**Given** a typical collab (≤500 messages, ≤50 media files totalling ≤500 MB)  
**When** a Premium user requests an export and the Celery worker processes the task  
**Then**  
- Median generation time < 60 seconds.  
- P95 generation time < 5 minutes.  
- `CollabExport.status = 'ready'` is set.  
- `pdf_s3_key` and (if media present) `zip_s3_key` are set with valid S3 keys.

**Verification**: Load test with synthetic collab fixture.

---

### AC-12 — Export Signed URLs Expire

**Given** a `CollabExport` with `status = 'ready'` and `expires_at < now()`  
**When** the caller polls `GET /collabs/exports/{export_id}`  
**Then**  
- The response omits `pdf_url` and `zip_url` (or returns them as `null`).  
- The `status` field remains `ready` (the export record is not deleted).  
- The user is instructed to request a new export.

**Verification**: Unit test with mocked clock past `expires_at`.

---

### AC-13 — Full-Text Search: Result Correctness

**Given** a collab with `title = "Album Cover Design"` and `description = "Summer EP artwork"`  
**When** the participant calls `GET /collabs?q=summer+artwork`  
**Then**  
- The collab appears in results.  
- `rank` reflects the weighted tsvector match (description weight `'B'`).

**Verification**: Integration test with seeded data.

---

### AC-14 — Full-Text Search: Chat Content Excluded

**Given** a collab with chat messages containing the term "secret project concept"  
**When** the participant calls `GET /collabs?q=secret+project+concept`  
**Then**  
- No results are returned (the term is only in chat content, not in title/description/names/file names).

**Verification**: Integration test.

---

### AC-15 — Full-Text Search: Participant Isolation

**Given** User A and User B have separate collabs, each with the word "photography" in the title  
**When** User A calls `GET /collabs?q=photography`  
**Then**  
- Only User A's collab is returned (not User B's).

**Verification**: Integration test with two user fixtures.

---

### AC-16 — Collab List P95 Latency

**Given** a dataset of 50 k collabs in Postgres with GIN and participant indexes built  
**When** `GET /collabs` is called concurrently at simulated 10 k RPS  
**Then**  
- P95 latency < 200 ms.

**Verification**: k6 load test against staging environment.

---

## 12. Open Risks

| Risk ID | Description | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R-001 | Export worker timeouts for very large collabs (1 000+ messages, >1 GB media) | Medium | High | Implement 10-min Celery task timeout; chunked PDF pagination; multipart ZIP upload with per-file streaming; expose `failed` status to user with "try again" CTA. Enforce upload limits upstream in `media-svc`. |
| R-002 | `chat-svc` internal API unavailable during export | Low | High | Celery retry with exponential backoff (max 5 retries, 30 s / 1 m / 2 m / 5 m / 10 m); after exhaustion, set `status = failed`. |
| R-003 | WeasyPrint rendering edge cases (Unicode, RTL text, very long messages) | Medium | Medium | Sanitize HTML via `bleach` before rendering; enforce line-wrap in CSS template; test with emoji-heavy + multi-language fixtures (English-only launch but names may include non-ASCII). |
| R-004 | `search_vector` trigger latency under high write load (file uploads → trigger per file name) | Low | Medium | Trigger calls a deferred function; batch file-name inserts in the `chat.media.scanned` consumer rather than one-by-one; monitor `pg_stat_activity` for lock contention. |
| R-005 | Profile display name changes not propagating to `search_vector` if `profile.display_name_changed` event is dropped | Medium | Low | Consumer is idempotent; implement Dead Letter Queue on the RabbitMQ consumer; schedule a nightly reconciliation job that refreshes `search_vector` for all collabs where the cached name differs from `profile-svc`. |
| R-006 | Feedback tag enum growth requires migrations | Low | Low | Define a broad initial set of tags; add new values via non-destructive `ALTER TYPE ... ADD VALUE`; never remove values without a backfill migration. |
| R-007 | `collab_export.expires_at` cleanup — S3 accumulates stale exports | Medium | Low | S3 lifecycle rule on the `exports/` prefix: auto-delete objects after 8 days (one day buffer beyond `expires_at`). |
| R-008 | Duplicate `match.created` events (at-least-once delivery) creating duplicate collabs | Low | High | Unique index on `(LEAST(a,b), GREATEST(a,b))` absorbs duplicates. Consumer catches `UniqueViolationError` and treats it as success. |
| R-009 | DMCA agent not registered (inherited from master spec) | Certain | Medium | Moderation pipeline still removes flagged content; full audit trail preserved. Legal risk accepted by product owner at the master spec level. |
| R-010 | India DPDP data residency for exports stored in us-east-1 S3 | Low | Medium | Flagged as `[NEEDS CLARIFICATION]` in Phase 5. Export S3 keys follow the same residency posture as all media (us-east-1 + SCCs). Revisit if India-localized storage is mandated. |
