# ADR 007-1 — WebSocket Connection Multiplicity at Launch

**Status**: Accepted  
**Date**: 2026-05-11  
**Phase**: P6 (007 Chat + Workspace Base)  

## Context

A mobile client may hold multiple WebSocket connections simultaneously:
- `chat-svc` — real-time messages, presence, typing (this phase)
- `collab-svc/whiteboard` — tldraw Y.js CRDT ops (Phase 010)
- `notification-svc` — in-app banners (Phase 014)

The RECONCILIATION.md identified this as a mild conflict requiring a decision.

## Decision

**Accept 3 separate WS connections at launch.** Each service owns distinct,
stateful real-time data that maps cleanly to a separate channel:

| Service | Channel | State |
|---|---|---|
| chat-svc | `wss://.../chat/{room_id}` | Messages, presence, typing |
| collab-svc | `wss://.../ws/rooms/{room_id}` | Y.js doc ops |
| notification-svc | `wss://.../notifications` | Push banners |

## Consequences

**Positive**:
- Clean isolation — each connection can be independently scaled and load-tested
- Failure in one WS stream (e.g., notification-svc pod restart) does not
  affect chat delivery
- API Gateway per-connection pricing at launch DAU is acceptable ($0.80/M conn-min)

**Negative / Risks**:
- 3× battery drain from keepalive pings on mobile
- 3× API Gateway quota usage
- More complex client-side reconnect logic

## Mitigation

- Heartbeat interval tuned to 8 min (chat) and 30s (notifications) to minimize
  battery impact
- Phase 019 (prelaunch hardening) includes a task to evaluate WS gateway
  consolidation behind a single connection with multiplexed channels
- If P18 load test shows battery regression > 15%, expedite consolidation

## Alternatives Considered

1. **Single WS gateway with multiplexing**: Cleaner client; requires a new
   gateway service to proxy frames. Deferred to v1.1.
2. **SSE for notifications**: One-directional; eliminates the third WS.
   Viable; deferred to v1.1 if battery proves problematic.
