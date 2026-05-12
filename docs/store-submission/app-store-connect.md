# App Store Connect Submission Packet — iOS

**Version**: 1.0  
**Date**: 2026-05-11  
**Owner**: Marketing + Engineering  
**Reference**: Phase 019 plan §5

---

## 1. App Metadata

| Field | Value |
|-------|-------|
| App name | `[BRAND_NAME]` — Creative Collab |
| Subtitle (30 chars max) | `Find Your Creative Partner` |
| Promotional text (170 chars) | `Join [BRAND_NAME] — the AI-powered platform where artists and creators build real projects together, not just followers.` |
| Bundle ID | `com.colab.[brandname]` (replace before submission) |
| SKU | `colab-ios-001` |
| Primary language | English (U.S.) |
| Category (primary) | Social Networking |
| Category (secondary) | Productivity |

---

## 2. Description Copy (Full — 4,000 char limit)

### Structure

**Opening hook** (lines 1–4):
```
Every creator knows the feeling: you have the vision, the skill, and the drive —
but no one to build it with. [BRAND_NAME] changes that.

We're the first platform built for serious creators who want real collaboration
partners, not follower counts or engagement farms.
```

**Core value props** (bulleted):
```
• AI-matched by creative compatibility — vocation, style, workflow, and goals,
  not vanity metrics
• Verified creators only — our Valid Profile Badge means every match is a real
  human with real work
• Real workspaces: shared files, whiteboards, AI tools, and video meetings —
  all in one place
• Vibe Check: send a lightweight collab invite before committing to a full project
• AI Assistant in chat: /brainstorm, /summarize-chat, /mockup-image — right
  where your conversation is happening
```

**Feature highlights**:
```
CREATIVE DISCOVERY
Swipe through profiles matched to your creative DNA. Save favorites, hide
profiles for 3 months if the timing's off, and get notified the moment a
compatible creator joins.

VIBE CHECK
Too intimidated to send a full pitch? Vibe Check is a lightweight "would you
collab?" signal. Low pressure. High signal.

AI COLLABORATION TOOLS
Premium members get access to in-chat AI commands powered by GPT-4 and
Stable Diffusion. Generate mood boards, brainstorm track concepts, or summarize
a long conversation — without leaving the chat.

SAFETY FIRST
Every member is ID-verified via our identity partner. Robust moderation with
real moderators. Report anything, flag anything. We take safety seriously.
```

**Community promise**:
```
[BRAND_NAME] is anti-follower-farming. Your match score is based on creative
output and compatibility, not your subscriber count. Quit the numbers game.
Build something real.
```

**CTA**:
```
Sign up free. Premium unlocks unlimited matching, workspace storage, and AI
credits. Pro unlocks image generation and advanced AI tools.

For creators 18+. Available in the US, Canada, Australia, New Zealand, and India.
```

---

## 3. Screenshot Specifications

### Required device classes

| Device | Resolution (portrait) | Required | Quantity |
|--------|----------------------|----------|---------|
| iPhone 6.9" (iPhone 16 Pro Max) | 1320 × 2868 px | YES | 6 |
| iPhone 6.7" (iPhone 15 Plus / 16 Plus) | 1290 × 2796 px | Auto-scaled from 6.9" | — |
| iPad Pro 13" (M4) | 2064 × 2752 px | YES | 6 |
| iPad Pro 11" | 1668 × 2388 px | Auto-scaled from 13" | — |

### Screenshot content (same set for all device sizes — scale assets)

| # | Screen | Caption overlay |
|---|--------|----------------|
| 1 | Discovery feed grid/swipe view | "Find your perfect creative match" |
| 2 | Profile card with AI match score callout | "Matched by creative DNA, not followers" |
| 3 | Vibe Check send flow | "Low-pressure. High signal. Vibe Check." |
| 4 | Collaboration workspace / chat + file panel | "Your workspace. Your collab." |
| 5 | AI command `/brainstorm` result in chat | "AI tools. Right in your conversation." |
| 6 | Profile with Valid Profile Badge | "Every member is verified. Every match is real." |

**Production rules**:
- Use real in-app UI on a clean simulator with seed data (no hand-drawn mockups)
- No device frames in screenshots (Apple renders frames in App Store)
- Status bar: show time 9:41, 100% battery (Apple standard)
- Dark mode preferred for visual impact; also submit light mode variants
- Screenshot capture via Detox + `scripts/store/generate-screenshots.sh`

---

## 4. Keyword Strategy

**Keyword field** (100 chars, comma-separated):
```
creative,collaboration,artist,musician,designer,creator,networking,AI,match,collab,portfolio,gig
```

**Strategy notes**:
- Avoid brand names in keyword field (Apple policy: includes competitor names)
- Avoid words already in app name or subtitle (Apple ignores them)
- Target long-tail search intent: "find music collaborator", "artist networking app", "creative partner finder"
- Refresh keywords quarterly using App Store Connect Analytics + keyword research tools (Sensor Tower, AppFollow)
- Top 3 priority keywords by volume + relevance: `collaboration`, `artist`, `creative`

