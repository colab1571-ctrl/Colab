# Google Play Console Submission Packet — Android

**Version**: 1.0  
**Date**: 2026-05-11  
**Owner**: Marketing + Engineering  
**Reference**: Phase 019 plan §6

---

## 1. App Metadata

| Field | Value |
|-------|-------|
| Package name | `com.colab.[brandname]` (replace before submission) |
| App name | `[BRAND_NAME]` — Creative Collab |
| Short description (80 chars) | `Find your creative partner. AI-matched collaborations for artists.` |
| Developer name | Colab Inc. (replace with legal entity name) |
| Category | Social |
| Tags | Networking, Creativity, Collaboration |
| Contact email | `support@[brandname].com` |
| Privacy policy URL | `https://[brandname].com/privacy` |

---

## 2. App Icon

| Asset | Specification |
|-------|--------------|
| High-res icon | 512 × 512 px, PNG, 32-bit color + alpha; no transparency in visible area |
| Adaptive icon foreground | 108 × 108 dp (432 × 432 px @ 4x), PNG with alpha |
| Adaptive icon background | Solid brand color or separate layer; safe zone 66 × 66 dp (264 × 264 px @ 4x) |
| Adaptive icon safe zone | Important content must be within center 66 dp circle; outside may be masked |

**Adaptive icon notes**:
- Foreground and background layers are separate files in the APK (`ic_launcher_foreground.png` + `ic_launcher_background.xml` or PNG)
- Expo handles adaptive icon via `app.json` `android.adaptiveIcon` configuration
- Icon must look good on any shape mask (circle, squircle, rounded square, teardrop)

---

## 3. Feature Graphic

| Attribute | Specification |
|-----------|--------------|
| Size | 1024 × 500 px, PNG or JPEG |
| Content | Brand visual: platform name + value prop tagline; no device frame required |
| Safe zone | Important content within center 924 × 400 px (50px margin each side; 25px top/bottom) |
| Text | Minimal; large readable font; must read at thumbnail size |
| Note | Displayed at top of Play Store listing; used in Google Play featured placement banners |

**Feature graphic content**:
- Background: brand gradient or solid color
- Text: `[BRAND_NAME]` large + `Find Your Creative Partner` subtitle
- Visual element: abstract creative/collaboration motif (instruments, design tools, etc.)
- Do NOT include device screenshots in feature graphic (Play policy)

---

## 4. Screenshots

| Device class | Min resolution | Quantity | Notes |
|-------------|---------------|----------|-------|
| Phone (portrait) | 1080 × 1920 px minimum; up to 2340 × 1080 px | 4–8 | Required |
| 7-inch tablet (portrait) | 1200 × 1920 px | 1–8 | Recommended; auto-scale from phone if skipped |
| 10-inch tablet (portrait) | 1600 × 2560 px | 1–8 | Recommended |
| Chromebook (landscape) | Varies | 1–8 | Optional |

### Screenshot content (mirror iOS set; adjust for Android UI)

| # | Screen | Caption overlay |
|---|--------|----------------|
| 1 | Discovery feed | "Find your perfect creative match" |
| 2 | Swipe card with match score | "Matched by creative DNA, not followers" |
| 3 | Vibe Check flow | "Low-pressure. High signal." |
| 4 | Collaboration workspace / chat | "Your workspace. Your collab." |
| 5 | AI command result in chat | "AI tools. Right in your chat." |
| 6 | Profile with Valid Profile Badge | "Every member is verified." |

**Android-specific adjustments**:
- Show Android navigation gestures (no home button on modern devices)
- Show Android system UI (status bar with correct time/battery)
- Use material design back navigation where relevant
- Dark mode + light mode variants

---

## 5. Full Description (4,000 chars)

Mirror the iOS description structure from `app-store-connect.md`, with Android-specific CTA:

```
[Copy iOS description body here]

Download from Google Play. Free to join. Premium unlocks unlimited matching
and AI credits. Pro unlocks AI image generation.

Compatible with Android 10 (API 29) and higher. Target SDK 35.
For creators 18+ in the US, Canada, Australia, New Zealand, and India.
```

---

## 6. Content Rating Questionnaire (IARC)

Navigate to Play Console → Content rating → Start questionnaire.

| Question | Answer |
|----------|--------|
| App category | Social networking |
| Violence | None |
| Sexual content | None |
| Profanity | None |
| Controlled substances | None |
| User-generated content | Yes — portfolio media, chat messages, AI-generated images |
| Social features | Yes — messaging between users |
| Location sharing | Yes — coarse location for discovery radius |
| Digital purchases | Yes — subscription IAP + credit packs |
| Personal information collection | Yes |
| User interaction (can communicate) | Yes |

