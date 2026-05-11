# Plan — 012 AI Assistant + Mockup Generation
**Spec**: `/specs/012-ai-assistant-mockups/spec.md`
**Service**: `ai-orchestrator-svc`
**Phase**: P11 (after P10 Meetings, before P12 Payments)
**Author**: plan agent · 2026-05-11
**Status**: DRAFT

---

## 1. Mission Recap

Colab's mission is to build the leading AI-powered networking and collaboration platform for rising artists and creators in the gig economy — optimizing for *real creative output*, not time-on-app. The AI Assistant + Mockup Generation feature (FR-C-7, FR-C-8) is the platform's primary creative-productivity differentiator. It surfaces five in-chat slash commands that let two matched Premium collaborators brainstorm, summarize, visualize, and hear early-stage mockups of their joint project — all without leaving the workspace.

Key constraints that shape every decision in this plan:

| Constraint | Value |
|---|---|
| Access gate | Premium or Premium Pro only; Free users see upsell tooltip |
| Mutual consent | Both parties must explicitly accept the AI Collab Preview consent modal before generation fires |
| Watermark | Always present on every generated asset — non-negotiable, immovable |
| Asset lifespan | 1 day (default) or 14 days (extended, user-selected at consent time) |
| Credit metering | Every command costs credits from §013 CreditWallet; admin-configurable amounts |
| Screenshot protection | Android FLAG_SECURE; iOS detection + audit-log entry |
| Retention | Assets set `active=false` on expiry but kept in S3 for IP audit (§009 retention rules apply) |
| Moderation | All AI output scanned through §008 pipeline before delivery |
| Geography | US, CA, AU, NZ, IN at launch |

---

## 2. Research & Technology Decisions

### 2.1 Text Command Provider — OpenAI GPT-4.1

All three text-only commands (`/summarize-chat`, `/brainstorm`, `/palette`) route through **OpenAI GPT-4.1** (master ARC-14), keeping LLM vendor surface consistent with the matching, profile-review, and support chatbot subsystems.

- **Model**: `gpt-4.1` (or `gpt-4.1-mini` for `/palette` to reduce latency — admin-configurable via feature flag).
- **Auth**: OpenAI API key stored in AWS Secrets Manager; injected into `ai-orchestrator-svc` pods via IRSA.
- **Token budgets** (starting values, admin-tunable):
  - `/summarize-chat`: up to 6 000 input tokens (≈50 messages × ~120 tokens), 800 output tokens.
  - `/brainstorm`: up to 1 000 input tokens, 1 000 output tokens.
  - `/palette`: up to 500 input tokens, 300 output tokens.
- **Streaming**: disabled at launch; full response awaited then pushed as a single `system` chat message. Revisit in Phase 5 if latency target is missed.
- **Safety layer**: responses pass through the §008 moderation pipeline (OpenAI moderation endpoint) before delivery. Any score ≥0.7 suppresses delivery and files a `ModerationCase` with `kind=auto`.

### 2.2 Image Generation — Replicate (SDXL / FLUX-1)

The `/mockup-image` command and the image arm of the AI Collab Preview both use **Replicate** as the model aggregator (master ARC-15) via the webhook-async pattern.

| Tier | Model | Notes |
|---|---|---|
| Premium (`mockup_fidelity=basic`) | `stability-ai/sdxl` (SDXL 1.0 base + refiner) | Reasonable quality, faster cold-start |
| Premium Pro (`mockup_fidelity=advanced`) | `black-forest-labs/flux-1.1-pro` | Higher fidelity, higher per-prediction cost |

- **Selection rationale**: SDXL is battle-tested on Replicate with stable API surface and broad prompt compliance. FLUX-1.1-pro offers measurably superior detail and prompt adherence suitable for portfolio-grade previews; its higher credit cost maps naturally to the Pro tier.
- **Input schema**: `prompt` (string, 500ch max), `negative_prompt` (hardcoded safety string appended server-side), `width`/`height` (fixed 1024×1024 for consistency), `num_inference_steps` (30 basic / 50 pro), `guidance_scale` (7.0).
- **Webhook**: Replicate calls `POST /webhooks/replicate` signed with `REPLICATE_WEBHOOK_SECRET`. Signature verification via HMAC-SHA256 (see §2.5).
- **Cold-start risk**: SDXL P95 latency on cold GPU ≈25-40 s; FLUX-1.1-pro ≈40-70 s. Mitigated by keeping predictions warm where Replicate allows warm-pool hints. UI shows indeterminate progress bar from the moment the prediction is queued.

### 2.3 Audio Generation — Replicate (MusicGen / Stable Audio)

The `/mockup-audio` command and the audio arm of the AI Collab Preview use **Replicate**-hosted audio models.

| Tier | Model | Notes |
|---|---|---|
| Premium (`mockup_fidelity=basic`) | `meta/musicgen` (MusicGen-melody-large) | Open-weights, strong genre/mood control |
| Premium Pro (`mockup_fidelity=advanced`) | `stability-ai/stable-audio` (Stable Audio 2.0) | Higher fidelity stereo, longer clips |

- **Selection rationale**: MusicGen is mature on Replicate, has reliable prompt-to-genre mapping, and generates 10–30 s clips in under 30 s wall-clock. Stable Audio 2.0 produces higher-fidelity stereo suitable for Pro-tier creative previews. Suno-style quality is noted as an open risk (spec §Open) and is a Phase 5 re-evaluation point.
- **Input schema**: `prompt` (string, 400ch max), `duration` (10 s basic / 20 s pro), `model_version` (pinned), `output_format` (mp3).
- **Same webhook path** as image (`POST /webhooks/replicate`); discriminated by `prediction.id` looked up in `MockupAsset.replicate_prediction_id`.

### 2.4 Moderation Integration (§008)

All AI output — text responses, generated images, generated audio — is scanned through `moderation-svc` before delivery:

- **Text**: OpenAI moderation API endpoint called synchronously (adds ~100 ms).
- **Image**: AWS Rekognition Content Moderation called synchronously after watermarking (adds ~800 ms — acceptable within the 60 s Replicate budget).
- **Audio**: Chromaprint fingerprint + embedding semantic dup check. No real-time audio content classifier available at launch; prompt-safety (pre-generation) is the primary gate (see §13 Open Risks).

If `moderation_score ≥ 0.7`, the asset is suppressed, the `AIInteraction` is marked `status=moderation_blocked`, credits are **refunded**, and a `ModerationCase` is auto-filed.

### 2.5 Replicate Webhook Signature Verification

Replicate sends a `Replicate-Signature` header with each webhook. Verification process:

```
1. Compute HMAC-SHA256(key=REPLICATE_WEBHOOK_SECRET, message=raw_body)
2. Compare hex digest to header value using hmac.compare_digest()
3. Reject with HTTP 403 if mismatch or missing header
4. Enforce idempotency: check Redis for prediction_id; skip processing if already handled
```

The secret is stored in AWS Secrets Manager as `colab/ai-orchestrator/replicate-webhook-secret` and rotated quarterly.

### 2.6 Image Watermarking — PIL ImageDraw

Watermark is rendered using **Python Pillow (PIL)** directly in `ai-orchestrator-svc` (no external service dependency):

