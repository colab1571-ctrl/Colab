# Runbook — moderation-svc

**Version**: 1.0 | **Date**: 2026-05-11 | **Owner**: Engineering Lead

---

## SLOs

| Metric | Target | Alert threshold |
|--------|--------|----------------|
| Moderation queue processing lag | ≤ 60s (auto tier) | >5min → P2 |
| CSAM detection accuracy | 100% true positive rate | Any miss → P1 |
| Moderator response time (manual queue) | ≤ 4h (MEDIUM risk), ≤ 1h (HIGH risk) | >SLA → P3 |
| OpenAI moderation API error rate | < 1% | >5% → P2 (fallback to rule-based) |
| Moderation worker availability | 99.9% | Downtime > 5min → P2 |

---

## Dashboards

- Grafana: `Colab Moderation Queue` → queue depth per risk tier, processing rate, action types
- CloudWatch: `colab-prod-moderation-svc` log group
- Sentry: `moderation-svc` project
- Admin console: `admin.[brandname].com/moderation` → live queue view

---

## Common Alerts and Recovery

### Alert: `moderation-queue-depth-high` (MEDIUM/HIGH queue > 500 items)

**Likely cause**: OpenAI moderation API rate limit hit, or Celery worker down.

**Recovery**:
```bash
# 1. Check moderation worker pods
kubectl get pods -n colab-production -l app=moderation-worker

# 2. Check OpenAI API rate limit
kubectl logs -l app=moderation-worker -n colab-production --since=5m | grep "openai\|rate_limit"

# 3. If OpenAI rate limited: workers will fallback to rule-based scanner automatically
#    Verify fallback is active:
kubectl logs -l app=moderation-worker --since=5m | grep "fallback"

# 4. Scale up workers
kubectl scale deployment moderation-worker --replicas=10 -n colab-production
```

### Alert: `csam-detection-failure` (PhotoDNA / hash check error)

**Severity**: P1. CSAM detection must be 100% reliable.

**Immediate action**:
1. Page on-call P1 immediately.
2. Pause all media upload acceptance:
   ```bash
   kubectl set env deployment/media-svc MEDIA_UPLOAD_ENABLED=false -n colab-production
   ```
3. Investigate PhotoDNA API connectivity.
4. If PhotoDNA API is down: do not re-enable uploads until API is restored or alternative hash check confirmed.
5. Notify legal team of any gap in CSAM detection capability.

### Alert: `moderation-manual-queue-sla-breach`

**Likely cause**: Insufficient moderator coverage (high volume period or under-staffed).

**Recovery**:
1. Check admin console → moderation queue → items older than SLA threshold
2. Temporarily reduce HIGH-risk threshold to route more items to auto-resolve
3. Alert engineering lead to add temporary moderator capacity
4. If queue contains CSAM-risk items that have not been reviewed: escalate to P1

---

## Safety Note

Any suspected CSAM content must be treated as P1 regardless of other incident priority. Legal obligations:
- US: NCMEC CyberTipline reporting required (18 U.S.C. § 2258A)
- Timeline: Report as soon as reasonably possible after becoming aware
- Contact: engineering lead + legal counsel immediately

Do not attempt to view CSAM content; handle only hashes and metadata.

---

## Escalation Contacts

- Primary: On-call engineer
- Safety escalation: Engineering Lead + legal counsel
- OpenAI issues: OpenAI support (platform.openai.com/support)
- PhotoDNA / Microsoft CSAM API: Microsoft support
