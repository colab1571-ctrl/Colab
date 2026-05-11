# 006 — Vibe Check Invites: Implementation Plan

**Spec**: `006-vibe-check/spec.md`
**Phase**: P5
**Service**: `invite-svc` (FastAPI, Postgres schema `invite`, Redis via ElastiCache)
**Depends on**: 002 Platform, 004 Profile, 008 Moderation (synopsis scan), 013 Billing (entitlement)
**Downstream consumers**: 014 Notifications (`match.created`), 007 Chat (chat room creation)

---

## 1. Mission Recap

`invite-svc` owns the full lifecycle of a Vibe Check: send → pending → accept|reject|expire|cancel → match emission. It enforces a rolling 7-day quota (Free: 5, Premium: unlimited), a hard 30-day TTL that archives (never deletes) stale invites, pre-send moderation of the 250-char synopsis, and block-aware visibility so blocked users cannot interact or appear in feeds/recs. A mutual accept atomically emits `match.created` (idempotent), which triggers chat-room creation and the "Match!" notification.

---

## 2. Research Notes

### 2.1 Celery Beat — 30-Day TTL Archival Job

- Celery Beat (ARC-24) runs on RabbitMQ. A periodic task `expire_stale_invites` fires **hourly** (cron `0 * * * *`).
- Query: `SELECT id FROM collab_invite WHERE status = 'pending' AND archive_at <= NOW()`.
- Bulk-update in batches of 500: `UPDATE … SET status = 'expired', responded_at = NOW()` then publish `invite.expired` events to RabbitMQ fanout.
- Archive means status flip; row is **never deleted**. Journey G queries read `status IN ('expired','rejected','cancelled')` as history.
- Idempotency: re-running the job on already-expired rows is a no-op (WHERE clause filters them out).
- Celery task uses `acks_late=True` + `max_retries=3` with exponential back-off to survive transient DB failures.

### 2.2 Redis Rolling-Window Rate Limit (Sorted Set Pattern)

Free users are capped at **5 invites per rolling 7-day window** (not a calendar week). Premium entitlement is read from `billing-svc` → `EntitlementSnapshot` (Redis-cached, <50ms per §013 NFR).

**Redis key**: `invite:quota:{user_id}` — Sorted Set, score = epoch milliseconds of send time, member = invite UUID.

**Algorithm** (atomic Lua script, single round-trip):

```lua
local key   = KEYS[1]
local now   = tonumber(ARGV[1])   -- epoch ms
local cutoff= now - 604800000     -- 7 days in ms
local limit = tonumber(ARGV[2])   -- 5 for free, 9999999 for premium
local inv   = ARGV[3]             -- invite UUID

redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)   -- evict stale
local count = redis.call('ZCARD', key)
if count >= limit then
  return 0   -- quota exceeded
end
redis.call('ZADD', key, now, inv)
redis.call('EXPIRE', key, 604800)   -- 7-day TTL on the key itself
return 1   -- allowed
```

- Return `0` → respond 402 with upsell payload before any DB write.
- Return `1` → proceed with invite creation.
- Key expires automatically after 7 days of inactivity (no wasted memory).
- Premium users pass `limit=9_999_999` (effectively unlimited); the Redis write still happens for audit trail, but the cap is never reached.

### 2.3 Idempotent Invite Creation

- `POST /invites` accepts an optional `X-Idempotency-Key` header (UUID4, client-generated).
- Redis key: `idem:invite:{idempotency_key}` (string, TTL 24h). Value = serialised response JSON.
- On duplicate key hit: return cached response with `200` (not `201`). No DB write, no quota increment.
- Without a client key: server generates a deterministic key from `(from_profile_id, to_profile_id, synopsis_hash)` with a 60-second dedup window to prevent accidental double-tap.

### 2.4 Block-Aware Visibility Queries

Blocks must be enforced at two layers:

