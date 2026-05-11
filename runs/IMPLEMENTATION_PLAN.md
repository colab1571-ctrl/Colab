# IMPLEMENTATION_PLAN.md — Colab

> Single source of truth for Phase 7 (RALPH execution). Each phase block lists its features and points at the spec's `plan.md` for the detailed task table. Tasks within each `plan.md` carry `id / title / outcome / est_hours / blocks / blocked_by`. The orchestrator advances feature-by-feature in dependency order.
>
> Generated 2026-05-11 from Phase 5 detailing outputs + Phase 5b reconciliation. ~625+ tasks, ~3,200+ engineer-hours total.

---

## Phase order (dependency-ordered)

| Phase | Feature | Spec dir | Plan link | Tasks | Est hours | Status |
|---|---|---|---|---|---|---|
| **P0** | Infrastructure Bootstrap | `specs/001-infrastructure` | [plan.md](../specs/001-infrastructure/plan.md) | ~50 | ~110 | pending |
| **P1** | Shared Platform (libs + base apps + CI) | `specs/002-shared-platform` | [plan.md](../specs/002-shared-platform/plan.md) | 42 | ~153 | pending |
| **P2a** | Auth + Identity | `specs/003-auth-identity` | [plan.md](../specs/003-auth-identity/plan.md) | 40 | ~210 | pending |
| **P2b** | Profile + AI Review + Valid Badge | `specs/004-profile-badge` | [plan.md](../specs/004-profile-badge/plan.md) | ~50 | ~180 | pending |
| **P3** | Moderation + Safety (built early — cross-cutting) | `specs/008-moderation` | [plan.md](../specs/008-moderation/plan.md) | ~30 | ~200 | pending |
| **P4** | Discovery + Matching | `specs/005-discovery-matching` | [plan.md](../specs/005-discovery-matching/plan.md) | 28 | ~156 | pending |
| **P5** | Vibe Check Invites | `specs/006-vibe-check` | [plan.md](../specs/006-vibe-check/plan.md) | 12 | ~68 | pending |
| **P6** | Chat + Workspace base | `specs/007-chat-workspace` | [plan.md](../specs/007-chat-workspace/plan.md) | 69 | ~503 | pending |
| **P7** | Collab Lifecycle + Feedback + History (Journey G) | `specs/009-collab-lifecycle` | [plan.md](../specs/009-collab-lifecycle/plan.md) | 26 | ~97 | pending |
| **P8** | Billing + Subscriptions + Credits + Entitlements | `specs/013-billing` | [plan.md](../specs/013-billing/plan.md) | 25 | ~250 | pending |
| **P9** | Notifications | `specs/014-notifications` | [plan.md](../specs/014-notifications/plan.md) | 26 | ~146 | pending |
| **P10** | Collab Tools (Whiteboard + Project Plan) | `specs/010-collab-tools` | [plan.md](../specs/010-collab-tools/plan.md) | 42 | ~288 | pending |
| **P11** | Meetings + Recall.ai | `specs/011-meetings` | [plan.md](../specs/011-meetings/plan.md) | 30 | ~140 | pending |
| **P12** | AI Assistant + Mockups | `specs/012-ai-assistant-mockups` | [plan.md](../specs/012-ai-assistant-mockups/plan.md) | 27 | ~164 | pending |
| **P13** | Support + AI Chatbot + Tickets | `specs/015-support` | [plan.md](../specs/015-support/plan.md) | 23 | ~180 | pending |
| **P14** | Admin Console + Analytics Rollups | `specs/016-admin-analytics` | [plan.md](../specs/016-admin-analytics/plan.md) | 24 | ~220 | pending |
| **P15** | Marketing Site (independent — could run parallel) | `specs/017-marketing-site` | [plan.md](../specs/017-marketing-site/plan.md) | 19 | ~65 | pending |
| **P16** | Accessibility + i18n hardening (retroactive) | `specs/018-a11y-i18n` | [plan.md](../specs/018-a11y-i18n/plan.md) | ~70 | ~198 | pending |
| **P17** | Pre-launch hardening | `specs/019-prelaunch-hardening` | [plan.md](../specs/019-prelaunch-hardening/plan.md) | 36 | ~428 | pending |

(Note: P3 moderation moved earlier than the master's P7 in §7 because every feature from P4 onward integrates moderation hooks; building moderation first means downstream features wire into a real service, not stubs.)

**Total ~625 tasks, ~3,756 engineer-hours = ~94 person-weeks (~1.8 person-years).**

---

## Execution rules (Phase 7 RALPH)

1. **One feature at a time.** Complete all tasks for the current feature before advancing.
2. **Branch per feature.** `git checkout -b feature/<spec-name>`.
3. **One task per RALPH iteration** per the orchestrator: Orchestrator → CodeSync → PolishVerify → SmokeRunner → AutoGuardian → back to Orchestrator.
4. **Atomic commits.** One commit per task. Commit message format: `<spec-id>(<area>): <title>` (e.g., `003(auth-svc): add argon2 password hashing`).
5. **Constitution check** every task (if `runs/constitution.md` exists).
6. **Done Evidence required** — "scaffolded" is not valid.
7. **No half-finished implementations.** Each task either completes or returns a REPAIR_PLAN.
8. **At feature end** — push the branch, merge to main, push main.
9. **Update `runs/state.json`** after every task (`current_phase`, `current_task`, `completed_tasks[]`).

---

## Cross-cutting tasks (interleaved into the per-feature plans)

These cross-cutting concerns are NOT a separate phase; they are addressed inside the feature plans where they apply:

- **i18n hooks** — every RN screen + Next.js page gets `<Trans>` wrappers and key registration. Catalog population is 018's job; integration is each feature's.
- **Accessibility** — every interactive element gets labels + roles + focus + 44pt targets during the feature build; 018 audits + closes gaps.
- **Observability** — Sentry + PostHog + CloudWatch wiring is in `colab_common` (002); each feature adds its own events.
- **Feature flags** — every new user-visible surface ships behind a flag toggleable in admin (016) by default.
- **DSR compliance** — every entity owning user data exposes an export + delete adapter (collected by §016 admin / DSR endpoint).

---

## Open blockers before P0 starts (from RECONCILIATION.md)

1. Apex domain not chosen — `example.com` placeholder.
2. AWS account not created — needed for `AWS_ACCOUNT_ID` + IAM admin user.
3. Vendor sign-ups parallelizable but several have multi-day lead times (Apple Dev, Stripe, Persona, Meta app review for OAuth, India DLT, India GST).
