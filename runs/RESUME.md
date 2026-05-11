# RESUME.md — Continue Colab from a fresh session

> If a new session opens this repo and needs to pick up where the unified-development pipeline left off, read this file first, then `runs/state.json`.

## Where we are

Phases 0–6 of the unified-development pipeline are complete:
- **Master spec**: `specs/000-master/spec.md`
- **23 clarify rounds** resolving ~95 items: `runs/clarify_log.md`
- **19 feature specs**: `specs/001-…/spec.md` through `specs/019-…/spec.md`
- **19 detailed plans**: `specs/001-…/plan.md` through `specs/019-…/plan.md`
- **Reconciliation pass**: `runs/RECONCILIATION.md`
- **Master task plan**: `runs/IMPLEMENTATION_PLAN.md`
- **Infra docs + IaC skeleton**: `docs/INFRA.md`, `.env.example`, `terraform/`

## What's next

**Phase 7 — RALPH implementation loop**, starting at **P0 Infrastructure** (`specs/001-infrastructure/plan.md`).

The RALPH loop is: Orchestrator picks next task → CodeSync implements → PolishVerify lints/tests → SmokeRunner runs acceptance → AutoGuardian gates → back to Orchestrator. One task per iteration. One commit per task.

## Open user-input blockers (must resolve before P0 finishes)

1. **Apex domain** — placeholder `example.com` in Terraform.
2. **AWS account** — root sign-up + IAM admin user.
3. **Vendor sign-ups** — Apple Dev, Google Play, Stripe, Persona, OpenAI, Replicate, Recall.ai, Mapbox, Sentry, PostHog, Meta for Devs, Spotify Dev, EAS (Expo). See `docs/INFRA.md` for the manual map.

## How to resume

If you're starting a new session:

1. Run: `cat /Users/amays/Desktop/Work/Colab_3/runs/state.json` — current pipeline state.
2. Run: `cat /Users/amays/Desktop/Work/Colab_3/runs/IMPLEMENTATION_PLAN.md` — phase order + task counts.
3. The current feature should be in `state.json.phase_7_state.current_feature` (null until P0 starts).
4. Open the feature's `plan.md`. Find the next task in the implementation task list (top of the list with `blocked_by` satisfied).
5. Execute the task; commit; update `state.json` (`current_task`, append to `completed_tasks`).
6. Repeat until the feature's task list is done. Then push branch, merge to main, advance to next feature.

## Model routing (per orchestrator)

- **Master orchestrator** (you, reading this): Opus
- **Sub-agents for code implementation**: Sonnet (CodeSync, PolishVerify, SmokeRunner)
- **Sub-agents for review/decision**: Opus (Orchestrator, AutoGuardian, Plan revisions)
- Promote any sub-agent to Opus only if quality-critical (e.g., security-sensitive code review).

## Key locked decisions (don't re-litigate)

See `specs/000-master/spec.md` §0. Highlights:
- React Native + Expo (mobile); 3× Next.js apps (marketing/consumer/admin).
- Python FastAPI microservices (12+).
- AWS EKS / RDS / Redis / S3 / MQ RabbitMQ / SNS / SES / Secrets Manager.
- Postgres + pgvector + PostGIS.
- OpenAI (LLM + moderation + embeddings) + Replicate (mockups) + Recall.ai (meetings).
- Persona (selfie/liveness).
- RevenueCat + Stripe payments.
- Sentry + PostHog + CloudWatch observability.
- Worldwide soft-launch in US/CA/AU/NZ/IN. 18+ only. WCAG 2.1 AA. English at launch; i18n-ready.