1. **`discovery-svc` feed queries** (§005): `JOIN block b ON (b.blocker_id = me AND b.blocked_id = profile.id) OR (b.blocker_id = profile.id AND b.blocked_id = me)` with `WHERE b.blocker_id IS NULL`. Materialised as a Postgres view `visible_profiles(viewer_id, profile_id)` refreshed on `block.created` / `block.removed` events.
2. **`invite-svc` pre-flight check**: before quota evaluation, check `Block` table bidirectionally. A → B blocked or B → A blocked → 403.

`block.created` event (RabbitMQ) is consumed by:
- `discovery-svc`: invalidates feed cache for both users.
- `chat-svc`: flips any open collab chat to read-only.
- `invite-svc`: no action needed (checks are live).

---

## 3. Detailed Data Model

### 3.1 `collab_invite` (Postgres schema `invite`)

```sql
CREATE TABLE collab_invite (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_profile_id  UUID NOT NULL REFERENCES profile(id),
    to_profile_id    UUID NOT NULL REFERENCES profile(id),
    synopsis         VARCHAR(250) NOT NULL,
    status           invite_status NOT NULL DEFAULT 'pending',
    ai_match_score   NUMERIC(5,4),          -- snapshot from §005 at send time
    mod_case_id      UUID,                  -- FK to moderation_case if flagged
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    responded_at     TIMESTAMPTZ,           -- accept/reject/expire timestamp
    archive_at       TIMESTAMPTZ NOT NULL   -- created_at + 30 days (set at insert)
);

CREATE TYPE invite_status AS ENUM (
    'pending', 'accepted', 'rejected', 'expired', 'cancelled'
);

-- Indices
CREATE INDEX ON collab_invite (to_profile_id, status, created_at DESC);   -- inbox queries
CREATE INDEX ON collab_invite (from_profile_id, status, created_at DESC); -- sent queries
CREATE INDEX ON collab_invite (status, archive_at) WHERE status = 'pending'; -- TTL job
```

### 3.2 `block` (Postgres schema `invite`)

```sql
CREATE TABLE block (
    blocker_id  UUID NOT NULL REFERENCES profile(id),
    blocked_id  UUID NOT NULL REFERENCES profile(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reason      block_reason,              -- nullable enum
    PRIMARY KEY (blocker_id, blocked_id)
);

CREATE TYPE block_reason AS ENUM (
    'harassment', 'spam', 'inappropriate_content', 'other'
);

CREATE INDEX ON block (blocked_id);  -- reverse lookup (is_blocked_by queries)
```

### 3.3 `InviteQuota` — Redis Schema

| Key pattern | Type | TTL | Description |
|---|---|---|---|
| `invite:quota:{user_id}` | Sorted Set | 7 days (sliding) | Members = invite UUIDs, scores = epoch ms of send |
| `idem:invite:{idem_key}` | String (JSON) | 24h | Idempotency cache |
| `entitlement:{user_id}:invites_per_week` | String | 5 min | Cached entitlement from billing-svc |

---

## 4. State Machine

```
                       ┌──────────────────────────────────────────┐
                       │                                          │
  POST /invites ──► [pending] ──► accept ──► [accepted] ──► match.created emitted
                       │                                          │
                       ├──► reject ──► [rejected] (silent)        │
                       │                                          │
                       ├──► expire (Celery Beat, archive_at ≤ NOW) ──► [expired]
                       │
                       └──► DELETE /invites/{id} (sender only, pending) ──► [cancelled]
```

**Transition rules**:

| From | Event | To | Actor | Side Effects |
|---|---|---|---|---|
| `pending` | `accept` | `accepted` | recipient | emit `invite.accepted`; if mirror invite accepted → emit `match.created` |
| `pending` | `reject` | `rejected` | recipient | emit `invite.rejected` (silent to sender) |
| `pending` | TTL job | `expired` | system | emit `invite.expired` |
| `pending` | cancel | `cancelled` | sender | emit `invite.cancelled` |
| `accepted` | — | terminal | — | no further transitions |
| `rejected` | — | terminal | — | no further transitions |
| `expired` | — | terminal | — | no further transitions |
| `cancelled` | — | terminal | — | no further transitions |

