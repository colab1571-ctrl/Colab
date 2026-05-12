# Severity Definitions — Colab Platform

**Version**: 1.0  
**Date**: 2026-05-11

---

## Quick Reference

| Severity | User impact | Revenue impact | Response target |
|----------|-------------|---------------|----------------|
| P1 — Critical | All users or core function | Immediate / severe | Ack 5 min; resolve 2h target |
| P2 — High | Majority of users or one key feature | Significant | Ack 15 min; resolve 4h target |
| P3 — Medium | Subset of users; workaround exists | Minor | Ack 2h; resolve within sprint |
| P4 — Low | Edge case; ≤1 user | None | Next business day |

---

## P1 — Critical

Complete service outage, data loss, or active security breach. All users are impacted or core platform functions are unavailable.

**Criteria (any one triggers P1)**:
- API Gateway returning ≥50% 5xx over any 2-minute window
- auth-svc down: users cannot log in or sign up
- chat-svc down: all WebSocket connections rejected
- RDS unreachable: database failover in progress and >5 min outage
- Confirmed or suspected data breach (any user PII exposed)
- Billing-svc down: no payment processing for >5 min
- Crash-free session rate drops below 95% (vs. 99% target)

**Resolution target**: Service restored or workaround in place within 2 hours  
**Communication**: Status page + #incidents-p1 + optional Discord post if >1h  
**Postmortem**: Required; published within 72h

---

## P2 — High

Significant degradation. Majority of users impacted or one key feature unavailable. Revenue may be affected.

**Criteria (any one triggers P2)**:
- Discovery feed failing for >20% of requests
- Billing webhooks failing (subscriptions not processing)
- Push notifications backlogged >30 min
- Chat message delivery delayed >5 seconds for >20% of messages
- AI command queue backed up >10 min
- Media uploads failing for all users
- Moderation queue backed up >1h (safety risk)
- Any service reporting >20% 5xx over 5-minute window
- Crash-free session rate between 95%–99%

**Resolution target**: Issue identified within 30 min; resolved within 4 hours  
**Communication**: Status page update within 15 min; Slack #incidents updates every 30 min  
**Postmortem**: Recommended for recurring P2s; optional for one-off events

---

## P3 — Medium

Partial degradation. Some users are impacted. A workaround exists. No immediate revenue impact.

**Criteria**:
- AI commands slow (>15s P95) but completing
- File upload failing for specific MIME types or file sizes
- Profile search latency degraded (>2s P95)
- Analytics event loss (PostHog delay >1h)
- Single-region push notification delay
- Non-critical admin function unavailable
- CI/CD pipeline intermittently failing (not blocking deployments)
- Rate limit false positives affecting a small subset of users

**Resolution target**: Acknowledged within 2h (business hours); resolved within current sprint  
**Communication**: Slack #engineering note; no status page update unless user-visible  
**Postmortem**: Not required; GitHub issue tracking

---

## P4 — Low

Minor issue with no meaningful user impact. Edge case or cosmetic.

**Criteria**:
- Cosmetic UI bug on a specific device/OS version
- Typo in error message or notification copy
- Analytics event missing for a non-critical action
- Slow response on an infrequently used, non-critical API endpoint
- Documentation inconsistency
- Accessibility issue affecting <5 users in specific configuration

**Resolution target**: Triaged in weekly standup; resolved in next available sprint slot  
**Communication**: GitHub issue only; no Slack page  
**Postmortem**: Not applicable

---

## Severity Escalation Rules

### Escalating a severity (P3 → P2, P2 → P1)

An engineer or on-call should escalate severity if:
- The issue is spreading to more users than initially estimated
- A workaround stops working
- Time-to-resolve is exceeding the target
- New information reveals higher impact than initially assessed

To escalate: Post in #incidents with `ESCALATING P[old] → P[new]` and trigger new PagerDuty incident at the appropriate severity.

### De-escalating a severity (P1 → P2, P2 → P3)

De-escalate when:
- A workaround is in place and user impact is substantially reduced
- The immediate emergency is resolved but root cause investigation continues
- Impact is confirmed to be smaller than initially assessed

To de-escalate: Update Statuspage.io component status; post in #incidents; no additional PagerDuty action needed.

---

## SLA Calculation

**Availability SLA target**: 99.9% per calendar month

99.9% availability = 43.8 minutes of downtime allowed per month.

**Downtime measurement**:
- Measured from first detection (Pingdom alert or first user report) to service fully restored
- Measured for P1 incidents only (P2+ contribute to degradation, not downtime)
- Excluded: Planned maintenance windows (announced 48h in advance on Statuspage)

**SLA breach notification**:
- Engineering lead notified when month-to-date downtime > 30 min
- Monthly SLA report published to #engineering by 5th of each month
