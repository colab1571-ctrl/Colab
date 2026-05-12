# Secrets Rotation Runbook — Colab Platform

**Version**: 1.0  
**Date**: 2026-05-11  
**Owner**: Engineering Lead + On-call rotation  
**Location of secrets**: AWS Secrets Manager (all environments)

---

## 1. Rotation Cadence

| Secret | AWS Secret Name | Interval | Rotation method |
|--------|----------------|----------|----------------|
| RDS master password (staging) | `colab/staging/rds/master` | 90 days | Secrets Manager auto-rotation Lambda |
| RDS master password (production) | `colab/prod/rds/master` | 90 days | Secrets Manager auto-rotation Lambda |
| ElastiCache Redis auth token (staging) | `colab/staging/redis/auth` | 90 days | Manual + rolling pod restart |
| ElastiCache Redis auth token (prod) | `colab/prod/redis/auth` | 90 days | Manual + rolling pod restart |
| JWT signing private key (KMS-wrapped) | `colab/prod/jwt/private-key` | 180 days | Blue/green overlap (see §3) |
| OpenAI API key | `colab/prod/openai/api-key` | 90 days | Manual; revoke old after 24h overlap |
| Replicate API key | `colab/prod/replicate/api-key` | 90 days | Manual; revoke old after 24h overlap |
| Persona API key | `colab/prod/persona/api-key` | 90 days | Manual |
| Stripe restricted key | `colab/prod/stripe/restricted-key` | 90 days | Manual; test in staging first |
| RevenueCat API key | `colab/prod/revenuecat/api-key` | 90 days | Manual |
| Recall.ai API key | `colab/prod/recallai/api-key` | 90 days | Manual |
| RabbitMQ master password | `colab/prod/mq/admin-password` | 90 days | Manual + Amazon MQ restart |
| AWS break-glass access key | `colab/prod/aws/break-glass` | 30 days | Manual; prefer IRSA for all automation |
| Apple APNs `.p8` key | `colab/prod/apns/p8-key` | Annual (Apple limit) | Coordinated with push test |
| FCM service account JSON | `colab/prod/fcm/service-account` | As needed | Google Console rotation |
| RevenueCat webhook HMAC secret | `colab/prod/revenuecat/webhook-hmac` | 90 days | Manual + billing-svc restart |
| Stripe webhook signing secret | `colab/prod/stripe/webhook-secret` | 90 days | Manual + billing-svc restart |
| Persona webhook HMAC secret | `colab/prod/persona/webhook-hmac` | 90 days | Manual |

---

## 2. Standard Rotation Procedure

Applies to all vendor API keys and database passwords unless overridden in §3.

```
PRE-CONDITIONS:
  - You are primary on-call or have explicit authorization from engineering lead.
  - Inform the team in #engineering Slack: "Starting rotation for [secret name]."
  - No deployment in progress.

STEPS:

1. GENERATE new credential at the provider console.
   - OpenAI: platform.openai.com → API Keys → Create new secret key
   - Stripe: dashboard.stripe.com → Developers → Restricted keys
   - RevenueCat: app.revenuecat.com → API Keys
   - Persona: withpersona.com → Settings → API Keys
   - Replicate: replicate.com → Account → API tokens

2. ADD new value as a new version in Secrets Manager.
   aws secretsmanager put-secret-value \
     --secret-id "colab/prod/<service>/api-key" \
     --secret-string "<new_key>" \
     --version-stages AWSPENDING

3. VALIDATE new credential with a targeted test.
   - API keys: call provider health endpoint with new key.
   - RDS: connect via psql with new password on a single pod.

4. DEPLOY canary pod with new version.
   kubectl set env deployment/<service> \
     AWS_SECRET_VERSION_STAGE=AWSPENDING
   # Wait for pod to reach Running state.
   kubectl rollout status deployment/<service>

5. SMOKE TEST for 15 minutes.
   - Watch Sentry for auth errors.
   - Watch CloudWatch for 5xx spikes on the service.

6. PROMOTE new version to AWSCURRENT.
   aws secretsmanager update-secret-version-stage \
     --secret-id "colab/prod/<service>/api-key" \
     --version-stage AWSCURRENT \
     --move-to-version-id <new_version_id> \
     --remove-from-version-id <old_version_id>

7. ROLLING RESTART all pods to pick up AWSCURRENT.
   kubectl rollout restart deployment/<service>

8. OBSERVE for 24 hours.
   - Watch error rate dashboards.
   - No action if clean.

9. REVOKE old credential at provider console.
   - Do NOT revoke before 24h observation window.

10. SET old Secrets Manager version TTL to 7 days.
    aws secretsmanager update-secret-version-stage \
      --secret-id "colab/prod/<service>/api-key" \
      --version-stage AWSPREVIOUS \
      --move-to-version-id <old_version_id>

11. LOG rotation.
    Update rotation log (Notion page: "Secrets Rotation Log"):
      - Date, secret name, performer, old version ID, new version ID, observation period outcome.
```

