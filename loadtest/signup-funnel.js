/**
 * k6 Load Test — Scenario A: Signup Funnel
 *
 * Simulates new user registration: email OTP, profile setup, portfolio upload,
 * and inbound Persona identity-webhook callback.
 *
 * Target: 500 VUs steady-state → 750 VU spike
 * Success criterion:
 *   - ≥99% of registration + OTP flows complete without error
 *   - Zero 5xx on auth-svc or profile-svc during steady state
 *   - Throughput ≥ 400 successful signups/min at peak
 *
 * Run:
 *   k6 run --env BASE_URL=https://api.staging.colab.test signup-funnel.js
 *   # Distributed: k6 cloud signup-funnel.js
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Counter, Trend } from 'k6/metrics';
import { randomString } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const BASE_URL = __ENV.BASE_URL || 'https://api.staging.colab.test';
const WEBHOOK_URL = `${BASE_URL}/identity/webhooks/persona`;

// ---------------------------------------------------------------------------
// Custom metrics
// ---------------------------------------------------------------------------
const registrationErrors = new Rate('signup_registration_errors');
const otpErrors = new Rate('signup_otp_errors');
const profileSetupErrors = new Rate('signup_profile_setup_errors');
const uploadErrors = new Rate('signup_upload_errors');
const successfulSignups = new Counter('signup_successful_total');
const e2eLatency = new Trend('signup_e2e_duration_ms', true);

// ---------------------------------------------------------------------------
// Ramp profile
// ---------------------------------------------------------------------------
export const options = {
  stages: [
    { duration: '5m',  target: 500 },   // Stage 1: warm-up 0→500 VUs
    { duration: '20m', target: 500 },   // Stage 2: steady state
    { duration: '5m',  target: 750 },   // Stage 3: spike ramp
    { duration: '10m', target: 750 },   // Stage 4: hold spike
    { duration: '5m',  target: 0 },     // Stage 5: cooldown
  ],
  thresholds: {
    // Latency budgets
    'http_req_duration{name:register}':       ['p(95)<200'],
    'http_req_duration{name:verify_otp}':     ['p(95)<200'],
    'http_req_duration{name:profile_setup}':  ['p(95)<200'],
    'http_req_duration{name:portfolio_upload}':['p(95)<500'],
    'http_req_duration{name:persona_webhook}':['p(95)<300'],
    // Error gates
    'signup_registration_errors':             ['rate<0.01'],
    'signup_otp_errors':                      ['rate<0.01'],
    'signup_profile_setup_errors':            ['rate<0.01'],
    'signup_upload_errors':                   ['rate<0.01'],
    // Global gates
    'http_req_failed':                        ['rate<0.01'],
  },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const VOCATIONS = ['visual', 'performing', 'literary', 'design', 'digital'];
const CITIES   = ['New York', 'Toronto', 'Sydney', 'Auckland', 'Mumbai'];

function randomEmail() {
  return `loadtest+${randomString(12)}@colab-test.invalid`;
}

function fakeOtpCode() {
  // Staging auth-svc accepts the magic OTP "000000" for load-test users
  return '000000';
}

function fakePortfolioPayload() {
  // 2 MB of zeros encoded as multipart — staging media-svc accepts synthetic payloads
  const body = new Uint8Array(2 * 1024 * 1024);
  return {
    file: http.file(body, 'portfolio.jpg', 'image/jpeg'),
    title: `Load test portfolio ${randomString(6)}`,
    media_type: 'image',
  };
}

function personaWebhookPayload(userId) {
  return JSON.stringify({
    data: {
      type: 'inquiry',
      id: `inq_loadtest_${randomString(16)}`,
      attributes: {
        status: 'completed',
        'reference-id': userId,
      },
    },
  });
}

// ---------------------------------------------------------------------------
// Main VU scenario
// ---------------------------------------------------------------------------
export default function () {
  const startTime = Date.now();
  const email = randomEmail();
  const password = `Load!${randomString(12)}`;
  let userId = null;
  let accessToken = null;

  group('1_register', () => {
    const res = http.post(
      `${BASE_URL}/auth/register`,
      JSON.stringify({ email, password }),
      {
        headers: { 'Content-Type': 'application/json' },
        tags: { name: 'register' },
      },
    );
    const ok = check(res, {
      'register 201': (r) => r.status === 201,
      'register returns user_id': (r) => {
        try { return !!JSON.parse(r.body).user_id; } catch { return false; }
      },
    });
    registrationErrors.add(!ok);
    if (ok) {
      userId = JSON.parse(res.body).user_id;
    }
  });

  if (!userId) return;
  sleep(1);

  group('2_verify_otp', () => {
    const res = http.post(
      `${BASE_URL}/auth/verify-email`,
      JSON.stringify({ email, code: fakeOtpCode() }),
      {
        headers: { 'Content-Type': 'application/json' },
        tags: { name: 'verify_otp' },
      },
    );
    const ok = check(res, {
      'otp 200': (r) => r.status === 200,
      'otp returns access_token': (r) => {
        try { return !!JSON.parse(r.body).access_token; } catch { return false; }
      },
    });
    otpErrors.add(!ok);
    if (ok) {
      accessToken = JSON.parse(res.body).access_token;
    }
  });

  if (!accessToken) return;
  sleep(0.5);

  const authHeaders = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${accessToken}`,
  };

  group('3_profile_setup', () => {
    const res = http.post(
      `${BASE_URL}/profile/setup`,
      JSON.stringify({
        display_name: `Creator ${randomString(6)}`,
        city: CITIES[Math.floor(Math.random() * CITIES.length)],
        country_code: 'US',
        vocations: [VOCATIONS[Math.floor(Math.random() * VOCATIONS.length)]],
        bio: 'Load test user — automated.',
        age_confirmed: true,
      }),
      { headers: authHeaders, tags: { name: 'profile_setup' } },
    );
    const ok = check(res, { 'profile setup 200': (r) => r.status === 200 });
    profileSetupErrors.add(!ok);
  });

  sleep(0.5);

  group('4_portfolio_upload', () => {
    const res = http.post(
      `${BASE_URL}/media/upload`,
      fakePortfolioPayload(),
      { headers: { Authorization: `Bearer ${accessToken}` }, tags: { name: 'portfolio_upload' } },
    );
    const ok = check(res, {
      'upload 201': (r) => r.status === 201,
    });
    uploadErrors.add(!ok);
  });

  sleep(0.5);

  group('5_persona_webhook', () => {
    // Simulate Persona callback arriving shortly after identity check initiated
    const hmacHeader = 'sha256=loadtest_valid_sig'; // staging webhook accepts this test sig
    const res = http.post(
      WEBHOOK_URL,
      personaWebhookPayload(userId),
      {
        headers: {
          'Content-Type': 'application/json',
          'Persona-Signature': hmacHeader,
        },
        tags: { name: 'persona_webhook' },
      },
    );
    const ok = check(res, { 'persona webhook 200': (r) => r.status === 200 });
    // Webhook endpoint should accept and queue, not fail
    if (ok) successfulSignups.add(1);
  });

  e2eLatency.add(Date.now() - startTime);
  sleep(2);
}
