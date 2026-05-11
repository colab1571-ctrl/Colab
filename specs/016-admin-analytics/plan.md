# Plan — 016 Admin Console + Analytics Rollups

**Phase**: P15
**Services**: `admin-svc` (FastAPI), `analytics-svc` (FastAPI + Celery Beat), `admin-web` (Next.js App Router)
**Owner**: Platform + Trust&Safety
**Status**: Phase 5 detailed plan

---

## 1. Mission Recap

Deliver an internal-only operations console that lets a small staff (moderators, support agents, billing admins, super-admins) run the day-to-day of Colab. The console is the surface for every operational task touched by other specs:

- **Moderation queue + case workflow** (consumes §008 ModerationCase + ModerationAction; writes back via the same APIs).
- **Support ticket queue + reply composer + escalation** (consumes §015 SupportTicket + Event timeline; cross-links to moderation when category is Harassment or IP/DMCA).
- **Billing administration** — tier definitions, entitlement-axis values, Stripe Price ID linkage, credit-bundle SKU map, refund decisions, ad-hoc credit grants (writes back into §013 entitlement tables and broadcasts `entitlement.changed`).
- **User 360°** — composite read that joins auth, profile, identity (Persona), badge, subscription, credit wallet, recent moderation cases, recent support tickets, and last-active.
- **Feature flag console** — env-scoped key/value + canary % per env, hot-reloadable by every service (PostHog feature flags as the runtime; admin-web mirrors and writes through).
- **KPI rollups** — nightly Celery Beat jobs computing the master §6 metric list as `KPIRollup` rows for the admin dashboard (above PostHog's stock dashboards) and as a stable read source for future reporting.
- **Audit log** — append-only Postgres table that records every admin action with target, payload diff (before/after), and reviewer.
- **AuthZ** — four roles (mod, support, billing_admin, super_admin) enforced at the API layer; admin-web gates routes on the same matrix.
- **Network controls** — IP allowlist for admin-web pinned at the AWS API Gateway resource-policy level (not at the application layer); also enforced as a defense-in-depth middleware on `admin-svc`.

Mission-success looks like: a moderator clears a case in <60s; a billing admin changes `invites_per_week` for Premium and every other service sees the new value within 60s; a super-admin can audit every action taken on every entity for the past year.

---

## 2. Research

### 2.1 Next.js admin app patterns (App Router + role gates)

- **App Router** (Next.js 14+). Server Components by default; Client Components only where interactive (forms, queue filters, feature-flag toggles).
- **Route groups for role-scoped sections**: `app/(mod)/queue`, `app/(support)/tickets`, `app/(billing)/tiers`, `app/(admin)/flags`. Each group has a `layout.tsx` that calls `requireRole(["mod", "super_admin"])` server-side; the call throws a redirect to `/forbidden` if the JWT claim doesn't match.
- **Middleware** (`middleware.ts`) verifies the admin session JWT and refreshes silently against `admin-svc`. The middleware also enforces `X-Forwarded-For` IP allowlist as a belt-and-braces layer (the canonical gate is API Gateway — see §2.5).
- **Server Actions** for mutations (case actions, ticket replies, flag toggles). Each Server Action calls `admin-svc` over server-to-server JWT, so the admin's browser never holds the high-privilege service credential.
- **Data fetching** uses `fetch` with `next: { revalidate: 0 }` on hot pages (queue, tickets) so list views are always fresh, and `revalidate: 300` for slower-changing pages (tier config).
- **Streaming + Suspense** on the User 360° page since it aggregates ~9 reads — render skeletons per panel.
- **Audit-log writes** are wrapped in a `withAudit(actionType, target, payloadFn)` helper that runs around every Server Action and posts to `/admin/audit` before returning. If the audit write fails, the action fails (no skip path).
- **shadcn/ui + Tailwind** for components (Table, Dialog, Form, Tabs). Charts via Recharts on the KPI dashboard page.

### 2.2 PostHog REST API for KPIs vs computing them ourselves

Two routes were considered:

**Option A — Pull from PostHog Query/Insights API.**
- Pros: PostHog already has all events, no double-bookkeeping.
- Cons: Insight definitions live in PostHog and drift from spec; the Query API is rate-limited and not ideal as a hot read path; backfill / historical recompute is awkward; auth model (personal API keys) is not great for service-to-service.

**Option B — Compute our own rollups in `analytics-svc` against Postgres + PostHog event mirror.**
- Pros: SQL is versioned in our repo; we own the definitions; KPIRollup table is queryable from the admin app in <50ms; backfill is a parameterized job; metric drift is impossible (one source of truth, one query).
- Cons: We duplicate work that PostHog does.

**Decision: Option B.** PostHog stays the place for ad-hoc product analytics and session replay; `analytics-svc` owns the canonical KPI numbers for the master §6 list. We mirror raw events into Postgres via the existing analytics event-ingestion proxy (already in scope for `analytics-svc`) — this gives us a queryable event store and removes the PostHog rate-limit dependency. The PostHog Capture API is still called from the same proxy for live dashboards.

### 2.3 Casbin or Oso for RBAC

- **Casbin (Python)**: model file + policy file (or DB-backed adapter). Mature, well-known, OSS. Policy syntax (`p, sub, obj, act`) is simple. Has a SQLAlchemy adapter we can point at Postgres.
- **Oso (Cloud or self-hosted)**: Polar-based policy language, more expressive, but Cloud is a paid SaaS and self-hosting adds an extra service.

**Decision: Casbin** with the SQLAlchemy adapter, policies stored in `casbin_rule` table in `admin-svc`'s schema. Roles and policies are seeded from `infra/casbin/policy.csv` and hot-loaded; super-admins can edit policies via the admin UI (writes to the table + `enforcer.load_policy()` invalidates the in-memory cache). Avoids an extra runtime dependency and keeps everything in-tree.

### 2.4 Immutable audit log

Pattern (PG-native, no external append-only DB needed):

1. `admin_audit_log` table is **append-only by Postgres privilege**.
2. The owning role (e.g. `admin_svc_app`) is granted **only** `INSERT, SELECT` on the table:
   ```sql
   REVOKE UPDATE, DELETE, TRUNCATE ON admin_audit_log FROM admin_svc_app;
   GRANT  INSERT, SELECT          ON admin_audit_log TO   admin_svc_app;
   ```
3. A `BEFORE UPDATE OR DELETE OR TRUNCATE` trigger raises an exception — defense in depth in case the privilege ever drifts:
   ```sql
   CREATE FUNCTION audit_log_no_mutate() RETURNS trigger AS $$
   BEGIN RAISE EXCEPTION 'admin_audit_log is append-only'; END;
   $$ LANGUAGE plpgsql;
   ```
4. Application code uses a thin wrapper `audit.write(action_type, target_kind, target_id, payload_before, payload_after)`; failures fail the request.
5. Retention follows master §0 (lifetime of account + 3 years archived after deletion).

### 2.5 IP allowlist at API Gateway resource-policy level

- The `admin-svc` API Gateway resource is fronted with an **AWS API Gateway resource policy** (`aws:SourceIp` condition) whose CIDR list is sourced from `infra/admin-allowlist.json`.
- Admin-web's CloudFront distribution is gated by an **AWS WAF Web ACL** with the same CIDR set; non-allowlisted IPs get 403 before they ever reach the Next.js server.
- Both lists are managed in Terraform (`infra/terraform/admin/allowlist.tf`); a CI job validates the JSON parses and flags any CIDR larger than `/24` for super-admin review.
- The application-layer middleware in `admin-svc` reads the same allowlist file at boot and re-enforces — so if the gateway policy is ever misconfigured, the service still rejects.

---

## 3. Detailed Data Model

All tables live in the `admin` schema (one Postgres database, multiple service schemas — master ARC-6).

### 3.1 `AdminUser`

| Column           | Type        | Notes                                          |
|------------------|-------------|------------------------------------------------|
| user_id          | uuid PK     | FK → `auth.user.id` (admin staff must also be a real user; we don't create a separate identity store). |
| roles            | text[]      | Subset of `{mod, support, billing_admin, super_admin}`. |
| status           | text        | `active` \| `suspended`.                       |
| created_at       | timestamptz | default `now()`.                               |
| created_by       | uuid        | FK → `admin_user.user_id`. Bootstrap row is self-referential. |
| last_login_at    | timestamptz | nullable.                                      |
| mfa_enrolled_at  | timestamptz | nullable, but enforced for `super_admin` + `billing_admin`. |

Indexes: PK on `user_id`; GIN on `roles`.

### 3.2 `AdminAuditLog` (append-only)

| Column          | Type        | Notes                                                              |
|-----------------|-------------|--------------------------------------------------------------------|
| id              | uuid PK     | `gen_random_uuid()`.                                               |
| admin_user_id   | uuid        | FK → `admin_user.user_id`. NOT NULL.                               |
| action_type     | text        | enum-like (`case.action`, `ticket.reply`, `ticket.escalate`, `entitlement.update`, `flag.toggle`, `tier.update`, `refund.decide`, `credit.grant`, `user.suspend`, `user.unsuspend`, ...). |
| target_kind     | text        | `moderation_case` \| `support_ticket` \| `user` \| `tier` \| `entitlement_axis` \| `feature_flag` \| `refund` \| `credit_wallet`. |
| target_id       | text        | id of the target row.                                              |
| payload_before  | jsonb       | nullable; full row snapshot for updates.                           |
| payload_after   | jsonb       | nullable; full row snapshot for updates.                           |
| reason          | text        | nullable; free text from the admin.                                |
| ip              | inet        | request IP.                                                        |
| user_agent      | text        | nullable.                                                          |
| created_at      | timestamptz | default `now()`.                                                   |

Indexes: PK on `id`; B-tree on `(admin_user_id, created_at)`, `(target_kind, target_id, created_at)`, `(action_type, created_at)`.

Privileges: `REVOKE UPDATE, DELETE, TRUNCATE` from `admin_svc_app`. Trigger as in §2.4. Backups + WAL archived to S3 Glacier per master retention.

### 3.3 `FeatureFlag`

| Column      | Type        | Notes                                                                       |
|-------------|-------------|-----------------------------------------------------------------------------|
| key         | text        | e.g. `discovery.rerank_v2`.                                                |
| env         | text        | `dev` \| `staging` \| `prod`.                                              |
| value       | jsonb       | boolean, percentage, or structured config — service-defined shape.         |
| canary_pct  | numeric(5,2)| 0..100, used when the value is a bucket-based rollout.                     |
| updated_by  | uuid        | FK → `admin_user`.                                                         |
| updated_at  | timestamptz | default `now()`.                                                           |
| description | text        | shown in the admin UI; required.                                           |

Composite PK on `(key, env)`. Writes mirror to PostHog feature flags via the PostHog Personal API so clients receive flags through the existing PostHog SDKs.

### 3.4 `EntitlementConfig`

Source of truth for what each tier grants — read on every entitlement evaluation by `billing-svc`. Distinct from `EntitlementSnapshot` in §013 (which is per-user materialized).

| Column      | Type           | Notes                                                                  |
|-------------|----------------|------------------------------------------------------------------------|
| tier        | text           | `free` \| `premium` \| `pro`.                                          |
| axis_key    | text           | one of the 11 axes in master FR-E-2.                                   |
| value       | jsonb          | scalar or structured (e.g. `{"limit": 30}` or `{"enabled": true}`).    |
| currency    | text           | nullable; only meaningful for price axes.                              |
| effective_at| timestamptz    | when this value goes live.                                             |
| superseded_at| timestamptz   | nullable; non-null when a newer row supersedes.                        |
| updated_by  | uuid           | FK → `admin_user`.                                                     |
| updated_at  | timestamptz    | default `now()`.                                                       |

Composite uniqueness on `(tier, axis_key, effective_at)`. The currently-active row per `(tier, axis_key)` is the latest one with `effective_at <= now()` and `superseded_at IS NULL OR superseded_at > now()`. Tier-definition edits append a new row and supersede the prior (so history is preserved and audit-loggable).

### 3.5 `KPIRollup`

| Column   | Type        | Notes                                                                                              |
|----------|-------------|----------------------------------------------------------------------------------------------------|
| day      | date        | the rollup day in UTC.                                                                             |
| key      | text        | one of: `onboarding_completion`, `dau_split`, `profile_health_dist`, `request_ratio`, `collab_feedback`, `support_csat`, `pct_reported`. |
| dims     | jsonb       | discriminator dims (e.g. `{"step": "selfie"}`, `{"segment": "new"}`, `{"bucket": "0.8-1.0"}`).      |
| value    | numeric     | the metric value.                                                                                  |
| count_n  | bigint      | denominator (when meaningful).                                                                     |
| updated_at | timestamptz | default `now()`.                                                                                 |

Composite PK on `(day, key, dims)`. Indexes: `(key, day)` for trend queries.

---

## 4. RBAC Model

### 4.1 Roles

- **mod** — moderator. Works the moderation queue, takes actions, files DMCA decisions, reads User 360° (no PII edit).
- **support** — support agent. Works the support queue, replies, escalates, reads User 360°; can issue credit grants ≤ $20.
- **billing_admin** — manages tiers/entitlements/Stripe Price ID mapping, approves refunds, issues unlimited credits, reads invoices and subscription state. Cannot take moderation actions.
- **super_admin** — full surface; grants/revokes admin roles; edits Casbin policies; configures feature flags in `prod`; manages IP allowlist (read-only in UI, edits via Terraform PR).

A user can hold multiple roles. MFA is required at first login for `billing_admin` and `super_admin`.

### 4.2 Permission Matrix

| Resource / Action                            | mod | support | billing_admin | super_admin |
|----------------------------------------------|:---:|:-------:|:-------------:|:-----------:|
| GET /admin/queue/moderation                  | Y   | N       | N             | Y           |
| POST /admin/cases/{id}/action                | Y   | N       | N             | Y           |
| POST /admin/dmca/{id}/decision               | Y   | N       | N             | Y           |
| GET /admin/queue/support                     | N   | Y       | N             | Y           |
| POST /admin/tickets/{id}/reply               | N   | Y       | N             | Y           |
| POST /admin/tickets/{id}/escalate            | N   | Y       | N             | Y           |
| GET /admin/users/{id}/360                    | Y   | Y       | Y             | Y           |
| POST /admin/users/{id}/suspend               | Y(*)| N       | N             | Y           |
| GET /admin/entitlements                      | N   | N       | Y             | Y           |
| PUT /admin/entitlements                      | N   | N       | Y             | Y           |
| GET /admin/tiers                             | N   | N       | Y             | Y           |
| PUT /admin/tiers/{tier}                      | N   | N       | Y             | Y           |
| POST /admin/refunds/{id}/decision            | N   | N       | Y             | Y           |
| POST /admin/credits/grant                    | N   | Y(≤$20) | Y             | Y           |
| GET /admin/flags                             | Y   | Y       | Y             | Y           |
| PUT /admin/flags (dev/staging)               | Y   | Y       | Y             | Y           |
| PUT /admin/flags (prod)                      | N   | N       | N             | Y           |
| GET /admin/kpi/rollups                       | Y   | Y       | Y             | Y           |
| GET /admin/audit                             | Y(own) | Y(own)| Y(own)        | Y(all)      |
| PUT /admin/users (grant role)                | N   | N       | N             | Y           |

(*) mod can suspend a target user via `case.action` of type `permanent_ban` or `delete_account`; direct user-suspend without a case is super-admin only.

Casbin policy is generated from this matrix at build time (`scripts/gen_policy.py`); the generated CSV ships as the seed in the migration.

---

## 5. Moderator Console Screens

### 5.1 Queue (`/mod/queue`)

- **Columns**: case id (short), subject kind icon, score, opened_at, SLA due (with red highlight if overdue), reporter (if any), action.
- **Filters**: subject kind (msg / profile / portfolio / invite), score band (0.4–0.7 / 0.7–0.9 / ≥0.9), DMCA-only, source (auto vs report), assigned-to-me, status.
- **SLA highlights**: rows ≤1h to breach → amber; breached → red; ≥0.9 with `actioned_at IS NULL` past 1h → red + escalates to super-admin daily digest.
- **Bulk**: select rows → bulk dismiss (with reason). Bulk warn is not supported (always per-case).
- **Server-side pagination**, default page 50.

### 5.2 Case Detail (`/mod/cases/[id]`)

Three-column layout:

- **Left — Subject preview**:
  - chat msg: rendered text + thread context (5 msgs before/after) + room link.
  - profile: profile card + flagged fields highlighted.
  - portfolio item: image/audio/video preview with watermark; link to S3 signed URL (expiring).
  - invite: synopsis text + sender/recipient.
- **Center — Scores breakdown**: table of `scores_breakdown` jsonb (OpenAI moderation categories, Rekognition labels, pHash/Chromaprint dup scores, embedding-dup top hits with thumbnails). Each row shows tool, label, score, threshold-crossed.
- **Right — Action menu + Audit history**:
  - Action menu (Casbin-gated): warn / hide / temp_mute_1h / temp_mute_24h / temp_mute_7d / permanent_ban / delete_account.
  - Reason field (required, 500ch).
  - Submit calls `POST /moderation/cases/{id}/action`, with audit-log wrap.
  - Audit history shows every `AdminAuditLog` row targeting this case (any admin who looked, replied, or acted).

### 5.3 DMCA Workflow Screen (`/mod/dmca/[id]`)

- **Tabs**: Notice / Target Subject / Counter-Notice / Decision.
- **Notice tab** — claimant name + contact + sworn statement (read-only; stored signed PDF link).
- **Target subject** — same preview component as Case Detail.
- **Counter-Notice tab** — if filed, shows counter-claimant statement + statutory window end date (timer).
- **Decision tab** — three buttons: `hide_24h` (default on takedown; auto-fires on intake), `restore` (no counter or no-suit at window end), `escalate_to_super` (when claim is contested or repeated).

---

## 6. Support Console Screens

### 6.1 Ticket Queue (`/support/queue`)

- **Columns**: ticket id, category badge (Harassment / IP / Payment / Technical / Other), user (handle + tier badge), subject (truncated), opened_at, ack-SLA timer, resolve-SLA timer, assigned-to.
- **Filters**: category, status (open / in_progress / pending_user / resolved / closed), priority, assigned-to-me, breached-SLA, Premium-Pro only.
- **Color coding**: cyan = pending_user (no SLA tick), green = within SLA, amber = ≤2h to breach, red = breached.

### 6.2 Ticket Detail (`/support/tickets/[id]`)

- **Top bar**: user pill (links to User 360°), category, current status, SLA timers.
- **Conversation timeline**: rendered from `SupportTicketEvent`s — chronological, color-coded by actor (user / agent / system).
- **Reply composer** (right side or bottom):
  - WYSIWYG with paste-as-text default.
  - Saved-reply picker (FAQ snippets keyed by category).
  - Attach file (S3 signed upload).
  - "Mark as first response" auto-sets `first_response_at` on send and stops ack-SLA.
  - Submit calls `POST /admin/tickets/{id}/reply` (which calls `support-svc`).
- **Sidebar**:
  - User mini-card (handle, tier, last active, recent moderation cases count).
  - "Escalate" button → modal asking for reason; routes to `super_admin` and to `moderation-svc` if category is Harassment or IP.
  - "Resolve" button → marks status `resolved`, fires CSAT email.
  - "Cross-link" — if Harassment/IP, shows nearest open moderation case for the user (clickable).

---

## 7. Billing Console Screens

### 7.1 Tier Definitions Editor (`/billing/tiers`)

- Three-column layout (Free / Premium / Pro).
- Each axis is a row; each cell is an editable value with a type-checked widget (number, boolean, select, currency).
- **Writes to `EntitlementConfig`** by appending a new row with `effective_at = now()` and superseding the prior. Audit-logged.
- On save: publish `entitlement.changed` (broadcast); every service invalidates its per-user `EntitlementSnapshot` cache. Verifies the change is live within 60s (NFR).
- "Schedule change" option lets a billing admin queue an `effective_at` in the future (e.g. promo end).

### 7.2 Stripe Price ID Mapping (`/billing/prices`)

- Table of `(tier, sku, billing_period, stripe_price_id, revenuecat_product_id, currency, active)`.
- Edits go through a confirm dialog ("This will change checkout for new subscribers — existing subscribers are unaffected until renewal").
- Validation: live ping to Stripe (`/v1/prices/{id}`) to ensure the price exists + is active.

### 7.3 Refund Decisions (`/billing/refunds`)

- Queue of `RefundRequest`s with status `pending`.
- Decision UI: approve / deny / partial. Partial shows an amount input (currency-aware).
- Approve calls `billing-svc` (Stripe refund or RevenueCat refund, depending on source); writes back to `RefundRequest.status`; broadcasts `refund.granted`.
- 14-day window auto-approvals (handled by `billing-svc`) appear as "auto-approved" rows for visibility — not editable.

### 7.4 Credit Grants (`/billing/credits`)

- "Grant credits" form: user (search), amount, reason (required), expires_at (optional).
- Submits a `CreditTransaction` row with `reason='admin_grant'`; references the admin user.
- Support agents are capped at $20 per grant + $200/day rolling (enforced in `admin-svc`, not just UI).

---

## 8. Feature Flag UI

`/admin/flags` — table per env (tabs: dev / staging / prod).

- Columns: key, description, current value, canary %, last updated by, last updated at.
- Inline edit for value + canary %. Toggle column for booleans.
- Save calls `PUT /admin/flags`, which writes to `FeatureFlag` and mirrors to PostHog via Personal API (server-side; key in Secrets Manager).
- `prod` edits require super_admin role (Casbin) and an MFA reauthentication step (`stepup_required: true` on the API response → admin-web shows MFA prompt).
- Canary % values 0–100, increments of 1; the bucket is `hash(user_id) % 100 < canary_pct`. The bucket function is shared library code — every service uses the same hash so a user assigned to canary is consistent across services.

---

## 9. User 360°

Path: `/admin/users/[id]`.

Composite view assembled by **`GET /admin/users/{id}/360`** in `admin-svc`. Fans out to:

- `auth-svc`        → email (masked), phone (masked), oauth providers, last_login_at, signup ip, suspended state.
- `profile-svc`     → display name, bio, "obsessed with", vocations, location-city, portfolio thumbnails, profile_health_score, last_active.
- `identity-svc`    → Persona status, last verification at, doc type.
- `profile-svc`     → badges (valid_profile_badge bool + reason).
- `billing-svc`     → subscription (tier, status, period_end), entitlement snapshot, refund history.
- `billing-svc`     → credit wallet balance + recent transactions (10).
- `moderation-svc`  → recent cases (10, with statuses + actions taken).
- `support-svc`     → recent tickets (10, with categories + statuses).
- `analytics-svc`   → last-active timestamp (from rolled event stream).

Rendered as a tabbed UI: **Overview / Identity / Subscription & Credits / Moderation / Support / Activity**. Each tab is a Suspense boundary; the panels stream in independently so the page is interactive in <300ms even if one service is slow.

PII (raw email, raw phone) is masked by default; revealing requires "Reveal PII" button + reason (writes an audit row of type `user.pii_reveal`).

---

## 10. KPI Rollups

The master §6 list maps to seven `KPIRollup` keys. Each is a SQL query in `analytics-svc` that runs nightly at **02:00 UTC** via Celery Beat. Backfill range is configurable (default last 30 days). All queries run against the **events mirror** (raw events in Postgres) joined with read-only views into `auth`, `profile`, `invite`, `collab`, `support`, `moderation` schemas.

### 10.1 `onboarding_completion`

Dims: `{"step": <step_name>}`. Step names: `signup`, `verify_email`, `age_attest`, `profile_basic`, `portfolio`, `selfie`, `badge`, `completed`.

```sql
WITH funnels AS (
  SELECT user_id,
         MIN(CASE WHEN event = 'signup'           THEN ts END) AS t_signup,
         MIN(CASE WHEN event = 'verify_email'     THEN ts END) AS t_verify_email,
         MIN(CASE WHEN event = 'age_attest'       THEN ts END) AS t_age_attest,
         MIN(CASE WHEN event = 'profile_basic'    THEN ts END) AS t_profile_basic,
         MIN(CASE WHEN event = 'portfolio_done'   THEN ts END) AS t_portfolio,
         MIN(CASE WHEN event = 'selfie_done'      THEN ts END) AS t_selfie,
         MIN(CASE WHEN event = 'badge_issued'     THEN ts END) AS t_badge
  FROM analytics.events
  WHERE ts::date = :day
  GROUP BY user_id
)
SELECT :day AS day,
       'onboarding_completion' AS key,
       jsonb_build_object('step', step) AS dims,
       count(*) FILTER (WHERE col IS NOT NULL)::numeric / NULLIF(count(*), 0) AS value,
       count(*) AS count_n
FROM funnels f,
     LATERAL (VALUES
       ('signup',         f.t_signup),
       ('verify_email',   f.t_verify_email),
       ('age_attest',     f.t_age_attest),
       ('profile_basic',  f.t_profile_basic),
       ('portfolio',      f.t_portfolio),
       ('selfie',         f.t_selfie),
       ('badge',          f.t_badge)
     ) AS s(step, col)
GROUP BY step;
```

### 10.2 `dau_split`

Dims: `{"segment": "new" | "existing"}`.

```sql
WITH actives AS (
  SELECT DISTINCT user_id
  FROM analytics.events
  WHERE ts::date = :day AND event = 'app_active'
),
ages AS (
  SELECT u.id AS user_id,
         CASE WHEN u.created_at::date = :day THEN 'new' ELSE 'existing' END AS segment
  FROM auth.user u
  JOIN actives a ON a.user_id = u.id
)
SELECT :day AS day, 'dau_split' AS key,
       jsonb_build_object('segment', segment) AS dims,
       count(*)::numeric AS value, count(*) AS count_n
FROM ages
GROUP BY segment;
```

### 10.3 `profile_health_dist`

Dims: `{"bucket": "0.0-0.2" | "0.2-0.4" | ... | "0.8-1.0"}`.

```sql
SELECT :day AS day, 'profile_health_dist' AS key,
       jsonb_build_object('bucket', width_bucket(profile_health_score, 0, 1, 5)) AS dims,
       count(*)::numeric AS value, count(*) AS count_n
FROM profile.profile
WHERE updated_at::date <= :day
GROUP BY 3;
```

### 10.4 `request_ratio` (accept / reject / expired)

Dims: `{"outcome": "accepted" | "rejected" | "expired" | "pending"}`.

```sql
SELECT :day AS day, 'request_ratio' AS key,
       jsonb_build_object('outcome', status) AS dims,
       count(*)::numeric AS value, count(*) AS count_n
FROM invite.collab_invite
WHERE created_at::date = :day
GROUP BY status;
```

The ratio in the UI is computed as `accepted / (accepted + rejected)` from these rows (we store the raw counts and derive ratios at read time).

### 10.5 `collab_feedback`

Dims: `{"axis": "project" | "partner", "direction": "up" | "down"}`.

```sql
SELECT :day AS day, 'collab_feedback' AS key,
       jsonb_build_object('axis', axis, 'direction', direction) AS dims,
       count(*)::numeric AS value, count(*) AS count_n
FROM collab.feedback
WHERE created_at::date = :day
GROUP BY axis, direction;
```

Up-vote ratio = `up / (up + down)` per axis at read time.

### 10.6 `support_csat`

Dims: `{"category": <category>}`; value = average score 1–5.

```sql
SELECT :day AS day, 'support_csat' AS key,
       jsonb_build_object('category', t.category) AS dims,
       avg(c.score)::numeric AS value, count(*) AS count_n
FROM support.csat c
JOIN support.ticket t ON t.id = c.ticket_id
WHERE c.created_at::date = :day
GROUP BY t.category;
```

### 10.7 `pct_reported`

Single row per day (dims = `{}`). Value = `reported_users / dau`.

```sql
WITH reported AS (
  SELECT DISTINCT subject_id AS user_id
  FROM moderation.report
  WHERE created_at::date = :day AND subject_type = 'profile'
),
dau AS (
  SELECT count(DISTINCT user_id) AS n
  FROM analytics.events
  WHERE ts::date = :day AND event = 'app_active'
)
SELECT :day AS day, 'pct_reported' AS key,
       '{}'::jsonb AS dims,
       (SELECT count(*) FROM reported)::numeric / NULLIF((SELECT n FROM dau), 0) AS value,
       (SELECT n FROM dau) AS count_n;
```

### 10.8 Job orchestration

- Celery Beat schedule entry: `0 2 * * *` UTC.
- Single task `rollup_day(day)` runs each query, upserts into `KPIRollup` (`ON CONFLICT (day, key, dims) DO UPDATE`).
- Failure handling: per-query try/except logs to Sentry and continues; the whole task can be retried with `--backfill from..to` from a CLI.
- NFR: <30 min for 100k DAU. We verify in load test with seeded events.

---

## 11. Audit Log

Every admin action goes through `audit.write()`. Examples:

- **Case action** — `action_type='case.action'`, `target_kind='moderation_case'`, `target_id=<case_id>`, `payload_before={status:'open'}`, `payload_after={status:'actioned', action_type:'temp_mute_24h'}`, reason=admin-supplied.
- **Ticket reply** — `action_type='ticket.reply'`, `target_kind='support_ticket'`, payload_after has the reply body hash + first_response set.
- **Entitlement update** — `action_type='entitlement.update'`, both before/after rows.
- **Feature flag toggle** — `action_type='flag.toggle'`, before/after value, env.
- **Refund decision** — `action_type='refund.decide'`, before/after RefundRequest.
- **Credit grant** — `action_type='credit.grant'`, payload_after has delta + reason.
- **User PII reveal** — `action_type='user.pii_reveal'`, target user id, payload has fields revealed.
- **Role grant** — `action_type='role.grant'`, before/after AdminUser.roles.

Append-only enforcement: §2.4. UI surface: `/admin/audit` (super_admin sees all; other roles see own actions only). Filter by `(actor, action_type, target_kind, target_id, date range)`; CSV export for super_admin.

---

## 12. API Contracts

All paths are under `/admin/v1` and require an admin JWT (claim `admin: true`, claim `roles: ["..."]`). All responses are JSON; pagination via `?cursor=` opaque cursor + `?limit=` (default 50, max 200).

### 12.1 Auth

- `POST /admin/v1/login` body `{email, password, mfa_code?}` → `{access_token, refresh_token, mfa_required?: bool}`.
- `POST /admin/v1/refresh` body `{refresh_token}` → `{access_token}`.
- `POST /admin/v1/mfa/enroll` (TOTP secret + backup codes).

### 12.2 Moderation

- `GET  /admin/v1/queue/moderation?score=...&kind=...&sla=overdue&assignee=me`
- `GET  /admin/v1/cases/{id}`
- `POST /admin/v1/cases/{id}/action` body `{action_type, reason}` (Casbin: `mod`).
- `GET  /admin/v1/dmca/{id}`
- `POST /admin/v1/dmca/{id}/decision` body `{decision: hide_24h|restore|escalate, reason}`.

### 12.3 Support

- `GET  /admin/v1/queue/support?category=...&breached=true&assignee=me`
- `GET  /admin/v1/tickets/{id}`
- `POST /admin/v1/tickets/{id}/reply` body `{body, attachments[]}` (Casbin: `support`).
- `POST /admin/v1/tickets/{id}/escalate` body `{to_role, reason}`.
- `POST /admin/v1/tickets/{id}/resolve` body `{resolution_note}`.

### 12.4 Billing

- `GET /admin/v1/tiers` → list of current entitlement rows per tier.
- `PUT /admin/v1/tiers/{tier}` body `{axes: [{axis_key, value, currency?, effective_at?}], reason}`.
- `GET /admin/v1/entitlements` (same as above for any tier).
- `PUT /admin/v1/entitlements` body `[{tier, axis_key, value, currency?, effective_at?}]`.
- `GET /admin/v1/prices`, `PUT /admin/v1/prices/{id}`.
- `GET /admin/v1/refunds?status=pending`.
- `POST /admin/v1/refunds/{id}/decision` body `{decision, amount?, reason}`.
- `POST /admin/v1/credits/grant` body `{user_id, delta, reason, expires_at?}`.

### 12.5 Users

- `GET  /admin/v1/users?q=...` (search by email/handle/id).
- `GET  /admin/v1/users/{id}/360` → composite blob (PII masked unless `?reveal=true`).
- `POST /admin/v1/users/{id}/suspend` body `{reason}`.
- `POST /admin/v1/users/{id}/unsuspend` body `{reason}`.

### 12.6 Flags

- `GET /admin/v1/flags?env=prod`.
- `PUT /admin/v1/flags` body `{key, env, value, canary_pct, description}`.

### 12.7 KPIs

- `GET /admin/v1/kpi/rollups?key=...&from=YYYY-MM-DD&to=YYYY-MM-DD&dims=...`.

### 12.8 Analytics (server-to-server)

- `POST /analytics/v1/events` body `[{event, ts, user_id, props}]` → mirrors to PostHog + writes to events mirror.

### 12.9 Audit

- `GET /admin/v1/audit?actor=...&action_type=...&target=...&from=...&to=...`.

---

## 13. Implementation Tasks

| id  | title                                                          | outcome                                                                                | est_hours | blocks         | blocked_by    |
|-----|----------------------------------------------------------------|----------------------------------------------------------------------------------------|-----------|----------------|---------------|
| T01 | admin-svc skeleton (FastAPI app, Postgres schema, Alembic)     | empty service deploys to EKS staging, `/healthz` ok.                                   | 6         | T02-T20        | platform      |
| T02 | analytics-svc skeleton (FastAPI + Celery + Beat)               | service + beat container deployed; sample task runs.                                   | 6         | T18,T19        | platform      |
| T03 | admin-web Next.js app skeleton (App Router + shadcn/ui)        | app deploys behind CloudFront + WAF; `/login` renders.                                 | 8         | T05-T12        | platform      |
| T04 | Casbin RBAC integration (`admin-svc`)                          | policies seeded; `requires_role` decorator on routes; unit-tested matrix.              | 10        | T06-T12        | T01           |
| T05 | Admin login + MFA (TOTP) + session refresh                     | super-admin can log in to admin-web with MFA.                                          | 10        | T06-T12        | T01,T03,T04   |
| T06 | AdminAuditLog table + append-only privileges + helper          | every write goes through `audit.write`; tests prove UPDATE/DELETE fails.               | 8         | T07-T15        | T01           |
| T07 | Moderator console — queue page                                 | filters + SLA highlights + pagination; integration test against seeded cases.          | 10        | —              | T04,T05       |
| T08 | Moderator console — case detail + action menu                  | actions persist via §008 API + audit-logged + UI updates.                              | 12        | —              | T07           |
| T09 | Moderator console — DMCA workflow screen                       | takedown/restore/escalate flow + counter-notice timer.                                 | 10        | —              | T08           |
| T10 | Support console — ticket queue + detail + reply composer       | reply stops SLA; escalate works; CSAT fires on resolve.                                | 14        | —              | T04,T05,T06   |
| T11 | Billing console — tier editor + Stripe price mapping           | EntitlementConfig writes broadcast `entitlement.changed`; takes effect <60s.           | 14        | —              | T04,T05,T06   |
| T12 | Billing console — refund decisions + credit grants             | refund decisions roundtrip to §013; credit-grant cap enforced.                         | 10        | —              | T11           |
| T13 | Feature flag UI + PostHog mirror                               | toggling in admin-web changes flag in PostHog within 5s.                               | 10        | —              | T04,T05,T06   |
| T14 | User 360° composite endpoint + UI page                         | streams 6+ panels in Suspense; PII reveal audit-logged.                                | 14        | —              | T04,T05,T06   |
| T15 | KPI rollups SQL + Celery Beat job (all 7 metrics)              | nightly job completes; admin dashboard renders charts.                                 | 18        | —              | T02,T06       |
| T16 | KPI dashboard page in admin-web (Recharts)                     | last-30-days chart per metric; export CSV.                                             | 10        | —              | T15           |
| T17 | Audit log viewer + CSV export                                  | super_admin filters across actors, targets, dates.                                     | 8         | —              | T06           |
| T18 | analytics-svc event ingestion proxy + events mirror table      | server-to-server events written to Postgres + forwarded to PostHog.                    | 10        | T15            | T02           |
| T19 | analytics-svc backfill CLI + retry path                        | `python -m analytics.rollup --backfill 2026-01-01..2026-02-01` works.                  | 6         | —              | T15           |
| T20 | API Gateway resource policy (IP allowlist) + WAF rules (Terraform) | non-allowlisted IPs receive 403 at gateway/CDN; covered by infra test.             | 8         | —              | T01,T03       |
| T21 | Defense-in-depth IP allowlist middleware in `admin-svc`        | bypasses 403 even if gateway misconfigured.                                            | 4         | —              | T20           |
| T22 | Audit + load test (100k DAU rollup window)                     | rollup completes <30 min on staging perf cluster.                                      | 10        | release        | T15           |
| T23 | E2E acceptance suite (Playwright)                              | <60s case-resolve, <60s entitlement propagation tested.                                | 14        | release        | T07-T17       |
| T24 | Runbook + on-call docs (`docs/admin/`)                         | super-admin can rotate Casbin policy, edit allowlist, run backfill.                    | 6         | release        | T20-T23       |

Splits:

- **admin-svc API**: T01, T04, T05, T06, T08-call-throughs, T10-call-throughs, T11-call-throughs, T12-call-throughs, T13, T14, T21.
- **admin-web Next.js**: T03, T07-T17 (UI portions).
- **analytics-svc**: T02, T15, T18, T19.
- **RBAC**: T04 + permission-matrix unit tests at every endpoint.
- **Audit log**: T06 + use sites in every mutation endpoint (T08, T10, T11, T12, T13, T14).
- **KPI rollups**: T15, T18, T19, T22.
- **Feature flags**: T13.
- **IP allowlist**: T20, T21.

---

## 14. Acceptance Criteria with Verifications

| # | Criterion                                                                                              | Verification                                                                                                 |
|---|--------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------|
| 1 | Moderator resolves a case in <60s end-to-end (queue → detail → action → log).                          | Playwright e2e (T23): seeded case, scripted clicks, asserts elapsed < 60s and `AdminAuditLog` row exists.    |
| 2 | Support agent reply stops ack-SLA timer.                                                               | Integration test against `support-svc`: post reply, fetch ticket, assert `first_response_at` set.            |
| 3 | Billing admin changes `invites_per_week` for Premium; new value takes effect within 60s for all users. | Test: change config, wait 60s, call `billing-svc /entitlements` for a Premium user, assert new value.        |
| 4 | Nightly KPI rollup runs successfully with backfill option.                                             | Backfill CLI (T19) idempotency test; staging cron observed for 7 days; alerts on failure.                    |
| 5 | Every admin action appears in `AdminAuditLog` (no skip path).                                          | Static lint: every mutation endpoint has `@audited` decorator; runtime test attempts an UPDATE on the table and expects an exception. |
| 6 | Admin console list pages P95 <300ms.                                                                   | k6 load test (T22) on `/queue/moderation`, `/queue/support`, `/admin/audit`.                                 |
| 7 | Rollup nightly <30 min for 100k DAU.                                                                   | T22 with seeded 100k-DAU dataset; CloudWatch metric `analytics.rollup.duration` <1800s.                      |
| 8 | Non-allowlisted IPs receive 403 at gateway level (not application).                                    | Infra test: curl from non-allowlisted IP returns 403 with `x-amzn-errortype: AccessDeniedException`.         |
| 9 | RBAC: `mod` cannot reach `/admin/refunds`.                                                             | Casbin matrix unit tests + e2e: mod JWT, GET `/admin/v1/refunds` → 403.                                      |
|10 | `prod` flag toggles require super_admin + MFA stepup.                                                  | E2E: billing_admin attempts → 403; super_admin without recent MFA → 401 `stepup_required`.                   |

---

## 15. Open Risks

1. **PostHog feature-flag mirror drift** — if our `FeatureFlag` writes to PostHog fail, our table becomes the source of truth but clients (which read flags from PostHog SDK) won't see changes. Mitigation: synchronous mirror call inside the same transaction wrapper; if it fails, the API returns 502; surface a dashboard alert.
2. **Audit log volume** — at 100k DAU with 50 admin actions/min worst case, table grows fast. Mitigation: partition by month (`PARTITION BY RANGE (created_at)`); cold partitions ship to S3 + are detached after 12 months; remains queryable via Athena per master retention.
3. **IP allowlist + remote staff** — staff travel/VPN breaks the allowlist. Mitigation: super_admin can add a temporary CIDR via Terraform PR with an expiry comment; future work to integrate Tailscale-style identity-aware proxy (deferred).
4. **Casbin policy drift between code-generated CSV and runtime DB** — admins editing in DB could diverge from `policy.csv`. Mitigation: CI job that diffs `policy.csv` vs DB on every deploy and posts to Slack; super_admin reconciles.
5. **DMCA agent registration deferred** (master §0 + §008 open) — admin UI must surface a banner reminding moderators that US safe-harbor is not claimed; some DMCA workflows route directly to legal counsel.
6. **PII reveal abuse** — a malicious admin could pull PII en masse. Mitigation: `user.pii_reveal` audit rows are anomaly-detected via a daily query that alerts super_admin on outlier admin volumes.
7. **KPI definitions vs PostHog** — operators may pull "DAU" from PostHog and see a different number than our rollup if event mirroring drifts. Mitigation: monthly reconciliation runbook (T24) comparing our `dau_split` total against PostHog and flagging deltas >2%.
8. **Tier change race** — `effective_at` scheduling combined with `entitlement.changed` broadcast must be ordered correctly to avoid a window where some services see new and others see old. Mitigation: scheduled changes are picked up by a single Celery Beat task at `effective_at` minute; broadcast then fires; services treat the snapshot table as authoritative (per §013 NFR).
