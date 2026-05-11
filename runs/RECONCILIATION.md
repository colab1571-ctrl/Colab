# Phase 5b — Cross-Feature Reconciliation

Pass over the 19 detailed plans. Checks: shared entities, contract alignment, dependency ordering, terminology drift, conflicting architecture decisions.

---

## ✅ Shared entities — consistent

| Entity | Owning spec | Consumers | Notes |
|---|---|---|---|
| `User` | 003 auth-svc | 004, 006, 007, 008, 009, 013, 014, 015, 016 | 1:1 with Profile. Auth state in auth-svc; profile data in profile-svc |
| `Profile` | 004 profile-svc | 005, 006, 007, 009, 013 (visibility), 014 | Owns badge state machine + portfolio + externals |
| `IdentityVerification` | 003 identity-svc | 004 (badge gate), 008 (under-18 escalation) | Persona-driven |
| `MatchScore` | 005 matching-svc | 006 (snapshot to invite) | Nightly recompute + on-demand |
| `CollabInvite` | 006 invite-svc | 009 (`match.created` consumer), 014 | 30-day archive |
| `Collaboration` | 009 collab-svc | 007 (`chat_room.collaboration_id` FK), 010, 011, 012 | Single aggregate root for the workspace |
| `ChatRoom` | 007 chat-svc | 009 (1:1 link), 010 (system msgs), 011 (meeting transcripts), 012 (AI cmds) | One per Collaboration |
| `ChatMessage` | 007 chat-svc | 008 (mod scan), 009 (last_activity), 014 (notification) | Lifetime+3yr retention |
| `Block` | 006 invite-svc | 005, 007, 009, 014 | Reciprocal; hard mutual |
| `Subscription` + `EntitlementSnapshot` + `CreditWallet` | 013 billing-svc | every gated feature (005/006/007/008/009/010/012) | Source of truth for all axes |
| `ModerationCase` + `ModerationAction` | 008 moderation-svc | 003/004/006/007/009/013/014/015/016 (action fan-out) | Risk-tier routing |
| `Notification` + `PushDevice` + `NotificationPreference` | 014 notification-svc | every emitting service | Single delivery layer |
| `SupportTicket` | 015 support-svc | 008 (cross-link), 013 (cross-link), 016 (queue) | SLA timers |
| `AdminAuditLog` + `EntitlementConfig` + `FeatureFlag` | 016 admin-svc | platform-wide | Append-only |
| `MockupConsent` + `MockupAsset` + `AIInteraction` | 012 ai-orchestrator-svc | 007 (in-chat), 013 (credit metering) | Premium-only |
| `Meeting` + `MeetingArtifact` | 011 meeting-svc | 007 (transcripts as system msgs), 009 (audit log) | Google Meet + Recall.ai |
| `WhiteboardSnapshot` + `Task` + `TaskComment` | 010 collab-svc extension | 007 (system msgs on task flip) | Y.js CRDT + LexoRank |

**No entity ownership conflicts** detected.

---

## ✅ Contract alignment — consistent

API styles all REST (no GraphQL/tRPC drift). All services expose OpenAPI; TS client codegen runs from `gateway-svc` aggregating each service's `/openapi.json`. Queue events use consistent naming (`<entity>.<verb_past>`, e.g., `match.created`, `invite.accepted`, `collab.archived`, `entitlement.changed`, `moderation.action_taken`).

**Webhook patterns** (Stripe / RevenueCat / Persona / Replicate / Recall.ai) all use HMAC verification + idempotency-key + event-log replay protection. Consistent.

---

## ✅ Dependency ordering — clean

Phase order P0 → P18 from master §7 holds. Per `runs/feature.json` the dependency edges are:

```
001 → 002 → {003, 008, 013, 014}
003 → 004
004 → 005
005 → 006 (via match-score snapshot)
006, 008 → 007
007 → 009
009 → {010, 011, 012}
013 → {005 (caps), 006 (quota), 007 (export), 009 (export), 010 (export), 012 (credits)}
{003,004,006,007,008,009,010,011,012,013,014,015} → 016 (admin reads)
002 → 017 (marketing) (independent of feature work)
002 → 018 (a11y/i18n cross-cutting, retroactive)
{all-above} → 019 (prelaunch hardening)
```

No cycles. The retroactive nature of 018 is explicit in its plan; each feature spec's RN/web tasks should stub i18n hooks even if 018 fills catalogs later.

---

## ⚠️ Terminology drift — minor, resolved

1. **Rating**: Master §0 R16 locked **thumbs up/down + tag chips**. 009 plan correctly uses `feedback_tag[]` + up/down enum; 004 references "up-vote count" on profile view. Consistent — but the source data model called it 1–5 stars. The master spec already records the revision; no further action.
2. **"Match!" notification** vs `match.created` event vs `match_notification` type — Notification type key is `new_match` (014); event name is `match.created` (006); UI copy is "Match!" — all distinct naming layers. No drift.
3. **"Picked for you"** (UI) vs `RecommendationSet` (entity, 005) — consistent.
4. **"Vibe Check"** (UI) vs `CollabInvite` (entity, 006) — consistent.

