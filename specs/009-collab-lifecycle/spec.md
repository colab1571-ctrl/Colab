# 009 — Collab Lifecycle + Feedback + History

**Phase**: P8.
**Services**: `collab-svc`.
**Mission**: Owns the `Collaboration` aggregate created on `match.created`. Status transitions, feedback collection at end, inactivity nudges + auto-archive, chat export (PDF + ZIP), Journey G activity-history views.

## In scope (master Journey C FR-C-9, FR-C-10, FR-C-11, FR-C-13, Journey G FR-G-1..G-4)

- Collaboration created on `match.created`.
- Status: Still Deciding / In Progress / Completed / Didn't Work Out. Owner = either participant; transitions logged.
- Auto-archive cadence: Completed and "Didn't Work Out" archive on flip; inactivity 14d → nudge (push + in-app + email fallback); 30d → auto-archive (Still Deciding / In Progress).
- Feedback on completion: thumbs up/down + tag chips. Separate ratings for project and partner.
- Chat export: PDF transcript + ZIP of media (Premium-only). Generation async (Celery + Replicate-free pipeline: Reportlab/wkhtmltopdf in worker).
- Activity history views: active projects, past projects, requests sent/received, search across titles/descriptions/names/file names. Postgres full-text via tsvector.

## Dependencies

- **Hard**: 002, 003, 004, 006 (consumes `match.created`), 007 (chat content for export).
- **Soft**: 008 (block ⇒ collab read-only + auto-archive at +30d), 013 (export entitlement), 014 (nudge notifications).

## Owned entities

- `Collaboration`: id, participants (array of 2 profile_ids), title (nullable, default e.g. "Collab with {name}"), status, last_activity_at, archive_at (nullable), created_at, completed_at, archived_at, search_vector (tsvector — computed).
- `CollabStatusEvent`: collab_id, actor_profile_id, prev_status, new_status, note, created_at.
- `CollabFeedback`: collab_id, from_profile_id, to_profile_id, target (project|partner), rating (up|down), tags (array enum), comment (500ch nullable), created_at.
- `CollabExport`: id, collab_id, requested_by, status (pending|generating|ready|failed), pdf_s3_key, zip_s3_key, expires_at.

## API surface

- `GET /collabs?status=active|past|all&cursor=...&q=`
- `GET /collabs/{id}`
- `POST /collabs/{id}/status` body `{new_status, note?}`
- `POST /collabs/{id}/feedback` body `{target, rating, tags[], comment?}` (post-completion only)
- `POST /collabs/{id}/export` (Premium only) → 202 + export_id
- `GET /collabs/exports/{id}` → status + signed download URLs when ready
- `GET /me/history/requests/sent`, `/me/history/requests/received` — proxied / joined with §006

### Queue events consumed
- `match.created` → create Collaboration
- `chat.message.sent` → update last_activity_at
- `collab.status_changed` (self-emit) → trigger archive cadence
- `block.created` → flip to read-only + archive_at = now+30d

### Queue events emitted
- `collab.created`, `collab.status_changed`, `collab.archived`, `collab.feedback_submitted`, `collab.export_ready`

## Acceptance criteria

- Match → Collaboration row + chat room.
- Status flip auto-recomputes archive_at.
- 14-day inactivity → notification sent (push+in-app+email fallback) once.
- 30-day inactivity → auto-archive.
- Completed feedback prompt fires once per participant.
- Export PDF + ZIP generated within 5 min for typical collab; expires after 7 days.
- Activity search: titles, descriptions, collaborator names, file names. Chat content excluded.

## NFRs

- Collab list P95 <200ms.
- Export median <60s, P95 <5min.

## Open

- Export-format niceness (cover sheet, watermark, hash of content for tamper-evidence) — Phase 5 detail.