```
Text:    "Colab • Generated for [User A display name] & [User B display name] • [ISO 8601 timestamp]"
Font:    Bundled TrueType font (DejaVu Sans Bold), size proportional to image height (≈2%)
Color:   RGBA(255, 255, 255, 80)  — semi-transparent white
Angle:   −30° diagonal
Tiling:  Repeated across entire canvas at (image_width/3) × (image_height/3) grid
Blend:   PIL Image.alpha_composite over source image
```

The watermark is applied **before** S3 upload. The original un-watermarked prediction artifact from Replicate is discarded (never stored). Watermark parameters are stored in `MockupAsset.watermark_meta` (JSONB) for auditability.

### 2.7 Audio Watermarking

Two-layer approach:

1. **Inaudible low-frequency tone**: A soft 5 kHz sine wave (−60 dBFS, imperceptible in normal playback) is injected at 0 s, 10 s, 20 s, etc. using `pydub` + `numpy`. The tone encodes the `MockupAsset.id` as a simple Manchester-coded sequence (Phase 5 may replace with a proper audio watermark library such as Audiowmark).
2. **Metadata tag**: ID3 `TXXX` tag (MP3) or `iTunSMPB`-equivalent comment (for AAC fallback) set to:
   ```
   COLAB_WATERMARK=asset_id=[uuid];user_a=[user_id];user_b=[user_id];ts=[iso8601]
   ```

Both layers are applied before S3 upload. Original Replicate audio artifact discarded.

---

## 3. Five-Command Catalogue

### 3.1 `/mockup-image <prompt>`

**Purpose**: Generate a watermarked visual concept image for the collaboration.

**Prompt Template**:
```
You are an art director. Generate a visual concept for a creative collaboration.
Context: [assembled from both users' vocation tags + "obsessed with" fields, ≤200 chars each]
User brief: {user_prompt}
Style guidance: photorealistic concept art, professional quality, suitable for portfolio preview.
Safe-for-work only. Do not depict real persons, logos, or copyrighted characters.
```
The template is assembled server-side; the user only supplies `{user_prompt}`.

**Input parsing rules**:
- Strip leading `/mockup-image` token; remainder is `user_prompt`.
- Max 500 characters. Excess truncated with warning in response.
- If `user_prompt` is empty → reject with `400 Bad Request`, message: "Please include a prompt after `/mockup-image`."
- Server appends hardcoded negative prompt: `"nude, explicit, gore, violence, real faces, text overlays, watermarks"`.

**Output schema**:
```json
{
  "type": "ai_mockup_image",
  "status": "queued",
  "ai_interaction_id": "uuid",
  "mockup_asset_id": "uuid",
  "estimated_seconds": 45,
  "message": "Your image is being generated. We'll notify you when it's ready."
}
```
On webhook completion, a `system` ChatMessage is inserted with `type=image` referencing the watermarked S3 asset.

**Credit cost**: `CREDIT_MOCKUP_IMAGE_BASIC` (Premium) / `CREDIT_MOCKUP_IMAGE_PRO` (Pro) — placeholder admin-configurable values; seed values TBD in §013 admin setup.

**Latency target**: <60 s P95 (Replicate-governed). UI shows indeterminate progress.

---

### 3.2 `/mockup-audio <prompt>`

**Purpose**: Generate a short watermarked audio clip as a sonic mood reference for the collaboration.

**Prompt Template**:
```
{user_prompt}. [Vocation context: {user_a_vocations} collaborating with {user_b_vocations}.]
Duration: {duration}s. Style: high-quality, professional demo, instrumental only.
```

**Input parsing rules**:
- Strip `/mockup-audio` token; remainder is `user_prompt`.
- Max 400 characters. Excess truncated.
- Empty prompt → reject with `400`.
- `duration` derived from tier: 10 s (basic), 20 s (pro). User cannot override at launch.

**Output schema**:
```json
{
  "type": "ai_mockup_audio",
  "status": "queued",
  "ai_interaction_id": "uuid",
  "mockup_asset_id": "uuid",
  "estimated_seconds": 30,
  "message": "Your audio clip is generating. Sit tight!"
}
```
On completion, a `system` ChatMessage is inserted with `type=audio` and a 5-minute signed CloudFront URL.

**Credit cost**: `CREDIT_MOCKUP_AUDIO_BASIC` / `CREDIT_MOCKUP_AUDIO_PRO` — admin-configurable.

**Latency target**: <45 s P95 (MusicGen basic) / <70 s P95 (Stable Audio pro).

---

### 3.3 `/summarize-chat [N]`

**Purpose**: Produce a concise summary of the last N messages in the chat room.

**Prompt Template**:
```
You are an assistant summarizing a creative collaboration chat.
Summarize the following {N} messages into 3–5 bullet points covering: decisions made, action items, creative ideas raised, and any blockers.
Be neutral. Do not editorialize. Output only the bullet list.

---
{message_transcript}
---
```
`message_transcript` is assembled from `ChatMessage` rows (text only; voice/file messages referenced as `[voice note]`, `[image]`, etc.).

**Input parsing rules**:
- Parse optional integer argument `N` after `/summarize-chat`. Default 50. Min 5. Max 200.
- If N > 200 → clamp to 200 with notice.
- Fetch messages from `ChatMessage` ordered by `created_at DESC`, limit N, then reverse for chronological order.
- Filter: only `status=delivered` messages; skip `deleted_at IS NOT NULL`.

**Output schema** (synchronous, delivered as a `system` ChatMessage):
```json
{
  "type": "ai_text",
  "command": "summarize-chat",
  "body": "• Decision: ... \n• Action item: ... \n• Idea raised: ...",
  "input_tokens": 3200,
  "output_tokens": 210,
  "ai_interaction_id": "uuid"
}
```

**Credit cost**: `CREDIT_SUMMARIZE_CHAT` — admin-configurable.

**Latency target**: <10 s P95.

---

### 3.4 `/brainstorm <topic>`

**Purpose**: Generate a short list of creative ideas or angles on a topic relevant to the collaboration.

**Prompt Template**:
```
You are a creative collaborator. The two artists on this project specialize in: {user_a_vocations} and {user_b_vocations}.
Brainstorm 5–7 distinct creative ideas or angles on the following topic. Be specific and actionable. Keep each idea to 1–2 sentences.
Topic: {user_topic}
```

**Input parsing rules**:
- Remainder after `/brainstorm` is `user_topic`. Required; min 3 chars. Max 300 chars.
- Empty or too-short topic → `400` with message.

**Output schema** (synchronous `system` ChatMessage):
```json
{
  "type": "ai_text",
  "command": "brainstorm",
  "body": "1. ...\n2. ...\n3. ...",
  "ai_interaction_id": "uuid"
}
```

**Credit cost**: `CREDIT_BRAINSTORM` — admin-configurable.

**Latency target**: <10 s P95.

---

### 3.5 `/palette <description>`

**Purpose**: Generate a curated color palette with hex codes from a descriptive prompt.

**Prompt Template**:
```
You are a visual designer. Generate a color palette of exactly 5 colors that fits the following mood/concept.
Output ONLY a JSON array of objects: [{name, hex, usage_note}]. No prose outside the JSON.
Concept: {user_description}
```

