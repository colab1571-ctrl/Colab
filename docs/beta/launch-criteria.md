# Beta Launch Criteria — Gate Checklist

**Version**: 1.0  
**Date**: 2026-05-11  
**Gate**: All criteria must be met before public launch is approved

---

## AC-5: Beta Completion Gate

The following criteria must all be GREEN before the public launch date is set.

---

### Gate 1: 100 Beta Users Onboarded

| Criterion | Target | Verification |
|-----------|--------|-------------|
| Signed NDAs | 100 | DocuSign completed envelopes |
| TestFlight installs | ≥ 90 (10 may prefer Android) | TestFlight install count in App Store Connect |
| Play Alpha installs | ≥ 10 | Play Console track install count |
| Onboarding started | ≥ 95 | PostHog: `onboarding_started` event |
| **Onboarding completed** | **≥ 80** | **PostHog: funnel step "portfolio_upload_completed"** |

**Verification query (PostHog)**:
```sql
SELECT
  count(distinct person_id) as completed,
  count(distinct person_id) * 100.0 / 100 as completion_rate
FROM events
WHERE event = 'portfolio_upload_completed'
  AND timestamp >= beta_start_date
  AND timestamp <= beta_end_date
```

---

### Gate 2: Crash-Free Sessions ≥ 99%

| Criterion | Target | Verification |
|-----------|--------|-------------|
| Overall crash-free session rate | ≥ 99.0% | Sentry → Releases → Crash Rate |
| Maximum single-day crash rate | < 2.0% | Sentry daily breakdown |
| Critical crash categories open | 0 | All CRITICAL crash types resolved or not reproducible |

**Escalation thresholds during beta**:
- >1% crash rate on any day → P2 incident; pause new invitations
- >2% crash rate on any day → P1 incident; investigate before continuing
- >5% crash rate → stop beta; fix and restart

**Sentry crash-free measurement**:
- Sentry "Crash Free Sessions" metric on the mobile project
- Exclude: intentional test crashes from QA devices (filter by device ID list)
- Include: all beta participants' devices

---

### Gate 3: Load Test Sign-Off (AC-1)

| Criterion | Target | Verification |
|-----------|--------|-------------|
| All 5 k6 scenarios green | Pass | k6 threshold summary JSON (all GREEN) |
| P95 latencies within budget | See plan §3 | Grafana dashboard export |
| HTTP error rate during test | < 1% | k6 `http_req_failed` metric |
| WebSocket disconnect rate | < 0.5% | k6 `chat_ws_disconnect_rate` metric |
| Chat message delivery rate | ≥ 99.9% | k6 `chat_msg_delivered_rate` metric |

Evidence stored in: `docs/load-tests/[date]/`

---

### Gate 4: Zero HIGH/CRITICAL Security Findings (AC-2)

| Criterion | Target | Verification |
|-----------|--------|-------------|
| Snyk: high/critical findings | 0 | `snyk test` exits 0 for all services |
| Trivy: CRITICAL/HIGH in ECR images | 0 (or all accepted with exception) | Trivy SARIF in GitHub Security |
| semgrep HIGH/CRITICAL | 0 | semgrep CI log |
| bandit HIGH | 0 | bandit CI log |
| Pen-test HIGH/CRITICAL open | 0 | Pen-test final report (T-017 retest) |
| MASVS required controls verified | All REQUIRED passed | `docs/security/owasp-masvs-mapping.md` evidence |

---

### Gate 5: App Store / Play Store Approval (AC-3, AC-4)

| Criterion | Target | Verification |
|-----------|--------|-------------|
| iOS TestFlight external track | Active | App Store Connect build status |
| iOS production submission | Approved or Ready for Sale | App Store Connect |
| Android Alpha track | Published | Play Console release status |
| Android production submission | Approved | Play Console |
| Age rating (iOS) | 17+ assigned | App Store Connect |
| Content rating (Android) | Assigned via IARC | Play Console |

**Known risk**: First submission may be rejected. Allow 2–3 review cycles in timeline. Track rejections in `docs/app-store/rejection-log.md`.

---

### Gate 6: Status Page + Runbook Published (AC-6)

| Criterion | Target | Verification |
|-----------|--------|-------------|
| Statuspage.io components live | All "Operational" | Navigate to status page URL |
| Pingdom checks passing | All "Up" for ≥24h | Pingdom dashboard |
| Status page linked in app | Yes | App Settings → System Status |
| Status page in marketing site footer | Yes | Marketing site QA |
| Runbook in repo | Yes | `docs/runbooks/` — files present + PR merged |
| Runbook reviewed by ≥2 engineers | Yes | PR approval count |

---

### Gate 7: Billing Sandbox Tests Passed

| Criterion | Target | Verification |
|-----------|--------|-------------|
| iOS sandbox purchase (premium_monthly) | Completes + entitlement granted | Manual test on TestFlight |
| iOS sandbox restore purchase | Restores correctly | Manual test |
| iOS sandbox cancel + expiry | Entitlement revoked after grace period | Manual test |
| Android sandbox purchase | Completes + entitlement granted | Manual test on Play Alpha |
| Credits consumable (ai_credits_100) | 100 credits added to wallet | Manual test |
| Duplicate webhook idempotency | No double-credit | Billing webhook storm load test |

---

## Sign-Off Record

| Gate | Status | Signed off by | Date |
|------|--------|--------------|------|
| Gate 1: 100 beta users onboarded | PENDING | — | — |
| Gate 2: Crash-free ≥99% | PENDING | — | — |
| Gate 3: Load test sign-off | PENDING | — | — |
| Gate 4: Zero HIGH/CRITICAL security | PENDING | — | — |
| Gate 5: Store approvals | PENDING | — | — |
| Gate 6: Status page + runbook | PENDING | — | — |
| Gate 7: Billing sandbox | PENDING | — | — |

**All gates PENDING → PUBLIC LAUNCH NOT APPROVED**

Update this table in the launch gate PR. Engineering lead and product lead must both sign off.