**Rejected, expired, cancelled** transitions are **silent to sender** (no push, no in-app banner). Only the recipient's inbox reflects the change; sender's "sent" history shows the terminal status in Journey G.

---

## 5. Rolling 7-Day Quota Algorithm

Full Redis sorted-set algorithm described in §2.2. Expanded flow:

```
POST /invites
  │
  ├─ 1. Auth check (JWT → profile_id)
  ├─ 2. Block check: bidirectional query on block table
  │       → if blocked: return 403 {"error": "blocked"}
  ├─ 3. Entitlement check: GET invite:quota:entitlement cache OR billing-svc
  │       → limit = 9_999_999 if premium, else 5
  ├─ 4. Idempotency key dedup (Redis, 60s window)
  ├─ 5. Quota Lua script (atomic):
  │       ZREMRANGEBYSCORE  (evict >7d old)
  │       ZCARD             (count active sends this window)
  │       if count >= limit → return 402 {quota_remaining:0, upsell:true}
  │       ZADD + EXPIRE     (record this send)
  ├─ 6. Moderation pre-check: POST moderation-svc /scan/text {text: synopsis}
  │       → score ≥ 0.4 → reject with 422 {"error": "synopsis_flagged", reason}
  │       → score < 0.4 → continue
  ├─ 7. DB insert: collab_invite (status=pending, archive_at=NOW()+30d)
  ├─ 8. Publish invite.sent to RabbitMQ
  └─ 9. Return 201 {invite_id, quota_remaining}
```

`quota_remaining` = `limit - ZCARD(key after insert)`. Free users see `4`, `3`, … `0` remaining.

---

## 6. Block Semantics

### 6.1 Filtering Rules

| Context | Rule |
|---|---|
| Feed / "Picked for you" recs | Both `blocker→blocked` AND `blocked→blocker` directions excluded. Neither sees the other. |
| Profile search | Same bidirectional exclusion. |
| Invite send | 403 if `block(A,B)` OR `block(B,A)` exists. |
| Invite inbox/sent | Existing invites from/to a blocked user are hidden from list endpoints (filtered in query). Historical records remain in DB for compliance. |
| Chat | Existing collab chat flips to read-only on `block.created`; archived at +30 days. Both users retain export rights (IP record). |
| Notification | No new notifications cross a block boundary. |

### 6.2 Reciprocal Block

- Blocking is **one-way write, two-way effect**: `block(A→B)` makes A invisible to B **and** B invisible to A in all surfaces.
- Only the blocker can remove the block (`DELETE /blocks/{profile_id}`). The blocked user has no knowledge of the block.
- Both `block(A,B)` and `block(B,A)` may coexist independently (both blocked each other). Either row being present is sufficient to enforce invisibility.

### 6.3 `block.created` Event Consumers

- `discovery-svc`: evict both users from each other's feed cache. Update `visible_profiles` view.
- `chat-svc`: set collab chat to `read_only = true` for any active collab between the pair.
- `notification-svc`: suppress delivery across the block boundary.

---

## 7. Match Logic

### 7.1 When Match Fires

A match is created when **both** `collab_invite(A→B)` and `collab_invite(B→A)` reach status `accepted`. This is evaluated inside a **database transaction** on each `accept` action:

```python
# Pseudocode — invite-svc accept handler
with db.transaction():
    invite = lock_and_get(invite_id)   # SELECT FOR UPDATE
    invite.status = 'accepted'
    invite.responded_at = now()
    db.flush()

    mirror = db.query(
        "SELECT id FROM collab_invite "
        "WHERE from_profile_id = :to AND to_profile_id = :from "
        "AND status = 'accepted'",
        to=invite.to_profile_id, from=invite.from_profile_id
    ).one_or_none()

    if mirror:
        emit_match_created(invite.from_profile_id, invite.to_profile_id)
```

### 7.2 Idempotency of `match.created`

