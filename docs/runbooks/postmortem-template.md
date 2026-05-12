# Postmortem Template — Colab Platform

**Instructions**: Copy this template for each P1 incident (and recommended for repeat P2s).
Fill within 72h of resolution. Publish to `docs/runbooks/postmortems/INC-{date}-{seq}.md`.
Share in Slack #postmortems and link from the GitHub incident issue.

---

# Postmortem — [Incident Title]

**Incident ID**: INC-YYYYMMDD-NNN  
**Date**: YYYY-MM-DD  
**Severity**: P[1–4]  
**Duration**: HH:MM – HH:MM UTC (X hours Y minutes)  
**Affected services**: [list services]  
**Affected users**: [estimated count or "all users"]  
**Incident commander**: [name]  
**Author**: [name]  
**Reviewers**: [name, name]  
**Status**: Draft | In Review | Published  

---

## Summary

*2–3 sentences. Plain English. No technical jargon. Suitable for a non-engineer to read.*

Example: "On [date], [BRAND_NAME]'s API Gateway experienced a full outage for 47 minutes. All users were unable to log in or use the app. The cause was a misconfigured Kubernetes liveness probe that caused a cascading restart loop."

---

## Timeline (UTC)

| Time (UTC) | Event |
|------------|-------|
| HH:MM | Alert fired (Pingdom / Sentry / user report) |
| HH:MM | On-call paged via PagerDuty |
| HH:MM | On-call acknowledged; incident declared P[X] |
| HH:MM | Status page updated: "Investigating" |
| HH:MM | [First hypothesis formed] |
| HH:MM | [Root cause identified] |
| HH:MM | [Fix deployed / mitigation applied] |
| HH:MM | Status page: "Monitoring" |
| HH:MM | Service fully restored; confirmed stable |
| HH:MM | Status page: "Resolved" |
| HH:MM | Incident closed in PagerDuty |

---

## Root Cause

*Be specific. Name the exact code, configuration, or infrastructure element that failed. No blame — focus on systems and processes, not individuals.*

Example: "The liveness probe for the gateway-svc deployment was configured with a `timeoutSeconds: 1` value, which was too short for the service's startup time after a rolling update. Kubernetes interpreted the slow startup as an unhealthy pod and restarted all pods in rapid succession."

---

## Contributing Factors

*List 2–5 factors that contributed to the incident occurring or taking longer to resolve.*

1. **Factor 1**: [e.g., Liveness probe timeout not reviewed during Dockerfile changes]
2. **Factor 2**: [e.g., No staging environment equivalent to production node count — issue didn't reproduce in staging]
3. **Factor 3**: [e.g., On-call engineer unfamiliar with Kubernetes probe configuration — runbook didn't cover this scenario]
4. **Factor 4**: [optional]
5. **Factor 5**: [optional]

---

## Impact

| Metric | Value |
|--------|-------|
| Users affected | [estimate] |
| Duration | [X hours Y min] |
| Revenue impact | [$X lost in subscription processing / N/A] |
| Data loss | Yes / No (if Yes: describe scope + notification obligations) |
| SLA breach | Yes / No (99.9% target = 43.8 min/month) |
| Error budget consumed | X min of Y min monthly budget |

---

## What Went Well

*Genuinely positive observations — detection, response, communication that worked.*

1. [e.g., Pingdom alert fired within 60 seconds of first failure]
2. [e.g., On-call acknowledged within 3 minutes — within 5-minute SLA]
3. [e.g., Status page updated before user complaints surfaced]

---

## What Went Poorly

*Honest assessment of gaps — no blame, just systems.*

1. [e.g., Root cause took 25 minutes to identify — runbook didn't cover cascading restart loop]
2. [e.g., Discord announcement delayed by 20 minutes — unclear who owns community communication]
3. [e.g., Duplicate PagerDuty pages fired due to Pingdom check interval misconfiguration]

---

## Resolution

*What was done to fix the immediate issue. Step-by-step if relevant.*

Example:
1. Rolled back gateway-svc to previous deployment version via `kubectl rollout undo deployment/gateway-svc`.
2. Confirmed pods came up healthy with readiness probe passing.
3. Verified traffic routing restored via API Gateway health check.
4. Monitored for 30 minutes before declaring resolved.

---

## Follow-up Action Items

| # | Action | Owner | Due date | GitHub issue |
|---|--------|-------|----------|-------------|
| 1 | [Specific preventative action] | [name] | YYYY-MM-DD | [#123] |
| 2 | [Add runbook section for this failure mode] | [name] | YYYY-MM-DD | [#124] |
| 3 | [Add monitoring alert for leading indicator] | [name] | YYYY-MM-DD | [#125] |
| 4 | [Optional] | | | |

**Action item SLA**: All P1 follow-up items must have GitHub issues created within 24h of postmortem draft. Due dates must be within 30 days.

---

## Lessons Learned

*Synthesized learnings — what to do differently next time.*

1. [Learning 1]
2. [Learning 2]
3. [Learning 3]

---

## Appendix

*Optional: include raw logs, relevant CloudWatch graphs, Sentry error details, or other supporting evidence.*

- CloudWatch screenshot: [attach or link]
- k6 load test showing impact: [attach or link]
- Relevant log lines: [attach or link]