**Input parsing rules**:
- Remainder after `/palette` is `user_description`. Required; max 200 chars.
- Empty → `400`.
- Server validates response is valid JSON with exactly 5 items before returning. On parse failure: retry once with stricter prompt; on second failure: return `500` and refund credits.

**Output schema** (synchronous `system` ChatMessage):
```json
{
  "type": "ai_palette",
  "command": "palette",
  "colors": [
    {"name": "Deep Slate", "hex": "#2D3142", "usage_note": "Primary background"},
    ...
  ],
  "ai_interaction_id": "uuid"
}
```
The chat UI renders swatches inline from this structured payload.

**Credit cost**: `CREDIT_PALETTE` — admin-configurable.

**Latency target**: <8 s P95.

---

## 4. AI Collab Preview — Consent Flow

The AI Collab Preview is a superset of the standard slash commands. It requires explicit bilateral consent because the generation combines both users' portfolio context, and the output is jointly owned IP.

### 4.1 Sequence Diagram

```
User A                    ai-orchestrator-svc           User B
  |                               |                        |
  |-- POST /collabs/{id}/mockup/  |                        |
  |   consent {lifespan, brief}   |                        |
  |                               |-- INSERT MockupConsent |
  |                               |   status=pending_b     |
  |<-- 201 {consent_id, status}   |                        |
  |                               |-- [event: consent.req] |
  |                               |   notification-svc  -->|-- Push: "A wants to
  |                               |                        |   co-generate a mockup"
  |                               |                        |
  |                               |         B opens modal <|
  |                               |         reads consent  |
  |                               |         + watermark    |
  |                               |         + lifespan doc |
  |                               |                        |
  |                               |<-- POST /collabs/{id}/ |
  |                               |    mockup/consent      |
  |                               |    {consent_id, accept}|
  |                               |                        |
  |                               |-- UPDATE MockupConsent |
  |                               |   party_b_consented_at |
  |                               |   status=approved      |
  |                               |                        |
  |                               |-- PRE-CHECK credits    |
  |                               |   (billing-svc)        |
  |                               |-- PESSIMISTIC RESERVE  |
  |                               |   CreditTransaction    |
  |                               |   reason=reserve       |
  |                               |                        |
  |                               |-- ENQUEUE Replicate    |
  |                               |   prediction           |
  |                               |   (Celery task)        |
  |                               |                        |
  |<-- Push: "Generating..."    <-|-- Notify both users    |
  |                               |                        |
  |                               |<--- POST /webhooks/    |
  |                               |     replicate          |
  |                               |     (prediction done)  |
  |                               |                        |
  |                               |-- VERIFY signature     |
  |                               |-- DOWNLOAD artifact    |
  |                               |-- RUN moderation scan  |
  |                               |-- APPLY watermark      |
  |                               |-- UPLOAD to S3         |
  |                               |-- UPDATE MockupAsset   |
  |                               |   active=true          |
  |                               |-- CONFIRM credit charge|
  |                               |   (remove reserve,     |
  |                               |    INSERT consume tx)  |
  |                               |                        |
  |<-- Push: "Mockup ready!" <----|-- Notify both users    |-->
  |                               |                        |
  |-- GET /collabs/{id}/mockups   |                        |
  |<-- [{asset, signed_url}]      |                        |
```

### 4.2 Consent Record Status Machine

```
pending_b  ──(B accepts)──►  approved  ──(generation queued)──►  generated
    │                            │
    │(B rejects)         (A or B revokes before queue)
    ▼                            ▼
 rejected                    rejected
    │
    │(TTL 48h no response)
    ▼
 expired
```

If generation fails (Replicate error, moderation block, watermark error):
- `MockupConsent.status` → `generated` (consent itself succeeded)
- `MockupAsset.active` → `false`
- Credits refunded via `CreditTransaction(reason=refund)`
- Both users notified of failure with error reason (generic: "Generation failed. Credits refunded.")

### 4.3 Consent Modal Content (Client)

The modal presented to User B must include:
1. A preview of the brief submitted by User A (verbatim, read-only).
2. The selected lifespan (1 day / 14 days).
3. Watermark policy statement (verbatim): "This mockup will be permanently watermarked with both your names and a timestamp. It is for preview purposes only."
4. Viewer restriction acknowledgment: "Only you and [User A] can view this mockup."
5. IP reminder: "Generating this mockup does not transfer any IP rights."
6. Two CTAs: **Accept & Generate** / **Decline**.

User A sees the same modal at initiation time (they are implicitly party A consented on `POST /collabs/{id}/mockup/consent`).

---

## 5. Detailed Data Model

### 5.1 `MockupConsent`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK | |
| `collab_id` | `uuid` FK → `Collaboration.id` | One active consent per collab at a time |
| `requested_by` | `uuid` FK → `Profile.id` | Party A |
| `party_a_consented_at` | `timestamptz` | Set on creation |
| `party_b_consented_at` | `timestamptz` | Set when B accepts |
| `lifespan_days` | `smallint` CHECK IN (1, 14) | User-selected |
| `brief` | `varchar(500)` | User A's plain-text brief |
| `status` | `enum` | `pending_b`, `approved`, `rejected`, `expired`, `generated` |
| `generation_kind` | `enum` | `image`, `audio`, `both` | Defaulting to `image` at launch |
| `created_at` | `timestamptz` | |
| `updated_at` | `timestamptz` | |
| `expires_consent_at` | `timestamptz` | `created_at + 48h`; Celery Beat expires if still `pending_b` |

**Indexes**: `(collab_id, status)` partial index on `status IN ('pending_b', 'approved')` for uniqueness enforcement.
**Constraint**: Only one `MockupConsent` per `collab_id` with `status IN (pending_b, approved)` (partial unique index).

---

### 5.2 `MockupAsset`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK | |
| `mockup_consent_id` | `uuid` FK → `MockupConsent.id` | |
| `replicate_prediction_id` | `varchar(64)` | Replicate's prediction identifier |
| `kind` | `enum` | `image`, `audio` |
| `s3_key` | `text` | Path in S3 (`mockups/{collab_id}/{asset_id}/{kind}`) |
| `watermark_meta` | `jsonb` | `{text, angle, opacity, font_size, grid_spacing, audio_tone_hz, audio_tone_dbfs, metadata_tag}` |
| `moderation_score` | `numeric(4,3)` | Score from §008 scan |
| `moderation_status` | `enum` | `passed`, `blocked` |
| `generated_at` | `timestamptz` | When Replicate webhook confirmed completion |
| `expires_at` | `timestamptz` | `generated_at + lifespan_days * 86400s` |
| `active` | `boolean` DEFAULT `true` | Set `false` by Celery Beat expiry job |
| `file_size_bytes` | `bigint` | |
| `duration_ms` | `integer` | Audio only |
| `width` | `integer` | Image only |
| `height` | `integer` | Image only |

**Indexes**: `(mockup_consent_id)`, `(expires_at) WHERE active = true` (for Celery Beat expiry job).

---