**Expected rating**: PEGI 12 / ESRB Teen (or potentially PEGI 16 / ESRB Mature 17+ due to UGC + social messaging). Verify rating output after completing questionnaire. App's 18+ enforcement is in ToS and onboarding — document this for reviewer.

---

## 7. Data Safety Form

Navigate to Play Console → Data safety.

### Data collection declarations

| Data type | Collected | Shared with 3rd parties | Can request deletion | Purpose |
|-----------|-----------|------------------------|---------------------|---------|
| Email address | Yes | No | Yes | Account management |
| Name (display name) | Yes | No | Yes | Profile display |
| User IDs | Yes | No | Yes | Authentication |
| Profile info (bio, vocation) | Yes | No | Yes | App functionality |
| Photos | Yes | No | Yes | Portfolio uploads |
| Videos | Yes | No | Yes | Portfolio uploads |
| Audio | Yes | No | Yes | Portfolio + voice notes |
| Location (approximate) | Yes | No | Yes | Discovery matching |
| In-app messages | Yes | No | Yes | Chat (persisted per audit log) |
| App interactions | Yes | No | Yes | Analytics (PostHog) |
| Crash logs | Yes | No | No | Sentry error tracking |
| Financial info | Yes | No | Yes | Subscription + IAP |
| Phone number | Yes | No | Yes | Optional OTP auth |

### Security practices

| Practice | Declared |
|----------|---------|
| Data encrypted in transit | Yes (TLS 1.2+) |
| Data encrypted at rest | Yes (RDS SSE + S3 SSE-S3) |
| Users can request data deletion | Yes (DSR endpoint; full GDPR-grade) |
| Independent security review | Yes (external pen-test — T-016) |

### Families policy

Not applicable. Do not enable Google Play Families.

---

## 8. Pre-Launch Report (Robo Test)

Before submitting for review, use Play Console's pre-launch report:

1. Upload APK/AAB to Internal testing track.
2. Play Console automatically runs Robo test on Firebase Test Lab.
3. Review crash report in pre-launch report tab.
4. Fix all crashes before submitting to production review.

Expected robo test coverage: ~60–70% of screens (robo cannot complete authenticated flows without credentials).

---

## 9. Track Configuration

### Internal testing track
- Up to 100 Google accounts (by email list or domain)
- No review required; instant publish
- Use for QA + smoke testing + Robo pre-launch report
- Feedback via in-app feedback form + email alias

### Closed testing (Alpha) track — closed beta
- Named email list of 100 invited creators (CSV upload)
- Requires Play review (1–3 days for new apps)
- Opt-in URL sent via invitation email
- Feedback: in-app shake-to-report + Discord private server + weekly Typeform
- Monitor crash rate via Play Console Android Vitals

---

## 10. First Submission Checklist

- [ ] Google Play developer account enrolled ($25 fee + KYC)
- [ ] App created in Play Console
- [ ] Bundle ID / package name registered
- [ ] Store listing complete (name, short desc, full desc, icon, feature graphic, screenshots)
- [ ] Content rating questionnaire complete
- [ ] Data safety form complete
- [ ] Privacy policy URL live at `https://[brandname].com/privacy`
- [ ] At least one AAB uploaded (via `scripts/store/upload-play-internal.sh`)
- [ ] Pre-launch Robo test complete and crash-free
- [ ] Target SDK = 35 (current Android requirement)
- [ ] In-App purchase products created in Play Console and Active
- [ ] RevenueCat connected to Play Console via Service Account JSON
- [ ] Internal testing track validated on physical device
- [ ] Submitted to Alpha track for review

---

## 11. Known Play Policy Touchpoints

| Policy | Mitigation |
|--------|-----------|
| [User-generated content](https://support.google.com/googleplay/android-developer/answer/9893335) | Moderation pipeline + reporting feature visible in UI |
| [Real-money gambling](https://support.google.com/googleplay/android-developer/answer/9899032) | No gambling features; credit packs are AI tool access, not gambling |
| [Data safety accuracy](https://support.google.com/googleplay/android-developer/answer/10787469) | All collected data types declared in form; annual re-audit |
| [Sensitive permissions](https://support.google.com/googleplay/android-developer/answer/9214102) | Location = coarse only; Camera + Microphone with clear in-context rationale |
| [Minimum target API](https://support.google.com/googleplay/android-developer/answer/11926878) | targetSdkVersion = 35; verified in `app.json` |
