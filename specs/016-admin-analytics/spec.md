# 016 — Admin Console + Analytics Rollups

**Phase**: P15.
**Services**: `admin-svc`, `analytics-svc`.
**Mission**: Internal-only Next.js admin app for moderators, support agents, billing admins. KPI rollups (above PostHog's stock dashboards). Feature flag + entitlement-axis configuration. Tier + price configuration.

## In scope

### admin-svc (backend for admin-web)
- Moderator console: queue, case detail, action (warn/hide/mute/ban), DMCA workflow UI, action log.
- Support console: ticket queue, SLA dashboard, ticket detail, reply, escalate, link to user record.
- Billing admin: tier definitions, entitlement-axis values, Stripe Price ID linkage, credit-bundle SKU linkage, refund decisions.
- User search + 360°: profile, identity, badge state, subscription, credit balance, recent moderation cases, recent tickets.
- Tax-jurisdiction admin (per-country flags).
- Audit log (every admin action immutable).
- AuthZ: admin role + scoped permissions (mod, support, billing-admin, super-admin).
- IP allowlist enforced at API Gateway.

### analytics-svc
- Event ingestion proxy (receives client + server events, dedupes, forwards to PostHog).
- KPI rollups: onboarding completion, DAU/WAU/MAU, profile-health distribution, request accept/reject ratio, collab feedback, support CSAT, % reported, ad metrics (when ads ship).
- Nightly rollup jobs (Celery Beat).

## Dependencies

- **Hard**: 002, 003, every other feature (read-side admin views).

## Owned entities

- `AdminUser`: user_id, roles (array), created_at, last_login_at.
- `AdminAuditLog`: id, admin_user_id, action, target_kind, target_id, payload, created_at.
- `FeatureFlag`: key, value, env, updated_by, updated_at.
- `EntitlementConfig`: tier, axis_key, value, currency (nullable for non-monetary axes), updated_by, updated_at.
- `KPIRollup`: day, key, dims (jsonb), value.

## API surface

- `POST /admin/login` (super-admin issues regular admin via console)
- `GET /admin/queue/moderation`, `/queue/support`
- `POST /admin/cases/{id}/action`
- `POST /admin/tickets/{id}/reply`, `/escalate`
- `GET /admin/users/{id}/360`
- `GET/PUT /admin/entitlements`
- `GET/PUT /admin/flags`
- `GET /admin/kpi/rollups?day=YYYY-MM-DD`
- `POST /analytics/events` (server-to-server)

## Acceptance criteria

- Moderator can resolve a case end-to-end (queue → detail → action → log) in <60 seconds.
- Support agent can reply to a ticket; SLA timers stop on first response.
- Billing admin can change `invites_per_week` for Premium tier; live takes effect within 60s for all users.
- Daily KPI rollup runs successfully every night with backfill.
- Admin actions all appear in `AdminAuditLog` (no skip path).

## NFRs

- Admin console list P95 <300ms.
- Rollup nightly <30 min for 100k DAU.

## Open

- KPI definitions per the master spec list — Phase 5 finalizes SQL.
