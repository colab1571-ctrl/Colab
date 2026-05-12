# Runbook — ai-orchestrator-svc

**Version**: 1.0 | **Date**: 2026-05-11 | **Owner**: Engineering Lead

---

## SLOs

| Metric | Target | Alert threshold |
|--------|--------|----------------|
| Command intake latency (P95) | ≤ 300ms | >1,000ms → P2 |
| `/brainstorm` e2e latency (P95) | ≤ 8,000ms | >15,000ms → P3 |
| Celery queue depth | ≤ 500 jobs | >2,000 → P2 |
| Credit deduction accuracy | 100% (no double-deduct) | Any duplicate → P1 |
| Replicate job success rate | ≥ 99% | <95% → P2 |
| OpenAI API error rate | < 2% | >10% → P2 |

---

## Dashboards

- Grafana: `Colab AI Orchestrator` → queue depth, job completion rate, credit deduction rate
- CloudWatch: `colab-prod-ai-orchestrator-svc` log group
- Sentry: `ai-orchestrator-svc` project
- Celery Flower (if deployed): `ai-worker.colab-prod.internal:5555`

---

## Common Alerts and Recovery

### Alert: `ai-celery-queue-depth` (>2,000 jobs)

**Likely cause**: OpenAI API throttle, Replicate API slowdown, or insufficient Celery workers.

**Recovery**:
```bash
# 1. Check worker pod count and health
kubectl get pods -n colab-production -l app=ai-worker

# 2. Check for OpenAI rate limit errors in logs
kubectl logs -l app=ai-worker -n colab-production --since=5m | grep "openai\|rate_limit\|429"

# 3. Scale up workers (HPA should trigger; do manually if lag)
kubectl scale deployment ai-worker --replicas=30 -n colab-production

# 4. If OpenAI throttled: check current tier limits in OpenAI platform
#    Upgrade tier or implement request queuing with exponential backoff

# 5. Check Replicate job status (via API)
curl -s -H "Authorization: Token ${REPLICATE_API_KEY}" \
  https://api.replicate.com/v1/models | jq '.results[0].latest_version.status'
```

### Alert: `ai-credit-double-deduction`

**Severity**: P1 — financial integrity.

**Recovery**:
1. Identify affected users:
   ```sql
   -- Find duplicate credit deductions (same job_id)
   SELECT job_id, user_id, count(*) as deductions
   FROM ai_credit_ledger
   WHERE created_at > NOW() - INTERVAL '1 hour'
   GROUP BY job_id, user_id
   HAVING count(*) > 1;
   ```
2. Issue credit refund via admin-svc credit adjustment endpoint.
3. Root cause: likely idempotency key failure in Celery task.
4. Deploy fix; postmortem required.

### Alert: `ai-replicate-webhook-failure` (webhook delivery failing)

**Likely cause**: Replicate cannot reach our webhook endpoint; our webhook endpoint returning non-200.

**Recovery**:
```bash
# 1. Check ai-orchestrator-svc is up and accepting webhook POST
curl -sf https://api.[brandname].com/ai/webhooks/replicate -X POST \
  -H "Content-Type: application/json" \
  -d '{"id": "health_check", "status": "test"}' | jq .

# 2. Check Replicate delivery logs in Replicate dashboard
# platform.replicate.com → Your predictions → failed deliveries

# 3. Manually re-trigger webhook delivery for failed jobs
#    (Replicate supports manual retry in dashboard)

# 4. For long-lived jobs: poll job status via REST as fallback
kubectl exec -it deployment/ai-orchestrator-svc -n colab-production -- \
  python -m app.tasks.poll_stale_jobs --hours=1
```

### Alert: `ai-mockup-consent-violation` (mockup generated without consent record)

**Severity**: P1 — product safety + legal risk.

**Immediate action**:
1. Disable `/mockup-image` command endpoint:
   ```bash
   kubectl set env deployment/ai-orchestrator-svc MOCKUP_ENABLED=false -n colab-production
   ```
2. Identify images generated without consent in `ai_interaction` table.
3. Delete generated images from S3.
4. Notify affected users.
5. Investigate consent check bypass in code.
6. Do not re-enable until root cause fixed and tested.

---

## Credit Cost Reference

| Command | Credits consumed | Provider |
|---------|-----------------|---------|
| `/brainstorm` | 5 credits | OpenAI GPT-4 |
| `/summarize-chat` | 3 credits | OpenAI GPT-4 |
| `/mockup-image` | 20 credits | Replicate SDXL |

---

## Escalation Contacts

- Primary: On-call engineer
- OpenAI issues: platform.openai.com/support
- Replicate issues: replicate.com/support
- Credit fraud: Engineering Lead + CEO
