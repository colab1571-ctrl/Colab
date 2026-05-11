# 008 — Moderation + Safety + IP — Implementation Plan

> Phase: **P7** (after chat foundations land in §007). Service: `moderation-svc`. Touches: `chat-svc` (007), `media-svc` (010), `profile-svc` (004), `invite-svc` (006), `billing-svc` (013), `notification-svc` (014), `admin-svc` (016), `auth-svc` (003), `support-svc` (015).
>
> Legal-heavy feature. Document carefully. Anything that touches DMCA, harassment-threat, or permanent ban needs a paper trail.

---

## 1. Mission recap

`moderation-svc` is the central guardrail for the Colab platform. Its mandate, drawn verbatim from master §0/§3 (FR-M-1..FR-M-6) and the §008 spec, is:

1. **Pre-publish scanning** of every user-generated text/image/audio/video artifact (chat messages, profile bios, "obsessed with" copy, invite synopses, portfolio uploads, mockup outputs) through a multi-tool layered pipeline (OpenAI omni-moderation-latest + AWS Rekognition + pHash + Chromaprint + pgvector semantic-dup).
2. **Risk-tiered routing** with master-locked thresholds (<0.4 / 0.4–0.7 / 0.7–0.9 / ≥0.9) and SLAs (24h / 6h / 1h), with IP/DMCA and harassment-threat **always** routed to humans regardless of score.
3. **Human moderator queue + actions** (warn, hide, temp-mute 1h/24h/7d, permanent ban, delete account) with an immutable, append-only action log.
4. **User-initiated reporting** from chat msg, profile, portfolio item, mockup, invite synopsis.
5. **DMCA + counter-notice statutory workflow** without a registered designated agent (US safe-harbor explicitly waived per master §0; documented in ToS + Community Guidelines).
6. **Action propagation** — when a moderator fires "permanent ban", a wave of downstream effects must fan out reliably to §003 lockout, §004 badge revoke, §007 chat read-only, §013 subscription pause + refund decision, §014 notification halt, all logged.

Out of scope this milestone (revisit Phase 5): cross-locale moderation thresholds (US/CA/AU/NZ/IN may diverge — master §0/§008 open), automated DMCA-agent registration (deferred), TikTok content moderation hooks (TikTok integration deferred), ad-content moderation (Journey D deferred), chat-translation moderation (translation deferred).

Non-goal: optimizing for moderator throughput at the cost of due-process accuracy. The platform is **quality-first** (master §0 timeline posture); a wrongly-banned creator destroys trust more than a slow queue. Therefore: human-in-the-loop for everything ≥0.4, mandatory dual-reviewer for "permanent ban" + "delete account" (added in this plan as a hardening over the master), and a public counter-notice form for any auto-hide that is later disputed.

---

## 2. Research — concrete tool integrations

### 2.1 OpenAI Moderation API

- **Model**: `omni-moderation-latest` (pinned via `OPENAI_MODEL_MOD` from `.env.example` line 113).
- **Endpoint**: `POST https://api.openai.com/v1/moderations` body `{model, input}` where `input` is text **or** an array of `{type: "text"|"image_url", text|image_url}` entries. Omni-mod supports multimodal (text + image_url) in a single call.
- **Output schema** we will consume:

  ```json
  {
    "id": "modr_...",
    "model": "omni-moderation-latest",
    "results": [{
      "flagged": true,
      "categories": {
        "sexual": false, "sexual/minors": false,
        "harassment": true, "harassment/threatening": true,
        "hate": false, "hate/threatening": false,
        "self-harm": false, "self-harm/intent": false, "self-harm/instructions": false,
        "violence": true, "violence/graphic": false,
        "illicit": false, "illicit/violent": false
      },
      "category_scores": {
        "sexual": 0.01, "sexual/minors": 0.0,
        "harassment": 0.83, "harassment/threatening": 0.71,
        "hate": 0.04, "hate/threatening": 0.01,
        "self-harm": 0.02, "self-harm/intent": 0.0, "self-harm/instructions": 0.0,
        "violence": 0.62, "violence/graphic": 0.04,
        "illicit": 0.0, "illicit/violent": 0.0
      },
      "category_applied_input_types": {
        "sexual": ["text"], "harassment": ["text"], ...
      }
    }]
  }
  ```

- **Latency budget**: P95 ≤ 600ms; chat-msg pipeline therefore runs this async with a soft "send-on-allow" pattern (see §3 algorithm).
- **Cost note**: omni-mod is currently free for OpenAI customers — but we cap requests/sec via Redis token bucket to defend against report-bombing.
- **Failure mode**: 5xx or timeout → treat as `score=null, status=manual_review` for affected subject (fail-safe, not fail-open). Auto-create a `ModerationCase(kind=auto, score=null)` with a synthetic 0.5 score so the message routes to the 0.4–0.7 tier (soft-warn + queue).

### 2.2 AWS Rekognition DetectModerationLabels (image + video)

- **API**: `rekognition.detect_moderation_labels(Image={S3Object: {...}} | {Bytes: ...}, MinConfidence=50)` for images. For video: `start_content_moderation(Video=..., MinConfidence=50)` → SNS notification → `get_content_moderation(JobId)`.
- **Output shape** (image):

  ```json
  {
    "ModerationLabels": [
      {"Confidence": 96.4, "Name": "Explicit Nudity", "ParentName": ""},
      {"Confidence": 96.4, "Name": "Graphic Male Nudity", "ParentName": "Explicit Nudity"}
    ],
    "ModerationModelVersion": "7.0"
  }
  ```

- **Category set** (parent labels, taxonomy v7): `Explicit`, `Non-Explicit Nudity of Intimate parts and Kissing`, `Swimwear or Underwear`, `Violence`, `Visually Disturbing`, `Drugs & Tobacco`, `Alcohol`, `Rude Gestures`, `Gambling`, `Hate Symbols`. We compute a per-category threshold table (see §3.3 weights).
- **Threshold per category** (admin-configurable; defaults below normalize to 0..1 by `Confidence/100`):

  | Rekognition parent | Default threshold | Outcome at ≥ |
  |---|---|---|
  | Explicit | 0.50 | hide + 1h SLA |
  | Hate Symbols | 0.40 | hide + escalate to human regardless of score |
  | Violence | 0.60 | hide + 6h SLA |
  | Visually Disturbing | 0.60 | soft-warn + 24h SLA |
  | Drugs & Tobacco | 0.70 | soft-warn + 24h SLA |
  | Rude Gestures | 0.80 | soft-warn + 24h SLA |
  | Swimwear/Underwear | 0.85 | log-only (allowed; platform serves visual artists) |

- **Region**: `us-east-1` (matches `AWS_REGION` line 20). Custom moderation adapters (CSAM) deferred — handle via auto-hide ≥0.9 + immediate human review + NCMEC report manual workflow.
- **Latency**: image ~500ms; video async (we poll on SNS callback). For chat real-time, images flow through `media-svc` upload pipeline before chat message commits — moderation is a pre-publish gate.

### 2.3 imagehash pHash (Python, perceptual image dup)

