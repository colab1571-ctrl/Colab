# 019 — Pre-launch Hardening

**Phase**: P18.
**Mission**: Load test to 100k DAU, security review, App Store + Play Store submission packets, closed beta, status page wired, runbook.

## In scope

- **Load test**: k6 or Artillery scenarios for:
  - Signup funnel + Persona webhook
  - Feed scroll + ranking
  - Chat fanout (10k concurrent rooms, 100k messages/min steady-state)
  - AI command invocation (queued + Replicate-bounded)
  - Billing webhook storms
- **Security review**:
  - Threat model per service
  - Dependency CVE scan (Dependabot, Trivy on container images)
  - Static analysis (semgrep, bandit, eslint-security)
  - Penetration test (external vendor recommended; budget approval needed)
  - Secrets-rotation drill
- **App Store + Play Store submission**:
  - App Store Connect listing (icon, screenshots × 6 devices, description, keywords, age rating ≥18, privacy questionnaire — Apple "Data Used to Track" set to none per ATT decision)
  - Google Play Store listing (icon, screenshots, feature graphic, description, content rating questionnaire, data safety form)
  - In-App Purchase products configured + RevenueCat synced
  - TestFlight + Internal Testing tracks set up
- **Closed beta**:
  - 100 invited creators
  - Crash + error monitoring active
  - Feedback channel (in-app + email)
- **Status page**: Statuspage.io configured + linked from marketing site
- **Runbook**: On-call rotation, paging policy, escalation tree, incident severity definitions, postmortem template, change management

## Dependencies

- **Hard**: all features 001–018 must be deployed to staging at minimum.

## Owned entities (none)

This is a process phase.

## Acceptance criteria

- Load test hits 100k concurrent users with P95 latencies within FR-NFR-1 envelopes.
- Zero high/critical findings open from security review.
- iOS app passes Apple Review (first submission may bounce; track resubmissions).
- Android app passes Play Console Review.
- 100 beta users onboarded; 80%+ complete onboarding; crash-free sessions ≥99%.
- Status page green; runbook published in `docs/runbooks/`.

## NFRs

- Production capacity reservation sized for 100k DAU peak.

## Open

- Pen-test vendor + budget — Phase 5 procurement decision.