### 5.3 `AIInteraction`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK | |
| `user_id` | `uuid` FK → `User.id` | Initiating user |
| `collab_id` | `uuid` FK → `Collaboration.id` | Nullable (commands outside collab context not in scope) |
| `room_id` | `uuid` FK → `ChatRoom.id` | |
| `command` | `varchar(50)` | `mockup_image`, `mockup_audio`, `summarize_chat`, `brainstorm`, `palette` |
| `args_json` | `jsonb` | Parsed input arguments |
| `input_tokens` | `integer` | OpenAI input tokens (nullable for Replicate commands) |
| `output_tokens` | `integer` | OpenAI output tokens (nullable for Replicate commands) |
| `cost_credits` | `integer` | Credits charged (or reserved, then confirmed/refunded) |
| `replicate_prediction_id` | `varchar(64)` | Nullable; set for image/audio commands |
| `mockup_asset_id` | `uuid` FK → `MockupAsset.id` | Nullable |
| `status` | `enum` | `queued`, `processing`, `completed`, `failed`, `moderation_blocked`, `refunded` |
| `failure_reason` | `text` | Nullable |
| `created_at` | `timestamptz` | |
| `completed_at` | `timestamptz` | Nullable |

**Indexes**: `(user_id, created_at DESC)`, `(replicate_prediction_id)` (for webhook lookup).

---

### 5.4 Supporting Audit Table — `MockupScreenshotAudit`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK | |
| `mockup_asset_id` | `uuid` FK | |
| `user_id` | `uuid` FK | User who triggered the screenshot |
| `platform` | `enum` | `ios`, `android` |
| `detected_at` | `timestamptz` | |
| `raw_event` | `jsonb` | Notification payload from client for audit |

Retained indefinitely for IP audit purposes.

---

## 6. Credit Metering

All credit operations integrate with `billing-svc` (§013) via internal REST calls and the `credits.*` event queue.

### 6.1 Pre-Check (Entitlement Gate)

Before any command is processed:

```
1. GET /billing/entitlements (billing-svc, cached in Redis ≤30s)
   → assert tier IN (premium, pro)
   → assert ai_credits_per_month > 0 OR user has purchased credit pack
2. GET /billing/credits/balance (billing-svc, Redis-cached)
   → assert balance >= command_credit_cost
3. If either check fails:
   → return 402 Payment Required with upsell payload
   → log AIInteraction(status=rejected_insufficient_credits)
```

### 6.2 Pessimistic Reserve at Queue Time

For async commands (`mockup-image`, `mockup-audio`) and the AI Collab Preview flow, credits are **reserved pessimistically** at the moment the Replicate prediction is enqueued — not when the result arrives. This prevents double-booking on concurrent commands.

```sql
INSERT INTO credit_transaction (user_id, delta, reason, reference, created_at)
VALUES (:user_id, -:cost, 'reserve', :ai_interaction_id, NOW());

UPDATE credit_wallet SET balance = balance - :cost WHERE user_id = :user_id;
```

Reserve is implemented as a `CreditTransaction(reason=reserve)` row in §013. The `ai_interaction_id` is the reference.

### 6.3 Confirmation on Success

When the Replicate webhook fires and the asset is successfully watermarked and stored:

```sql
UPDATE credit_transaction SET reason = 'consume' WHERE reference = :ai_interaction_id;
UPDATE ai_interaction SET status = 'completed' WHERE id = :ai_interaction_id;
```

Queue event `credits.consumed` emitted with `{user_id, delta, ai_interaction_id}`.

### 6.4 Refund on Failure

Failure paths that trigger refund:
- Replicate prediction status = `failed`
- Moderation score ≥ 0.7 (output suppressed)
- Watermark/S3 upload error after 3 retries
- OpenAI API error on text commands (after 2 retries with exponential backoff)

```sql
UPDATE credit_transaction SET reason = 'refund', delta = +:cost WHERE reference = :ai_interaction_id;
UPDATE credit_wallet SET balance = balance + :cost WHERE user_id = :user_id;
UPDATE ai_interaction SET status = 'refunded', failure_reason = :reason WHERE id = :ai_interaction_id;
```

Queue event `credits.consumed` with negative delta, plus `ai.credit_refunded` for notification-svc to push "Your credits have been refunded."

### 6.5 Admin-Configurable Credit Costs (Seed Values)

These are placeholder seed values to be finalized during §013 billing setup and admin config. All stored in the `entitlement_config` admin table.

| Command | Axis Key | Seed Value (credits) |
|---|---|---|
| `/mockup-image` (basic) | `CREDIT_MOCKUP_IMAGE_BASIC` | TBD |
| `/mockup-image` (pro) | `CREDIT_MOCKUP_IMAGE_PRO` | TBD |
| `/mockup-audio` (basic) | `CREDIT_MOCKUP_AUDIO_BASIC` | TBD |
| `/mockup-audio` (pro) | `CREDIT_MOCKUP_AUDIO_PRO` | TBD |
| `/summarize-chat` | `CREDIT_SUMMARIZE_CHAT` | TBD |
| `/brainstorm` | `CREDIT_BRAINSTORM` | TBD |
| `/palette` | `CREDIT_PALETTE` | TBD |

---

## 7. Watermarking

### 7.1 Image Watermark (PIL ImageDraw)

Implementation in `ai-orchestrator-svc/watermark/image.py`:

```python
from PIL import Image, ImageDraw, ImageFont
import math

def apply_image_watermark(img: Image.Image, user_a: str, user_b: str, ts: str) -> Image.Image:
    txt = f"Colab • Generated for {user_a} & {user_b} • {ts}"
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font_size = max(16, img.height // 50)
    font = ImageFont.truetype("/app/fonts/DejaVuSans-Bold.ttf", font_size)
    text_w, text_h = draw.textsize(txt, font=font)
    angle_rad = math.radians(30)
    # Tile across canvas
    step_x = img.width // 3
    step_y = img.height // 3
    for x in range(-img.width, img.width * 2, step_x):
        for y in range(-img.height, img.height * 2, step_y):
            draw.text((x, y), txt, font=font, fill=(255, 255, 255, 80))
    rotated = overlay.rotate(30, expand=False)
    composite = Image.alpha_composite(img.convert("RGBA"), rotated)
    return composite.convert("RGB")
```

Watermark parameters stored in `MockupAsset.watermark_meta`:
```json
{
  "text_template": "Colab • Generated for {user_a} & {user_b} • {ts}",
  "angle_deg": 30,
  "opacity": 80,
  "font": "DejaVuSans-Bold",
  "font_size_ratio": 0.02,
  "grid_step_ratio": 0.333
}
```

**Constraints**:
- Watermark is applied before S3 upload; source prediction output is deleted after watermarking.
- Watermark is non-removable by users via the app. Removal attempts are a ToS violation.
- The `DejaVuSans-Bold.ttf` font is bundled in the Docker image (open source, SIL license).

### 7.2 Audio Watermark

Implementation in `ai-orchestrator-svc/watermark/audio.py`:

