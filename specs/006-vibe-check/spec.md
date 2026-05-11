# 006 — Vibe Check Invites

**Phase**: P5.
**Services**: `invite-svc`.
**Mission**: Send/accept/reject collab requests ("Vibe Checks"), enforce 5/wk free quota + premium unlimited, manage 30-day TTL with archive-not-delete, "Match!" notification on mutual accept.

## In scope (master Journey B FR-B-8 through FR-B-10, FR-B-13)

- Send Vibe Check: 250-char synopsis, no attachments.
- Free 5 per rolling 7-day window; Premium unlimited (`billing-svc` entitlement check).
- Accept / reject. Reject + unanswered are silent to sender.
- 30-day TTL → status flips to `expired`, archived (not deleted) into recipient archive + sender's "past sent" history (Journey G).
- Mutual accept → emit `match.created` → notification (§014) → §007 chat room opens.
- Pre-send moderation: synopsis runs through OpenAI moderation (§008).
- Block respect: cannot send to or receive from blocked users; cannot see blocked users in feed/recs.

## Dependencies

- **Hard**: 002 Platform, 004 Profile, 008 Moderation (synopsis scan), 013 Billing (entitlement).
- **Soft**: 014 Notifications (Match!), 007 Chat (chat room creation on match).

## Owned entities

- `CollabInvite`: id, from_profile_id, to_profile_id, synopsis (250ch), status (pending|accepted|rejected|expired|cancelled), ai_match_score (snapshot from §005), created_at, responded_at, archive_at.
- `Block`: blocker_id, blocked_id, created_at, reason (nullable enum).
- `InviteQuota` (Redis-backed, week-rolling): user_id → invite count.

## API surface

`invite-svc`:
- `POST /invites` body `{to_profile_id, synopsis}` → 200 / 402 (quota exceeded for free, prompt upsell) / 403 (blocked)
- `POST /invites/{id}/accept` (recipient only)
- `POST /invites/{id}/reject` (recipient only; silent to sender)
- `DELETE /invites/{id}` — sender cancels before action
- `GET /invites/inbox?status=pending|accepted|rejected|expired|all`
- `GET /invites/sent?status=...`
- `POST /blocks/{profile_id}`, `DELETE /blocks/{profile_id}`
- `GET /blocks`

### Queue events

- `invite.sent`, `invite.accepted`, `invite.rejected`, `invite.expired`, `invite.cancelled`
- `match.created` (on mutual accept) — consumed by §007 + §014
- `block.created`, `block.removed` — consumed by §005, §007 (block existing chats)

## Acceptance criteria

- Free user sending 6th invite within 7 days → 402 with upsell payload.
- Recipient sees pending invites in inbox; accept → chat opens + Match! notification; reject → invite vanishes from inbox; sender sees nothing.
- 30-day TTL job (Celery Beat hourly) flips pending invites to expired + archives.
- Blocked users cannot send invites; reciprocal block.
- Synopsis run through OpenAI mod before persistence; flagged synopses rejected with reason.

## NFRs

- Send P95 <250ms.
- Inbox query P95 <150ms.

## Open

- Reaction nudge: should we notify Premium users when their invite has not been seen in N days? Phase 5 detail.