- RabbitMQ message key: `match:{min(profile_a, profile_b)}:{max(profile_a, profile_b)}` (canonical ordering).
- `chat-svc` uses an `ON CONFLICT DO NOTHING` upsert on `collab(profile_a_id, profile_b_id)` unique index.
- If `match.created` is delivered twice (at-least-once delivery), the second delivery creates no duplicate chat room and fires no duplicate notification (notification-svc checks `collab_id` for existing "Match!" notification).

### 7.3 `match.created` Payload

```json
{
  "event": "match.created",
  "profile_a_id": "<uuid>",
  "profile_b_id": "<uuid>",
  "invite_a_id": "<uuid>",
  "invite_b_id": "<uuid>",
  "matched_at": "<iso8601>"
}
```

Consumed by:
- `chat-svc` (§007): creates private 1:1 collab chat room.
- `notification-svc` (§014): sends "Match!" push + in-app banner + email fallback to both users.

---

## 8. API Contracts

### 8.1 `POST /invites`

**Request**
```json
{ "to_profile_id": "<uuid>", "synopsis": "<string, max 250 chars>" }
```

**Responses**

| Status | Condition | Body |
|---|---|---|
| 201 | Created | `{invite_id, quota_remaining, archive_at}` |
| 402 | Free quota exceeded | `{error:"quota_exceeded", quota_remaining:0, upsell:true}` |
| 403 | Blocked | `{error:"blocked"}` |
| 422 | Synopsis flagged by moderation | `{error:"synopsis_flagged", reason:"<category>"}` |
| 409 | Duplicate (idempotency) | cached 201 body |

### 8.2 `POST /invites/{id}/accept`

- Auth: calling user must be `to_profile_id`.
- 200: `{invite_id, status:"accepted", matched: bool}`.
- 403: not the recipient.
- 404: invite not found or terminal.

### 8.3 `POST /invites/{id}/reject`

- Auth: calling user must be `to_profile_id`.
- 200: `{invite_id, status:"rejected"}`.
- Rejection is silent to sender (no event emitted to notification-svc).

### 8.4 `DELETE /invites/{id}`

- Auth: calling user must be `from_profile_id`.
- Only valid when `status = 'pending'`.
- 200: `{invite_id, status:"cancelled"}`.

### 8.5 `GET /invites/inbox`

```
GET /invites/inbox?status=pending|accepted|rejected|expired|all&cursor=<opaque>&limit=20
```

Response: `{ items: [InviteCard], next_cursor, total_pending }`.

`InviteCard` fields: `invite_id`, `from_profile` (name, avatar_url, city, top_vocation), `synopsis`, `status`, `created_at`, `archive_at`, `ai_match_score`.

Blocked senders excluded. Terminal statuses (rejected/expired/cancelled) only appear in Journey G history (`status=all`).

### 8.6 `GET /invites/sent`

Mirror of inbox, filtered to `from_profile_id = me`. Blocked recipients excluded.

### 8.7 `POST /blocks/{profile_id}`

- Body: `{reason?: "harassment"|"spam"|"inappropriate_content"|"other"}`.
- 200: `{blocker_id, blocked_id, created_at}`.
- Emits `block.created`.

### 8.8 `DELETE /blocks/{profile_id}`

- 200: `{unblocked: true}`.
- Emits `block.removed`.

### 8.9 `GET /blocks`

- Returns list of profiles the calling user has blocked.
- Paginated, 50/page.

---

## 9. Implementation Tasks

### T-001 — Service Scaffold
**Title**: Bootstrap `invite-svc` FastAPI service
**Outcome**: Deployable service skeleton: FastAPI app, Alembic migrations, Docker image, EKS deployment manifest, health check endpoint, Sentry + PostHog hooks wired.
**Est. hours**: 6
**Blocks**: All other tasks
**Blocked by**: 002 Platform (base FastAPI library)

---

### T-002 — Database Schema
**Title**: Create Postgres schema for `collab_invite` and `block`
**Outcome**: Alembic migration creates tables, enums, indices. Seed script for CI test DB.
**Est. hours**: 4
**Blocks**: T-004, T-005, T-006, T-007, T-008, T-009
**Blocked by**: T-001