---

## ⚠️ Conflicting architecture decisions — 2 mild

### 1. Service-to-service auth: HS256 vs IRSA-JWT (RS256)

- **002 shared-platform** defaulted service-to-service auth to **HS256 shared-secret** at launch with a note to revisit when >2 internal callers exist.
- **003 auth-identity** mentioned IRSA-issued service tokens.

**Resolution**: ship HS256 shared-secret at launch per 002's default; revisit RS256+IRSA in v1.1 when the call graph proves the need. Document in `colab_common.auth.service_to_service`. Capture as ADR in `docs/adr/` during 002 implementation.

### 2. WebSocket connection multiplicity

A single mobile client may hold three WebSocket connections simultaneously:
- `chat-svc` for messages (007)
- `whiteboard-svc` (inside collab-svc) for tldraw ops (010)
- `notification-svc` for in-app banners (014)

**Resolution**: accept three connections at launch (each owns distinct state). Add Phase 19 (prelaunch hardening) task to evaluate consolidation behind a single WS gateway in v1.1 — there's a clean refactor opportunity but it's not blocking. Document as risk in `019-prelaunch-hardening/plan.md` follow-ups.

---

## ⚠️ Open user-input blockers (must answer before Phase 7 P0 lands)

1. **Apex domain name** — placeholder `example.com` in Terraform. Without this: no DNS, no ACM cert, no SES verified domain, no OAuth redirect URIs, no API Gateway custom domain, no CloudFront aliases, no App Store listing URL. Single biggest blocker.
2. **AWS account ID** — once you sign up, the bootstrap + Terraform need it (filled into `.env` + Terraform tfvars).
3. **GitHub Actions OIDC**: confirm the deploy role naming convention (`colab-github-deploy-<env>` is the default in 001 plan).

## ⚠️ Open vendor/legal blockers (parallelizable; not blocking Phase 7 start but blocking pieces)

- AWS root sign-up + IAM admin user creation (manual KYC; 24–48h).
- AWS SES production-access ticket (24–48h).
- Apple Developer enrollment ($99/yr; D-U-N-S if org; 1–7 days).
- Google Play Console enrollment ($25 + KYC; 1–3 days).
- Apple `.p8` APNs key + Google FCM v1 service account (created post-enrollment).
- Stripe account activation (KYC + bank; 1–7 days).
- RevenueCat free account (instant; uploads Apple/Play keys).
- Persona sandbox (instant); production KYB (1–7 days).
- OpenAI / Replicate / Mapbox / Sentry / PostHog / Recall.ai accounts (each instant via OAuth where supported).
- Meta for Developers + Spotify Developer — app review takes 2–6 weeks; start NOW for §004 OAuth phase.
- India DLT SMS registration (003 risk) — blocks phone signup in IN; 4–8 weeks for telco approval.
- India GST registration / reseller path (013 risk) — blocks IN B2C IAP+web payments unless via Apple/Play (which handle store-side tax).
- DMCA designated agent — deferred per master §0 (accepted reduced safe harbor).

## ⚠️ Open product / UX items (deferred to admin config or v1.1)

- Pricing values (Premium $/mo, Pro $/mo, monthly/annual, credit-bundle sizes) — admin config from launch dashboard.
- Entitlement-axis values per tier — admin config.
- Brand name lock + brand voice copy — pre-launch.
- Onboarding KPI numeric targets — set post-launch from real data.
- Affinity matrix tuning (005's 9×9 vocation matrix) — admin config.
- Vocation taxonomy refinement (004's 9 categories + sub-tags) — admin content review.

---

## Open questions surfaced by detailing agents (non-blocking; defer to v1.x)

1. **(003)** Add "confirm-to-link" email path for OAuth email collisions? → Defer; current 409 behavior acceptable for v1.
2. **(003)** KMS-wrapped private-key caching to reduce JWT signing latency? → Defer; needs security review when launch traffic demands it.
3. **(003)** Final clock-skew SLO threshold? → Default to 30s leeway; revisit if tokens are misissued in prod.
4. **(005)** Cold-start ranking for users with empty portfolios? → Heuristic: vocation-only match + recency. Document in 005 plan if not already.
5. **(007)** API Gateway WebSocket 2-hour hard limit reconnect UX — front-end smoothness needs a follow-up design pass.
6. **(010)** ypy-websocket maturity check at integration time; possible move to Yrs (Rust) backend if Python perf is insufficient.
7. **(013)** India GST reseller registration vs Paddle-MoR fallback — final decision deferred pending Stripe Tax India coverage validation.

---

## Conclusion

**No spec-blocking conflicts.** The 19 plans cohere into one platform. The handful of user-input blockers (apex domain, vendor sign-ups) are parallelizable with Phase 7 P0 work. Resolution items either: (a) auto-resolve in admin config, (b) defer to v1.1 with a recorded ADR, or (c) need a user decision (collected separately).

Phase 6 (task merge) can start.