---

## 5. Age Rating

**Declared rating**: **17+**

Apple age rating questionnaire responses:

| Question | Answer |
|----------|--------|
| Cartoon or Fantasy Violence | None |
| Realistic Violence | None |
| Prolonged Graphic or Sadistic Realistic Violence | None |
| Profanity or Crude Humor | None |
| Mature/Suggestive Themes | Infrequent/Mild |
| Horror/Fear Themes | None |
| Medical/Treatment Information | None |
| Alcohol, Tobacco, or Drug Use | None |
| Simulated Gambling | None |
| Sexual Content or Nudity | None |
| Graphic Sexual Content or Nudity | None |
| Unrestricted Web Access | No |
| User-Generated Content | Yes |
| Gambling or Lotteries | No |

**Rationale**: UGC + social messaging gives 17+. The platform enforces 18+ at the application level (age-attestation on signup, FR-A-3, COMP-2) with ToS enforcement, which exceeds Apple's system. Note this in App Review notes.

---

## 6. Privacy Questionnaire Answers

| Data category | Collected? | Linked to identity? | Purpose |
|--------------|-----------|---------------------|---------|
| **Data Used to Track You** | **None** | — | No cross-app tracking; ATT deferred per ARC-33 |
| Contact info (email) | Yes | Yes | Account management, transactional email |
| Contact info (phone) | Yes | Yes | Optional phone OTP authentication |
| Identifiers (User ID) | Yes | Yes | Account management |
| Usage data (app interactions) | Yes | Yes | Analytics (PostHog, first-party only) |
| Diagnostics (crash logs) | Yes | Yes | Sentry error tracking |
| Location (coarse) | Yes | Yes | Discovery radius matching |
| Photos | Yes | Yes | Portfolio uploads |
| Videos | Yes | Yes | Portfolio uploads |
| Audio | Yes | Yes | Portfolio audio, voice notes |
| Financial info | Yes | Yes | Subscription via IAP (RevenueCat) |
| User content (messages) | Yes | Yes | Chat functionality (audit log requirement) |
| Health & fitness | No | — | — |
| Sensitive info | No | — | — |
| Contacts | No | — | — |
| Browsing history | No | — | — |

**Privacy policy URL**: `https://[brandname].com/privacy` (must be live before submission)

---

## 7. TestFlight Track Configuration

### Internal Testing Track
- Up to 100 internal testers (Apple accounts of engineering + QA)
- No Apple review required for each build
- Build expiry: 90 days
- Enable: crash reporting + automatic screenshot feedback
- Feedback routing: Sentry (crashes) + TestFlight feedback tab

### External Testing Track (Closed Beta)
- Up to 10,000 external testers (use for 100-creator beta)
- Requires Apple review of TestFlight build (typically 24–48h)
- Use private link (not public link) for invite-only beta
- Beta app description (reviewed by Apple — must be accurate):
  ```
  [BRAND_NAME] is an AI-powered creative networking and collaboration platform
  for artists, musicians, designers, and creators 18+. This TestFlight build
  is an invite-only closed beta. Features may be incomplete or change before
  public release.
  ```
- Feedback: TestFlight in-app feedback + weekly Typeform survey in welcome email

### First submission checklist

- [ ] Bundle ID created in Apple Developer portal
- [ ] App ID registered (`com.colab.[brandname]`)
- [ ] Provisioning profile: Distribution (App Store) created
- [ ] Push notification entitlement enabled
- [ ] Sign in with Apple entitlement enabled
- [ ] EAS build with `--profile production` successful
- [ ] IPA uploaded via `scripts/store/upload-testflight.sh`
- [ ] All metadata fields complete (name, subtitle, description, keywords)
- [ ] All screenshots uploaded for required device classes
- [ ] Privacy questionnaire complete
- [ ] Age rating questionnaire complete
- [ ] In-App Purchase products in "Submitted" status
- [ ] Privacy policy URL live
- [ ] App Review Information: test account credentials + notes provided

### Review notes for Apple

```
This app is a creative networking and collaboration platform for creators 18+.

Key notes for reviewers:
1. Age verification: Users must attest to being 18+ on signup (FR-A-3).
   The 17+ App Store rating reflects Apple's scale maximum.
2. AI-generated image ("mockup") feature: The AI mockup screen displays
   a full-screen warning before generation and shows a persistent overlay
   on the result image. Screenshots are blocked on this screen (FLAG_SECURE
   on Android; similar UX on iOS).
3. User-generated content: All content passes through an AI moderation
   pipeline + human moderators. Reporting and blocking features are present
   and visible in the UI.
4. In-app purchases: Premium ($X/month) and Pro ($X/month) subscriptions
   plus AI credit packs. All premium features require IAP; no external
   payment links in the app.
5. Test account: [provide test credentials here]
```