---

### T-003 — Redis Quota Lua Script
**Title**: Implement rolling 7-day invite quota with Redis sorted set
**Outcome**: Lua script atomically enforces free-tier cap. Unit tests cover boundary (4th, 5th, 6th send within 7d window). Entitlement fetch from billing-svc (with Redis cache + invalidation on `entitlement.changed` event).
**Est. hours**: 5
**Blocks**: T-004
**Blocked by**: T-001, 013 Billing entitlement endpoint live

---

### T-004 — Send Invite Endpoint (`POST /invites`)
**Title**: Implement send invite flow: block check → quota → moderation → DB insert → event emit
**Outcome**: All validation layers applied in order. Idempotency key dedup (60s). Returns correct status codes (201/402/403/422/409). `invite.sent` published to RabbitMQ.
**Est. hours**: 8
**Blocks**: T-010 (integration tests)
**Blocked by**: T-002, T-003, 008 Moderation `/scan/text` endpoint live

---

### T-005 — Accept / Reject / Cancel Endpoints
**Title**: Implement `POST /invites/{id}/accept`, `POST /invites/{id}/reject`, `DELETE /invites/{id}`
**Outcome**: State transitions enforced. Accept handler checks for mirror invite in transaction; emits `match.created` if mutual. Reject is silent. Cancel restricted to sender + pending state only.
**Est. hours**: 6
**Blocks**: T-010
**Blocked by**: T-002, T-004

---

### T-006 — Inbox / Sent List Endpoints
**Title**: Implement `GET /invites/inbox` and `GET /invites/sent`
**Outcome**: Cursor-based pagination (keyset on `created_at DESC`). Block filter applied. Profile card data joined from profile-svc (via internal HTTP). P95 <150ms verified in load test.
**Est. hours**: 5
**Blocks**: T-010
**Blocked by**: T-002, 004 Profile read API stable

---

### T-007 — Block / Unblock Endpoints
**Title**: Implement `POST /blocks/{profile_id}`, `DELETE /blocks/{profile_id}`, `GET /blocks`
**Outcome**: DB writes + RabbitMQ `block.created` / `block.removed` events emitted. Reciprocal block semantics documented in code comments.
**Est. hours**: 4
**Blocks**: T-004, T-010
**Blocked by**: T-002

---

### T-008 — Celery Beat TTL Archival Job
**Title**: Implement `expire_stale_invites` Celery Beat periodic task
**Outcome**: Hourly job batch-updates `status=expired` for `pending` rows past `archive_at`. Publishes `invite.expired` events. Idempotent re-runs. Celery Beat schedule registered in `celeryconfig.py`. Integration test: seed expired invite → run job → assert status + event.
**Est. hours**: 5
**Blocks**: T-010
**Blocked by**: T-002, T-001 (Celery worker wired)

---

### T-009 — RabbitMQ Event Publishers + Consumers
**Title**: Wire all RabbitMQ publish/subscribe for invite-svc
**Outcome**:
  - Publishers: `invite.*`, `match.created`, `block.*`.
  - Consumers: `entitlement.changed` (invalidate local Redis cache).
  - Dead-letter queue configured. Message schemas (JSON Schema) documented in `events/` directory.
**Est. hours**: 5
**Blocks**: T-004, T-005, T-007, T-008
**Blocked by**: T-001, 002 Platform (RabbitMQ connection library)

---

### T-010 — Integration & Contract Tests
**Title**: Write pytest integration tests covering all acceptance criteria
**Outcome**: All ACs pass. Tests run against a local Docker Compose stack (Postgres + Redis + mock moderation-svc + mock billing-svc). See §10 for specific test cases.
**Est. hours**: 10
**Blocks**: None
**Blocked by**: T-004, T-005, T-006, T-007, T-008

---

