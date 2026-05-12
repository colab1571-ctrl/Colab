# Penetration Test Scope — Colab Platform

**Version**: 1.0  
**Date**: 2026-05-11  
**Status**: DRAFT — pending vendor selection (T-016)  
**Owner**: Engineering Lead

---

## 1. Engagement Overview

| Item | Detail |
|------|--------|
| Test type | Black-box (unauthenticated) + Grey-box (authenticated test accounts provided) |
| Environment | Staging only — no production testing |
| Duration | Minimum 2-week test window |
| Deliverables | Written report: executive summary, findings (CVSS scored), PoC steps, remediation recommendations |
| Retest | All HIGH/CRITICAL findings retested after remediation sprint |
| NDA | Mutual NDA signed before engagement |
| Rules of engagement | Vendor must not test production; must not use exploits against third-party services; must not retain any user data |

---

## 2. In-Scope Targets

### 2.1 API Endpoints (REST + WebSocket)

| Target | URL | Notes |
|--------|-----|-------|
| API Gateway | `https://api.staging.colab.test` | All routes |
| WebSocket endpoint | `wss://api.staging.colab.test/chat/ws/{room_id}` | chat-svc |
| WebSocket endpoint | `wss://api.staging.colab.test/collab/ws/{collab_id}` | collab-svc (whiteboard) |
| Webhook: RevenueCat | `POST /billing/webhooks/revenuecat` | HMAC tested |
| Webhook: Stripe | `POST /billing/webhooks/stripe` | Stripe-Signature tested |
| Webhook: Persona | `POST /identity/webhooks/persona` | HMAC tested |
| Webhook: Replicate | `POST /ai/webhooks/replicate` | HMAC tested |
| Webhook: Recall.ai | `POST /meeting/webhooks/recallai` | HMAC tested |

### 2.2 Service-Specific Focus Areas

| Service | Focus |
|---------|-------|
| auth-svc | Authentication bypass, JWT attacks, OAuth flow manipulation (PKCE, state, nonce), token fixation, refresh token theft, brute-force OTP, phone number enumeration |
| gateway | Rate limit bypass, CORS misconfiguration, path traversal to internal services, JWT `alg:none` / `alg:HS256 downgrade` attack |
| chat-svc (WebSocket) | Unauthorized room access, message injection as another user, presence spoofing, mass disconnect attack |
| media-svc | Malicious file upload (polyglot files, archive bombs, SSRF via image processing), MIME bypass, pre-signed URL abuse |
| billing-svc | HMAC bypass on webhook endpoints, entitlement manipulation, credit wallet fraud, idempotency key collision |
| admin-svc | Privilege escalation, IDOR on moderation actions, admin route exposure from internet |
| ai-orchestrator-svc | Prompt injection, credit quota bypass, job result IDOR, Replicate webhook forgery |
| moderation-svc | Moderator privilege escalation, self-moderation bypass |

### 2.3 Mobile Application

| Platform | Build type | Focus |
|----------|-----------|-------|
| iOS (TestFlight) | Release build | OWASP MASVS L1: data storage, network security, cryptography, authentication, platform interaction, code quality |
| Android (APK) | Release APK | OWASP MASVS L1: same as iOS; plus: exported activities, implicit intents, WebView configuration |

**Mobile test methods**:
- Binary analysis (Frida, jadx, objection)
- Traffic interception (mitmproxy with certificate bypass attempt)
- Runtime manipulation (Frida hooks on auth and payment flows)
- SSL pinning bypass attempt

### 2.4 AWS Infrastructure (Limited Scope)

| Target | Scope |
|--------|-------|
| S3 bucket policies | Verify no public-read buckets; no bucket enumeration |
| ECR image access | Verify no unauthenticated pull |
| Secrets Manager | Verify no IAM policies granting cross-account or public access |
| VPC security groups | Verify only gateway exposed to internet; all other services VPC-internal only |
| CloudFront distribution | Verify signed URL enforcement; no origin bypass |
| EKS cluster endpoint | Verify not public; RBAC configured |

---

## 3. Out-of-Scope (Exclusions)

The following are **explicitly out of scope**:

| Excluded target | Reason |
|----------------|--------|
| Production environment (`api.colab.test`) | No production testing; staging only |
| Stripe infrastructure | Third-party; tested at integration point only |
| RevenueCat infrastructure | Third-party |
| Persona infrastructure | Third-party |
| OpenAI / Replicate APIs | Third-party |
| Recall.ai infrastructure | Third-party |
| Apple App Store / Google Play Store | Third-party |
| Physical infrastructure | Not applicable (cloud-only) |
| Social engineering / phishing | Not in scope for technical pen-test |
| Denial of service attacks at network layer | k6 load test covers DoS; packet-flood not authorized |
| Other Colab team members' personal devices | Not in scope |

---

## 4. Test Accounts Provided

Engineering will provision the following test accounts for grey-box testing:

| Role | Count | Notes |
|------|-------|-------|
| Free tier user | 5 | Fully onboarded; 0 credits |
| Premium user | 5 | Active `premium` entitlement |
| Premium Pro user | 5 | Active `premium_pro` entitlement; 500 credits |
| Moderator | 2 | `role=moderator` JWT; no admin access |
| Admin | 1 | `role=admin`; for admin-svc testing only |
| Blocked user | 2 | Account blocked by another test user |

All accounts use the `@colab-test.invalid` email domain. No real users' data is accessible via test accounts.

---

## 5. Severity Classification

Vendor should use CVSS 3.1 scoring. Colab maps CVSS to internal severity as follows:

| CVSS score | Internal severity | Remediation SLA |
|------------|------------------|----------------|
| 9.0–10.0 | CRITICAL | Fix within 48h; launch blocked |
| 7.0–8.9 | HIGH | Fix within 7 days; launch blocked |
| 4.0–6.9 | MEDIUM | Fix within 30 days; launch not blocked |
| 0.1–3.9 | LOW | Fix at next sprint; informational |

**Launch gate**: Zero open CRITICAL or HIGH findings required before public launch.

---

## 6. Timeline

| Milestone | Target date |
|-----------|------------|
| RFP sent to 3 vendors | T-016 week 1 |
| Vendor selected + SOW signed | T-016 week 2 |
| Pre-engagement call + test account provisioning | T-016 week 3 |
| Active test window opens | T-016 week 4 |
| Active test window closes | T-016 week 6 |
| Findings report delivered | T-016 week 7 |
| Remediation sprint | 2 weeks |
| Retest of HIGH/CRITICAL | T-017 |

**Fallback**: If vendor procurement is delayed past T-016 week 3, initiate internal red-team exercise using OWASP Testing Guide. Commit to external retest within 4 weeks post-launch.

---

## 7. Reporting Requirements

The final report must include:

1. Executive summary (1 page; non-technical; suitable for board/investor sharing)
2. Findings table (finding ID, title, CVSS score, affected component, description, PoC steps, remediation recommendation)
3. Positive findings (things done well — useful for compliance evidence)
4. Methodology section
5. Re-test attestation section (filled by vendor after remediation sprint)

**Report format**: PDF + Excel findings tracker  
**Delivery**: Encrypted delivery to engineering lead email; do not email raw findings to distribution list
