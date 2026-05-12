# Runbook — billing-svc

**Version**: 1.0 | **Date**: 2026-05-11 | **Owner**: Engineering Lead

---

## SLOs

| Metric | Target | Alert threshold |
|--------|--------|----------------|
| Webhook intake latency (P95) | ≤ 100ms | >500ms → P2 |
| Webhook processing success rate | ≥ 99.9% | <99% → P2 |
| RabbitMQ queue depth | ≤ 5,000 msgs | >10,000 → P2 |
| Credit wallet deduction accuracy | 100% (zero double-charges) | Any duplicate → P1 |
| Celery worker lag | ≤ 60s | >300s → P2 |

---

## Dashboards

- Grafana: `Colab Billing Pipeline` → webhook ingestion rate, queue depth, credit mutations
- CloudWatch: `colab-prod-billing-svc` log group + Amazon MQ metrics
- Sentry: `billing-svc` project → payment processing errors

---

## Common Alerts and Recovery

### Alert: `billing-webhook-queue-depth` (>10k messages)

**Likely cause**: Celery workers down or overwhelmed during end-of-month renewal storm.

**Recovery**:
```bash
# 1. Check Celery worker pods
kubectl get pods -n colab-production -l app=billing-worker

# 2. Check worker logs for errors
kubectl logs -l app=billing-worker -n colab-production --since=5m

# 3. Scale up workers manually if HPA hasn't kicked in
kubectl scale deployment billing-worker --replicas=20 -n colab-production

# 4. Monitor queue drain
# Amazon MQ Console → broker → queue depth graph

# 5. Check for poison-pill messages (messages that always fail)
# RabbitMQ management UI → billing-events queue → messages tab
```

### Alert: `billing-credit-double-charge` (duplicate credit award detected)

**Severity**: P1 — financial integrity issue.

**Recovery**:
1. Page on-call immediately.
2. Identify affected users via `webhook_event_log` table (duplicate idempotency keys with multiple debit records).
3. Issue credit refund via admin-svc refund endpoint (manual step with IC approval).
4. Identify root cause: idempotency check failure in worker code.
5. Deploy fix before restoring normal operation.
6. Postmortem required.

```sql
-- Identify potential duplicate credits (run on prod RDS — read replica)
SELECT idempotency_key, count(*) as count
FROM webhook_event_log
WHERE processed_at > NOW() - INTERVAL '1 hour'
GROUP BY idempotency_key
HAVING count(*) > 1;
```

### Alert: `billing-stripe-hmac-rejection` (>1% tampered webhook rejection rate)

**Note**: Some rejection is expected (attackers probing). Alert only on sustained rate >5% of total webhooks.

**Recovery**:
1. Check if Stripe has rotated its webhook signing secret (check Stripe dashboard).
2. If yes: update `colab/prod/stripe/webhook-secret` in Secrets Manager and restart billing-svc.
3. If no: investigate potential attack (IP source in logs); consider WAF rule.

---

## Escalation Contacts

- Primary: On-call engineer
- Financial escalation: Engineering Lead + CEO (P1 double-charge)
- Stripe issues: Stripe support dashboard (support.stripe.com)
- RevenueCat issues: RevenueCat support (app.revenuecat.com/support)