**Layer 1 — Low-frequency tone**:
```python
from pydub import AudioSegment
from pydub.generators import Sine
import numpy as np

TONE_HZ = 5000          # 5 kHz — above typical vocal range
TONE_DBFS = -60         # imperceptible in normal playback
TONE_DURATION_MS = 200  # 200 ms burst
TONE_INTERVAL_MS = 10_000  # every 10 seconds

def inject_tone_watermark(audio: AudioSegment) -> AudioSegment:
    tone = Sine(TONE_HZ).to_audio_segment(duration=TONE_DURATION_MS).apply_gain(TONE_DBFS)
    result = audio
    pos = 0
    while pos < len(audio):
        result = result.overlay(tone, position=pos)
        pos += TONE_INTERVAL_MS
    return result
```

**Layer 2 — Metadata tag** (ID3 for MP3):
```python
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TXXX

def tag_audio(path: str, asset_id: str, user_a_id: str, user_b_id: str, ts: str):
    audio = MP3(path, ID3=ID3)
    audio.tags.add(TXXX(
        encoding=3,
        desc="COLAB_WATERMARK",
        text=f"asset_id={asset_id};user_a={user_a_id};user_b={user_b_id};ts={ts}"
    ))
    audio.save()
```

Parameters stored in `MockupAsset.watermark_meta`:
```json
{
  "tone_hz": 5000,
  "tone_dbfs": -60,
  "tone_duration_ms": 200,
  "tone_interval_ms": 10000,
  "metadata_key": "COLAB_WATERMARK",
  "metadata_value_template": "asset_id={asset_id};user_a={user_a_id};user_b={user_b_id};ts={ts}"
}
```

---

## 8. Screenshot Guard

### 8.1 Android — FLAG_SECURE

Applied to the `MockupViewerActivity` (or the equivalent React Native `Modal` wrapping the mockup viewer):

```java
// In the RN native module or Expo plugin
getActivity().getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
```

In React Native + Expo, this is implemented via a native module:
- **Android**: `ReactActivity.onStart()` applies `FLAG_SECURE`; removed on `onStop()`.
- The flag prevents screenshots via hardware buttons, the Recents thumbnail, ADB screencap, and screen recording on the mockup viewer screen.
- FLAG_SECURE is applied only while the mockup viewer is in the foreground; it is lifted on navigation away.

### 8.2 iOS — Screenshot Detection + Overlay Warning

iOS does not provide a reliable screenshot block equivalent to FLAG_SECURE. The approach:

1. **Detection**: Subscribe to `UIApplicationUserDidTakeScreenshotNotification` in the native module.
2. **Overlay warning**: On detection, immediately render a full-screen semi-transparent overlay with the message: "Screenshots of AI mockups are logged. This preview is watermarked and for your eyes only."
3. **Audit log entry**: Client posts to `POST /ai/mockups/{asset_id}/screenshot-event` (fire-and-forget with retry on failure). Server inserts into `MockupScreenshotAudit`.

```typescript
// RN iOS native module usage
import { MockupScreenshotGuard } from '@colab/native-mockup-guard';

// Inside MockupViewerScreen
useEffect(() => {
  const sub = MockupScreenshotGuard.onScreenshotDetected(({ assetId }) => {
    setOverlayVisible(true);
    api.post(`/ai/mockups/${assetId}/screenshot-event`).catch(() => {
      // queue for retry via offline queue
    });
  });
  return () => sub.remove();
}, [assetId]);
```

Audit log entry format:
```
Audit: user_id={uuid} screenshot of mockup asset_id={uuid} at {ISO 8601 timestamp} platform=ios
```

**Note**: iOS detection is best-effort. A determined user can circumvent it using another device to photograph the screen. This is acknowledged as an accepted limitation; the audit log + watermark are the primary IP protection mechanisms.

### 8.3 Web (consumer-web)

If the mockup viewer is ever surfaced on web (not in scope at launch — mobile-only for mockup viewer):
- `user-select: none; pointer-events: none` CSS on image/audio elements.
- `contextmenu` event suppressed.
- `printDocument` intercepted to show warning.
- Web does not have FLAG_SECURE equivalent; watermark is the primary guard.

---

## 9. Lifespan Expiry

### 9.1 Expiry Job (Celery Beat)

A Celery Beat periodic task runs **every hour** to expire assets past their `expires_at` timestamp.

```python
# celery_schedule.py
from celery.schedules import crontab

CELERYBEAT_SCHEDULE = {
    "expire-mockup-assets": {
        "task": "ai_orchestrator.tasks.expire_mockup_assets",
        "schedule": crontab(minute=0),  # hourly at :00
    },
    "expire-mockup-consents": {
        "task": "ai_orchestrator.tasks.expire_pending_consents",
        "schedule": crontab(minute=30),  # hourly at :30
    },
}
```

```python
# tasks/expire.py
@app.task
def expire_mockup_assets():
    """Set active=false for all MockupAssets past expires_at."""
    now = datetime.utcnow()
    expired = db.query(MockupAsset).filter(
        MockupAsset.active == True,
        MockupAsset.expires_at <= now
    ).all()
    for asset in expired:
        asset.active = False
        db.add(AuditLog(
            entity="MockupAsset",
            entity_id=asset.id,
            event="expired",
            ts=now
        ))
    db.commit()
    # Notify both parties
    for asset in expired:
        consent = asset.mockup_consent
        notification_svc.notify_both(
            consent.collab_id,
            "Your AI mockup has expired and is no longer viewable."
        )

@app.task
def expire_pending_consents():
    """Expire MockupConsent rows still pending_b after 48h."""
    cutoff = datetime.utcnow() - timedelta(hours=48)
    db.query(MockupConsent).filter(
        MockupConsent.status == "pending_b",
        MockupConsent.created_at <= cutoff
    ).update({"status": "expired"})
    db.commit()
```

### 9.2 Asset Retention Policy

- `active=false` assets are **not deleted** from S3. The `s3_key` remains valid.
- Assets are retained for the lifetime of the `Collaboration` + 3 years (inheriting §009 / master §3 Compliance retention policy) for IP audit purposes.
- Support team can retrieve expired assets via the admin console (`admin-svc` endpoint gated to `ROLE_SUPPORT`).
- DSR erasure requests: `MockupAsset.s3_key` content deleted within 30 days; the `MockupAsset` row is pseudonymized (user names in `watermark_meta.text` replaced with `[REDACTED]`).

---

## 10. API Contracts

### 10.1 `POST /ai/chat/{room_id}/command`

**Auth**: Bearer JWT. Premium or Pro required.

**Request**:
```json
{
  "command": "summarize-chat | brainstorm | palette | mockup-image | mockup-audio",
  "args": {
    "prompt": "string (optional for summarize-chat)",
    "n": 50
  }
}
```

**Responses**:
- `200 OK` — synchronous result (summarize-chat, brainstorm, palette)
  ```json
  {
    "ai_interaction_id": "uuid",
    "command": "brainstorm",
    "result": { "body": "...", "type": "ai_text" },
    "credits_charged": 5,
    "credits_remaining": 95
  }
  ```
- `202 Accepted` — async queued (mockup-image, mockup-audio)
  ```json
  {
    "ai_interaction_id": "uuid",
    "mockup_asset_id": "uuid",
    "status": "queued",
    "estimated_seconds": 45
  }
  ```
- `400 Bad Request` — invalid command / missing args
- `402 Payment Required` — insufficient credits or wrong tier
  ```json
  {"error": "insufficient_credits", "upsell": {"tier": "premium", "cta_url": "..."}}
  ```
