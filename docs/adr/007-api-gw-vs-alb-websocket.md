# ADR 007-2 — API Gateway WebSocket vs ALB Native WebSocket

**Status**: Accepted (with decision gate at P18)  
**Date**: 2026-05-11  
**Phase**: P6 (007 Chat + Workspace Base)  

## Context

chat-svc needs a WebSocket gateway. Two options:

**Option A — AWS API Gateway WebSocket API** (chosen)  
- Managed service; no load-balancer config
- Lambda authorizer for JWT validation before upgrade
- 2-hour hard connection limit; 10-minute idle timeout
- $0.80/M connection-minutes + $1.00/M messages

**Option B — ALB + ECS/EKS native WebSocket**  
- No 2-hour limit; no idle timeout beyond TCP keepalive
- Sticky sessions via ALB target group stickiness
- Requires more infra config; no built-in Lambda authorizer

## Decision

**Ship with API Gateway WebSocket API (Option A) for launch.**

Rationale:
1. Faster to provision (Terraform module already implemented)
2. Built-in Lambda authorizer eliminates JWT parsing in FastAPI hot path
3. 2-hour limit acceptable with `connection_expiry_warning` + client-side
   proactive reconnect (T-16 implemented)
4. At 100k DAU with avg 20-min sessions: ~33M connection-minutes/month ≈ $26/month

## Decision Gate at P18

If P18 load test demonstrates:
- Reconnect storm causing > 5% message loss during 2-hour reconnect windows, OR
- API Gateway connection quota bottlenecking during spike traffic

→ Execute the ALB swap (1-sprint change per plan §2.1, all logic stays in FastAPI handlers).

## Implementation Notes

- `connection_expiry_warning` sent at t=6900s (5 min before expiry)
- Client sends `reconnect` with `since_msg_id` on new connection
- Server responds with `replay` (up to 200 messages from Postgres)
- Zero message loss: Postgres is source of truth; Redis is best-effort