### T-011 — Discovery Feed Block Filter
**Title**: Implement block-aware feed exclusion in `discovery-svc`
**Outcome**: Feed queries join `block` table bidirectionally. `visible_profiles` Postgres view created. Feed cache invalidated on `block.created` / `block.removed` events. Premium `hide_from_non_premium` filter respected independently.
**Est. hours**: 6
**Blocks**: T-010 (discovery-level acceptance test)
**Blocked by**: T-007, 005 Discovery feed query baseline

---

### T-012 — API Gateway Rate Limit & OpenAPI Spec
**Title**: Register invite-svc routes in API Gateway; generate OpenAPI spec + TS client
**Outcome**: Routes proxied through gateway. OpenAPI spec published. TypeScript client generated and tested against RN app stub.
**Est. hours**: 4
**Blocks**: None
**Blocked by**: T-004, T-005, T-006, T-007

---

**Total estimated hours**: ~68 hours

---

## 10. Acceptance Criteria with pytest Verifications

### AC-001 — Free Quota Enforcement

```python
def test_free_user_sixth_invite_returns_402(client, free_user, five_invites_sent):
    """Sending the 6th invite within a rolling 7-day window returns 402 with upsell."""
    resp = client.post("/invites", json={"to_profile_id": other_profile(), "synopsis": "Let's collab"})
    assert resp.status_code == 402
    body = resp.json()
    assert body["quota_remaining"] == 0
    assert body["upsell"] is True
```

### AC-002 — Premium User Unlimited Invites

```python
def test_premium_user_can_send_beyond_five(client, premium_user):
    """Premium user can send more than 5 invites in a 7-day window."""
    for _ in range(7):
        resp = client.post("/invites", json={"to_profile_id": unique_profile(), "synopsis": "collab"})
        assert resp.status_code == 201
```

### AC-003 — Rolling Window Resets Correctly

```python
def test_quota_rolls_after_7_days(client, free_user, redis_client):
    """After 7 days, old send records evict and quota resets."""
    # Seed 5 sends with timestamps 8 days ago
    seed_quota_entries(free_user.id, count=5, age_days=8, redis_client=redis_client)
    resp = client.post("/invites", json={"to_profile_id": other_profile(), "synopsis": "new"})
    assert resp.status_code == 201
```

### AC-004 — Inbox Shows Pending; Accept Opens Chat

```python
def test_accept_invite_emits_match_when_mutual(client, user_a, user_b, rabbitmq):
    """Accepting the mirror invite emits match.created event."""
    inv_ab = send_invite(client, user_a, user_b)
    inv_ba = send_invite(client, user_b, user_a)
    client.post(f"/invites/{inv_ab['invite_id']}/accept", headers=auth(user_b))
    resp = client.post(f"/invites/{inv_ba['invite_id']}/accept", headers=auth(user_a))
    assert resp.json()["matched"] is True
    event = rabbitmq.get_last_event("match.created")
    assert set([event["profile_a_id"], event["profile_b_id"]]) == {user_a.id, user_b.id}
```

### AC-005 — Reject is Silent

```python
def test_reject_produces_no_notification_event(client, user_a, user_b, rabbitmq):
    """Rejecting an invite produces no event visible to sender."""
    inv = send_invite(client, user_a, user_b)
    client.post(f"/invites/{inv['invite_id']}/reject", headers=auth(user_b))
    assert not rabbitmq.has_event("notification.send", filter_={"user_id": user_a.id})
```

### AC-006 — 30-Day TTL Archival

```python
def test_celery_ttl_job_expires_stale_invite(db, celery_app):
    """Celery Beat job flips pending invite past archive_at to expired."""
    inv = create_invite(db, archive_at=utcnow() - timedelta(hours=1))
    assert inv.status == "pending"
    celery_app.tasks["invite.expire_stale_invites"].apply()
    db.refresh(inv)
    assert inv.status == "expired"
```

### AC-007 — Block Prevents Send

```python
def test_blocked_user_cannot_send_invite(client, user_a, user_b):
    """User A cannot send to User B after B blocks A."""
    client.post(f"/blocks/{user_a.id}", headers=auth(user_b))
    resp = client.post("/invites", json={"to_profile_id": user_b.id, "synopsis": "hi"}, headers=auth(user_a))
    assert resp.status_code == 403
```