- `404 Not Found` — room not found or user not a participant
- `429 Too Many Requests` — rate limit (max 10 commands per user per minute, Redis sliding window)

---

### 10.2 `POST /collabs/{id}/mockup/consent`

**Auth**: Bearer JWT. Both callers must be participants in the Collaboration.

**Request**:
```json
{
  "lifespan_days": 1,
  "brief": "We want to generate a visual concept for our indie film poster.",
  "kind": "image"
}
```

**Behavior**:
- If no `MockupConsent` with `status IN (pending_b, approved)` exists for this `collab_id`: creates one with `status=pending_b`, `requested_by=caller`, `party_a_consented_at=now`. Returns `201`.
- If one exists with `status=pending_b` and caller is the *other* participant (party B): sets `party_b_consented_at=now`, `status=approved`, triggers generation queue. Returns `200`.
- If caller is party A and consent already exists: returns `409 Conflict` with current status.

**Responses**:
- `201 Created` — party A initiated
  ```json
  {"consent_id": "uuid", "status": "pending_b", "message": "Waiting for your collaborator to consent."}
  ```
- `200 OK` — party B accepted, generation queued
  ```json
  {"consent_id": "uuid", "status": "approved", "ai_interaction_id": "uuid", "estimated_seconds": 60}
  ```
- `409 Conflict` — duplicate or already approved
- `402 Payment Required` — insufficient credits (checked at approval time)

---

### 10.3 `POST /webhooks/replicate`

**Auth**: HMAC-SHA256 signature verification (see §2.5). No JWT.

**Headers**: `Replicate-Signature: sha256=<hex_digest>`

**Request body**: Replicate prediction webhook payload (varies by model; key fields: `id`, `status`, `output`, `error`).

**Behavior**:
1. Verify signature → `403` if invalid.
2. Look up `AIInteraction` by `replicate_prediction_id` → `404` if not found.
3. Check Redis idempotency key `replicate:{prediction_id}` → `200` early return if already processed.
4. If `status=succeeded`: download output, scan, watermark, upload, confirm credits, notify.
5. If `status=failed`: set `AIInteraction.status=failed`, refund credits, notify.
6. Set Redis key `replicate:{prediction_id}` with 24h TTL.
7. Always return `200 OK` to Replicate (retry semantics handled by Celery, not Replicate retry).

---

### 10.4 `GET /collabs/{id}/mockups`

**Auth**: Bearer JWT. Caller must be a participant.

**Query params**: `?include_expired=false` (default false; `true` requires `ROLE_SUPPORT`).

**Response**:
```json
{
  "mockups": [
    {
      "id": "uuid",
      "consent_id": "uuid",
      "kind": "image",
      "active": true,
      "generated_at": "2026-05-11T14:30:00Z",
      "expires_at": "2026-05-12T14:30:00Z",
      "signed_url": "https://cdn.colab.app/mockups/...",
      "signed_url_expires_at": "2026-05-11T14:35:00Z",
      "watermark_present": true
    }
  ]
}
```

Signed URLs are 5-minute CloudFront signed URLs generated at request time. Client must re-fetch when expired.

---

### 10.5 `POST /ai/mockups/{asset_id}/screenshot-event`

**Auth**: Bearer JWT.

**Request**:
```json
{"platform": "ios", "detected_at": "2026-05-11T14:31:00Z"}
```

**Response**: `204 No Content` (fire-and-forget from client perspective).

**Behavior**: Inserts `MockupScreenshotAudit` row. If `asset_id` not found or caller not a participant → `404` (but client should swallow this).

---

## 11. Implementation Tasks

| ID | Title | Outcome | Est. Hours | Blocks | Blocked By |
|---|---|---|---|---|---|
| T-012-01 | `ai-orchestrator-svc` service scaffold | FastAPI service deployable to EKS; health check; OpenAPI schema; Postgres schema migrations for `MockupConsent`, `MockupAsset`, `AIInteraction`, `MockupScreenshotAudit` | 8h | T-012-02 through T-012-15 | T-002-xx (platform base), T-003-xx (auth), T-007-xx (chat-svc), T-013-xx (billing-svc) |
| T-012-02 | OpenAI client wrapper + retry logic | Singleton client with exponential backoff (2 retries, 2s/4s), timeout 30s, structured error logging to Sentry | 4h | T-012-05, T-012-06, T-012-07 | T-012-01 |
| T-012-03 | Replicate client wrapper + webhook dispatcher | Async prediction creation, polling fallback, webhook handler with HMAC-SHA256 verification, idempotency via Redis | 8h | T-012-08, T-012-09, T-012-10 | T-012-01 |
| T-012-04 | Credit pre-check + reserve + confirm + refund | Internal billing-svc client; pessimistic reserve pattern; confirm/refund Celery tasks; integration test with billing-svc mock | 6h | T-012-05 through T-012-12 | T-012-01, T-013-xx |
| T-012-05 | `/summarize-chat` command | OpenAI call, prompt template, message fetch from chat-svc, output schema, system ChatMessage insertion, credit charge | 6h | — | T-012-01, T-012-02, T-012-04, T-007-xx |
| T-012-06 | `/brainstorm` command | OpenAI call, prompt template, vocation context assembly, output schema, credit charge | 4h | — | T-012-01, T-012-02, T-012-04 |
| T-012-07 | `/palette` command | OpenAI call, JSON-strict prompt, response validation + retry, palette output schema, swatch payload, credit charge | 5h | — | T-012-01, T-012-02, T-012-04 |
| T-012-08 | `/mockup-image` command + Replicate prediction | Prompt assembly (user brief + vocation context), tier-based model selection (SDXL vs FLUX-1.1-pro), prediction enqueue, 202 response, credit reserve | 8h | T-012-10 | T-012-01, T-012-03, T-012-04 |
| T-012-09 | `/mockup-audio` command + Replicate prediction | Prompt assembly, tier-based model selection (MusicGen vs Stable Audio), prediction enqueue, 202 response, credit reserve | 8h | T-012-10 | T-012-01, T-012-03, T-012-04 |
| T-012-10 | Replicate webhook handler | Signature verify, idempotency, download artifact, dispatch to watermark pipeline, moderation scan call, S3 upload, credit confirm/refund, notify | 10h | T-012-11, T-012-12 | T-012-03, T-012-13, T-012-14 |
| T-012-11 | Image watermark (PIL) | `apply_image_watermark()`, font bundle, overlay tiling, RGBA compositing, watermark_meta population, unit tests | 6h | T-012-10 | T-012-01 |
| T-012-12 | Audio watermark (pydub + mutagen) | `inject_tone_watermark()`, `tag_audio()`, 5 kHz tone injection every 10s, ID3 TXXX tag, unit tests | 6h | T-012-10 | T-012-01 |
| T-012-13 | Moderation scan integration | Internal `moderation-svc` client, post-generation scan for image (Rekognition) + text (OpenAI mod), suppression logic, ModerationCase creation | 6h | T-012-10 | T-012-01, T-008-xx |
| T-012-14 | S3 upload + CloudFront signed URL | Boto3 upload with server-side encryption, ACL private, `MockupAsset.s3_key` storage, 5-min signed URL generation, rotation on `GET /collabs/{id}/mockups` | 4h | T-012-10 | T-012-01 |
| T-012-15 | AI Collab Preview consent flow | `POST /collabs/{id}/mockup/consent` endpoint, `MockupConsent` state machine, party A/B detection, 48h expiry task, approval → generation trigger, notification events | 10h | — | T-012-01, T-012-08, T-012-09, T-013-xx |
| T-012-16 | Lifespan expiry Celery Beat jobs | `expire_mockup_assets` hourly task, `expire_pending_consents` hourly task, AuditLog insertion, notification dispatch, idempotency | 4h | — | T-012-01 |
| T-012-17 | `GET /collabs/{id}/mockups` endpoint | Active + expired listing, participant-only gate, signed URL generation, `include_expired` support-role gate | 3h | — | T-012-01, T-012-14 |
| T-012-18 | `POST /ai/chat/{room_id}/command` dispatcher | Route to correct command handler, Premium gate check, rate limit (10/user/min, Redis sliding window), unified error responses, AIInteraction logging | 5h | — | T-012-01, T-012-05..09 |
| T-012-19 | Screenshot audit endpoint | `POST /ai/mockups/{asset_id}/screenshot-event`, `MockupScreenshotAudit` insertion, fire-and-forget response | 2h | — | T-012-01 |
| T-012-20 | RN — AI command input UI | Slash command autocomplete in chat input, command argument input, loading states, error states, upsell modal for Free users | 10h | — | T-007-xx (chat UI), T-012-18 |
| T-012-21 | RN — Mockup image viewer with screenshot guard | Full-screen viewer, FLAG_SECURE (Android native module), iOS UIApplicationUserDidTakeScreenshotNotification handler, overlay warning, audit event POST | 10h | — | T-012-17, T-012-19 |
| T-012-22 | RN — AI Collab Preview consent modal | Modal UI for party A initiation + party B acceptance, lifespan selector, brief input, watermark policy text, CTAs, pending state for party A | 8h | — | T-012-15 |
| T-012-23 | RN — palette swatch inline renderer | ChatMessage type=ai_palette: render color swatches with hex codes inline in the chat bubble | 4h | — | T-012-07, T-012-20 |
| T-012-24 | RN — audio mockup player | In-chat audio player for type=audio system messages, watermark badge indicator, expired state | 5h | — | T-012-17 |
| T-012-25 | PostHog event instrumentation | Track: `ai_command_invoked`, `ai_command_completed`, `ai_command_failed`, `ai_mockup_consent_initiated`, `ai_mockup_consent_accepted`, `ai_mockup_generated`, `ai_mockup_expired`, `ai_screenshot_detected` | 3h | — | T-012-05..16 |
| T-012-26 | Integration tests (ai-orchestrator-svc) | pytest fixtures for all 5 commands, consent flow happy path, moderation block, credit refund, webhook idempotency, lifespan expiry | 12h | — | T-012-05..19 |
| T-012-27 | Load test — command throughput | k6 script: 200 concurrent Premium users sending `/brainstorm` commands; assert P95 <10s; assert no credit double-charge under load | 4h | — | T-012-26 |

