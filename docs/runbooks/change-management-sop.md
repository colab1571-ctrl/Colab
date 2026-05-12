# Change Management SOP — Colab Platform

**Version**: 1.0  
**Date**: 2026-05-11  
**Owner**: Engineering Lead

---

## 1. Change Categories

| Category | Definition | Approval | Deploy window |
|----------|-----------|---------|--------------|
| **Standard** | Routine code deploy via CI/CD; covered by automated tests | None — CI/CD gates are the approval | Anytime (weekdays preferred) |
| **Normal** | DB migration, config change, dependency major version upgrade, new environment variable | Engineering Lead async approval via GitHub PR review | Weekdays 10:00–16:00 local |
| **Emergency** | Hotfix for active P1/P2 incident | Incident Commander verbal approval | Anytime; postmortem required |
| **Major** | EKS cluster upgrade, RDS major version upgrade, new service deployment, architecture change | Engineering Lead sync approval + staging soak ≥48h | Weekdays 10:00–14:00 local |

---

## 2. Standard Change Checklist

Standard changes go through CI/CD without additional approvals. The pipeline is the gatekeeper.

**Required gates** (all must be green before deployment):
1. Unit tests pass (`make test`)
2. SAST clean: semgrep + bandit + eslint-security (no new HIGH/CRITICAL)
3. Trivy container scan: no new CRITICAL/HIGH vulnerabilities
4. Snyk: no new HIGH/CRITICAL findings
5. OpenAPI contract check: no breaking changes (`make openapi-check`)
6. Lint: `make lint` passes
7. Staging deploy successful (GitHub Actions deploy workflow)
8. Staging smoke tests pass (automated)
9. Engineering team peer review: minimum 1 approval on PR

**Deployment process** (automated via GitHub Actions `deploy.yml`):
1. Main branch merge triggers staging deploy automatically
2. Manual approval gate in GitHub Actions for production deploy
3. Canary: deploy to 5% of production pods
4. Monitor error rate for 15 minutes
5. Full rollout if error rate delta < 1%
6. Automatic rollback if error rate spikes >2%

**Rollback command**:
```bash
kubectl rollout undo deployment/{service-name} -n colab-production
```

---

## 3. Normal Change Checklist

For database migrations, config changes, and major dependency upgrades.

**Pre-change requirements**:
1. GitHub PR with detailed description of change and rollback plan
2. DB migration: migration script tested in staging; rollback script written and tested
3. Staging deploy + 4h soak period minimum
4. Engineering Lead PR approval (not just any engineer)
5. Change scheduled in advance: announced in #engineering Slack ≥24h before

**DB migration procedure**:
```bash
# On staging first:
kubectl exec -it deployment/auth-svc -n colab-staging -- \
  uv run alembic upgrade head

# Verify migration success:
kubectl logs -l app=auth-svc -n colab-staging | tail -20

# If rollback needed:
kubectl exec -it deployment/auth-svc -n colab-staging -- \
  uv run alembic downgrade -1

# On production (only after staging soak):
# Same commands with -n colab-production
```

**Rollback plan requirement**: Every Normal change PR must include a "Rollback" section in the PR description:
```markdown
## Rollback plan
1. `kubectl rollout undo deployment/auth-svc`
2. `alembic downgrade -1` if migration was applied
3. Revert environment variable in AWS Secrets Manager if config was changed
```

---

## 4. Emergency Change Checklist

For hotfixes during P1/P2 incidents.

**When to use**: Active incident (P1 or P2); fix needed immediately; normal change process would delay resolution.

**Approval process**:
1. Incident Commander gives verbal (Slack/call) approval to proceed
2. One additional engineer must review the diff before deploy (can be quick async review in incident Slack thread)
3. Change is deployed
4. PR is created retroactively with postmortem reference

**Emergency deploy procedure**:
```bash
# Fast path: deploy single service without waiting for full CI
# (Use only during active P1 — CI can be bypassed by IC decision)

# Build and push emergency image
docker build -t colab/auth-svc:emergency-fix-${SHA} services/auth-svc/
docker push ${ECR_REGISTRY}/auth-svc:emergency-fix-${SHA}

# Deploy with zero downtime
kubectl set image deployment/auth-svc \
  auth-svc=${ECR_REGISTRY}/auth-svc:emergency-fix-${SHA} \
  -n colab-production

kubectl rollout status deployment/auth-svc -n colab-production
```

**Postmortem**: Required for all Emergency changes. Include the emergency change in the postmortem timeline.

---

## 5. Major Change Checklist

For EKS cluster upgrades, RDS major version upgrades, new service launches.

**Pre-change requirements**:
1. RFC document (short form): problem, solution, alternatives considered, rollback plan
2. Staging environment fully tested: ≥48h soak at production-equivalent load
3. Engineering Lead sync approval (verbal + written in GitHub)
4. Schedule announced in #engineering + Statuspage.io scheduled maintenance
5. On-call engineer dedicated to change window (not their normal on-call shift)
6. Customer notification: Statuspage scheduled maintenance posted ≥48h in advance

**EKS cluster upgrade procedure** (example):

```bash
# Step 1: Upgrade control plane
aws eks update-cluster-version \
  --name colab-prod \
  --kubernetes-version 1.32 \
  --region us-east-1

# Monitor upgrade
aws eks describe-update \
  --name colab-prod \
  --update-id ${UPDATE_ID}

# Step 2: Upgrade managed node group (rolling)
aws eks update-nodegroup-version \
  --cluster-name colab-prod \
  --nodegroup-name colab-prod-nodes \
  --kubernetes-version 1.32

# Step 3: Upgrade add-ons (CoreDNS, kube-proxy, vpc-cni)
aws eks update-addon --cluster-name colab-prod --addon-name coredns --addon-version v1.11.x
aws eks update-addon --cluster-name colab-prod --addon-name kube-proxy --addon-version v1.32.x
aws eks update-addon --cluster-name colab-prod --addon-name vpc-cni --addon-version v1.18.x
```

**Rollback**: EKS downgrades are not supported by AWS. Rollback = deploy a replacement cluster from Terraform.

---

## 6. Freeze Windows

### Absolute freeze windows (no Normal or Major changes)

| Window | Duration | Reason |
|--------|----------|--------|
| 48h before public launch | 48h | Stability |
| 48h after public launch | 48h | Monitor launch traffic |
| Friday 17:00 – Monday 09:00 | Every weekend | Avoid weekend incidents |
| Major public holidays (US/CA/AU) | 24h | Reduced team availability |

**During freeze**: Only Emergency changes (P1/P2 hotfixes) are permitted.

### Pre-holiday freeze announcement

Post in #engineering by 14:00 on the last business day before freeze:
```
:snowflake: FREEZE WINDOW starting today 17:00 local.
No Normal or Major deploys until Monday 09:00.
Emergency (P1/P2) hotfixes only. IC approval required.
On-call this weekend: @[name]
```

---

## 7. Post-Deploy Verification

After every production deploy (Standard, Normal, or Major):

```bash
# 1. Verify pods are running
kubectl get pods -n colab-production -l app={service}

# 2. Check recent logs for errors
kubectl logs -l app={service} -n colab-production --since=5m | grep -i "error\|exception\|critical"

# 3. Hit health endpoint
curl -sf https://api.[brandname].com/{service}/health | jq .

# 4. Watch Sentry for new errors (5 min observation)
# Open Sentry → Releases → {new_version} → Issues

# 5. Check CloudWatch error rate dashboard (5 min)
# Open Grafana → Colab Production Overview → {service} error rate
```

If error rate delta > 1% after 5 minutes: initiate rollback immediately. Do not wait.
