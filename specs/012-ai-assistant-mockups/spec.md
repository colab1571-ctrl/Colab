# 012 — AI Assistant + Mockup Generation

**Phase**: P11.
**Services**: `ai-orchestrator-svc`.
**Mission**: Premium-gated AI surfaces inside the collab workspace. Five in-chat commands. Mutual-consent AI Collab Preview mockups (image + audio). Replicate webhook orchestration. Credit-wallet metering.

## In scope (master Journey C FR-C-7, FR-C-8)

### In-chat AI assistant (5 commands at launch)
- `/mockup-image <prompt>` — generates a watermarked image (basic-tier Replicate model for Premium; advanced model for Pro).
- `/mockup-audio <prompt>` — generates a watermarked audio clip (basic for Premium, advanced for Pro).
- `/summarize-chat [N]` — summary of the last N messages (default 50).
- `/brainstorm <topic>` — short creative ideation.
- `/palette <description>` — color palette + hex codes.
- Cost metering: each call charges credits from CreditWallet (§013). Pricing values admin-configurable.
- Premium-only gate. Free users see a tooltip + upsell.

### AI Collab Preview mockup
- Both users open the consent modal → `MockupConsent` row created.
- Mutual-consent doc with lifespan (1d / 14d) + watermark policy + viewer-only acknowledgment.
- Generation: prompt assembled from both portfolios + user-provided brief → Replicate model → polled or webhook-completed.
- Output watermarked + stored to S3; viewable only by both participants.
- Android FLAG_SECURE; iOS screenshot-detect + audit-log warning entry.
- Lifespan expires → file marked inactive but retained for audit per §009 retention.

## Dependencies

- **Hard**: 002, 003, 007 Chat (commands invoked inside chat), 013 Billing (credit-wallet check), 008 Moderation (AI output scanned before delivery), 009 Collab.
- **External**: Replicate, OpenAI.

## Owned entities

- `MockupConsent`: id, collab_id, requested_by, party_a_consented_at, party_b_consented_at, lifespan_days (1|14), brief (500ch), created_at, status (pending_a|pending_b|approved|rejected|expired|generated).
- `MockupAsset`: id, mockup_consent_id, replicate_prediction_id, kind (image|audio), s3_key, watermark_meta (jsonb), generated_at, expires_at, active (bool).
- `AIInteraction`: id, user_id, command, input_tokens, output_tokens, cost_credits, replicate_prediction_id (nullable), status, created_at.

## API surface

- `POST /ai/chat/{room_id}/command` body `{command, args}` (Premium only) → 200 sync (summarize/brainstorm/palette) or 202 async (mockup-image/mockup-audio)
- `POST /collabs/{id}/mockup/consent` body `{lifespan_days, brief}` (creates or progresses consent)
- `POST /webhooks/replicate` (signed)
- `GET /collabs/{id}/mockups` — list active + expired (party only)

### Queue events

- `ai.command_invoked`, `ai.mockup_generated`, `ai.credit_charged`
- `mockup.consent_complete` → trigger generation

## Acceptance criteria

- Free user runs a slash command → upsell modal.
- Premium user runs `/summarize-chat` → response in <10s with credit charge logged.
- Mockup consent flow: both consent → Replicate prediction queued → webhook fires → asset stored watermarked → both notified.
- Asset viewable inside chat only for both parties.
- iOS screenshot attempt → audit log entry (`Audit: <user_id> screenshot of mockup <asset_id> at <ts>`).
- Lifespan expiry hides asset from viewers; still retrievable by support for audit.

## NFRs

- Command latency (text commands) <10s P95.
- Mockup latency target <60s P95 (governed by Replicate); UI shows progress.

## Open

- Suno-style music generation vs MusicGen quality trade-off — Phase 5 model selection.
- Pre-generation prompt-safety review (avoid generating disallowed content) — Phase 5 detail; share with §008 moderation pipeline.
