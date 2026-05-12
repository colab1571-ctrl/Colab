# OWASP MASVS Mapping — Colab React Native App

**Standard**: OWASP Mobile Application Security Verification Standard v2.1  
**Platform**: React Native (Expo SDK 53) — iOS + Android  
**Version**: 1.0  
**Date**: 2026-05-11

---

## MASVS-STORAGE — Secure Data Storage

| Control ID | Control Description | Status | Implementation |
|------------|--------------------|---------|-----------------------------|
| MASVS-STORAGE-1 | App does not store sensitive data in app internal storage unencrypted | REQUIRED | JWTs stored via `expo-secure-store` (Keychain on iOS, Keystore on Android); never in `AsyncStorage` |
| MASVS-STORAGE-2 | App does not store sensitive data in external storage | REQUIRED | No writes to external/public storage (no `WRITE_EXTERNAL_STORAGE` permission) |
| MASVS-STORAGE-3 | App prevents leakage of sensitive data in backups | REQUIRED | iOS: `NSFileProtectionCompleteUntilFirstUserAuthentication`; Android: `allowBackup=false` in `AndroidManifest.xml` |
| MASVS-STORAGE-4 | App does not store credentials in plaintext | REQUIRED | Passwords never stored client-side; only access/refresh tokens in `expo-secure-store` |
| MASVS-STORAGE-5 | No sensitive data in logs | REQUIRED | `react-native-logs` configured to strip tokens/PII patterns in production build; log level = ERROR only in release |

---

## MASVS-CRYPTO — Cryptography

| Control ID | Control Description | Status | Implementation |
|------------|--------------------|---------|-----------------------------|
| MASVS-CRYPTO-1 | App uses strong, up-to-date cryptography | REQUIRED | JWT signature verification uses RS256; no client-side crypto beyond OS-provided |
| MASVS-CRYPTO-2 | App implements cryptographic primitives correctly | REQUIRED | No custom crypto; use `expo-crypto` for hashing only (non-sensitive data) |
| MASVS-CRYPTO-3 | App does not contain hardcoded cryptographic keys | REQUIRED | No hardcoded keys in source; all keys from AWS Secrets Manager via API response (never bundled) |

---

## MASVS-AUTH — Authentication and Session Management

| Control ID | Control Description | Status | Implementation |
|------------|--------------------|---------|-----------------------------|
| MASVS-AUTH-1 | App uses secure and proven authentication | REQUIRED | JWT (RS256); Apple Sign In; Google Sign In; phone OTP — all via auth-svc |
| MASVS-AUTH-2 | App verifies user identity for sensitive transactions | REQUIRED | Biometric re-auth (`expo-local-authentication`) required for: payment initiation, account deletion, export PII |
| MASVS-AUTH-3 | App enforces token expiry | REQUIRED | Access token: 6h TTL; refresh token: 30d; expired tokens rejected server-side |
| MASVS-AUTH-4 | App properly handles session termination | REQUIRED | Logout: deletes local tokens from secure store + server-side refresh token invalidation |

---

## MASVS-NETWORK — Network Communication

| Control ID | Control Description | Status | Implementation |
|------------|--------------------|---------|-----------------------------|
| MASVS-NETWORK-1 | Data in transit encrypted (TLS 1.2+) | REQUIRED | All API calls via HTTPS; TLS 1.3 preferred; minimum TLS 1.2 enforced at API Gateway |
| MASVS-NETWORK-2 | TLS settings are verified | REQUIRED | Certificate validation enforced by iOS ATS and Android Network Security Config; no `cleartext` allowed |
| MASVS-NETWORK-3 | App verifies X.509 certificate of remote endpoint | REQUIRED | Certificate pinning via `react-native-ssl-pinning` for `api.colab.test`; pins leaf + intermediate |
| MASVS-NETWORK-4 | App does not expose sensitive functionality via 3rd-party SDKs | REQUIRED | No third-party analytics SDK with unfiltered event capture; PostHog SDK configured with PII filter |