**Total estimated hours**: ~164h

---

## 12. Acceptance Criteria

### AC-01: Free user upsell gate
**Scenario**: A Free tier user types `/brainstorm collaboration ideas` in a chat room.
**Verification**:
1. `POST /ai/chat/{room_id}/command` returns `402` with `{"error": "insufficient_credits", "upsell": {...}}`.
2. Client renders upsell modal ("Upgrade to Premium to use AI commands").
3. No `AIInteraction` row created. No credits charged.
4. PostHog event `ai_command_invoked` with `result=gated_free_user` emitted.

---

### AC-02: `/summarize-chat` happy path with credit charge
**Scenario**: A Premium user with ≥5 credits runs `/summarize-chat 20`.
**Verification**:
1. Response arrives within 10 s P95.
2. A `system` ChatMessage of `type=ai_text` with `command=summarize_chat` appears in the chat room.
3. `AIInteraction` row: `status=completed`, `cost_credits=CREDIT_SUMMARIZE_CHAT`, `input_tokens` > 0.
4. `CreditWallet.balance` decremented by `CREDIT_SUMMARIZE_CHAT`.
5. `CreditTransaction` row with `reason=consume` and `reference=ai_interaction_id`.

---

### AC-03: `/palette` returns structured swatches
**Scenario**: A Premium user runs `/palette moody neon cyberpunk`.
**Verification**:
1. Response is a `system` ChatMessage of `type=ai_palette`.
2. `colors` array contains exactly 5 objects each with `name`, `hex` (valid 6-digit hex), `usage_note`.
3. RN chat UI renders 5 color swatches inline.
4. Credits charged.

---

### AC-04: `/mockup-image` — async generation happy path
**Scenario**: A Premium user runs `/mockup-image indie film poster, dark and dramatic`.
**Verification**:
1. `POST /ai/chat/{room_id}/command` returns `202` with `status=queued` within 3s.
2. Replicate prediction created with SDXL model (verify via Replicate API or mock).
3. Credit pessimistically reserved (`CreditTransaction(reason=reserve)`).
4. Within 60s (P95), Replicate webhook fires, `MockupAsset` created with `active=true`.
5. Watermark is present on the stored image (verified by reading pixel data at expected overlay coordinates).
6. `system` ChatMessage of `type=image` inserted in chat room referencing the asset.
7. Both users receive push notification "Your AI mockup is ready!"
8. `AIInteraction.status=completed`; `CreditTransaction(reason=consume)`.

---

### AC-05: `/mockup-image` — moderation block + refund
**Scenario**: Generated image scores ≥0.7 on Rekognition.
**Verification**:
1. Asset not delivered; no `system` ChatMessage created.
2. `MockupAsset.moderation_status=blocked`.
3. `AIInteraction.status=moderation_blocked`.
4. Credits refunded: `CreditTransaction(reason=refund)`, wallet balance restored.
5. User notified "Generation failed. Credits refunded."
6. `ModerationCase` created with `kind=auto`, `subject_type=mockup_asset`.

---

### AC-06: AI Collab Preview — full bilateral consent flow
**Scenario**: User A initiates a consent; User B accepts; generation completes.
**Verification**:
1. User A `POST /collabs/{id}/mockup/consent` → `201`, `status=pending_b`.
2. User B receives push notification.
3. User B `POST /collabs/{id}/mockup/consent` with same `consent_id` → `200`, `status=approved`.
4. `MockupConsent.party_b_consented_at` is set.
5. Replicate prediction queued immediately after approval.
6. On Replicate webhook: `MockupAsset` created, watermark applied, both users notified.
7. `GET /collabs/{id}/mockups` returns the asset with a valid signed URL for both users.
8. A third-party user (not a participant) receives `404` on `GET /collabs/{id}/mockups`.

---

### AC-07: Consent TTL expiry
**Scenario**: User A initiates consent; User B does not respond for 48h.
**Verification**:
1. Celery Beat job at next hourly run sets `MockupConsent.status=expired`.
2. User A sees the consent as expired in the UI.
3. No credits were charged (reserve never placed, since approval never happened).

---

