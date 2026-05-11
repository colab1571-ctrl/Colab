# 011 — Meetings + Recall.ai Bot

**Phase**: P10.
**Services**: `meeting-svc`.
**Mission**: Schedule Google Meet calls from inside the collab workspace, optionally dispatch a Recall.ai bot to attend + record + transcribe, store transcript to audit log.

## In scope (master Journey C FR-C-6)

- Google Meet creation via Google Calendar API (server-side service account).
- Meeting record with start, end, attendees (the two collab participants + bot), join URL.
- Optional Recall.ai bot: launched when both participants opt in (mutual consent toggle); joins meeting, records, transcribes; webhook delivers transcript + recording URL.
- Transcript stored as a `ChatMessage(type=system|transcript)` in the room + as an audit-log entry in §009.

## Dependencies

- **Hard**: 002, 003, 007, 009.
- **External**: Google Cloud project with Calendar + Meet APIs; Recall.ai account.

## Owned entities

- `Meeting`: id, collab_id, organizer_profile_id, scheduled_at, duration_min, join_url, status (scheduled|started|ended|cancelled), created_at, bot_enabled (bool), bot_status (none|requested|joined|left|failed), recall_bot_id (nullable).
- `MeetingArtifact`: meeting_id, kind (transcript|recording|summary), s3_key, ready_at.

## API surface

- `POST /collabs/{collab_id}/meetings` body `{scheduled_at, duration_min, bot_enabled}` → `{join_url, ics_url}`
- `PATCH /meetings/{id}` (reschedule + cancel)
- `POST /meetings/{id}/bot/start` (idempotent; both participants must consent first)
- `POST /webhooks/recall` (signed) — transcript + recording ready

### Queue events

- `meeting.scheduled`, `meeting.cancelled`, `meeting.transcript_ready`

## Acceptance criteria

- Scheduling creates a Google Meet event with both participants invited via calendar.
- Bot launch requires `meeting.bot_consent` row from both participants.
- Recall.ai webhook signed-verified; transcript stored to S3 + audit log.
- Transcript surfaced in chat as a system message with collapsible content.

## NFRs

- Schedule API P95 <500ms (excludes Google API latency).

## Open

- Whether to ship pre-meeting agenda generator (using GPT) — could fit into §012 in-chat AI assistant as `/agenda` command. Phase 5 decides.
