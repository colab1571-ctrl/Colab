# Runbook — auth-svc

**Version**: 1.0 | **Date**: 2026-05-11 | **Owner**: Engineering Lead

---

## SLOs

| Metric | Target | Alert threshold |
|--------|--------|----------------|
| Availability | 99.9% | <99.5% triggers P1 |
| P95 login latency | ≤ 200ms | >500ms → P2 |
| P95 JWT verify latency (gateway) | ≤ 50ms | >200ms → P2 |
| OTP delivery success rate | ≥ 99% | <95% → P2 |
| Failed login rate (per IP) | < 10/min per IP | >10/min → auto block (rate limit) |

---

## Dashboards

- Grafana: `Colab Auth Service` dashboard → login rate, OTP success, JWT issuance rate
- CloudWatch: `colab-prod-auth-svc` log group → filter `level=error`
- Sentry: `auth-svc` project → unhandled exceptions

---

## Common Alerts and Recovery

### Alert: `auth-svc-5xx-spike` (>5% 5xx over 5 min)

**Likely causes**:
1. Database connection pool exhausted
2. JWT KMS key unreachable (KMS throttle)
3. Pod OOM kill

**Recovery**:
```bash
# 1. Check pod status
kubectl get pods -n colab-production -l app=auth-svc

# 2. Check logs
kubectl logs -l app=auth-svc -n colab-production --since=5m | grep -i "error\|exception"

# 3. Check DB connections
kubectl exec -it deployment/auth-svc -n colab-production -- \
  python -c "from app.db import engine; print(engine.pool.status())"

# 4. If OOM: check memory
kubectl top pods -n colab-production -l app=auth-svc

# 5. Rolling restart (if suspected memory leak)
kubectl rollout restart deployment/auth-svc -n colab-production
```

### Alert: `auth-svc-otp-failure-rate` (OTP delivery <95%)

**Likely cause**: Twilio service degradation or SES quota.

**Recovery**:
1. Check Twilio status at status.twilio.com
2. Check SES send statistics in AWS Console → SES → Account dashboard
3. If Twilio down: check if email OTP fallback is active (config: `OTP_CHANNEL=email`)
4. If SES in sandbox: verify SES production access is still active

### Alert: `auth-svc-jwt-kms-error`

**Likely cause**: KMS key policy changed or key scheduled for deletion.

**Recovery**:
```bash
# Verify KMS key status
aws kms describe-key --key-id ${JWT_KMS_KEY_ID} --region us-east-1 | jq '.KeyMetadata.KeyState'

# Should return "Enabled". If "PendingDeletion" — cancel deletion immediately:
aws kms cancel-key-deletion --key-id ${JWT_KMS_KEY_ID}
```

---

## Escalation Contacts

- Primary: On-call engineer (PagerDuty rotation)
- Escalation: Engineering Lead
- Twilio incidents: Twilio support dashboard
- AWS KMS issues: AWS Support (ticket via console)