- **Library**: `imagehash==4.3.1` (Python), backed by Pillow.
- **Algorithm**: `imagehash.phash(Image.open(fp))` returns a 64-bit hash (8x8 DCT). Stored as `bytea(8)` in Postgres + a `bit(64)` column for Hamming distance queries (Postgres supports `bit_count(a # b)` for bitwise-XOR + popcount).
- **Threshold**: Hamming distance ≤ 6 (≈9% of 64 bits) → duplicate flag. ≤ 4 → near-identical (auto-block re-uploads from a banned hash list).
- **Index**: BK-tree (in Redis sorted set keyed by sub-hash buckets) for sub-linear lookup; fallback Postgres full-scan acceptable for first 100k DAU because count(images) ≪ 10M at launch.
- **Use cases**:
  1. **Banned-content registry**: hashes of confirmed CSAM / known harassment imagery / prior takedowns. Any upload matching → auto-hide + 1h SLA + flag for NCMEC manual report.
  2. **Spam/duplicate portfolio detection**: a user posting the same image 12 times → flag.
  3. **Cross-user impersonation**: same selfie used by 3 different signups → flag for identity team.

### 2.4 pyacoustid + fpcalc (Chromaprint audio fingerprinting)

- **Library**: `pyacoustid==1.3.0`. Requires `fpcalc` binary (Chromaprint 1.5.x) on the worker pod (bake into the moderation-svc Docker image).
- **Algorithm**: `chromaprint.decode_fingerprint(...)` → 32-bit integer array (typical 100–300 ints for 30s clip). Stored as `int4[]` in Postgres.
- **Compare**: cosine similarity between integer arrays after bit-decomposition (Chromaprint's standard compare). Threshold ≥ 0.85 = duplicate. ≥ 0.95 = identical.
- **Use cases**: duplicate portfolio audio detection; matching audio against a banned-clip registry (e.g., voice harassment recordings flagged in prior cases).
- **Cost**: fingerprint extraction ~1.5s per 30s clip on 1 vCPU. Run in Celery worker `mod-audio-worker` (dedicated queue) so it doesn't block chat-msg fast path.

### 2.5 Semantic duplicate via pgvector cosine

- **Embedding**: OpenAI `text-embedding-3-large` (3072-dim) per `.env.example` line 114. Already used by `matching-svc` for profile embeddings.
- **Store**: `mod_text_embedding` table with `vector(3072)` column + `ivfflat` index `WITH (lists = 100)`.
- **Threshold**: cosine similarity > 0.95 → flag as duplicate (likely copy-paste spam, reused harassment message, scam template). Combined with a 24h Redis bloom filter for short-circuit on exact text matches.
- **Use cases**: detect that user X is mass-DMing the same vibe-check synopsis to 50 recipients (engagement-farming anti-pattern per master §1); detect copy-paste of a known scam ("send $50 for collab fee").

### 2.6 DMCA notice required fields (17 USC §512(c)(3))

A valid takedown notice must contain **all six** of the following or it is statutorily defective and we do not have to act:

1. **Physical or electronic signature** of a person authorized to act on behalf of the owner. We capture a typed full name + checkbox "I am authorized..." + we store `hash_of_signature` (SHA-256 of name + timestamp + IP) as a tamper-evident token.
2. **Identification of the copyrighted work** claimed to have been infringed (title, registration if any, URL of original work).
3. **Identification of the allegedly infringing material** with sufficient information to locate it (URL to the profile/portfolio item/chat asset on Colab, plus subject_id captured at form submit).
4. **Contact information** of the complaining party — full legal name, mailing address, phone, email.
5. **Good-faith statement** under penalty of perjury that use is not authorized.
6. **Statement that the information in the notice is accurate** and that the complainant is authorized to act on behalf of the owner of an exclusive right.

We collect (1)–(6) on a single form before we will even open a `DMCANotice` record. If any field is missing, return 422 with a templated "Your notice was statutorily defective for the following reasons..." message that lists missing fields. **Do not** treat a defective notice as a valid takedown.

Counter-notice (17 USC §512(g)(3)) needs:

1. Physical/electronic signature.
2. Identification of the material removed and the location at which it appeared before.
3. Statement under penalty of perjury that the user has a good-faith belief that the material was removed as a result of mistake or misidentification.
4. User's name, address, phone, and consent to jurisdiction of Federal District Court for the judicial district in which the address is located (or for foreign users, any in which the service provider may be found), plus consent to service of process from the complainant.

Statutory wait per §512(g)(2)(C): the service provider must replace the removed material **not less than 10, nor more than 14, business days** following receipt of the counter-notice, unless the original complainant files an action seeking a court order. We pick **14 calendar days** (more generous to claimant) as our `statutory_window_end`. The user accepts this in ToS at signup.

> Master §0 + §008-open caveat: we have **explicitly deferred** registering a DMCA designated agent with the Copyright Office, which means we cannot rely on the §512(c) safe-harbor. We still run the workflow for civic-duty + community-trust reasons, and we document this risk in the ToS + Community Guidelines so plaintiffs are on notice that they may sue directly.

---

## 3. Risk-tier routing algorithm

### 3.1 Inputs

For each subject (chat msg, profile field, portfolio item, invite synopsis, mockup output), we compute:

- `t_score` — OpenAI omni-moderation max(category_scores).
- `t_categories` — set of categories with `flagged=true`.
- `r_score` — Rekognition max(Confidence/100) across moderation labels (image/video only).
- `r_categories` — Rekognition parent labels with confidence ≥ category-specific threshold (see §2.2).
- `phash_match` — bool, true if image matches banned-hash registry within Hamming-6.
- `chromaprint_match` — bool, true if audio cosine ≥ 0.85 to a banned-clip.
- `semdup_match` — bool, true if text cosine > 0.95 to a banned-text registry or to user's own prior 24h sends.
- `category_weights` — per-category multipliers (admin-tunable):

  | Category | Weight |
  |---|---|
  | sexual/minors | 1.5 (force ≥0.9 tier on any positive) |
  | harassment/threatening | 1.3 |
  | hate/threatening | 1.3 |
  | violence/graphic | 1.2 |
  | self-harm/intent | 1.2 |
  | Rekognition Explicit | 1.2 |
  | Rekognition Hate Symbols | 1.3 |
  | illicit/violent | 1.2 |
  | sexual | 1.0 |
  | harassment | 1.0 |
  | violence | 1.0 |
  | default | 1.0 |

### 3.2 Combined score

```python
def combined_score(t_score, t_categories, r_score, r_categories,
                   phash_match, chromaprint_match, semdup_match,
                   weights):
    # Maximum of per-tool weighted scores
    text_weighted = max(
        (weights.get(c, 1.0) * t_categories[c] for c in t_categories),
        default=0.0,
    )
    image_weighted = max(
        (weights.get(c, 1.0) * r_categories[c] for c in r_categories),
        default=0.0,
    )
    # Heuristic bumps for dup hits
    dup_bump = 0.3 if (phash_match or chromaprint_match or semdup_match) else 0.0
    score = min(1.0, max(text_weighted, image_weighted, t_score, r_score) + dup_bump)
    return score

def route(score, t_categories, r_categories):
    # Forced-human routing regardless of score:
    if "sexual/minors" in t_categories:
        return ("auto_hide", "1h", "FORCED:csam_path", human_required=True, ncmec=True)
    if (
        "harassment/threatening" in t_categories
        or "violence/graphic" in t_categories
        or "Hate Symbols" in r_categories
        or has_ip_claim  # always human
    ):
        return ("hide_or_warn_by_score", sla_by_score(score), "FORCED:human", human=True)
    # Threshold routing per master §3 FR-M-2
    if score < 0.4:   return ("allow_log",            "none", "auto-allow")
    if score < 0.7:   return ("soft_warn_user_queue", "24h",  "tier-1")
    if score < 0.9:   return ("hide_content_queue",   "6h",   "tier-2")
    return                  ("auto_hide_temp_mute_queue","1h", "tier-3")
```

### 3.3 Worked example

User Alice sends a chat message *"shut up or i'll find you, you stupid b****"* with an attached selfie of someone holding a knife.

- OpenAI omni-mod returns:
  - `harassment=0.92, harassment/threatening=0.78, violence=0.61`
  - `flagged=true, t_score=0.92`
- Rekognition on image returns:
  - `Violence (Confidence=82) → 0.82`
  - `r_score=0.82, r_categories={"Violence": 0.82}`
- pHash check: no banned-hash match.
- Chromaprint: N/A (no audio).
- Semdup: 0.42 cosine to nearest prior text (no match).

Weighted scores:
- text_weighted = max(1.0·0.92 harassment, 1.3·0.78 harassment/threatening=1.014→cap, 1.0·0.61 violence) = 1.014 → cap at 1.0.
- image_weighted = max(1.0·0.82) = 0.82.

Combined: min(1.0, max(1.0, 0.82, 0.92, 0.82) + 0) = **1.0**.

Route: score ≥ 0.9 → `auto_hide_temp_mute_queue` (1h SLA).

**But also**: `harassment/threatening` is in `t_categories` → forced human-routing flag set. Message hidden, sender temp-muted 1h (auto), case opened with `sla_due_at = now + 1h`, escalation event emitted. Moderator gets a "harassment/threat" badge on the queue item indicating mandatory human action — no auto-resolve, no auto-dismiss.

If a moderator then chooses "permanent ban," all downstream actions of §6 fire.

### 3.4 Worked counter-example — borderline harassment

Bob sends *"that beat slaps, you're killing it"*.

- OpenAI: `harassment=0.31, sexual=0.02, violence=0.04, flagged=false, t_score=0.31`.
- No image.
- No dup.

Combined = 0.31. Route: `<0.4` → `auto-allow` + log only. No case opened. Logged in `mod_scan_log` for future audit.

---

## 4. Detailed data model

All tables live in the `moderation` Postgres schema. All `*_at` columns are `timestamptz` in UTC. All immutable / append-only tables have row-level `INSERT`-only grants for the service role; updates rejected at the DB. Hardened with row-checksums in `audit.action_log`.

### 4.1 `ModerationCase`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `kind` | enum(`auto`, `report`, `dmca`) | source of the case |
| `subject_type` | enum(`msg`, `profile_field`, `portfolio_item`, `invite_synopsis`, `mockup`, `user`) | what's being moderated |
| `subject_id` | uuid | FK to the subject table, validated at app layer (no DB cross-schema FK to keep services decoupled) |
| `subject_owner_user_id` | uuid | denormalized author of subject; used for action propagation |
| `reporter_user_id` | uuid NULL | NULL for auto/dmca |
| `score` | numeric(3,2) NULL | NULL on DMCA / NULL on tool-failure fallback |
| `scores_breakdown` | jsonb | `{openai: {...}, rekognition: {...}, phash: {...}, chromaprint: {...}, semdup: {...}, weighted: 0.92}` |
| `forced_human` | bool | true if IP / harassment-threat / CSAM forced this |
| `forced_reason` | text NULL | "harassment/threatening", "Hate Symbols", "ip_claim", "csam_path" |
| `status` | enum(`open`, `in_review`, `actioned`, `dismissed`, `escalated`) | |
| `priority_tier` | enum(`tier_0_allow`, `tier_1_24h`, `tier_2_6h`, `tier_3_1h`) | |
| `sla_due_at` | timestamptz | `opened_at + tier-sla` |
| `sla_breached_at` | timestamptz NULL | set by Celery Beat scanner when breached |
| `opened_at` | timestamptz | |
| `claimed_by` | uuid NULL | moderator who picked it up |
| `claimed_at` | timestamptz NULL | |
| `actioned_at` | timestamptz NULL | |
| `actioned_by` | uuid NULL | |
| `action_type` | enum (see ModerationAction) NULL | final action taken; mirrors ModerationAction for query speed |
| `second_reviewer_id` | uuid NULL | required for `permanent_ban` / `delete_account` |
| `idempotency_key` | text UNIQUE NULL | for upstream-retry de-dup of "auto" cases |
| `created_at` / `updated_at` | timestamptz | |

Indexes: `(status, priority_tier, sla_due_at)` for queue scans; `(subject_type, subject_id)` for lookup; `(subject_owner_user_id, opened_at desc)` for user-360 view.

### 4.2 `ModerationAction`

Append-only. The single source of truth for "what happened to a case."

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `case_id` | uuid FK | |
| `action_type` | enum(`warn`, `hide`, `restore`, `temp_mute_1h`, `temp_mute_24h`, `temp_mute_7d`, `permanent_ban`, `delete_account`, `dismiss`, `escalate_to_legal`) | |
| `reviewer_id` | uuid | |
| `reason` | text | required; min 12 chars |
| `evidence_refs` | jsonb | array of subject_ids/screenshots/log entry refs |
| `target_user_id` | uuid | the user the action affects (may differ from `subject_owner_user_id` for reporter-side actions like dismiss-spam-report) |
| `created_at` | timestamptz | immutable |
| `propagation_status` | enum(`pending`, `partial`, `complete`, `failed`) | filled by the action-dispatcher |
| `propagation_events` | jsonb | `{auth_lockout: "ok", chat_readonly: "ok", badge_revoke: "ok", subscription_pause: "pending"}` |

DB trigger rejects `UPDATE` and `DELETE` (`pg_temp.no_modify()` raises). Append-only enforced.

### 4.3 `Report`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `reporter_user_id` | uuid FK | |
| `subject_type` | enum (same as ModerationCase) | |
| `subject_id` | uuid | |
| `description` | varchar(1000) | required, min 10 chars |
| `screenshot_s3_key` | text NULL | uploaded via signed URL to `S3_BUCKET_AUDIT_LOGS` |
| `case_id` | uuid FK NULL | created during report intake |
| `created_at` | timestamptz | |
| `reporter_ip` | inet | for abuse detection |
| `device_id` | text NULL | from RN client |

Trigger creates a `ModerationCase` row on insert (kind=`report`) and emits `moderation.report_filed` event.

### 4.4 `DMCANotice`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `claimant_name` | varchar(200) | required |
| `claimant_address` | text | required |
| `claimant_phone` | varchar(40) | required |
| `claimant_email` | varchar(320) | required, validated, **deliverability-checked** via DNS MX before accept |
| `is_authorized_agent` | bool | required true |
| `sworn_statement_text` | text | the full §512(c)(3)(v)+(vi) text the user attested to; verbatim copy |
| `signature_full_name` | varchar(200) | typed name |
| `hash_of_signature` | bytea(32) | SHA-256(signature_full_name + received_at + claimant_ip) |
| `copyrighted_work_description` | text | required |
| `copyrighted_work_url_or_registration` | text NULL | one or both must be present |
| `target_subject_type` | enum | |
| `target_subject_id` | uuid | |
| `target_url_on_colab` | text | the URL the claimant cited |
| `target_user_id` | uuid | resolved server-side from subject |
| `claimant_ip` | inet | |
| `received_at` | timestamptz | |
| `hide_at` | timestamptz | computed = `received_at + 24h` (master FR-M-5 says 24h hide) |
| `hidden_at` | timestamptz NULL | set when the takedown actually fires |
| `state` | enum(`received`, `hidden`, `counter_pending`, `restored`, `permanent`, `rejected_defective`) | |
| `rejection_reason` | text NULL | for defective notices |
| `case_id` | uuid FK | always linked to a ModerationCase |

### 4.5 `CounterNotice`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `dmca_id` | uuid FK | one-to-one (DB unique) |
| `counter_claimant_user_id` | uuid FK | the user whose content was taken down |
| `counter_claimant_legal_name` | varchar(200) | required |
| `counter_claimant_address` | text | required |
| `counter_claimant_phone` | varchar(40) | required |
| `counter_statement_text` | text | verbatim §512(g)(3)(C) attestation |
| `consent_to_jurisdiction` | bool | required true |
| `consent_to_service_of_process` | bool | required true |
| `signature_full_name` | varchar(200) | typed name |
| `hash_of_signature` | bytea(32) | SHA-256 |
| `received_at` | timestamptz | |
| `statutory_window_end` | timestamptz | `received_at + 14 days` per §512(g)(2)(C) (we chose 14 calendar days; master §008 says 10–14d, we pick the longer for claimant fairness) |
| `forwarded_to_claimant_at` | timestamptz NULL | when we relayed the counter-notice to the original claimant |
| `suit_filed_notice_received_at` | timestamptz NULL | claimant may notify us of suit; halts auto-restore |
| `restored_at` | timestamptz NULL | actual restore time |
| `state` | enum(`received`, `awaiting_window`, `restored`, `permanent_taken_down`) | |

### 4.6 Auxiliary

- `BannedHashRegistry(hash_phash bytea(8), source, severity, created_at, notes)` — pHash entries for known-bad imagery.
- `BannedAudioFingerprint(fingerprint_int4_array int4[], source, severity, created_at)` — Chromaprint banned clips.
- `BannedTextEmbedding(embedding vector(3072), source, severity)` — pgvector banned-text store.
- `ModScanLog(id, subject_type, subject_id, tool, score, raw_response jsonb, scanned_at)` — every scan logged for audit, ~30d retention then archived to S3.
- `ReportThrottle(reporter_user_id, day, count)` — per-reporter daily cap to defend against report-bombing (default 20/day; admin tunable).

---

## 5. Workflow state machines

### 5.1 ModerationCase states

```
                       open  ──(moderator claims)──▶ in_review
                        │                              │
                        │                              ├──(action: warn/hide/mute/ban/delete)──▶ actioned
                        │                              ├──(no policy violation)──▶ dismissed
                        │                              └──(needs legal review)──▶ escalated
                        │
                        └──(SLA breach scanner)──▶ open (still) + sla_breached_at set + paged
```

Transitions:

- `open → in_review` requires a moderator with `mod` role to call `POST /moderation/cases/{id}/claim`. Sets `claimed_by, claimed_at`.
- `in_review → actioned` requires an action call. If `action_type ∈ {permanent_ban, delete_account}`, also requires `second_reviewer_id != claimed_by`, enforced at API layer.
- `in_review → dismissed` allowed by single reviewer; logs `action_type=dismiss`.
- `in_review → escalated` flips status; queue UI surfaces escalated bin separately; only super-admin can act.
- `open ↛ actioned` directly (must claim first).
- Reopening: a moderator can call `POST /moderation/cases/{id}/reopen` (super-admin only) which inserts a new case linked via `parent_case_id` (we don't mutate the original).

### 5.2 DMCA states

```
   ┌────────┐  (24h timer or moderator approves)   ┌──────┐
   │received├────────────────────────────────────▶│hidden│
   └───┬────┘                                      └──┬───┘
       │                                              │
       │(defective)                                   │(counter-notice filed)
       ▼                                              ▼
  ┌──────────┐                                  ┌─────────────┐
  │rejected_ │                                  │counter_     │
  │defective │                                  │pending      │
  └──────────┘                                  └────┬────────┘
                                                     │
                          (statutory_window_end + no suit filed)
                                                     │
                                                     ▼
                                                ┌────────┐
                                                │restored│
                                                └────────┘
                                                     ▲
                                                     │
                          (suit filed by claimant in window)
                                                     │
                                                     ▼
                                                ┌─────────┐
                                                │permanent│
                                                └─────────┘
```

Transitions:

- `received → hidden`: Celery Beat task `mod.dmca.enact_hide` runs every 5 min, finds DMCANotice where `state='received' AND hide_at <= now()`, executes hide via `moderation.case.action(case_id, action_type='hide')`. Emits `dmca.notice_filed_hidden`.
- `received → rejected_defective`: form validator at intake step. Notification sent to claimant explaining defect; nothing hidden.
- `hidden → counter_pending`: target user submits valid counter-notice. Computes `statutory_window_end = now + 14d`. Emits `dmca.counter_filed` (relayed to claimant within 48h via SES).
- `counter_pending → restored`: Celery Beat `mod.dmca.scan_counter_window` runs every 1h, finds notices where `state='counter_pending' AND statutory_window_end <= now AND suit_filed_notice_received_at IS NULL`. Calls `moderation.case.action(case_id, action_type='restore')`. Emits `dmca.restored`.
- `counter_pending → permanent`: claimant emails our DMCA mailbox proving suit filed; admin marks `suit_filed_notice_received_at = now`. Content stays hidden indefinitely (permanent state).

---

## 6. Moderator action consequences ("permanent ban" fan-out)

When a moderator (with a second reviewer co-signing) confirms `action_type=permanent_ban` on case C targeting user U, the action-dispatcher emits **`moderation.action_taken`** with payload `{case_id, action_type, target_user_id, reason, reviewer_id, second_reviewer_id, propagation_id}` to `mod.exchange`. Subscribers act as follows:

1. **§003 auth-svc** consumes `mod.action.permanent_ban` queue:
   - Set `user.account_status = 'banned_permanent'`.
   - Revoke all active sessions + refresh tokens (purge from Redis session store).
   - Lockout login: `auth.login()` returns 403 with `reason=account_banned` and a link to appeal.
   - Emit `auth.lockout_applied(user_id)` back to mod-svc; dispatcher marks `propagation_events.auth_lockout = 'ok'`.

2. **§004 profile-svc**:
   - Revoke ValidProfileBadge (set `badge_state='revoked'`, `revoked_reason='moderation_ban'`).
   - Mark profile `is_hidden_from_feed=true` (defense-in-depth; the auth lockout already prevents login, but discovery-svc reads profile flags).
   - Emit `profile.badge_revoked(user_id, reason)`.

3. **§013 billing-svc**:
   - Pause active Stripe subscription (`subscription.update(pause_collection={behavior: 'mark_uncollectible'})`) — no new charges.
   - Pause RevenueCat entitlement (`subscribers/{user_id}/entitlements/{entitlement}/revoke_promotionals` won't apply to paid; we instead call store refund APIs only on user request).
   - **Refund decision**: NOT automatic. We post an internal billing-admin task: "review ban for refund eligibility (14-day window? prior credits unused?)". Per §013 plan + master FR-E-7, 14-day no-questions refund still honored when timely; later prorated only for annual SKUs; store-IAP refunds routed per Apple/Google policy (we cannot unilaterally refund mobile IAP — we annotate the case for the user to self-request through the store).
   - Emit `billing.subscription_paused(user_id, mode='moderation_ban')`.

4. **§007 chat-svc**:
   - Mark all `ChatRoom` rows where `user_a_id=U OR user_b_id=U` as `state='read_only'`.
   - Block any inbound WebSocket auth from U.
   - Other party retains read access for IP-records purposes (master FR-C-14 block semantics).
   - Emit `chat.readonly_applied(user_id, room_ids)`.

5. **§014 notification-svc**:
   - Disable all notification channels for U (push, email except transactional/security, in-app).
   - Cancel any queued notifications targeting U or scheduled by U.
   - Emit `notif.halted(user_id)`.

6. **§006 invite-svc**:
   - Cancel all outbound `CollabInvite` rows with `sender_id=U AND status='pending'` (set `status='cancelled_by_moderation'`).
   - Reject all inbound pending invites to U.
   - Emit `invite.cancelled_batch(user_id, count)`.

7. **§008 audit log** (this service):
   - Append-only insert into `audit.moderation_action_propagation(action_id, target_event, status, timestamp)` for each downstream event.
   - After all 6 above ack within 60s, set `ModerationAction.propagation_status='complete'`. If any times out → `partial` and PagerDuty alert.

8. **§009 collab-svc**:
   - Active `Collaboration` rows with U as a party → flip to `state='admin_paused_moderation'`. Other party can still export per FR-C-14.

9. **§015 support-svc**:
   - Auto-open a support ticket "Account permanently banned — appeal window 30 days" assigned to U with prefilled context (case ID, reason summary, appeal instructions). Master FR-F-5: harassment tickets 4h ack, 24h resolve apply to the appeal.

10. **§016 admin-svc**: AdminAuditLog row inserted referencing the ModerationAction id.

**Compensation / rollback**: if a permanent ban is reversed on appeal (super-admin override), a `moderation.action_reversed` event fans out and each subscriber executes the inverse (re-enable auth, restore badge eligibility if AI review still passes, restore subscription with prorated credit, lift chat read-only flag, re-enable notifications, restore invites that haven't expired). Implemented in P7.5 follow-up (not blocking ban-flow).

---

## 7. SLA timers

### 7.1 Scanner schedule

Celery Beat task `mod.sla.scan` runs every **5 minutes** (`crontab(minute='*/5')` for cheap clock skew). Per scan it:

1. Selects `ModerationCase` rows where `status IN ('open','in_review') AND sla_breached_at IS NULL AND sla_due_at <= now()`.
2. For each, sets `sla_breached_at = now()`, emits `moderation.sla_breached(case_id, tier, breach_minutes)`.
3. Posts to PagerDuty + Slack #mod-sla channel for tier_3 (1h) breaches; emails the on-call lead for tier_2 (6h) and tier_1 (24h).
4. Auto-escalates tier_3 unclaimed at +30 min past breach to `status='escalated'` → super-admin queue.

### 7.2 SLA tier targets (locked from master FR-M-2)

| Tier | Score range | Auto-action | SLA |
|---|---|---|---|
| tier_0_allow | < 0.4 | allow + log | none |
| tier_1_24h | 0.4–0.7 | soft-warn + queue | 24h |
| tier_2_6h | 0.7–0.9 | hide + queue | 6h |
| tier_3_1h | ≥ 0.9 | auto-hide + temp-mute + queue | 1h |

Forced-human override: any IP claim, harassment-threat, hate-threat, CSAM signal pulls the case into the highest applicable tier (≥0.9 unless score lower; in that case at minimum tier_2_6h) **and** sets `forced_human=true` so it cannot be auto-dismissed.

### 7.3 Acknowledgement vs resolution

Per §008 NFR "Mod queue P95 SLAs honored: ≥0.9 case acked within 1h…" — **ack** = a moderator claimed the case (`status='in_review'`). Final actioning may take longer. We track both `time_to_ack` and `time_to_action` as KPIs (rolled up by analytics-svc per §016).

### 7.4 SLA telemetry events

Emitted to `mod.sla.exchange`:
- `moderation.case.opened` (tier, due_at)
- `moderation.case.claimed` (time_to_ack)
- `moderation.case.actioned` (time_to_action, action_type)
- `moderation.case.sla_breached` (tier, breach_minutes)
- `moderation.case.escalated`

Consumed by analytics-svc and PostHog ingestion.

---

## 8. DMCA workflow

### 8.1 Intake (`POST /dmca/notice`)

1. Public endpoint (no auth required — DMCA claimants are often outside the platform). Rate-limited by IP + email (5/day/IP, 10/day/email).
2. Form validates §512(c)(3) fields 1–6 (see §2.6). Defective → 422 + `state='rejected_defective'` recorded + email confirmation to claimant with checklist.
3. On valid notice:
   - Insert `DMCANotice(state='received', hide_at=now+24h)`.
   - Insert `ModerationCase(kind='dmca', priority_tier='tier_2_6h', forced_human=true, forced_reason='ip_claim', sla_due_at=now+6h)`.
   - Email claimant: confirmation + counter-notice window explanation + reminder we have no registered DMCA agent.
   - Email target user: "A DMCA takedown notice has been filed against your content. It will be hidden in 24h unless our team determines the notice is defective. You may file a counter-notice." Includes link to counter-notice form at `https://app.example.com/legal/counter-notice/{dmca_id}` with a single-use token.
   - Emit `dmca.notice_filed(dmca_id, target_user_id)`.

### 8.2 24h hide

Celery Beat `mod.dmca.enact_hide` (every 5 min) scans `DMCANotice where state='received' AND hide_at<=now() AND not in moderator override`. Calls `moderation.action.hide(case_id)` (which also propagates via §6 fan-out, scoped). Sets `state='hidden', hidden_at=now()`. Emits `dmca.notice_filed_hidden`.

Override: a moderator can mark the notice `state='rejected_defective'` before `hide_at` if it's facially invalid (e.g., not the rights-holder, fair-use that's clearly defensible, etc.). This is a manual judgment call; the moderator must document `reason`.

### 8.3 Counter-notice

Target user (and only target user) accesses `POST /dmca/{id}/counter-notice` from the emailed link. Form requires §512(g)(3) fields (see §2.6). On accept:

- Insert `CounterNotice(state='received', statutory_window_end=now+14d)`.
- Update `DMCANotice.state='counter_pending'`.
- SES email to original claimant: "We received a counter-notice. Unless you provide notice that you have filed an action seeking a court order against the user within 14 calendar days, we will restore the material." Include redacted user contact info per §512(g)(2)(B) (full counter-claimant name + address + consent-to-jurisdiction text).
- Mark `forwarded_to_claimant_at=now()`.
- Emit `dmca.counter_filed`.

### 8.4 Statutory window + auto-restore

Celery Beat `mod.dmca.scan_counter_window` (every 1h):

1. Find `CounterNotice where state='received' AND statutory_window_end<=now() AND dmca_notice.suit_filed_notice_received_at IS NULL`.
2. For each: call `moderation.action.restore(case_id)`; update `DMCANotice.state='restored'`, `CounterNotice.state='restored', restored_at=now()`.
3. Emit `dmca.restored`. Email both parties (claimant: "we restored per statute"; user: "your content is restored").

If `suit_filed_notice_received_at` is set (claimant emailed proof of suit), `DMCANotice.state='permanent'` and content stays hidden. Manual admin step to verify proof; admin-action audit-logged.

### 8.5 Required-template notice text

Inline copy that target user receives (stored in `legal_templates` table, versioned):

> A notice of claimed infringement under 17 U.S.C. §512(c)(3) has been received concerning content you posted to {BRAND_NAME}. Pursuant to our Terms of Service, we will hide the identified material in 24 hours unless the notice is determined to be statutorily defective.
>
> If you believe the content was removed by mistake or misidentification, you may file a counter-notice at the link below. Filing a counter-notice subjects you to consent to jurisdiction and consent to service of process per 17 U.S.C. §512(g)(3). The original claimant has 14 calendar days to file a court action; if they do not, we will restore your content.
>
> {BRAND_NAME} is not currently a registered DMCA designated agent. This notice and counter-notice process is offered as a community-trust workflow; it does not constitute legal advice. Consult an attorney if you have questions.

---

## 9. API contracts

All endpoints served by `moderation-svc` behind the API Gateway (`API_DOMAIN`). Auth: bearer JWT (`auth-svc` issuer). Admin endpoints require `mod`/`super-admin` role claim.

### 9.1 Public / authenticated user

- `POST /reports`
  - Body: `{subject_type: "msg"|"profile_field"|"portfolio_item"|"invite_synopsis"|"mockup", subject_id: uuid, description: string(10..1000), screenshot_s3_key?: string}`
  - Auth: required (reporter must be authenticated).
  - Rate-limit: 20 reports/day/user (admin-tunable). Returns 429 with retry-after.
  - Response 201: `{report_id, case_id, created_at, status: 'open'}`
  - Side effects: insert Report → trigger creates ModerationCase → publish `moderation.report_filed`.

- `POST /dmca/notice`
  - Body: full §512(c)(3) form (12 fields).
  - Auth: none required (DMCA claimants often aren't users).
  - Rate-limit: 5 notices/day/IP, 10 notices/day/email.
  - Response 201: `{dmca_id, case_id, received_at, state: 'received', hide_at}` or 422 with checklist of defective fields.

- `POST /dmca/{dmca_id}/counter-notice`
  - Body: §512(g)(3) form.
  - Auth: required + token-bound (the token emailed to target user; URL param + bearer).
  - Response 201: `{counter_id, dmca_id, statutory_window_end, state: 'received'}`.

### 9.2 Moderator

- `POST /moderation/cases/{id}/claim` — sets `status=in_review, claimed_by=me`.
- `POST /moderation/cases/{id}/release` — un-claims (sets back to `open`).
- `POST /moderation/cases/{id}/action`
  - Body: `{action_type, reason: string(12..2000), evidence_refs?: array, second_reviewer_id?: uuid}`
  - 422 if `action_type ∈ {permanent_ban, delete_account}` and no `second_reviewer_id` or second_reviewer == reviewer.
  - 200: `{action_id, propagation_id, status}`. Synchronously persists `ModerationAction(propagation_status='pending')`. The dispatcher fans out async; final propagation status is queryable via `GET /moderation/actions/{id}`.
- `GET /moderation/queue`
  - Query: `tier`, `sla`, `subject_type`, `forced_human`, `assigned_to`, `pagination`.
  - Returns paginated list of cases sorted by `(priority_tier desc, sla_due_at asc)`.
- `GET /moderation/cases/{id}` — full case detail incl. scan breakdown + history.
- `POST /moderation/cases/{id}/escalate` — escalate to super-admin queue.
- `POST /moderation/cases/{id}/reopen` — super-admin only, creates linked new case.
- `GET /moderation/users/{user_id}/history` — all cases + actions involving user (for user-360 view in §016).
- `POST /moderation/dmca/{id}/mark-defective` — moderator marks before `hide_at`.
- `POST /moderation/dmca/{id}/mark-suit-filed` — super-admin records claimant suit-filed.

### 9.3 Internal (service-to-service, mTLS in cluster)

- `POST /internal/scan/text` — body `{text, ctx: {subject_type, subject_id, owner_user_id}}` → returns synchronous `{score, breakdown, decision: 'allow'|'soft_warn'|'hide'|'auto_hide_mute', case_id?}`. Used by §007 chat send path.
- `POST /internal/scan/image` — body `{s3_key, ctx}` → same shape (synchronous because images are uploaded then linked).
- `POST /internal/scan/audio` — body `{s3_key, ctx}` → async returns `{job_id}`; result delivered via webhook `POST {ctx.callback_url}` when ready.
- `POST /internal/scan/video` — async (Rekognition video is async natively).
- `GET /internal/user/{user_id}/state` — returns current ban/mute state for §007 chat gate.

### 9.4 Event topics (RabbitMQ `mod.exchange`, fanout to per-service queues)

| Routing key | Payload | Consumer |
|---|---|---|
| `moderation.case.opened` | case summary | analytics-svc |
| `moderation.case.claimed` | case_id, moderator | analytics-svc |
| `moderation.case.actioned` | action summary | analytics-svc, admin-svc |
| `moderation.case.sla_breached` | tier, breach_minutes | pager, analytics |
| `moderation.action_taken` (per action_type) | full payload | many (see §6) |
| `moderation.action_reversed` | full payload | many |
| `moderation.report_filed` | report + case | analytics |
| `dmca.notice_filed` | dmca_id, target_user_id | notif, admin |
| `dmca.notice_filed_hidden` | dmca_id | notif, audit |
| `dmca.counter_filed` | counter_id | notif (relay claimant) |
| `dmca.statutory_window_expired` | dmca_id | mod-svc (self), notif |
| `dmca.restored` | dmca_id | notif |

---

## 10. Implementation tasks

> Format: `id | title | outcome | est_hours | blocks | blocked_by`

### 10a. Pipeline workers (Celery)

- `M-001 | Bootstrap moderation-svc skeleton | FastAPI service + EKS deployment + Postgres schema + RabbitMQ topology + healthcheck | 6 | M-010..M-090 | 002-platform`
- `M-002 | OpenAI omni-moderation client + retry/backoff | `openai_mod.scan(text|multimodal)` returning normalized score breakdown; circuit breaker on 5xx | 8 | M-020 | M-001`
- `M-003 | Rekognition image+video adapter | `rekognition.scan_image(s3_key)` sync; `scan_video(s3_key)` async with SNS callback handler | 12 | M-020 | M-001`
- `M-004 | pHash worker + banned-hash registry | imagehash worker, Postgres BannedHashRegistry + Redis BK-tree | 10 | M-020 | M-001`
- `M-005 | Chromaprint worker (pyacoustid + fpcalc) | dedicated `mod-audio-worker` queue with fpcalc baked in image; banned-clip registry | 10 | M-020 | M-001`
- `M-006 | pgvector semantic dup scanner | embedding via OpenAI text-embedding-3-large; banned-text vector store; 24h Redis bloom for short-circuit | 10 | M-020 | M-001, 004-profile (shared embedding util)`
- `M-007 | Combined-score + routing engine | `score.combine + route` per §3 algorithm; admin-tunable weights stored in `mod_config` table | 8 | M-020 | M-002..M-006`
- `M-008 | Internal scan APIs | /internal/scan/{text,image,audio,video}, sync vs async modes | 8 | M-040 | M-007`

### 10b. Case management API

- `M-010 | ModerationCase + ModerationAction schema + migrations | tables + indexes + INSERT-only triggers on action log | 6 | M-020 | M-001`
- `M-011 | Case open/claim/release/action endpoints | with dual-reviewer guard for ban/delete; idempotency on action insert | 10 | M-040, M-060 | M-010`
- `M-012 | Queue list + filters + detail endpoints | paginated, sort by tier desc + sla_due_at asc; user-360 history | 8 | M-040 | M-011`
- `M-013 | SLA scanner Celery Beat task | every 5 min; sets `sla_breached_at`, emits events, escalates tier_3 at +30m | 6 | M-070 | M-011`
- `M-014 | Case reopen + escalate flows | super-admin gated; preserves history | 4 | – | M-011`

### 10c. Report intake

- `M-020 | Report schema + endpoint | `POST /reports` with rate-limit + ReportThrottle counter | 6 | M-040 | M-010`
- `M-021 | Reporter rate-limit + abuse detection | per-day cap, sliding window in Redis; auto-flag reciprocal-report-bombing | 6 | – | M-020`
- `M-022 | Screenshot signed-URL upload helper | client uploads to S3_BUCKET_AUDIT_LOGS, passes key in body | 4 | – | M-020`

### 10d. DMCA flow

- `M-030 | DMCA + CounterNotice schema | tables + state enum + statutory window calc helpers | 6 | M-031..M-035 | M-010`
- `M-031 | DMCA intake endpoint with §512(c)(3) validator | 12-field form; defective-notice 422 with checklist | 10 | M-040 | M-030`
- `M-032 | 24h hide Celery Beat task | mod.dmca.enact_hide; calls hide action + emits event | 6 | – | M-030, M-011`
- `M-033 | Counter-notice intake endpoint | §512(g)(3) form; single-use token via SES email | 8 | – | M-031`
- `M-034 | Counter-notice 14-day window scanner | mod.dmca.scan_counter_window; auto-restore | 6 | – | M-033`
- `M-035 | Suit-filed mark + permanent state | super-admin endpoint | 3 | – | M-033`

### 10e. Admin console hooks (§016)

- `M-040 | OpenAPI spec + TS client generation | typed client for admin-web | 4 | M-041 | M-011..M-035`
- `M-041 | admin-web mod queue page | list + filters + tier badge + SLA countdown | 16 | M-042 | M-040`
- `M-042 | admin-web case detail + action panel | scan breakdown viewer, evidence carousel, action form with second-reviewer field | 16 | – | M-041`
- `M-043 | admin-web DMCA workflow UI | notice viewer, counter-notice viewer, "mark defective" / "mark suit filed" actions | 10 | – | M-040`
- `M-044 | admin-web user-360 moderation history tab | timeline + filter | 6 | – | M-040`

### 10f. Action propagation

- `M-050 | Action-dispatcher service worker | listens to mod.action_taken; fans out to 6+ downstream queues with timeouts + retries | 12 | M-051..M-056 | M-011`
- `M-051 | §003 auth lockout consumer | session revoke + login block | 4 | – | 003-auth`
- `M-052 | §004 badge revoke + profile hide consumer | | 4 | – | 004-profile`
- `M-053 | §007 chat read-only consumer | flips ChatRoom states | 4 | – | 007-chat`
- `M-054 | §013 subscription pause + refund task consumer | Stripe pause_collection; RC entitlement; admin task | 6 | – | 013-billing`
- `M-055 | §014 notification halt consumer | disable channels + cancel queued | 4 | – | 014-notifications`
- `M-056 | §006 + §009 invite/collab cancel consumer | | 6 | – | 006-invite, 009-collab`
- `M-057 | Propagation completeness watcher | marks ModerationAction.propagation_status; alerts on partial | 4 | – | M-050`
- `M-058 | Reversal flow | inverse fanout on `moderation.action_reversed` | 8 | – | M-050`

### 10g. Audit log

- `M-060 | Append-only audit.moderation_action_propagation table | per-event row; row checksums | 4 | M-061 | M-050`
- `M-061 | Daily S3 archival of older logs | S3_BUCKET_AUDIT_LOGS partition; 3-year retention per master compliance | 4 | – | M-060`

### 10h. RN report UI

- `M-070 | RN report-button on chat msg / profile / portfolio | bottom-sheet form with description + optional screenshot | 8 | M-071 | M-020`
- `M-071 | RN "we received your report" confirmation + tracking link to /support | – | 3 | – | M-070`
- `M-072 | RN soft-warn UX (tier_1 / tier_2 messages) | in-thread system message explaining why a message was flagged or hidden + appeal link | 6 | – | M-008`
- `M-073 | RN counter-notice form (web view) | linked from emailed token; full §512(g)(3) form | 10 | – | M-033`

### 10i. Tests including adversarial

- `M-090 | Unit tests for combined-score + routing | parametrized matrix incl. all category-weight combos | 8 | – | M-007`
- `M-091 | Integration tests for chat-send → scan → case lifecycle | happy + each tier path | 10 | – | M-008, M-011`
- `M-092 | Red-team test suite | borderline content, harassment escalation, DMCA abuse, false-positive recovery, reciprocal report-bombing (see §11) | 16 | – | M-091`
- `M-093 | E2E DMCA workflow tests | notice → 24h hide → counter-notice → 14d window → restore; also suit-filed permanent path | 8 | – | M-030..M-035`
- `M-094 | Load test mod queue + scan throughput | k6 / Locust → 100k DAU peak (300 scans/sec) | 12 | – | M-008`

Total est: ~325 hours; about 8 developer-weeks for a team of 2 + 1 frontend.

---

## 11. Test strategy — red-team cases

A regular unit + integration test suite is mandatory but not sufficient. We additionally encode the following adversarial scenarios as automated tests in `M-092`:

### 11.1 Borderline content

- "this beat is sick" with a 0.31 score should never open a case (tier_0_allow).
- A message at score=0.39 with `harassment` category but no `harassment/threatening` opens tier_0 (just below cutoff) — confirm we do not auto-warn at 0.39.
- A message at score=0.401 opens tier_1 with 24h SLA — confirm exact-boundary inclusion.

### 11.2 Harassment escalations

- Same sender hits 3 separate `harassment` cases within 7 days → auto-escalate next message to tier_2 even if score=0.5. (Implementation: `RecentOffenderTracker` Redis sorted set; bump weight.)
- After 5 cases → propose `permanent_ban` recommendation surfaced in queue UI (still requires human + dual review).

### 11.3 DMCA abuse

- Spam takedown: same IP files 50 notices in 1 day against random users → rate-limit caps + admin alert; cases tagged "potential_DMCA_abuse".
- Defective notice flooding: notices missing signature → 422 + tracked per-IP; auto-block after 10 defective in 24h.
- Targeted abuse: claimant repeatedly takes down same user's legitimate content → mod-side detection ("3 takedowns against same target, 0 sustained") surfaces to super-admin; future takedowns require manual gating.

### 11.4 False-positive recovery

- Test: a user's content is auto-hidden at score 0.91 due to an OpenAI mod miscall (verified by human review).
  - Verify case can be dismissed → content un-hides automatically.
  - Verify the user gets an in-app "we restored your content" notification.
  - Verify the false-positive does not bump their `RecentOffenderTracker`.
  - Verify the scan log keeps the original tool response for audit.

### 11.5 Reciprocal-report-bombing protection

- 5 users coordinate to mass-report user U at the same time. System behavior:
  - Each report still creates its own `Report` row (we want the data).
  - But all reports collapse into a single `ModerationCase` per subject (de-dup by `(subject_type, subject_id, status='open')`).
  - Reporter-side throttle (20/day) caps each attacker's count.
  - The `forced_human=false` case stays in its tier; we do **not** escalate tier just because count is high (otherwise attackers control routing). Master FR-M-2 thresholds are score-based only.
  - Additionally: pattern detector flags coordinated attack (≥5 reports of same subject from distinct accounts within 10 min) → super-admin alert + freeze the multi-reporter cluster.

### 11.6 CSAM hard-path

- Any `sexual/minors` true → tier_3_1h + `forced_human=true` + auto-NCMEC report task + content quarantined to admin-only S3 location + uploader auto-banned pre-review (master FR-M-3 supports permanent_ban; this is the one case where we pre-emptively temp-ban before human confirms, on the basis that delayed action here is unacceptable; super-admin confirms within 1h). Test that the pipeline runs to completion within SLA.

### 11.7 Multimodal evasion

- Send a chat message with text "you know what to do, friend" plus an image of a known-harassment meme. Text alone scores 0.2; image alone scores 0.7. Combined: routing should consider image at tier_2 and not let text-alone bias the decision.
- Test: encrypted-looking text (steganographic content). Embedding-dup catches if it matches a banned-text registry entry.

### 11.8 SLA breach tests

- Open a tier_3 case, advance system clock 70 min, run SLA scanner → `sla_breached_at` set, pager fired, status advances to `escalated` at +30 min past breach.

### 11.9 DMCA full lifecycle

- Notice → 24h hide test: insert notice, advance clock 24h, scanner fires hide, content `is_hidden=true`.
- Counter-notice → 14d restore test: insert counter, advance clock 14d, scanner fires restore.
- Suit-filed → permanent: counter filed, day 5 super-admin marks `suit_filed_notice_received_at`; advance to day 15; scanner skips this notice; content remains hidden indefinitely.

### 11.10 Action propagation completeness

- Fire `permanent_ban`. Assert within 60s:
  - 6 downstream consumers ack.
  - `propagation_status='complete'`.
  - User cannot log in.
  - User's badge is revoked.
  - All chat rooms read-only.
  - Subscription paused.
  - Notifications halted.
  - Outbound invites cancelled.
- Failure injection: take down notif-svc. Re-fire ban. Assert `propagation_status='partial'`, pager fires, ban still applied to all healthy services, replay queue picks up notif-svc when it recovers.

---

## 12. Acceptance criteria + verification

| AC | Verified by |
|---|---|
| Every chat text msg passes through the pipeline pre-publish | M-091 integration test that asserts no Message row is created without a `mod_scan_log` entry with the same `idempotency_key` |
| Auto-hide ≥0.9 → case visible to moderator within 1h SLA | M-094 load test + M-091 timing assertion |
| Soft-warn UX in §007 explains the flag | M-072 + manual UAT |
| Reporting flow chat → case in queue → SLA | M-091 happy-path test |
| Moderator can warn/hide/mute/ban from admin console | M-042 e2e test (Playwright) |
| DMCA hides within 24h, counter-notice restarts clock | M-093 e2e |
| Action log immutable | DB trigger test (insert + update attempt fails) |
| Permanent-ban fan-out completes in <60s, 6 services updated | M-057 + M-050 propagation test |
| Reciprocal-report-bombing does not bias routing | M-092 11.5 test |
| CSAM auto-quarantines | M-092 11.6 test (synthetic flag — not real CSAM; we use a labeled corpus) |
| SLA scanner fires every 5 min, breaches paged | M-013 verified in staging |
| §016 admin console: case resolved end-to-end in <60s | UAT timing |

---

## 13. Open risks + mitigations

1. **DMCA designated agent deferred → no §512(c) safe-harbor**.
   - Mitigation: explicit ToS clause + Community Guidelines section: "Colab is not currently a registered DMCA designated agent. We may still receive notices and act on them as a community-trust workflow, but this does not constitute a §512(c) safe-harbor election."
   - Track for post-launch: register agent (form + $6 fee + DMCA mailbox + agent name in ToS) — Phase 5 or M+3 follow-up.
   - Legal review of ToS language before launch.
2. **Cross-locale moderation thresholds (US/CA/AU/NZ/IN diverge)**.
   - Mitigation: thresholds + category weights are admin-configurable per-tenant; for launch we ship the US baseline and document that locale-specific tuning is Phase 5.
3. **Free OpenAI moderation API rate limits**.
   - Mitigation: Redis token bucket + back-pressure to chat-svc on burst; fallback to AWS Comprehend (stretch) if rate limit is breached for >5 min.
4. **CSAM handling**.
   - We are not legally a "provider of electronic communication service" with full NCMEC reporting obligations until certain thresholds — but our policy commits to NCMEC reporting on positive CSAM signal. Manual report workflow (not automated upload to NCMEC) at launch; automated CyberTipline submission deferred.
5. **Moderator burnout / vicarious-trauma**.
   - Operational risk, not engineering. Document a wellness rotation in the moderator playbook. Pixelated/blurred preview default for tier_3 imagery; click-to-reveal with audit log.
6. **Audit-log retention vs DSR erasure**.
   - Master compliance posture exempts audit logs from DSR erasure (3-year archived retention with pseudonymized IDs). Confirm legal team signs off on this exemption before launch; document on ToS.
7. **Append-only DB enforcement bypass**.
   - DB triggers prevent client UPDATE/DELETE; but a malicious DBA can disable triggers. Mitigation: row checksums in `audit.moderation_action_propagation` validated nightly; alerts on mismatch.
8. **Action propagation eventual-consistency window**.
   - 60s window between ban action and full fan-out completion. During this window the banned user could still send a message that scrolls into a chat. Mitigation: §007 chat-svc consults `/internal/user/{user_id}/state` (Redis-backed, <5ms) on every send; banned state set in Redis synchronously by the action endpoint, propagation is the slower DB+downstream piece.

---

## 14. Out-of-scope (Phase 5+)

- Cross-locale threshold tuning per master open item.
- Locale-specific DMCA equivalents (e.g., AU OnlineSafety Act takedown, IN IT Rules 2021 §3(2)(b) intermediary takedown). At launch we run DMCA-style workflow as a baseline; localization deferred.
- TikTok content moderation (TikTok integration deferred).
- Ad content moderation (Journey D deferred).
- Live-streaming moderation (no live streaming at launch).
- Automated CyberTipline reporting (manual NCMEC at launch).
- Translated-content moderation (chat translation deferred).
- Appeals workflow UI for users (text appeals via auto-opened support ticket at launch; dedicated appeal UI in P15+).

---

## 15. Phase order check

Per master §7 phase plan, this is **P7 — Moderation & Safety**. Hard dependencies:
- §002 Platform (FastAPI base, RabbitMQ, Postgres, Redis): must be live.
- §003 Auth: ban consumer + user lookup APIs ready.
- §007 Chat foundations: WebSocket service exists with hook points for pre-publish scan and `is_read_only` flag on rooms.

Soft dependencies acceptable at P7 start (consumers can be stubbed):
- §004 Profile: badge revoke consumer can ship as a stub; full integration with badge state machine lands in P7+.
- §013 Billing: subscription pause consumer stubbed initially; full Stripe + RC integration lands in P12 — at which point we wire the real handler. Meantime the dispatcher records `propagation_events.subscription_pause='deferred'`.
- §016 Admin console UI: moderator can use a CLI-issued action endpoint at P7 launch; full admin-web UI lands in P15. Moderator team operates from a thin internal Next.js page (M-041..M-044) that we ship out-of-band as P7.5.

This decoupling is intentional: we want moderation enforcement live before consumer features fully integrate (otherwise the platform can ship without safety rails).

---

## 16. Definitions

- **Tier**: the score-band routing classification (tier_0..tier_3) per master FR-M-2.
- **SLA**: time from case open to moderator claim. Distinct from time-to-action.
- **Forced human**: a flag that means score-band routing is overridden by a category-based forced-escalation rule (IP, harassment-threat, hate-threat, CSAM).
- **Propagation**: the fan-out from a single ModerationAction to all downstream services.
- **Append-only**: rows cannot be updated or deleted via the service or DB API; corrections happen via new rows with `parent_id` linkage.
- **Counter-notice statutory window**: 10–14 business days per §512(g)(2)(C); we pick 14 calendar days for claimant-friendliness.
- **Safe-harbor**: §512(c) protection from secondary copyright liability; **not claimed** by Colab at launch because DMCA designated agent is not registered.

---

End of plan.