---

## 3. JWT Signing Key Rotation (Blue/Green)

JWT keys require special handling because outstanding tokens are signed with the old key.

```
JWT KEY ROTATION PROCEDURE:

1. Generate new RSA-4096 private key (stored KMS-wrapped in Secrets Manager).
   aws secretsmanager put-secret-value \
     --secret-id "colab/prod/jwt/private-key" \
     --secret-string "<new_pem>" \
     --version-stages AWSPENDING

2. Publish NEW public key to JWKS endpoint alongside existing key.
   - auth-svc supports multiple active JWKS keys simultaneously.
   - Deploy auth-svc with `JWT_KEY_VERSION=both` to serve both keys.

3. Wait 6 hours (all existing tokens expire within 6h per JWT_ACCESS_EXPIRY=6h).

4. Promote new key to AWSCURRENT.
   - Deploy auth-svc with `JWT_KEY_VERSION=new` (only new key signs new tokens).
   - Keep old public key in JWKS for 24h to validate any lingering long-lived tokens.

5. After 24h: remove old public key from JWKS endpoint.
   - Deploy auth-svc with `JWT_KEY_VERSION=new_only`.

6. Revoke old private key version in Secrets Manager (7-day TTL).

7. Log rotation per §2 step 11.
```

---

## 4. RDS Password Rotation (Auto-rotation Lambda)

Secrets Manager Rotation Lambda is configured by Terraform (`terraform/modules/secrets`). Manual trigger:

```bash
aws secretsmanager rotate-secret \
  --secret-id "colab/prod/rds/master" \
  --rotation-lambda-arn "arn:aws:lambda:us-east-1:<account>:function:colab-prod-rds-rotate"
```

Lambda follows the `setSecret → testSecret → finishSecret` lifecycle. Monitor Lambda logs in CloudWatch for errors.

---

## 5. Emergency Rotation Procedure

**Trigger**: Suspected credential compromise (detection via Sentry auth anomaly, vendor breach notice, accidental commit to public repo, or staff departure).

```
EMERGENCY ROTATION — Execute within 30 minutes of suspected compromise.

T+0  Page on-call P1 via PagerDuty.
     Open incident channel: #incident-<date>-secrets in Slack.
     Incident commander: Engineering Lead.

T+5  Identify compromised credential(s).
     Check: GitHub commit history, Slack logs, vendor breach notices.

T+10 Generate and add new credential version to Secrets Manager (step 2 above).
     Skip 24h observation window — immediate promotion.

T+15 Promote new version to AWSCURRENT.
     Rolling restart all affected services simultaneously.

T+20 REVOKE old credential at provider immediately.
     Do not wait 24h when compromise is confirmed or suspected.

T+25 Verify services healthy with new credential.
     Check Sentry, CloudWatch, status page.

T+30 All services operational — declare "contained."

T+72h Postmortem published.
      Root cause, blast radius assessment, action items.
      Notify affected users if PII was potentially accessed (legal review required).
```

---

## 6. Quarterly Rotation Drill

Run quarterly (Jan, Apr, Jul, Oct) on staging environment:

1. Select 3 random secrets from the cadence table.
2. Execute full standard rotation procedure (§2) on staging.
3. Document in rotation log.
4. Verify that no hardcoded secrets remain in codebase:
   ```bash
   git secrets --scan-history
   trufflehog git --since-commit HEAD~100 file://$(pwd)
   ```
5. Run Trivy secrets scan on all Docker images in staging ECR.
6. Sign off drill completion in Notion rotation log.