### AC-08: Android FLAG_SECURE on mockup viewer
**Verification**:
1. On Android device, navigate to `MockupViewerScreen`.
2. Attempt hardware screenshot (Volume Down + Power) → screenshot is blocked (black image or system toast).
3. ADB `screencap` command on the window returns a black frame.
4. Navigate away from viewer → screenshot works normally on other screens.

---

### AC-09: iOS screenshot detection + audit log
**Verification**:
1. On iOS device, open mockup viewer.
2. Take screenshot (Home + Side button or equivalent).
3. Within 500ms, a full-screen overlay warning appears in-app.
4. `MockupScreenshotAudit` row inserted with correct `user_id`, `asset_id`, `platform=ios`, `detected_at` within 2s.
5. Audit log entry visible in admin console.

---

### AC-10: Lifespan expiry — 1-day asset
**Verification**:
1. Create a `MockupAsset` with `lifespan_days=1`. Set `expires_at = NOW() - 1 second`.
2. Trigger `expire_mockup_assets` task manually.
3. `MockupAsset.active` = `false`.
4. `GET /collabs/{id}/mockups` (without `include_expired=true`) returns empty list.
5. Both users receive push: "Your AI mockup has expired."
6. `GET /collabs/{id}/mockups?include_expired=true` (with `ROLE_SUPPORT`) returns the asset with `active=false`.
7. S3 object still exists (not deleted).

---

### AC-11: Credit pre-check — insufficient balance
**Scenario**: Premium user has 0 credits.
**Verification**:
1. Command returns `402` with `error=insufficient_credits`.
2. No Replicate prediction created.
3. No `CreditTransaction` row created.
4. `AIInteraction` row has `status=rejected_insufficient_credits`.

---

### AC-12: Replicate webhook idempotency
**Verification**:
1. Send identical Replicate webhook payload twice (same `prediction.id`).
2. First call: processes normally.
3. Second call: returns `200` without re-processing (Redis idempotency key present).
4. Only one `MockupAsset` row created.
5. Credits charged only once.

---

### AC-13: Rate limiting — 10 commands per user per minute
**Verification**:
1. Send 11 rapid `/brainstorm` commands from the same user within 60 seconds.
2. First 10 succeed.
3. 11th returns `429 Too Many Requests`.
4. After 60-second window resets, commands succeed again.

---

## 13. Open Risks

### RISK-01: Audio generation model quality vs. latency trade-off
**Description**: MusicGen (basic tier) produces 10 s clips in ~20-30 s wall-clock on Replicate, which is acceptable. However, Stable Audio 2.0 (pro tier) may have cold-start latencies of 60-90s on Replicate, potentially missing the 60s P95 target. Suno-style quality (noted in spec §Open) would require a dedicated Suno API integration not currently available as a standard Replicate model.
**Mitigation**: Pin model versions to warm-pool-capable Replicate deployments. Implement Replicate deployment warmup pings via Celery Beat if warm-pool API is available. Adjust Pro tier latency target to 90s P95 if cold-start data confirms the gap. Phase 5 model selection review before P11 execution.
**Owner**: Phase 5 `ai-orchestrator-svc` lead.
**Status**: OPEN.

---

### RISK-02: Replicate cold-starts under low-traffic periods
**Description**: During off-peak hours (overnight US time), Replicate GPU instances for SDXL and FLUX-1.1-pro may cold-start, adding 30-60s of uncontrolled latency on top of inference time. The 60s P95 target may be breached without warm GPU availability.
**Mitigation**:
1. Use Replicate's `deployment` feature (dedicated GPU) for Pro tier if traffic justifies cost.
2. For Basic tier, accept occasional cold-starts; UI shows "Generating... (this can take up to 90 seconds on first run)."
3. Monitor p95/p99 latency via PostHog + CloudWatch. Set alarm at >75s P95.
**Owner**: DevOps + ai-orchestrator-svc lead.
**Status**: OPEN — revisit in P11 sprint planning.

---

### RISK-03: Prompt safety — pre-generation content filter
**Description**: The spec notes (§Open) that pre-generation prompt safety (preventing disallowed content) needs Phase 5 detail and shared use of the §008 moderation pipeline. A user could craft a prompt that passes text moderation but produces disallowed visual/audio content at the model level.
**Mitigation**:
1. Run user-supplied prompt through OpenAI moderation API **before** submitting to Replicate. Score ≥0.4 → reject with `422 Unprocessable Entity`, no credit charge.
2. Append hardcoded negative prompt to all Replicate image calls.
3. Post-generation scan (Rekognition for images) as second defense layer (AC-05).
4. Phase 5: implement semantic prompt analysis to detect adversarial prompt patterns. Share blocklist with §008 moderation-svc.
**Owner**: moderation-svc + ai-orchestrator-svc leads.
**Status**: OPEN — pre-generation scan is MVP requirement; semantic analysis is Phase 5+.

---

### RISK-04: IP ownership ambiguity of AI-generated mockups
**Description**: AI-generated content IP ownership is unsettled in all five launch jurisdictions (US, CA, AU, NZ, IN). If a generated mockup resembles copyrighted training data, the platform may face DMCA or equivalent claims.
**Mitigation**:
1. ToS explicitly states: AI mockups are for creative preview only; no IP rights are transferred; users are advised not to use mockups as final deliverables.
2. Watermark policy reinforces preview-only nature.
3. Consent modal includes IP reminder (§4.3 item 5).
4. DMCA workflow in §008 handles takedown claims even though DMCA agent is deferred (accepted risk from master §0).
5. Consult legal counsel on AI-generated IP language in ToS before launch. `[OPEN LEGAL RISK — Phase 5 legal review]`.
**Owner**: Legal + product.
**Status**: OPEN.

---

### RISK-05: Audio watermark circumvention
**Description**: The 5 kHz tone watermark can be removed by a determined user via audio editing software (e.g., applying a notch filter at 5 kHz). The metadata tag is trivially removable.
**Mitigation**:
1. Watermarks are deterrents, not cryptographic guarantees. The ToS makes circumvention a violation.
2. Phase 5+: evaluate Audiowmark (robust psychoacoustic watermarking) as a replacement for the tone-based approach. Audiowmark is resistant to common audio transformations.
3. The visible (visual) watermark on image mockups is significantly harder to remove without degrading quality.
**Owner**: ai-orchestrator-svc lead.
**Status**: ACCEPTED at launch; Audiowmark upgrade in Phase 5+ backlog.

---

### RISK-06: `MockupConsent` uniqueness race condition
**Description**: Two concurrent requests from user A and user B could both attempt to create a `MockupConsent` simultaneously, resulting in two `pending_b` rows for the same `collab_id`.
**Mitigation**:
1. Partial unique index on `(collab_id) WHERE status IN ('pending_b', 'approved')` in Postgres.
2. Application-level: wrap `INSERT` in a `SELECT FOR UPDATE` on the `Collaboration` row to serialize concurrent consent creation.
3. Return `409 Conflict` if unique constraint violation detected.
**Owner**: ai-orchestrator-svc backend lead.
**Status**: MITIGATED by partial unique index; verify under concurrent load in T-012-27.

---

*End of plan — 012 AI Assistant + Mockup Generation*
