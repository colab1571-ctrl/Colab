# Paging Policy — Colab Platform

**Version**: 1.0  
**Date**: 2026-05-11

---

## 1. Severity Levels

| Severity | Short name | Response SLA | Page target |
|----------|------------|-------------|------------|
| P1 | Critical | Ack within 5 min | Primary + Secondary + IC simultaneously |
| P2 | High | Ack within 15 min | Primary on-call |
| P3 | Medium | Ack within 2h (business hours) | Primary on-call (business hours only) |
| P4 | Low | Next business day | Ticket only; no page |

---

## 2. P1 — Critical

**Definition**: Complete service outage, active security breach, or confirmed data loss affecting any users.

**Examples**:
- auth-svc down (no one can log in or sign up)
- chat-svc total failure (all WebSocket connections rejected)
- Database unreachable (RDS failover not completing, >5 min outage)
- Active security incident (suspected credential compromise, data exfiltration)
- Billing-svc down (all payment processing blocked)
- API Gateway returning 5xx on >50% of requests

**Page target**: Primary on-call + Secondary on-call + Incident Commander simultaneously  
**Response SLA**: Acknowledged within 5 minutes  
**Escalation**: If no ack in 10 minutes → page Engineering Lead directly

**P1 actions**:
1. Page fires → engineer acks in PagerDuty
2. Open #incidents-p1 Slack channel immediately
3. Post incident commander declaration: who is IC?
4. Update Statuspage.io within 5 min of detection
5. Start incident Zoom/Meet call; link posted in Slack
6. Postmortem required within 72h

---

## 3. P2 — High

**Definition**: Significant degradation affecting majority of users or all users in a specific feature; revenue impact.

**Examples**:
- Discovery feed not loading for >20% of users
- Billing webhooks failing (subscription processing delayed)
- Push notifications not delivering (>30 min backlog)
- chat-svc delivering messages with >5 second delay
- AI orchestrator queue backed up >10 min (all AI commands queued)
- Media uploads failing for all users

**Page target**: Primary on-call  
**Response SLA**: Acknowledged within 15 minutes  
**Escalation**: If no ack in 20 min → page Secondary on-call

**P2 actions**:
1. Page fires → acknowledge
2. Post in #incidents (not #incidents-p1 unless escalating to P1)
3. Update Statuspage.io if user-visible
4. Investigate + fix; post updates every 30 min in #incidents
5. Create tracking GitHub issue if systemic fix needed

---

## 4. P3 — Medium

**Definition**: Partial degradation affecting subset of users; workaround exists; no immediate revenue impact.

**Examples**:
- AI commands slow (>15s) for some users
- File upload failing for specific MIME types
- Moderation queue backed up (manual review delayed)
- Single region's push notifications delayed
- Profile search returning slow results
- Analytics events missing (PostHog delay)

**Page target**: Primary on-call (business hours 09:00–18:00 local only)  
**Response SLA**: Acknowledged within 2 hours  
**Escalation**: If no ack in 4h → page Secondary on-call

**P3 actions**:
1. Page fires (business hours) or becomes active at 09:00 (if occurred overnight)
2. Post in #engineering
3. Investigate; no Statuspage update unless it becomes user-visible
4. Fix within current sprint

---

## 5. P4 — Low

**Definition**: Minor issue; single user or edge case; cosmetic or non-impacting.

**Examples**:
- Typo in error message
- Single user reporting analytics discrepancy
- Non-critical cosmetic bug on specific device
- Slow response on a rarely-used endpoint (P95 > SLO but not affecting users)

**Page target**: None — ticket created in GitHub Issues  
**Response SLA**: Next business day  
**Action**: Triaged in weekly engineering standup

---

## 6. Escalation Tree

```
P1 Incident
├── Primary on-call (ack within 5 min)
├── Secondary on-call (simultaneous)
├── Incident Commander / Engineering Lead (simultaneous on P1)
│   └── If all three unreachable within 15 min:
│       └── CEO / Founding Team (emergency contact — outside business hours only)
│
P2 Incident
├── Primary on-call (ack within 15 min)
│   └── No ack in 20 min:
│       └── Secondary on-call
│           └── No ack in additional 20 min:
│               └── Engineering Lead
```

### Emergency contacts (to be filled before launch)

| Role | PagerDuty user | Mobile | Backup |
|------|---------------|--------|--------|
| Primary on-call | Per rotation | — | — |
| Secondary on-call | Per rotation | — | — |
| Engineering Lead | [name] | [redacted] | [redacted] |
| CEO / Co-founder | [name] | [redacted] | [redacted] |

**Sensitive data note**: Full contact list maintained in PagerDuty (not in this file). Update PagerDuty user profiles, not this document.

---

## 7. Alert Source Mapping

| Alert source | Default severity | Routing |
|-------------|-----------------|---------|
| Pingdom: 2 consecutive failures (critical endpoint) | P1 | Primary + Secondary |
| Pingdom: 3 consecutive failures (non-critical) | P2 | Primary |
| Sentry: crash rate >2% on any release | P1 | Primary + Secondary |
| Sentry: crash rate >1% (warning) | P2 | Primary |
| CloudWatch: EKS node NotReady | P2 | Primary |
| CloudWatch: RDS failover started | P1 | Primary + Secondary + IC |
| CloudWatch: Redis failover | P2 | Primary |
| CloudWatch: billing queue depth >10k | P2 | Primary |
| CloudWatch: chat disconnect rate >2% | P1 | Primary + Secondary |
| Manual trigger (Slack /pd trigger) | As specified | As specified |
| GitHub Actions: deploy failure to production | P3 | Primary |

---

## 8. Policy Review

This policy is reviewed:
- Quarterly (Jan, Apr, Jul, Oct)
- After every P1 postmortem (update if escalation gaps identified)
- When team composition changes (rotation pool changes)

Owner: Engineering Lead. Changes require sign-off from at least 2 engineers.