**Certificate pinning note**: Pins must be updated each certificate renewal (every 90 days for Let's Encrypt or 1 year for commercial cert). Process: update pin in `eas.json` + forced app update via EAS Update.

---

## MASVS-PLATFORM — Platform Interaction

| Control ID | Control Description | Status | Implementation |
|------------|--------------------|---------|-----------------------------|
| MASVS-PLATFORM-1 | App uses the minimal permissions | REQUIRED | Permissions requested: Camera (portfolio uploads only), Microphone (voice notes), Location (discovery, coarse only), Push Notifications. No Contacts, no Bluetooth, no Calendar. |
| MASVS-PLATFORM-2 | App does not export sensitive functionality via IPC | REQUIRED | No exported Activities (Android); no custom URL schemes that bypass auth; deep link validation verifies `host` matches `colab.test` |
| MASVS-PLATFORM-3 | App does not use deprecated APIs | REQUIRED | Metro bundler configured to warn on deprecated React Native APIs; Expo SDK upgrade policy: upgrade within 1 major version |
| MASVS-PLATFORM-4 | App protects against UI overlay attacks | REQUIRED | AI mockup generation screen: `FLAG_SECURE` on Android (`expo-keep-awake` + `setKeepScreenOn` + native module); overlay warning on iOS per FR-C-8 |
| MASVS-PLATFORM-5 | App prevents JavaScript injection in WebViews | REQUIRED | No `WebView` components in app (full-native UI). If added in future: `javaScriptEnabled=false` by default, `originWhitelist` restricted |

---

## MASVS-CODE — Code Quality

| Control ID | Control Description | Status | Implementation |
|------------|--------------------|---------|-----------------------------|
| MASVS-CODE-1 | App is signed and provisioned correctly | REQUIRED | iOS: Distribution certificate + provisioning profile via EAS; Android: upload key (not debug key) |
| MASVS-CODE-2 | App is built in release mode | REQUIRED | `eas build --profile production`; `__DEV__` false; Metro minification enabled; Hermes bytecode |
| MASVS-CODE-3 | Debug symbols are not leaked | REQUIRED | Release builds: source maps uploaded to Sentry (not bundled in app); `EXPO_USE_MAPS=0` |
| MASVS-CODE-4 | App does not contain test code | REQUIRED | CI build step verifies no `*.test.ts` or `*.spec.ts` in bundle via `metro-bundle-analyzer` |
| MASVS-CODE-5 | No use of eval() | REQUIRED | ESLint rule `no-eval` + `security/detect-eval-with-expression` enforced; Hermes does not support `eval` |

---

## MASVS-RESILIENCE — Anti-Tampering and Anti-Reverse Engineering

| Control ID | Control Description | Status | Notes |
|------------|--------------------|---------|-----------------------------|
| MASVS-RESILIENCE-1 | App detects and responds to rooted/jailbroken devices | ADVISORY | `expo-device` `isRootedExperimentalAsync()` check; advisory warning shown (not blocked — per product decision) |
| MASVS-RESILIENCE-2 | App prevents debugging in release builds | REQUIRED | Hermes prevents source-level debug; `__DEV__` false disables Flipper/devtools |
| MASVS-RESILIENCE-3 | App detects and responds to tampering | ADVISORY | Expo integrity API (`expo-updates` checksums); auto-rollback on integrity failure |
| MASVS-RESILIENCE-4 | App implements anti-reverse engineering | INFORMATIONAL | Hermes bytecode obfuscation (Hermes is not easily reversible); not a security guarantee |

---

## Verification Evidence Required

Before security sign-off (T-033), evidence must be produced for REQUIRED controls:

| Evidence type | How collected |
|--------------|---------------|
| Keychain/Keystore usage confirmed | Code review: search for `SecureStore.setItemAsync` — no `AsyncStorage` for tokens |
| Certificate pin verified | mitmproxy intercept attempt during testing; should fail with pin error |
| FLAG_SECURE on Android verified | Screen recording attempt on AI mockup screen should show black frame |
| Permissions manifest reviewed | `app.json` permissions field + iOS `Info.plist` review |
| Release build settings confirmed | `eas build --profile production` output log shows Hermes + minification |
| No hardcoded secrets in bundle | `strings colab.app \| grep -E "(sk-|rc_prod|pk_live)"` should return empty |
