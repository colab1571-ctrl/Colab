# Beta Feedback Channels

**Version**: 1.0  
**Date**: 2026-05-11

---

## 1. In-App Feedback (Sentry User Feedback + Shake-to-Report)

### Shake-to-Report

Available on both iOS and Android. Trigger: shake device (or long-press feedback button in Settings).

**Flow**:
1. User shakes device → feedback sheet slides up
2. User selects category: Bug / Feature Request / Crash / Other
3. User types description (free text, optional screenshot auto-attached)
4. Submit → Sentry user feedback event created
5. In-app confirmation: "Thanks! We'll review this within 24h."

**Integration**:
- Sentry SDK: `@sentry/react-native` with `Sentry.showReportDialog()` or custom shake detection
- Sentry feedback events appear in Sentry project under "User Feedback" tab
- Tagged with beta user ID + app version + device model

### "Send Feedback" in Settings

Settings → Help → Send Feedback → same Sentry sheet as above. Visible always (not just on shake).

---

## 2. Email: beta@[brand].com

**Routing**: Gmail or Fastmail alias → support-svc ticket queue via Zapier or SMTP hook.

- Tag: `beta` — separates beta tickets from production support
- Auto-reply template:
  ```
  Thanks for your feedback, [name]! We've received your message and will
  respond within 24 hours during the beta. If it's urgent, ping us in
  the #beta-bugs Discord channel.

  — The [BRAND_NAME] team
  ```
- SLA: Respond to all beta emails within 24h (business hours)
- Escalation: Crashes or data loss reported via email → treat as P2; page on-call

---

## 3. Discord Private Server (Invite-Only)

**Server name**: `[BRAND_NAME] Closed Beta`  
**Access**: Invite link sent only to NDA-signed beta participants

### Channels

| Channel | Purpose |
|---------|---------|
| `#welcome` | Rules, how to report bugs, beta guide link |
| `#beta-general` | General discussion about the platform |
| `#beta-bugs` | Bug reports (structured format encouraged) |
| `#beta-ideas` | Feature requests + suggestions |
| `#status-updates` | Founder posts: build updates, downtime notices |
| `#weekly-prompts` | Each week's focus area for testing |

### Bug report format (pinned in #beta-bugs)

```
**Summary**: One sentence describing the issue
**Steps to reproduce**: 
  1. ...
  2. ...
**Expected behavior**: What should have happened
**Actual behavior**: What actually happened
**Platform**: iOS / Android
**App version**: (find in Settings → About)
**Device**: iPhone 15 / Pixel 8 / etc.
**Screenshot**: (attach if helpful)
```

### Team engagement policy

- Founder or PM active in Discord daily (weekdays)
- React with ✅ on bug reports that are filed in Sentry
- React with 🔁 on issues being investigated
- React with ✨ on feature requests being considered
- No screenshots/videos to be shared in Discord (NDA reminder pinned in welcome)

---

## 4. Weekly Typeform Survey

Sent every Monday morning during the 4-week beta.

**Week 1 survey focus**: Onboarding experience
- Did you complete onboarding? (Yes/No/In progress)
- What was the most confusing part of onboarding? (Free text)
- Did the profile verification process feel smooth? (1–5 scale)
- Did you see any matches? Were they relevant? (1–5 + free text)

**Week 2 survey focus**: Core matching + Vibe Check
- Have you sent a Vibe Check? If not, why? (Multiple choice)
- How relevant were your discovery feed matches? (1–5 scale)
- Did you accept or receive any Vibe Checks? (Yes/No)
- What's missing from the discovery experience? (Free text)

**Week 3 survey focus**: Collaboration workspace
- Have you started a collaboration? (Yes/No)
- Rate the chat experience (1–5 scale)
- Did you use any AI commands? Which ones? (Multiple choice)
- Did you encounter any bugs or crashes? (Yes/No + describe)

**Week 4 survey focus**: Overall experience + NPS
- Net Promoter Score: "How likely would you recommend [BRAND_NAME] to a fellow creator?" (0–10)
- What is the single most valuable feature? (Free text)
- What is the single biggest problem? (Free text)
- Would you pay for Premium? If so, what's a fair monthly price? (Free text)

**Survey distribution**: Email to beta participants each Monday via Mailchimp or direct send.  
**Response incentive**: Weekly "top contributor" shoutout in Discord.

---

## 5. Crash Monitoring (Sentry)

**Automated monitoring**:
- Sentry dashboard: crash-free session rate (target ≥99%)
- Alert rule: crash-free sessions drops below 99% on any day → email + Slack #incidents
- Alert rule: crash-free sessions drops below 98% → PagerDuty P2 page

**Beta crash triage SLA**:
- Crash reported (automated or manual) → acknowledged within 2h during beta
- Fix deployed → same build day if P1 (data loss / full app crash)
- Fix deployed → next build within 48h for P2 (feature crash)

**Crash dashboard link**: Share read-only Sentry dashboard URL in `#status-updates` so beta participants can see we're actively monitoring.
