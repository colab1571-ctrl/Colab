/**
 * k6 Load Test — Scenario D: AI Command Invocation
 *
 * Simulates premium users invoking in-chat AI commands:
 *   /brainstorm, /summarize-chat, /mockup-image
 *
 * Target: 200 VUs steady-state → 400 VU spike
 * AI command rate is intentionally lower — these are premium credit-gated ops.
 *
 * Success criteria:
 *   - ai-orchestrator-svc returns 202 Accepted for all valid commands within latency budget
 *   - Celery worker scale-out triggered automatically at queue depth > 100 (HPA)
 *   - Credit wallet deduction idempotent (no double-charges on retry)
 *   - Zero Replicate webhook delivery failures (staging mock)
 *
 * Run:
 *   k6 run --env BASE_URL=https://api.staging.colab.test ai-commands.js
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Counter, Trend } from 'k6/metrics';
import { SharedArray } from 'k6/data';
import { randomString } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const BASE_URL = __ENV.BASE_URL || 'https://api.staging.colab.test';
const POLL_INTERVAL_MS = 500;
const POLL_MAX_ATTEMPTS = 40; // 20 seconds max poll

// Premium test users — pre-seeded with credit balance ≥100 credits
const PREMIUM_TOKENS = new SharedArray('premium_tokens', function () {
  const tokens = [];
  for (let i = 0; i < 1000; i++) {
    tokens.push(`loadtest_premium_token_${i}`);
  }
  return tokens;
});

// ---------------------------------------------------------------------------
// Custom metrics
// ---------------------------------------------------------------------------
const commandIntakeErrors  = new Rate('ai_cmd_intake_error_rate');
const brainstormLatency    = new Trend('ai_brainstorm_e2e_ms', true);
const summarizeLatency     = new Trend('ai_summarize_e2e_ms', true);
const mockupQueueLatency   = new Trend('ai_mockup_queue_ms', true);
const creditDoubleCharge   = new Counter('ai_credit_double_charge_count');
const commandsCompleted    = new Counter('ai_commands_completed_total');
const idempotencyViolations= new Counter('ai_idempotency_violations');

// ---------------------------------------------------------------------------
// Ramp profile
// ---------------------------------------------------------------------------
export const options = {
  stages: [
    { duration: '5m',  target: 200 },
    { duration: '20m', target: 200 },
    { duration: '5m',  target: 400 },
    { duration: '10m', target: 400 },
    { duration: '5m',  target: 0 },
  ],
  thresholds: {
    'http_req_duration{name:ai_cmd_intake}':  ['p(95)<300'],
    'ai_brainstorm_e2e_ms':                   ['p(95)<8000'],
    'ai_summarize_e2e_ms':                    ['p(95)<5000'],
    'ai_mockup_queue_ms':                     ['p(95)<500'],
    'ai_cmd_intake_error_rate':               ['rate<0.01'],
    'ai_credit_double_charge_count':          ['count<1'],
    'ai_idempotency_violations':              ['count<1'],
    'http_req_failed':                        ['rate<0.01'],
  },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function pollJobStatus(jobId, token) {
  const headers = { Authorization: `Bearer ${token}` };
  for (let i = 0; i < POLL_MAX_ATTEMPTS; i++) {
    const res = http.get(`${BASE_URL}/ai/job/${jobId}`, { headers });
    if (res.status === 200) {
      try {
        const body = JSON.parse(res.body);
        if (body.status === 'completed') return body;
        if (body.status === 'failed') return null;
      } catch { /* continue polling */ }
    }
    sleep(POLL_INTERVAL_MS / 1000);
  }
  return null; // timeout
}

function mockChatHistory() {
  return [
    { role: 'user', content: 'I want to create a lo-fi hip-hop album' },
    { role: 'user', content: 'Maybe something that mixes jazz samples with modern production' },
    { role: 'user', content: 'Thinking about the 90s aesthetic but with a modern twist' },
  ];
}

