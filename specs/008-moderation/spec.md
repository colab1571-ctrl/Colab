# 008 — Moderation + Safety + IP

**Phase**: P7.
**Services**: `moderation-svc`.
**Mission**: Centralized moderation pipeline. Risk-tiered routing. Multi-tool layered scanning. Moderator queue + actions. Reporting workflow. DMCA + counter-notice workflow (without registered agent — see master §0 known risk).

## In scope (master Journey C FR-C-12, Cross-cutting Moderation FR-M-1..FR-M-6)

- Pipeline (real-time): chat msgs, image/video uploads, portfolio uploads, profile bio/obsessed-with text, invite synopses.
- Tools: OpenAI moderation (text); AWS Rekognition Content Moderation (image+video); perceptual hash pHash (image dup); Chromaprint (audio dup); semantic dup via embeddings.
- Risk-tiered routing:
  - `<0.4` → auto-allow + log
  - `0.4–0.7` → soft-warn user + mod queue (24h SLA)
  - `0.7–0.9` → hide content + mod queue (6h SLA)
  - `≥0.9` → auto-hide + temp-mute user + mod queue (1h SLA)
- IP / DMCA + harassment-threat: always escalate to human regardless of score.
- Reporting flow: in-app report on chat msg / profile / portfolio item. Required description, optional screenshot. Auto-routes to mod queue.
- Moderator actions: warn, hide content, temp mute (1h/24h/7d), permanent ban, delete account.
- DMCA takedown intake (signed-under-penalty-of-perjury form), 24h hide, counter-notice form, 10–14d statutory wait, auto-restore on no-suit-filed.
- Action log with reviewer ID + timestamp + reason.

## Dependencies

- **Hard**: 002 Platform, 003 Auth (user lookup for action targets).
- **Soft**: 004 Profile (badge held on AI review), 007 Chat (message hides + temp mute apply to chat send), 006 Invite (synopsis scan), 016 Admin (mod queue console).

## Owned entities

- `ModerationCase`: id, kind (auto|report|dmca), subject_type (msg|profile|portfolio|invite), subject_id, reporter_user_id (nullable), score, scores_breakdown (jsonb), status (open|in_review|actioned|dismissed), opened_at, sla_due_at, actioned_at, actioned_by, action_type.
- `ModerationAction`: case_id, action_type (warn|hide|temp_mute_1h|temp_mute_24h|temp_mute_7d|permanent_ban|delete_account), reviewer_id, reason, created_at.
- `Report`: id, reporter_user_id, subject_*, description (1000ch), screenshot_s3_key (nullable), case_id, created_at.
- `DMCANotice`: id, claimant_name, claimant_contact, sworn_statement_text, target_subject_*, hash_of_signature, received_at, hide_at.
- `CounterNotice`: dmca_id, counter_claimant_name, counter_statement, statutory_window_end, received_at.

## API surface

`moderation-svc`:
- `POST /reports` body `{subject_type, subject_id, description, screenshot?}`
- `POST /dmca/notice` (signed form) → 24h hide + DMCA notice email + counter-notice slot
- `POST /dmca/{id}/counter-notice` (target only)
- `POST /moderation/cases/{id}/action` (moderator role only) body `{action_type, reason}`
- `GET /moderation/queue?filter=...&sla=overdue` (moderator role)
- Internal scan APIs called by §007, §004, §006.

### Queue events

- `moderation.action_taken` → §007 (force read-only / temp-mute), §003 (lockout), §004 (badge revoke), §013 (subscription pause for permanent ban + refund)
- `moderation.report_filed`
- `dmca.notice_filed`, `dmca.counter_filed`, `dmca.statutory_window_expired`

## Acceptance criteria

- Every chat text msg scans through the pipeline before delivery.
- Auto-hide ≥0.9 → moderator sees the case within 1h SLA.
- Soft-warn user UX in §007 explains why a message was flagged.
- Reporting flow from chat → case created → in queue with SLA.
- Moderator can warn / hide / temp-mute / ban from the admin console (§016).
- DMCA takedown hides content within 24h; counter-notice restarts the statutory clock.
- Action log immutable (append-only).

## NFRs

- Mod queue P95 SLAs honored: ≥0.9 case acked within 1h, ≥0.7 within 6h, ≥0.4 within 24h.
- Scan throughput sized for 100k DAU peak.

## Open

- DMCA agent registration — explicitly deferred (master §0 known risk). Document this on Community Guidelines + privacy page.
- Cross-locale moderation thresholds (US/CA/AU/NZ/IN have different community-standards expectations) — Phase 5 detail.
