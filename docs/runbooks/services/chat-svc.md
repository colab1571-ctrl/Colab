# Runbook — chat-svc

**Version**: 1.0 | **Date**: 2026-05-11 | **Owner**: Engineering Lead

---

## SLOs

| Metric | Target | Alert threshold |
|--------|--------|----------------|
| WebSocket disconnect rate | < 0.5% | >2% → P1 |
| Message e2e latency (P95) | ≤ 500ms | >2,000ms → P2 |
| Message delivery success | ≥ 99.9% | <99% → P1 |
| WS connection establishment (P95) | ≤ 200ms | >1,000ms → P2 |
| chat-svc pod memory | Stable (no leak) | >2GB per pod → P2; OOM → P1 |
| Concurrent WebSocket connections | 10k+ sustained | Degradation below capacity → P1 |

---

## Dashboards

- Grafana: `Colab Chat Real-time` → WS connections, message throughput, disconnect rate, pod memory
- CloudWatch: `colab-prod-chat-svc` log group
- Sentry: `chat-svc` project → unhandled exceptions
- CloudWatch: API Gateway WebSocket connection count metric

---

## Common Alerts and Recovery

### Alert: `chat-ws-disconnect-rate` (>2% disconnect rate)

**Likely causes**:
1. Pod memory leak causing OOM kills
2. API Gateway WebSocket 2-hour hard limit triggered (expected; handled by client reconnect)
3. chat-svc pod crash loop
4. Redis pub/sub channel subscription limit

**Recovery**:
```bash
# 1. Check pod health and memory
kubectl top pods -n colab-production -l app=chat-svc
kubectl get pods -n colab-production -l app=chat-svc

# 2. Check for OOM kills
kubectl describe pods -n colab-production -l app=chat-svc | grep -i "OOMKilled"

# 3. Check Redis pub/sub stats
kubectl exec -it deployment/redis-proxy -n colab-production -- \
  redis-cli INFO pubsub

# 4. If memory leak: rolling restart (graceful WS drain)
kubectl rollout restart deployment/chat-svc -n colab-production
# chat-svc should handle SIGTERM with WS close frame to clients

# 5. Scale up if connection count exceeds capacity
kubectl scale deployment/chat-svc --replicas=20 -n colab-production

# 6. Check API Gateway WebSocket connection quota
aws apigatewayv2 get-stage --api-id ${WS_API_ID} --stage-name prod
```

### Alert: `chat-svc-message-delivery-failure` (<99% delivery)

**Likely cause**: RabbitMQ connectivity issue or chat-svc database write errors.

**Recovery**:
```bash
# 1. Check RabbitMQ connectivity from chat-svc
kubectl exec -it deployment/chat-svc -n colab-production -- \
  python -c "import pika; pika.BlockingConnection(pika.URLParameters('$RABBITMQ_URL'))"

# 2. Check Amazon MQ status in AWS Console

# 3. Check Postgres write lag
kubectl exec -it deployment/chat-svc -n colab-production -- \
  psql $DATABASE_URL -c "SELECT now() - pg_last_xact_replay_timestamp() AS replication_lag;"

# 4. If DB primary unreachable: check RDS failover status
aws rds describe-db-instances --db-instance-identifier colab-prod-db | \
  jq '.DBInstances[0].DBInstanceStatus'
```

### Alert: `chat-svc-pod-oom`

**Immediate action**: OOM kill means messages in-flight are lost. Declare P1 if disconnect rate spikes.

```bash
# Emergency: increase memory limit temporarily
kubectl set resources deployment/chat-svc \
  --limits=memory=4Gi \
  -n colab-production

# Investigate leak: heap dump (if OOMed pod still running)
kubectl exec -it ${POD_NAME} -n colab-production -- \
  python -c "import tracemalloc; tracemalloc.start(); # ... run heap snapshot"
```

---

## WebSocket Architecture Note

API Gateway has a 2-hour hard limit on WebSocket connections. The mobile client is expected to reconnect automatically on disconnect. If clients are not reconnecting:
1. Check mobile client reconnect logic in `apps/mobile/src/hooks/useWebSocket.ts`
2. Issue a forced app update via EAS Update if client-side fix is needed

---

## Escalation Contacts

- Primary: On-call engineer
- AWS API Gateway issues: AWS Support (ticket)
- Amazon MQ issues: AWS Support
