/**
 * k6 Load Test — Scenario C: Chat Fanout
 *
 * Simulates 10,000 concurrent active chat rooms with message send/receive fanout.
 * Steady-state target: 100,000 messages/minute.
 *
 * Architecture note: Each VU holds one side of a chat room WebSocket.
 * Rooms are pre-seeded; VU pairs are coordinated via room IDs in the SharedArray.
 *
 * Target: 10,000 VUs steady-state → 15,000 VU spike
 *
 * Success criteria:
 *   - WebSocket disconnect rate < 0.5%
 *   - Message delivery rate ≥ 99.9% (no dropped messages)
 *   - chat-svc pod memory stable (no leak) over 30-min run
 *   - Postgres chat message write throughput ≥ 100k inserts/min
 *
 * Run:
 *   k6 run --env BASE_URL=https://api.staging.colab.test chat-fanout.js
 *   # For WS support ensure k6 ≥ 0.42 with experimental websockets
 */

import { WebSocket } from 'k6/experimental/websockets';
import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Counter, Trend } from 'k6/metrics';
import { SharedArray } from 'k6/data';

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const BASE_URL = __ENV.BASE_URL || 'https://api.staging.colab.test';
const WS_URL   = BASE_URL.replace('https://', 'wss://').replace('http://', 'ws://');

// 10k pre-seeded room IDs. In real execution, the seed script writes this file.
const ROOMS = new SharedArray('rooms', function () {
  const rooms = [];
  for (let i = 0; i < 10000; i++) {
    rooms.push(`room_loadtest_${String(i).padStart(6, '0')}`);
  }
  return rooms;
});

const TEST_TOKENS = new SharedArray('tokens', function () {
  const tokens = [];
  for (let i = 0; i < 20000; i++) {
    tokens.push(`loadtest_token_user_${i}`);
  }
  return tokens;
});

// ---------------------------------------------------------------------------
// Custom metrics
// ---------------------------------------------------------------------------
const wsDisconnectRate   = new Rate('chat_ws_disconnect_rate');
const msgDeliveredRate   = new Rate('chat_msg_delivered_rate');
const msgDroppedRate     = new Rate('chat_msg_dropped_rate');
const wsConnectLatency   = new Trend('chat_ws_connect_ms', true);
const msgRoundTripLatency= new Trend('chat_msg_rtt_ms', true);
const fileMsgLatency     = new Trend('chat_file_msg_ms', true);
const totalMsgSent       = new Counter('chat_messages_sent_total');

// ---------------------------------------------------------------------------
// Ramp profile
// ---------------------------------------------------------------------------
export const options = {
  stages: [
    { duration: '5m',  target: 10000 },
    { duration: '20m', target: 10000 },
    { duration: '5m',  target: 15000 },
    { duration: '10m', target: 15000 },
    { duration: '5m',  target: 0 },
  ],
  thresholds: {
    'chat_ws_connect_ms':      ['p(95)<200'],
    'chat_msg_rtt_ms':         ['p(95)<500'],
    'chat_file_msg_ms':        ['p(95)<2000'],
    'chat_ws_disconnect_rate': ['rate<0.005'],
    'chat_msg_dropped_rate':   ['rate<0.001'],
    'http_req_failed':         ['rate<0.01'],
  },
};

// ---------------------------------------------------------------------------
// Main VU scenario
// ---------------------------------------------------------------------------
export default function () {
  const vu       = __VU;
  const roomIdx  = vu % ROOMS.length;
  const roomId   = ROOMS[roomIdx];
  const token    = TEST_TOKENS[vu % TEST_TOKENS.length];
  const wsEndpoint = `${WS_URL}/chat/ws/${roomId}?token=${token}`;

  const connectStart = Date.now();
  let connected = false;
  let msgsSent  = 0;
  let msgsAcked = 0;
  let lastSendAt = 0;

  const ws = new WebSocket(wsEndpoint);

  ws.addEventListener('open', () => {
    connected = true;
    wsConnectLatency.add(Date.now() - connectStart);

    // Send text messages every 0.6 seconds for 30 minutes (session length)
    const msgInterval = setInterval(() => {
      if (msgsSent >= 3000) { // cap per VU to avoid runaway
        clearInterval(msgInterval);
        ws.close();
        return;
      }
      const msgId = `${vu}_${msgsSent}`;
      lastSendAt = Date.now();
      ws.send(JSON.stringify({
        type: 'message',
        id: msgId,
        room_id: roomId,
        content: `Load test message ${msgId}`,
        content_type: 'text',
      }));
      msgsSent++;
      totalMsgSent.add(1);
    }, 600);

    // Send one file message per session after 5s warm-up
    const fileTimer = setTimeout(() => {
      ws.send(JSON.stringify({
        type: 'message',
        id: `${vu}_file`,
        room_id: roomId,
        content: 'data:image/jpeg;base64,/9j/loadtest_synthetic_500kb',
        content_type: 'image',
        file_name: 'loadtest.jpg',
        file_size_bytes: 512000,
      }));
    }, 5000);

    // Presence ping every 30 seconds
    const pingInterval = setInterval(() => {
      ws.send(JSON.stringify({ type: 'presence_ping', room_id: roomId }));
    }, 30000);

    ws.addEventListener('close', () => {
      wsDisconnectRate.add(!connected || msgsSent > 0 && msgsAcked < msgsSent * 0.99);
      clearInterval(msgInterval);
      clearInterval(pingInterval);
      clearTimeout(fileTimer);
    });
  });

  ws.addEventListener('message', (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === 'message_ack' || data.type === 'message') {
        const rtt = Date.now() - lastSendAt;
        msgRoundTripLatency.add(rtt);
        msgsAcked++;
        msgDeliveredRate.add(true);
      } else if (data.type === 'file_ack') {
        fileMsgLatency.add(Date.now() - lastSendAt);
      } else if (data.type === 'error') {
        msgDroppedRate.add(true);
      }
    } catch { /* ignore malformed frames */ }
  });

  ws.addEventListener('error', () => {
    wsDisconnectRate.add(true);
    msgDroppedRate.add(true);
  });

  // Hold VU connection for 30 minutes (matches scenario steady-state)
  sleep(1800);
}
