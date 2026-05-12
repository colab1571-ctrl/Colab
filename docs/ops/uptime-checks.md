# Uptime Checks Configuration — Colab Platform

**Version**: 1.0  
**Date**: 2026-05-11  
**Tool**: Pingdom (primary) + AWS Route 53 Health Checks (fallback / secondary)

---

## 1. Pingdom Uptime Check Configuration

### Core endpoints

| Check name | URL | Method | Interval | Alert threshold | Tags |
|------------|-----|--------|----------|----------------|------|
| API Gateway Health | `https://api.[brandname].com/health` | GET | 1 min | 2 consecutive failures | production, critical |
| Auth Service | `https://api.[brandname].com/auth/health` | GET | 1 min | 2 consecutive failures | production, critical |
| Discovery Feed | `https://api.[brandname].com/discovery/health` | GET | 1 min | 2 consecutive failures | production |
| Billing Service | `https://api.[brandname].com/billing/health` | GET | 2 min | 2 consecutive failures | production, revenue |
| AI Orchestrator | `https://api.[brandname].com/ai/health` | GET | 2 min | 3 consecutive failures | production |
| Media CDN | `https://cdn.[brandname].com/health.json` | GET | 2 min | 3 consecutive failures | production, cdn |
| Chat Health (REST) | `https://api.[brandname].com/chat/health` | GET | 1 min | 2 consecutive failures | production, critical |
| Moderation Service | `https://api.[brandname].com/moderation/health` | GET | 5 min | 3 consecutive failures | production |
| Marketing Site | `https://[brandname].com` | GET | 5 min | 3 consecutive failures | production, marketing |
| Status Page itself | `https://status.[brandname].com` | GET | 5 min | 3 consecutive failures | production |

### WebSocket uptime check (custom)

Pingdom does not natively support WebSocket health checks. Use a dedicated Lambda pinger:

```
AWS CloudWatch Event (every 2 min)
  → Lambda function: colab-prod-ws-health-pinger
    → Opens WS connection to wss://api.[brandname].com/chat/ws/health
    → Sends {"type": "ping"} frame
    → Expects {"type": "pong"} within 5 seconds
    → On failure: CloudWatch alarm → PagerDuty → Statuspage.io
```

Terraform resource: `terraform/modules/monitoring/ws-pinger.tf` (add in infra iteration post-launch).

---

## 2. Alert Thresholds and Routing

| Severity | Threshold | Alert target |
|----------|-----------|-------------|
| P1 | Confirmed outage (3+ consecutive failures on critical endpoint) | Pingdom → PagerDuty P1 → #incidents-p1 Slack |
| P2 | Degraded performance (P95 response time > 2× normal for 5+ minutes) | Pingdom → PagerDuty P2 → #incidents Slack |
| P3 | Single check failure (resolved on retry) | Pingdom → email to on-call only |
| P4 | Non-critical endpoint slow | Pingdom → email to engineering team |

---

## 3. Response Time SLOs (Pingdom targets)

| Endpoint | P95 target | Alert on P95 > |
|----------|-----------|---------------|
| `GET /health` (API Gateway) | ≤ 100ms | 500ms |
| `GET /auth/health` | ≤ 100ms | 500ms |
| `GET /discovery/health` | ≤ 200ms | 1,000ms |
| `GET /chat/health` | ≤ 100ms | 500ms |
| `GET /billing/health` | ≤ 200ms | 1,000ms |
| `GET /ai/health` | ≤ 500ms | 2,000ms |
| CDN (`cdn.[brandname].com`) | ≤ 50ms | 500ms |
| Marketing site | ≤ 500ms | 2,000ms |

---

## 4. AWS Route 53 Health Checks (Secondary/Failover)

Configure as failover backup to Pingdom. Used for DNS-level failover routing.

| Health check | Resource | Threshold |
|-------------|----------|-----------|
| `colab-prod-gateway-hc` | API Gateway ALB DNS | 2/3 checks in 30s |
| `colab-prod-cdn-hc` | CloudFront distribution | 2/3 checks in 30s |

Route 53 failover routing policy:
- Primary record: Production EKS ALB
- Secondary record: Static maintenance page on S3/CloudFront

---

## 5. Pingdom Integration with PagerDuty

In Pingdom Dashboard → Integrations → PagerDuty:

1. Connect Pingdom to PagerDuty using PagerDuty API key
2. Map each Pingdom alert to corresponding PagerDuty service:

| Pingdom check | PagerDuty service |
|--------------|------------------|
| API Gateway Health | Colab API Gateway |
| Auth Service | Colab API Gateway |
| Chat Health | Colab Chat Service |
| Billing Service | Colab Billing Service |
| AI Orchestrator | Colab AI Orchestrator |
| Media CDN | Colab Infrastructure |
| Marketing Site | Colab Infrastructure (P3 only) |

---

## 6. Pingdom Integration with Statuspage.io

In Pingdom Dashboard → Integrations → Statuspage.io:

1. Connect via Statuspage.io API key
2. Map Pingdom checks to Statuspage components:

| Pingdom check | Statuspage component |
|--------------|---------------------|
| API Gateway Health | API & Authentication |
| Auth Service | API & Authentication |
| Discovery Feed | Discovery Feed |
| Chat Health | Messaging & Chat |
| Billing Service | Billing & Subscriptions |
| AI Orchestrator | AI Assistant |
| Media CDN | Media Delivery (CDN) |

**Auto-update policy**: 2 consecutive failures → component status set to "Degraded Performance". Manual override by on-call for full "Major Outage" status.

---

## 7. Grafana Cloud Dashboard (Internal)

Import the following dashboards from Grafana Cloud k6 + CloudWatch integration:

| Dashboard | Purpose |
|-----------|---------|
| `Colab Production Overview` | Real-time P95 latencies per service, error rates, pod counts |
| `Colab Chat Real-time` | WebSocket connections, message throughput, disconnect rate |
| `Colab Billing Pipeline` | Webhook ingestion rate, queue depth, credit wallet mutations |
| `Colab AI Orchestrator` | Celery queue depth, job completion rate, credit deductions |
| `Colab EKS Cluster` | Node CPU/memory, HPA status, pod restarts |

Dashboard links pinned in #engineering Slack channel.
