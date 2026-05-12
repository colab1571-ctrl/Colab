# On-Call Rotation — Colab Platform

**Version**: 1.0  
**Date**: 2026-05-11  
**Tool**: PagerDuty  
**Owner**: Engineering Lead

---

## 1. Rotation Structure

| Role | Rotation interval | Count | Notes |
|------|------------------|-------|-------|
| Primary on-call | 1 week | 1 engineer | Rotates every Monday 09:00 local time |
| Secondary on-call | 1 week | 1 senior engineer | Same rotation, offset by 4 days |
| Incident Commander | Per-incident | Engineering Lead | Paged on P1 only; not in rotation |

### Rotation cadence

```
Week 1: Engineer A (Primary) + Engineer B (Secondary)
Week 2: Engineer B (Primary) + Engineer C (Secondary)
Week 3: Engineer C (Primary) + Engineer A (Secondary)
Week 4: Engineer A (Primary) + Engineer B (Secondary)
...
```

Rotation pool at launch: minimum 3–4 engineers. With <3 engineers, compress to 2-person rotation with compensatory time off (1 business day off per week of primary on-call).

### Handoff protocol

Every Monday 09:00 local:
1. Outgoing primary posts a handoff note in #incidents channel:
   ```
   @[incoming_name] Handing off on-call.
   - Active incidents: None / [list]
   - Ongoing investigations: [list or "none"]
   - Known fragile areas this week: [list or "none"]
   - Any deployment freeze in effect: Yes/No
   ```
2. Incoming primary acknowledges in the same thread.
3. Incoming primary verifies PagerDuty shows them as active.

---

## 2. PagerDuty Setup

### Schedule configuration

```
Schedule name: Colab Production On-Call
Rotation type: Weekly
Restriction: Yes — P3/P4 pages suppressed 23:00–07:00 local time
Rotation start: Monday 09:00 America/New_York (adjust per team timezone)

Layers:
  Layer 1 (Primary): Weekly rotation through [Engineer A, B, C, D]
  Layer 2 (Secondary): Weekly rotation through [Engineer B, C, D, A] (shifted 4 days)
```

### Escalation policy

| Level | Target | Timeout |
|-------|--------|---------|
| L1 | Primary on-call | 5 min for ack |
| L2 | Secondary on-call | 10 min (if no L1 ack) |
| L3 (P1 only) | Engineering Lead | 10 min (simultaneous with L1+L2) |

### Service configuration

Create one PagerDuty service per critical service group:

| PagerDuty service | Maps to | Escalation policy |
|------------------|---------|------------------|
| Colab API Gateway | gateway-svc + auth-svc | Production Escalation |
| Colab Chat Service | chat-svc | Production Escalation |
| Colab Billing Service | billing-svc | Production Escalation |
| Colab AI Orchestrator | ai-orchestrator-svc | Production Escalation |
| Colab Media Service | media-svc | Production Escalation |
| Colab Infrastructure | EKS, RDS, Redis, MQ | Production Escalation |
| Colab Security | auth-svc (security alerts) | Security Escalation (always pages IC) |

### Integrations

| Integration | PagerDuty service |
|------------|------------------|
| Pingdom uptime | Colab API Gateway + per-service |
| Sentry (crash spike) | Colab API Gateway |
| AWS CloudWatch (EKS/RDS alarms) | Colab Infrastructure |
| Statuspage.io (manual trigger) | All services |
| Slack /pd trigger | All services |

---

## 3. Quiet Hours Policy

| Severity | Paged during quiet hours (23:00–07:00 local)? |
|----------|----------------------------------------------|
| P1 | Yes — always |
| P2 | Yes — always |
| P3 | No — suppressed; surfaces at 07:00 |
| P4 | No — ticket only |

**Definition of "local time"**: Primary on-call engineer's local timezone (set in PagerDuty user profile). Rotation schedule adjusts to the current primary's timezone.

---

## 4. On-Call Expectations

### During on-call week

- Keep phone available and notifications enabled (no phone-off days)
- Acknowledge PagerDuty pages within 5 minutes (P1/P2)
- If unable to respond within 5 minutes: immediately call secondary
- No overseas travel without arranging swap with another engineer
- If sick: notify engineering lead immediately; arrange temporary coverage

### Response checklist (P1/P2)

```
1. Acknowledge PagerDuty page
2. Open #incidents-p1 (P1) or #incidents (P2) in Slack
3. Post: "@channel Acknowledged. Investigating. IC: [self or @engineering-lead]"
4. Open status page and check all components
5. Check CloudWatch dashboard for the affected service
6. Check Sentry for error spike
7. Open relevant runbook (docs/runbooks/services/<service>.md)
8. Follow runbook recovery procedure
9. Post updates every 15 min to Slack incident channel
10. Update Statuspage.io
11. Resolve or escalate
12. Close PagerDuty incident when service is stable
13. Initiate postmortem (P1) or create tracking issue (P2)
```

### On-call compensation

- Compensatory time off: 1 business day per week of primary on-call
- P1 incident outside business hours (per incident): 0.5 business day additional comp time
- Policy review: annually in Q4; adjust as team scales

---

## 5. Test Page Protocol

Before going live, all engineers in the rotation must:

1. Complete PagerDuty onboarding (verify app installed, notifications enabled, schedule active)
2. Participate in a test page: engineering lead triggers a test PagerDuty incident during business hours
3. Confirm: acknowledgment works, phone notification fires, Slack bridge fires
4. Verify: rotation schedule shows correct coverage for next 4 weeks

Test page scheduled: 2 weeks before public launch.
