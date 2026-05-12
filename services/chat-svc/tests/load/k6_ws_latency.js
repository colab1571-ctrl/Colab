/**
 * k6 load test — WS latency at 1k concurrent rooms (T-69 / AC-34).
 *
 * Target: P95 e2e message round-trip < 500ms at 2000 concurrent connections.
 *
 * Run:
 *   k6 run --vus 2000 --duration 60s services/chat-svc/tests/load/k6_ws_latency.js
 *
 * Environment variables:
 *   K6_WS_URL   — WebSocket base URL (default: ws://localhost:8000)
 *   K6_TOKEN    — JWT bearer token for auth
 *   K6_ROOM_ID  — Target room UUID (or 'random' for VU-specific rooms)
 */

import { check, sleep } from "k6";
import ws from "k6/ws";
import { Rate, Trend } from "k6/metrics";

// ---------------------------------------------------------------------------
// Custom metrics
// ---------------------------------------------------------------------------

const msgRoundTripLatency = new Trend("msg_round_trip_ms", true);
const messagesSent = new Rate("messages_sent");
const messagesReceived = new Rate("messages_received");
const reconnectCount = new Rate("reconnect_count");

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const WS_BASE = __ENV.K6_WS_URL || "ws://localhost:8000";
const TOKEN = __ENV.K6_TOKEN || "dev-test-token";
const ROOM_ID = __ENV.K6_ROOM_ID || "00000000-0000-0000-0000-000000000001";

export const options = {
  vus: 2000,
  duration: "60s",
  thresholds: {
    // AC-34: P95 < 500ms
    msg_round_trip_ms: ["p(95)<500"],
    // Median target < 200ms
    "msg_round_trip_ms{quantile:0.5}": ["p(50)<200"],
    messages_sent: ["rate>0.95"],
    messages_received: ["rate>0.95"],
  },
};

// ---------------------------------------------------------------------------
// VU logic
// ---------------------------------------------------------------------------

export default function () {
  const vuId = __VU;
  // Each VU pair (1+2, 3+4, ...) shares a room for realistic cross-pod fanout
  const roomId = ROOM_ID !== "random"
    ? ROOM_ID
    : `00000000-0000-0000-0000-${String(Math.floor(vuId / 2)).padStart(12, "0")}`;

  const profileId = `00000000-0000-0000-0000-${String(vuId).padStart(12, "0")}`;
  const wsUrl = `${WS_BASE}/chat/${roomId}?token=${TOKEN}&profile_id=${profileId}`;

  let msgSendTime = 0;
  let nonce = `nonce-${vuId}-${Date.now()}`;

  const res = ws.connect(wsUrl, {}, function (socket) {
    socket.on("open", () => {
      // Send a text message after short warmup
      sleep(0.1);

      nonce = `nonce-${vuId}-${Date.now()}`;
      msgSendTime = Date.now();

      socket.send(
        JSON.stringify({
          type: "send",
          payload: {
            body: `k6 load test message from VU ${vuId}`,
            client_nonce: nonce,
          },
          request_id: nonce,
          ts: new Date().toISOString(),
        })
      );
      messagesSent.add(true);
    });

    socket.on("message", (rawData) => {
      const frame = JSON.parse(rawData);

      if (frame.type === "message_ack" && frame.payload.client_nonce === nonce) {
        const latency = Date.now() - msgSendTime;
        msgRoundTripLatency.add(latency);
        messagesReceived.add(true);

        check(latency, {
          "round-trip < 500ms": (l) => l < 500,
          "round-trip < 200ms (median target)": (l) => l < 200,
        });

        socket.close();
      }

      if (frame.type === "message") {
        // Received from other participant — record latency if we can
        messagesReceived.add(true);
      }

      if (frame.type === "connection_expiry_warning") {
        reconnectCount.add(true);
        // Simulate clean reconnect
        socket.close();
      }
    });

    socket.on("error", (e) => {
      messagesSent.add(false);
    });

    // Timeout if no ack in 2s
    socket.setTimeout(() => {
      if (msgSendTime > 0 && Date.now() - msgSendTime > 2000) {
        messagesReceived.add(false);
        socket.close();
      }
    }, 2000);
  });

  check(res, { "WS connection established": (r) => r && r.status === 101 });
  sleep(1);
}