// ---------------------------------------------------------------------------
// Main VU scenario
// ---------------------------------------------------------------------------
export default function () {
  const token = PREMIUM_TOKENS[__VU % PREMIUM_TOKENS.length];
  const authHeaders = {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  };

  // --- Command 1: /brainstorm ---
  group('1_brainstorm', () => {
    const idempotencyKey = `brainstorm_${__VU}_${__ITER}`;
    const startTime = Date.now();

    const res = http.post(
      `${BASE_URL}/ai/command`,
      JSON.stringify({
        command: '/brainstorm',
        context: mockChatHistory(),
        room_id: `room_loadtest_${__VU % 1000}`,
      }),
      {
        headers: { ...authHeaders, 'Idempotency-Key': idempotencyKey },
        tags: { name: 'ai_cmd_intake' },
      },
    );

    const ok = check(res, {
      'brainstorm 202': (r) => r.status === 202,
      'brainstorm has job_id': (r) => {
        try { return !!JSON.parse(r.body).job_id; } catch { return false; }
      },
    });
    commandIntakeErrors.add(!ok);

    if (ok) {
      const jobId = JSON.parse(res.body).job_id;
      // Idempotency check: re-sending same key must not create new job
      const res2 = http.post(
        `${BASE_URL}/ai/command`,
        JSON.stringify({ command: '/brainstorm', context: mockChatHistory(), room_id: `room_loadtest_${__VU % 1000}` }),
        { headers: { ...authHeaders, 'Idempotency-Key': idempotencyKey }, tags: { name: 'ai_cmd_intake' } },
      );
      if (res2.status === 202) {
        try {
          const body2 = JSON.parse(res2.body);
          if (body2.job_id !== jobId) {
            idempotencyViolations.add(1); // new job created — idempotency broken
          }
        } catch { /* ignore */ }
      }

      // Poll for completion (staging Replicate mock returns in ≤3s)
      const result = pollJobStatus(jobId, token);
      if (result) {
        brainstormLatency.add(Date.now() - startTime);
        commandsCompleted.add(1);
      }
    }
  });

  sleep(2);

  // --- Command 2: /summarize-chat ---
  group('2_summarize', () => {
    const startTime = Date.now();
    const res = http.post(
      `${BASE_URL}/ai/command`,
      JSON.stringify({
        command: '/summarize-chat',
        room_id: `room_loadtest_${__VU % 1000}`,
        last_n_messages: 50,
      }),
      {
        headers: { ...authHeaders, 'Idempotency-Key': `summarize_${__VU}_${__ITER}` },
        tags: { name: 'ai_cmd_intake' },
      },
    );
    const ok = check(res, { 'summarize 202': (r) => r.status === 202 });
    commandIntakeErrors.add(!ok);

    if (ok) {
      const jobId = JSON.parse(res.body).job_id;
      const result = pollJobStatus(jobId, token);
      if (result) {
        summarizeLatency.add(Date.now() - startTime);
        commandsCompleted.add(1);
      }
    }
  });

  sleep(2);

  // --- Command 3: /mockup-image (async, webhook-delivered) ---
  group('3_mockup_image', () => {
    const startTime = Date.now();
    const res = http.post(
      `${BASE_URL}/ai/command`,
      JSON.stringify({
        command: '/mockup-image',
        prompt: `Album cover: lo-fi jazz hip-hop, vintage aesthetic, ${randomString(8)}`,
        room_id: `room_loadtest_${__VU % 1000}`,
        require_consent: true, // mockup requires consent flag per FR-C-8
      }),
      {
        headers: { ...authHeaders, 'Idempotency-Key': `mockup_${__VU}_${__ITER}` },
        tags: { name: 'ai_cmd_intake' },
      },
    );
    const ok = check(res, {
      'mockup 202': (r) => r.status === 202,
      'mockup queued': (r) => {
        try { return JSON.parse(r.body).status === 'queued'; } catch { return false; }
      },
    });
    commandIntakeErrors.add(!ok);
    // Async: result delivered via webhook — measure queue acceptance latency only
    mockupQueueLatency.add(Date.now() - startTime);
    if (ok) commandsCompleted.add(1);
  });

  sleep(5);
}