### AC-008 — Reciprocal Block Visibility

```python
def test_block_bidirectional_feed_exclusion(client, user_a, user_b):
    """After A blocks B, neither appears in the other's feed."""
    client.post(f"/blocks/{user_b.id}", headers=auth(user_a))
    feed_a = client.get("/feed", headers=auth(user_a)).json()["items"]
    feed_b = client.get("/feed", headers=auth(user_b)).json()["items"]
    assert not any(p["profile_id"] == user_b.id for p in feed_a)
    assert not any(p["profile_id"] == user_a.id for p in feed_b)
```

### AC-009 — Synopsis Moderation Rejection

```python
def test_flagged_synopsis_rejected_before_db_insert(client, user_a, user_b, mock_moderation_svc):
    """Synopsis scoring >= 0.4 returns 422 and no DB row is created."""
    mock_moderation_svc.set_score(0.75)
    resp = client.post("/invites", json={"to_profile_id": user_b.id, "synopsis": "bad content"})
    assert resp.status_code == 422
    assert resp.json()["error"] == "synopsis_flagged"
    assert db.query(CollabInvite).filter_by(to_profile_id=user_b.id).count() == 0
```

### AC-010 — Idempotent Match Creation

```python
def test_match_created_is_idempotent(client, user_a, user_b, rabbitmq):
    """Delivering match.created twice results in only one chat room."""
    trigger_match(user_a, user_b)
    deliver_event_twice("match.created", user_a, user_b)
    assert db.query(Collab).filter_by(profile_a_id=user_a.id, profile_b_id=user_b.id).count() == 1
```

### AC-011 — Send Performance

```python
def test_send_invite_p95_under_250ms(locust_runner):
    """P95 latency for POST /invites < 250ms under 100 concurrent users."""
    stats = locust_runner.run(endpoint="POST /invites", users=100, duration=60)
    assert stats.p95 < 250
```

### AC-012 — Inbox Performance

```python
def test_inbox_p95_under_150ms(locust_runner):
    """P95 latency for GET /invites/inbox < 150ms."""
    stats = locust_runner.run(endpoint="GET /invites/inbox", users=100, duration=60)
    assert stats.p95 < 150
```

---

## 11. Open Risks

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R-001 | `block.created` event fan-out latency causes brief window where blocked user's profile still appears in feed | Low | Medium | Accept <1s eventual consistency; discovery-svc also applies live DB check on profile-detail fetch |
| R-002 | Lua script clock skew between Redis instances if cluster failover occurs during quota check | Low | Low | Use Redis Cluster with single-shard key (`{user_id}` hash tag); all replicas share clock via NTP |
| R-003 | Celery Beat job misses a run (worker restart during job) | Low | Medium | `acks_late=True`; job is idempotent (re-run is safe); PagerDuty alert if job hasn't run in 2h |
| R-004 | Moderation-svc latency spike causes `POST /invites` to exceed 250ms P95 | Medium | Medium | Moderation call has 200ms timeout; on timeout → allow + async queue for deferred review (risk-accept: rare bad synopsis may slip through briefly) |
| R-005 | Duplicate `match.created` triggers duplicate "Match!" push notification | Low | Medium | notification-svc dedup on `(user_id, event_type, reference_id)` with 24h window |
| R-006 | Free user circumvents quota by deleting + re-creating account | Medium | Low | Quota key is on `user_id`; account-level abuse tracked by trust-score in profile-svc; moderation-svc flags rapid re-signup patterns |
| R-007 | India DPDP data-residency: invite data stored in us-east-1 | Medium | High | Deferred per master §8; Phase 5 decision on in-region object store or processor agreements |
| R-008 | Reaction nudge (notify Premium user when invite unseen N days) | Low | Low | Deferred to Phase 5 per spec §Open; would require Celery Beat periodic scan + notification-svc integration |
