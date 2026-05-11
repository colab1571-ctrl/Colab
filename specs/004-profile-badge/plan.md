# 004 — Profile + AI Review + Valid Badge — Implementation Plan

**Phase**: P2 + P3.
**Service**: `profile-svc`.
**Master refs**: §0 locked decisions, §3 Journey A (FR-A-4 … FR-A-13), §3 cross-cutting moderation (FR-M-1, FR-M-2).
**Spec refs**: 004 spec, 003 spec (User entity + badge integration), `.env.example`.
**Posture**: Quality-first. Soft-block — only the Valid Profile Badge is gated; matching, chat, discovery proceed without it.

---

## 1. Mission Recap

Deliver the profile capture, persistence, and trust-issuance layer of Colab:

1. **Profile data**: display name, location (PostGIS point + Mapbox-resolved city), radius (locale default 50mi/80km, max "Anywhere"), 9-category vocations + curated sub-tags (free-text `other` flagged), bio (≤280ch), "obsessed with" (≤140ch), open-to-remote toggle, optional past experience and "what I'm looking for".
2. **Portfolio**: up to 12 items, image ≤10MB / audio ≤30MB / video ≤100MB, whitelisted MIME, S3 presigned uploads, AI moderation on each item.
3. **Optional content**: personality quiz (5–7 Qs → archetype), three OAuth links (Instagram Business/Creator, YouTube via Google, Spotify for Artists) with KMS-encrypted tokens.
4. **Trust**: AI profile review (OpenAI moderation text + AWS Rekognition Image + perceptual-hash dup + audio fingerprint dup + embedding semantic dup), risk-tier routing into `moderation-svc`, Valid Profile Badge state machine driven by `user.email_verified` + `identity.verified` + `ai_review_pending → passed`.
5. **Health score**: 40% completeness / 30% activity / 30% feedback per master spec, recomputed nightly + on update, used by matching-svc only (not exposed as a filter).
6. **Telemetry**: PostHog onboarding funnel; target ≥70% completion in <8 minutes.

Out of scope: badge-state UX surfaces beyond the API; moderation review console (lives in §016 admin); the dedicated personality screen (deferred per master); matching ranking math (§005); chat-bound media (§007).

---

## 2. Research Findings — Versions + Biggest Gotcha

| Topic | Version / Pin | Biggest gotcha |
|---|---|---|
| **SQLAlchemy 2.x async** | `sqlalchemy==2.0.36`, `asyncpg==0.30.0` | Implicit I/O — accessing an unloaded relationship outside an `await session.refresh()` raises `MissingGreenlet`. Always eager-load via `selectinload()` or set `lazy="raise"` on the model to fail fast. |
| **Alembic migrations** | `alembic==1.14.0` | Async engines need `run_sync()` around `context.run_migrations()` in `env.py`; autogenerate misses PostGIS column types unless `include_object` hook is set and `geoalchemy2` is imported in `env.py`. |
| **PostGIS for `location_point`** | PostGIS 3.4 on RDS Postgres 16 | `geography(Point,4326)` (not `geometry`) so radius math uses meters; `ST_DWithin` on a `geography` column requires a `GiST` index — without it 10k-row scans go from 5ms to 1.5s. |
| **pgvector profile embedding** | `pgvector==0.3.6`, ext 0.8.0; `text-embedding-3-large` = 3072-dim | `ivfflat` index hard-caps at 2000 dims. Use `hnsw` (`m=16, ef_construction=64`) which supports 2000+ dims, or reduce to 1024-dim via OpenAI `dimensions` param. We choose `dimensions=1536` and HNSW to stay under the cap with headroom. |
| **AWS Rekognition Image** | `boto3==1.35.x`, `DetectModerationLabels` v2 taxonomy | The v2 taxonomy released Aug 2024 changes label hierarchy ("Explicit Nudity" → "Explicit"). Pin to `ProjectVersion="LATEST"` *and* version-stamp every stored `ai_review_payload` so re-scoring after taxonomy change is deterministic. |
| **OpenAI moderation API** | `omni-moderation-latest` (multimodal, free tier) | The classifier returns `category_scores` per category; the `flagged` boolean uses provider thresholds that are *not* tunable. Don't trust `flagged` alone — store the raw `category_scores`, apply our own per-category thresholds, and let admins re-tune. |
| **OpenAI text-embedding-3-large** | `openai==1.54.x`, model `text-embedding-3-large` | Pass `dimensions=1536` at call time to match pgvector HNSW limits — if you don't, default 3072 silently won't index. Embed normalized text (lowercase, NFC-normalize, strip emoji) so identical-meaning bios cluster. |
| **Replicate webhooks (idempotency)** | `replicate==1.0.x` | Replicate retries webhooks up to 8h on non-2xx and the same `prediction.id` *can* appear out-of-order (`starting` after `succeeded`). Store a `WebhookReceipt(provider, external_id, payload_hash)` row with a unique index and treat duplicate as 200-no-op; never advance state backwards. |
| **Perceptual hashing (`imagehash`)** | `imagehash==4.3.1`, `Pillow==11.0.x`, `phash` algorithm | `phash` is 64-bit; Hamming distance ≤6 catches re-encodes/resizes but blows up on logos and screenshots (lots of black). Combine with `ahash` Hamming ≤10 as a second signal and disqualify either if image is <100×100. |
| **Audio fingerprinting (Chromaprint)** | `pyacoustid==1.3.0`, `fpcalc` 1.5.1 binary in Docker image | `fpcalc` needs `ffmpeg` and 30s+ of audio to give a stable fingerprint; <30s clips collide. For samples shorter than 30s fall back to MFCC mean-vector cosine via `librosa==0.10.x`. |
| **MJML email templates** | `mjml==4.15.x` via Node sidecar; Python wrapper `mjml-python==0.4.0` | MJML compilation is CPU-heavy (~80ms per render). Pre-compile templates at container build time to static HTML with `{{handlebars}}` placeholders; substitute at runtime. Never compile in the request path. |
| **S3 presigned URLs** | `boto3==1.35.x`, SigV4 | Presigned `PUT` URLs do **not** enforce `Content-Length` unless you sign with `Content-Length-Range` in a presigned POST policy. Use **presigned POST** (`generate_presigned_post`) with `["content-length-range", 0, MAX_BYTES]` and `["starts-with", "$Content-Type", "image/"]` to enforce caps server-side. |
| **Mapbox Geocoding API** | Search Box API v1 (Forward + Reverse) | Free tier = 100k req/mo; **600 req/min** hard limit and `5 req/sec per IP` for the public token. Always proxy through `geo-svc` with a Redis 24h cache keyed by `lower(query)+country` so typeahead doesn't burn budget. |

---

## 3. Detailed Data Model

All tables in `profile_svc` Postgres schema. PK = `uuid` (`gen_random_uuid()`) unless noted. All timestamps `timestamptz` default `now()`. FKs to `auth_svc.users.id` are logical (cross-service); we store `user_id uuid not null` and enforce referential integrity via the `user.created` event.

### 3.1 `profiles`

| Column | Type | Constraints | Index |
|---|---|---|---|
| `id` | uuid | PK | |
| `user_id` | uuid | NOT NULL, UNIQUE | unique btree |
| `display_name` | citext | NOT NULL, length 2–40, UNIQUE | unique btree |
| `bio` | text | length ≤ 280 (CHECK `char_length(bio) <= 280`) | |
| `obsessed_with` | text | length ≤ 140 (CHECK) | |
| `location_point` | `geography(Point,4326)` | nullable | **GiST** |
| `location_city` | text | nullable, ≤120 | btree (trigram for autocomplete echo) |
| `location_country` | char(2) | ISO-3166-1 alpha-2 | btree |
| `radius_value` | int | NOT NULL default 50, range 1–9999, sentinel 9999 = "Anywhere" | |
| `radius_unit` | text | CHECK in (`mi`,`km`), default by locale | |
| `open_to_remote` | bool | NOT NULL default false | partial idx where true |
| `experience_level` | smallint | CHECK 1–5, nullable | |
| `looking_for` | text | nullable ≤ 500 | |
| `past_experience` | text | nullable ≤ 1000 | |
| `personality_archetype` | text | nullable, FK-ish to enum table | btree |
| `profile_health_score` | real | default 0.0, CHECK 0–100 | btree desc for ranking |
| `badge_state` | text | NOT NULL default `'unverified'`, CHECK in state-machine set | btree |
| `badge_granted_at` | timestamptz | nullable | |
| `badge_held_reason` | text | nullable | |
| `is_visible_to_non_premium` | bool | NOT NULL default true | |
| `embedding` | `vector(1536)` | nullable | **HNSW** `m=16,ef_construction=64` |
| `created_at` | timestamptz | NOT NULL | |
| `updated_at` | timestamptz | NOT NULL, trigger-maintained | |
| `last_active_at` | timestamptz | nullable | btree desc |

Partial index `WHERE badge_state='badge_granted' AND is_visible_to_non_premium` to back the free-tier discovery feed.

### 3.2 `profile_vocations`

| Column | Type | Constraints | Index |
|---|---|---|---|
| `profile_id` | uuid | FK profiles.id ON DELETE CASCADE | |
| `category` | text | NOT NULL, CHECK in 9 fixed categories | composite (profile_id, category) unique |
| `subtag` | text | NOT NULL, refs taxonomy table OR `'other:<slug>'` | btree (subtag) |
| `is_primary` | bool | NOT NULL default false; exactly one true per profile | partial unique idx where is_primary |
| `flagged_for_review` | bool | default false (true when free-text) | |

### 3.3 `profile_skills` (free-text + normalization queue)

| Column | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `profile_id` | uuid | FK, CASCADE |
| `label_raw` | text | NOT NULL ≤ 40 |
| `label_normalized` | text | nullable; populated by normalization worker |
| `created_at` | timestamptz | |

Unique on `(profile_id, lower(label_raw))`.

### 3.4 `portfolio_items`

| Column | Type | Constraints | Index |
|---|---|---|---|
| `id` | uuid | PK | |
| `profile_id` | uuid | FK, CASCADE | btree |
| `position` | smallint | NOT NULL, CHECK 0–11 (cap 12) | composite (profile_id, position) unique |
| `type` | text | CHECK in (`image`,`audio`,`video`,`link`) | |
| `s3_bucket` | text | NOT NULL | |
| `s3_key` | text | NOT NULL | |
| `mime` | text | whitelisted | |
| `size_bytes` | bigint | CHECK `<= type_cap` (10/30/100 MB) | |
| `caption` | text | ≤ 200 | |
| `metadata` | jsonb | EXIF stripped; dimensions, duration, codec | GIN |
| `phash` | bigint | nullable; image only | btree |
| `ahash` | bigint | nullable | btree |
| `chromaprint_fp` | text | nullable; audio only | btree |
| `embedding` | `vector(1536)` | nullable | HNSW |
| `ai_review_status` | text | CHECK (`pending`,`passed`,`flagged`,`hidden`), default `pending` | btree |
| `ai_review_score` | real | nullable, 0–1 | |
| `ai_review_payload` | jsonb | provider raw responses, version-stamped | |
| `created_at` | timestamptz | | |

Partial index `WHERE ai_review_status='passed'` to back public renders.

### 3.5 `external_links`

| Column | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `profile_id` | uuid | FK, CASCADE |
| `provider` | text | CHECK (`instagram`,`youtube`,`spotify`) |
| `provider_handle` | text | display label |
| `provider_id` | text | stable account id |
| `encrypted_access_token` | bytea | KMS-envelope; see §10 |
| `encrypted_refresh_token` | bytea | nullable |
| `data_key_ciphertext` | bytea | KMS-wrapped DEK |
| `scopes` | text[] | granted scopes |
| `token_expires_at` | timestamptz | |
| `linked_at` | timestamptz | |
| `last_synced_at` | timestamptz | nullable |
| `sync_state` | text | (`ok`,`needs_reauth`,`revoked`) |

Unique on `(profile_id, provider)`.

### 3.6 `personality_answers`

| Column | Type | Constraints |
|---|---|---|
| `profile_id` | uuid | FK, CASCADE, part of PK |
| `question_key` | text | part of PK (composite PK) |
| `answer_key` | text | NOT NULL |
| `answered_at` | timestamptz | |

### 3.7 `profile_reviews`

| Column | Type |
|---|---|
| `id` | uuid PK |
| `profile_id` | uuid FK, CASCADE, btree |
| `target_kind` | text CHECK (`profile_text`,`portfolio_item`,`display_name`,`bio`) |
| `target_id` | uuid nullable (portfolio_items.id when applicable) |
| `kind` | text CHECK (`text`,`image`,`video`,`audio`) |
| `score` | real CHECK 0–1 |
| `reasons` | jsonb |
| `status` | text CHECK (`passed`,`flagged`,`escalated`,`overridden`) |
| `provider_versions` | jsonb (e.g., `{rekognition:"2024.08",openai_mod:"omni-2024-10"}`) |
| `created_at` | timestamptz |
| `decided_at` | timestamptz nullable |

Index on `(profile_id, created_at desc)`.

### 3.8 `vocation_taxonomy` (lookup, admin-editable)

| Column | Type |
|---|---|
| `category` | text PK part |
| `subtag` | text PK part |
| `display` | text |
| `is_active` | bool |
| `sort_order` | int |

### 3.9 `personality_questions` (admin-editable)

| Column | Type |
|---|---|
| `question_key` | text PK |
| `prompt` | text |
| `options` | jsonb (array of `{answer_key, label, weights:{archetype:float}}`) |
| `sort_order` | int |
| `is_active` | bool |

### 3.10 `webhook_receipts` (idempotency)

| Column | Type |
|---|---|
| `provider` | text |
| `external_id` | text |
| `payload_hash` | text |
| `received_at` | timestamptz |
| PK | `(provider, external_id)` |

### 3.11 Migration order (Alembic)

1. `0001_enable_extensions` — `CREATE EXTENSION postgis, vector, citext, pg_trgm`.
2. `0002_taxonomy_tables` — `vocation_taxonomy`, `personality_questions` (seed).
3. `0003_profiles` — base profile table (no embedding yet).
4. `0004_profile_dependents` — vocations, skills, portfolio_items, external_links, personality_answers, profile_reviews.
5. `0005_indexes_geo_vec` — GiST on `location_point`, HNSW on `profiles.embedding`, HNSW on `portfolio_items.embedding`.
6. `0006_webhook_receipts`.
7. `0007_partial_indexes` — `WHERE badge_state='badge_granted'`, `WHERE ai_review_status='passed'`.

---

## 4. Vocation Taxonomy — 9 Categories + Curated Sub-tags

The 9 top-level categories satisfy master FR-A-4. Each lists 8–20 sub-tags (admin-editable post-launch; shape locked). Free-text "other" goes to `profile_skills` with `flagged_for_review=true` for moderator triage.

### V1. Visual Arts
illustration, painting, mixed-media, oil-painting, watercolor, acrylic, gouache, ink, charcoal, pastel, printmaking, comics, manga, concept-art, character-design, storyboarding, mural, fine-art-photography.

### V2. Music & Audio
singer, songwriter, lyricist, music-producer, beatmaker, dj, instrumentalist-guitar, instrumentalist-piano, instrumentalist-strings, instrumentalist-percussion, vocalist-rap, vocalist-rnb, vocalist-indie, vocalist-classical, audio-engineer, mixing, mastering, sound-design, foley, podcast-host.

### V3. Performing Arts
actor-film, actor-theatre, actor-voice, dancer-contemporary, dancer-hiphop, dancer-classical, choreographer, stand-up-comedian, improv-performer, theatre-director, musical-theatre, drag-performer, performance-artist, circus-arts.

### V4. Film, Video & Animation
director, cinematographer, video-editor, colorist, gaffer, sound-recordist, animator-2d, animator-3d, motion-graphics, vfx-artist, screenwriter, documentarian, music-video-director, content-creator-shortform, content-creator-longform, youtuber.

### V5. Design
graphic-design, brand-identity, type-designer, ui-designer, ux-designer, product-designer, industrial-designer, fashion-designer, textile-designer, jewelry-designer, interior-designer, set-designer, costume-designer, web-designer, packaging-designer, illustrator-commercial.

### V6. Writing & Literature
novelist, short-fiction-writer, poet, essayist, journalist, copywriter, screenwriter-feature, screenwriter-tv, playwright, ghostwriter, editor, translator, literary-critic, technical-writer, newsletter-author, zine-maker.

### V7. Digital, Code & New Media
creative-technologist, generative-artist, interactive-designer, ar-vr-creator, game-designer, game-developer, indie-dev-solo, web3-creator, ai-artist, immersive-installation-artist, software-artist, data-visualization, livecoder, modder.

### V8. Craft, Fashion & Maker
ceramicist, sculptor, glassblower, woodworker, leatherworker, metalsmith, jeweler-maker, fashion-pattern-maker, tailor, milliner, knitter-fiber, embroidery, screen-printer, bookbinder, candlemaker, perfumer, floral-designer.

### V9. Producing, Curation & Direction
creative-director, art-director, music-director, producer-film, producer-music, producer-theatre, producer-events, curator-gallery, curator-music, festival-programmer, booker, manager-artist, label-founder, magazine-founder, gallery-founder, collective-organizer, creative-strategist.

**Shape lock**: exactly 9 categories; sub-tags stored as `(category, subtag)` rows in `vocation_taxonomy`; admin can edit `display`, `is_active`, `sort_order` and add new sub-tags without migration. Adding a 10th category requires a CHECK constraint migration (intentional friction).

---

## 5. Personality Quiz

**Goal**: Optional, ≤90 seconds, feeds a minor matching signal weight (per master). 6 questions chosen.

### 5.1 Questions (schema → `personality_questions`)

Each option carries weights toward archetypes (sum across an option = 1.0).

1. **`work_pace`** — *"When you're deep in a project, you…"*
   a. plan every beat ahead (Architect 0.7, Connector 0.3)
   b. ride the wave and edit later (Mystic 0.6, Maverick 0.4)
   c. ship a draft, then obsess (Craftsperson 0.7, Storyteller 0.3)
   d. need a collaborator in the room (Connector 0.8, Producer 0.2)

2. **`feedback_style`** — *"Best feedback you ever got was…"*
   a. brutally specific (Architect 0.5, Craftsperson 0.5)
   b. emotionally validating (Mystic 0.6, Connector 0.4)
   c. one provocative question (Maverick 0.7, Producer 0.3)
   d. "I'd buy this" (Showrunner 0.6, Producer 0.4)

3. **`risk_appetite`** — *"You'd rather…"*
   a. nail what you know (Craftsperson 0.7, Architect 0.3)
   b. invent a new lane (Maverick 0.8, Mystic 0.2)
   c. translate between worlds (Connector 0.6, Storyteller 0.4)
   d. scale what works (Producer 0.7, Showrunner 0.3)

4. **`collab_role`** — *"In a duo, you naturally…"*
   a. set the vision (Architect 0.5, Showrunner 0.5)
   b. hold the room together (Connector 0.8, Producer 0.2)
   c. push the weird (Maverick 0.6, Mystic 0.4)
   d. polish the output (Craftsperson 0.8, Storyteller 0.2)

5. **`success_metric`** — *"A project is 'done' when…"*
   a. it's perfect (Craftsperson 0.8, Architect 0.2)
   b. it moves someone (Storyteller 0.7, Mystic 0.3)
   c. people are using it (Producer 0.6, Showrunner 0.4)
   d. it changed your mind (Maverick 0.6, Mystic 0.4)

6. **`energy_source`** — *"You're recharged by…"*
   a. solitude + a notebook (Mystic 0.7, Craftsperson 0.3)
   b. a packed studio session (Connector 0.6, Showrunner 0.4)
   c. blueprint + spreadsheets (Architect 0.7, Producer 0.3)
   d. an argument worth having (Maverick 0.6, Storyteller 0.4)

### 5.2 Scoring → Archetype

For each archetype `A`, score = `Σ option_weight_for_A`. The archetype with the highest score wins; ties broken by question 1 then question 4. Persist all 6 answers, the score vector (jsonb), and the chosen archetype.

### 5.3 Archetypes (8)

| Key | One-line |
|---|---|
| `architect` | Plans the whole arc before laying a brick. |
| `craftsperson` | Lives for the detail nobody else would notice. |
| `mystic` | Trusts the vibe, makes work that feels inevitable. |
| `maverick` | Allergic to the obvious, picks the weird door. |
| `connector` | Makes great work happen by making rooms work. |
| `storyteller` | Smuggles meaning inside something that moves you. |
| `producer` | Turns the spark into the schedule into the shipped thing. |
| `showrunner` | Holds vision, budget, and people in one head. |

---

## 6. Profile Health Score — Formula

Master spec mandates 40% completeness / 30% activity / 30% feedback. Score is float 0–100. Recomputed (a) synchronously on profile mutation (debounced 60s), (b) nightly via Celery Beat for all profiles, (c) on `feedback.created` events from §008/§009.

```
health = 100 * (0.40 * completeness + 0.30 * activity + 0.30 * feedback)
```

### 6.1 Completeness (0–1)

Weighted checklist, each 0/1 unless noted:

| Field | Weight |
|---|---|
| display_name set | 0.05 |
| location_point + city set | 0.10 |
| ≥1 vocation with primary flag | 0.10 |
| bio length ≥ 60 chars | 0.08 |
| obsessed_with set | 0.05 |
| ≥3 portfolio items passed review | 0.30 (linear up to 6 items, then capped) |
| ≥1 external link connected | 0.10 |
| personality quiz completed | 0.05 |
| experience_level set | 0.04 |
| looking_for set | 0.06 |
| past_experience set | 0.04 |
| selfie+liveness approved | 0.03 |

`completeness = Σ weight_i * achieved_i`, clamped to [0,1].

### 6.2 Activity (0–1)

```
activity = 0.4 * recency + 0.3 * weekly_logins + 0.3 * portfolio_freshness
```

- `recency`: exponential decay on `last_active_at`. `recency = exp(-days_since/14)`, clamped 0–1.
- `weekly_logins`: distinct login days in last 28 days / 14 (cap 1.0).
- `portfolio_freshness`: `min(1.0, additions_or_edits_last_90d / 3)`.

### 6.3 Feedback (0–1)

Driven by §009 collab feedback (`thumbs_up`, `thumbs_down`, `tag_chips`):

```
n = thumbs_up + thumbs_down
laplace_ratio = (thumbs_up + 1) / (n + 2)                     # Laplace smoothing
volume_factor = min(1.0, n / 10)                              # full credit at 10+ feedback events
tag_boost     = min(0.1, distinct_positive_tag_chips * 0.02)  # caps at +0.1
feedback = clamp(laplace_ratio * volume_factor + tag_boost, 0, 1)
```

New profiles with `n=0` get `feedback = 0.5` (neutral prior) so they aren't penalized at launch.

### 6.4 Reporting

`profile_health_score` is **never exposed as a filter** (per FR-B-5) but is returned to the owner on `GET /profile/me` for transparency, and to `matching-svc` via the internal embedding endpoint.

---

## 7. AI Profile Review Pipeline

```
        +----------------------+
        |  profile.updated     |
        |  or portfolio.added  |
        +----------+-----------+
                   |
        +----------v-----------+
        |  review-orchestrator |
        |  (Celery task)       |
        +----------+-----------+
                   |
       +-----------+-----------+----------------+--------------+
       |                       |                |              |
+------v-------+      +--------v--------+   +---v-----+   +----v-----+
| text fan-out |      | image fan-out   |   |  audio  |   |  video   |
| bio/obsessed |      | portfolio image |   | portfo. |   | portfo.  |
+------+-------+      +--------+--------+   +---+-----+   +----+-----+
       |                       |                |              |
+------v-------+   +-----------+--+   +--+------v---+   +------v-----+
| OpenAI mod.  |   | Rekognition  |   | Chromaprint  |  | Rekognition|
| (omni-2024)  |   | Moderation   |   | fp + dup     |  | Video Mod  |
+------+-------+   +----+----+----+   +------+-------+  +------+-----+
       |                |    |               |                 |
       |          +-----v+   v +------+      |                 |
       |          | pHash |  | aHash |      |                 |
       |          | dup   |  | dup   |      |                 |
       |          +---+---+  +---+---+      |                 |
       |              |          |          |                 |
       |   +----------+----------+----------+-----------------+
       |   |
+------v---v-----------+
| embedding semantic   |   <-- text-embedding-3-large @ 1536d
| dup (cosine vs corp) |       pgvector HNSW nearest-neighbor
+----------+-----------+
           |
+----------v-----------+
| Risk Aggregator      |
|  score = max(        |
|    weighted blend    |
|  )                   |
+----------+-----------+
           |
   +-------+--------+----------+-------------+
   | <0.4           | 0.4-0.7  |  0.7-0.9    |  >=0.9
   v                v          v             v
auto-allow      soft-warn    hide content   auto-hide + temp-mute
+ log           + mod queue  + mod queue    + mod queue
                (24h SLA)    (6h SLA)       (1h SLA)
```

**Aggregation weights** (admin-tunable):
`risk = 0.35 * max_category(openai_mod) + 0.35 * max_label(rekognition) + 0.20 * dup_signal + 0.10 * embedding_outlier`.

- `dup_signal` = 1.0 if any phash Hamming ≤6, ahash Hamming ≤10, or Chromaprint cosine ≥0.92 against an existing distinct user's asset, else 0.
- `embedding_outlier` = 1.0 if profile bio cosine ≥0.98 vs any other profile's bio (likely copy-paste), else 0.

**Always-human routing**: any signal of IP claim, weapon imagery, sexual content involving real persons, or contact-info doxxing skips score routing and goes straight to humans (queue priority HIGH).

**Output**: one `profile_reviews` row per kind + an aggregate row. Emits `profile.review_completed` event consumed by the badge state machine.

---

## 8. Badge State Machine

### 8.1 States

`unverified`, `email_verified`, `identity_pending`, `identity_approved`, `ai_review_pending`, `badge_granted`, `badge_held`, `badge_revoked`.

### 8.2 Transitions

| From | Event | To | Side effect |
|---|---|---|---|
| `unverified` | `user.created` (003) | `unverified` | profile shell created (idempotent) |
| `unverified` | `user.email_verified` (003) | `email_verified` | emit `profile.email_verified` |
| `email_verified` | `identity.inquiry_started` (003) | `identity_pending` | none |
| `email_verified` | (no Persona inquiry, profile is otherwise saved) | `email_verified` | sticky; badge withheld |
| `identity_pending` | `identity.verified` (003) | `identity_approved` | fire AI review |
| `identity_pending` | `identity.declined` (003) | `email_verified` | retry path open |
| `identity_pending` | `identity.needs_review` (003) | `identity_pending` | route to §008 mod queue |
| `identity_approved` | `ai.review.started` (internal) | `ai_review_pending` | none |
| `ai_review_pending` | `profile.review_completed` score <0.4 | `badge_granted` | emit `profile.badge_granted`, set `badge_granted_at` |
| `ai_review_pending` | `profile.review_completed` score 0.4–0.7 | `badge_held` | `badge_held_reason='soft_flag'`, mod queue entry, 24h SLA |
| `ai_review_pending` | `profile.review_completed` score 0.7–0.9 | `badge_held` | reason `'content_hidden'`, 6h SLA |
| `ai_review_pending` | `profile.review_completed` score ≥0.9 | `badge_held` | reason `'severe_flag'`, 1h SLA + emit `user.temp_mute_requested` |
| `badge_held` | `moderation.cleared` (008) | `badge_granted` | emit `profile.badge_granted` |
| `badge_held` | `moderation.upheld` (008) | `badge_revoked` | emit `profile.badge_revoked` |
| `badge_granted` | `profile.updated` (material text/image) | `ai_review_pending` | re-review (badge stays visible during re-review, flag in audit) |
| `badge_granted` | `moderation.upheld` (post-hoc report) | `badge_revoked` | propagate |
| `badge_granted` | `POST /profile/me/badge/recheck` | `ai_review_pending` | rate-limited 1/24h |
| `badge_revoked` | `moderation.appeal_upheld` | `badge_granted` | reinstate |
| any | `user.deleted` (003) | terminal | cascade row-delete |

Re-reviews are debounced 60s on profile mutation. `badge_state` and `badge_granted_at` are surfaced on every public profile read.

---

## 9. API Contracts

All endpoints under `profile-svc`. Auth = bearer JWT from `auth-svc`. Errors per platform error envelope. Routes mounted at `/api/v1`.

### 9.1 Profile CRUD

**`GET /profile/me`** → `200`
```yaml
resp:
  id: uuid
  user_id: uuid
  display_name: string
  bio: string|null
  obsessed_with: string|null
  location: {lat: float, lng: float, city: string, country: string}|null
  radius: {value: int, unit: "mi"|"km"}
  open_to_remote: bool
  experience_level: 1..5|null
  looking_for: string|null
  past_experience: string|null
  vocations: [{category, subtag, is_primary}]
  skills: [{label_raw, label_normalized}]
  personality_archetype: string|null
  portfolio: [PortfolioItem]
  externals: [{provider, provider_handle, linked_at, sync_state}]
  badge_state: enum
  badge_granted_at: timestamp|null
  profile_health_score: float
  last_active_at: timestamp|null
```

**`PATCH /profile/me`** body subset of mutable fields; server-side enforces bio ≤280, obsessed ≤140. Returns updated profile. Emits `profile.updated`.

**`GET /profile/{handle}`** (handle = display_name) — public view; honors blocks (§007), hides PII (only city + country, never lat/lng), respects `is_visible_to_non_premium`. Returns `404` for blocked, `403` if hidden. Subject to badge visibility annotation.

### 9.2 Portfolio (presigned upload)

**`POST /profile/me/portfolio/upload-url`** — request presigned POST policy.
```yaml
req:
  type: "image"|"audio"|"video"
  mime: string  # must be whitelisted
  size_bytes: int
resp: # 200
  upload:
    url: string
    fields: {key, policy, x-amz-credential, x-amz-algorithm, x-amz-date, x-amz-signature, Content-Type}
    conditions:
      content-length-range: [0, 10485760|31457280|104857600]
  portfolio_item_id: uuid   # pre-allocated; row in 'pending' state
  expires_at: timestamp     # 15 min
errors:
  413: size over cap
  415: mime not whitelisted
  409: portfolio already at cap (12 items)
```

Client `POST`s directly to S3. Then:

**`POST /profile/me/portfolio/{id}/finalize`**
```yaml
req:
  caption?: string  # <= 200
  position?: int    # 0-11
resp: 200 PortfolioItem (ai_review_status='pending')
side-effects:
  - verify S3 object exists, size matches, content-type matches via head_object
  - extract metadata (pillow / ffprobe sidecar)
  - emit profile.portfolio_added
  - fire ai review pipeline
```

**`DELETE /profile/me/portfolio/{id}`** → 204; S3 object soft-deleted (versioned bucket retains for 30d).

**`PATCH /profile/me/portfolio/reorder`** body `{order: [item_id]}` → 200.

### 9.3 Vocations, Skills, Personality

**`PUT /profile/me/vocations`** body `{vocations: [{category, subtag, is_primary}]}` — replace set. Validates against `vocation_taxonomy`; unknown subtag → either rejected (`strict=true`) or accepted as `other:<slug>` with `flagged_for_review=true` (default).

**`PUT /profile/me/skills`** body `{labels: [string]}` (≤ 20).

**`POST /profile/me/personality`**
```yaml
req:
  answers: [{question_key, answer_key}]   # 5-7
resp:
  archetype: enum
  scores: {archetype: float}
```

### 9.4 External OAuth links

**`POST /profile/me/externals/{provider}/connect`** — kicks off OAuth state.
```yaml
resp:
  authorize_url: string  # signed state token embedded
  state: string
```

**`GET /oauth/{provider}/callback?code=...&state=...`** — exchange + persist (§10). Returns 302 to deep link `colab://profile/externals?status=connected&provider=...`.

**`DELETE /profile/me/externals/{provider}`** → 204; revokes provider token if API allows; clears stored ciphertext.

### 9.5 Badge

**`GET /profile/me/badge`**
```yaml
resp:
  state: enum
  granted_at: timestamp|null
  held_reason: string|null
  next_action: "verify_email"|"verify_identity"|"awaiting_ai_review"|"mod_review"|null
  ai_review_summary: {latest_score: float, hidden_items: int}
```

**`POST /profile/me/badge/recheck`** — rate-limited 1/24h.
```yaml
resp:
  queued: bool
  earliest_next_recheck_at: timestamp
```

### 9.6 Internal (gateway-scoped, service auth)

**`GET /internal/profile/{id}/embedding`** — returns 1536-d vector for matching-svc.

**`GET /internal/profile/by-user/{user_id}/summary`** — id + badge_state + health_score (for discovery-svc and notification-svc).

### 9.7 Webhooks (inbound)

**`POST /webhooks/replicate`** — for embedding async jobs and AI mockup-related re-review. Idempotent via `webhook_receipts`.

### 9.8 Queue events (emitted)

`profile.created`, `profile.updated`, `profile.health_recomputed`, `profile.badge_granted`, `profile.badge_held`, `profile.badge_revoked`, `profile.portfolio_added`, `profile.portfolio_flagged`, `profile.review_completed`, `profile.external_linked`, `profile.external_unlinked`.

---

## 10. OAuth Provider Linking (KMS Envelope Encryption)

### 10.1 Shared pattern: AWS KMS envelope encryption

For each token persisted:

1. Generate a 32-byte **DEK** via `kms:GenerateDataKey` against `KMS_KEY_ID_TOKENS` (one CMK per env). KMS returns plaintext + ciphertext.
2. AES-256-GCM encrypt the token with the plaintext DEK, 12-byte random IV, AAD = `f"{provider}:{profile_id}:{token_kind}"`.
3. Persist `encrypted_access_token = iv || ciphertext || tag`, `data_key_ciphertext`, `provider`, `scopes`, `token_expires_at`.
4. Zero the plaintext DEK from memory.
5. On read: `kms:Decrypt(data_key_ciphertext)` → DEK → AES-GCM decrypt with same AAD. Cache decrypted token in process memory for ≤ token TTL minus 60s; never in Redis.
6. CMK has automatic rotation enabled (annual). DEKs are re-wrapped lazily on next write — old DEKs remain decryptable via key version metadata kept by KMS.
7. Key access: IRSA-scoped role with `kms:Decrypt` + `kms:GenerateDataKey` only on the tokens CMK; CloudTrail audit on every call.

### 10.2 Instagram (Meta Graph API — Business/Creator)

- **App config**: Meta App Type "Business"; product "Instagram Graph API"; permissions: `instagram_basic`, `pages_show_list`, `business_management`, `instagram_manage_insights` (read-only, no posting).
- **Auth flow**: OAuth 2.0 via `https://www.facebook.com/v21.0/dialog/oauth` → short-lived user token → exchange for long-lived (60d) page token via `/oauth/access_token?grant_type=fb_exchange_token`.
- **Scopes stored**: `instagram_basic,pages_show_list,business_management,instagram_manage_insights`.
- **Refresh**: long-lived tokens **don't refresh** but can be **refreshed** before 60d via `GET /refresh_access_token`. Celery Beat job daily: any link with `token_expires_at < now + 7d` → refresh; failure ⇒ `sync_state='needs_reauth'` + push notification.
- **Revocation**: `DELETE /{user-id}/permissions` on disconnect.
- **Gotcha**: only Business or Creator accounts work; personal IG accounts fail at `/me/accounts`. Handle with explicit "convert your account" error copy.

### 10.3 YouTube (Google OAuth + Data API v3)

- **Auth flow**: standard Google OAuth 2.0; scopes `https://www.googleapis.com/auth/youtube.readonly` + `userinfo.profile`. `access_type=offline`, `prompt=consent` to guarantee a refresh token.
- **Token lifecycle**: access token ~1h, refresh token long-lived. Store both KMS-encrypted.
- **Refresh**: on demand, before API call when `token_expires_at < now + 60s`. POST to `https://oauth2.googleapis.com/token` with `grant_type=refresh_token`.
- **Revocation**: `POST https://oauth2.googleapis.com/revoke?token=<refresh_token>`.
- **Pulled data**: `channels.list?part=snippet,statistics,brandingSettings` for handle + thumbnail + subs count; `playlists.list` for top 3 uploads. Cached 24h.
- **Gotcha**: Google's unverified-app screen for sensitive scopes — keep to `youtube.readonly` (non-sensitive) to avoid the verification gauntlet at launch.

### 10.4 Spotify for Artists (Spotify Web API)

- **Auth flow**: OAuth 2.0 Authorization Code with PKCE; scopes `user-read-private,user-read-email,user-top-read`. (Note: Spotify for Artists analytics endpoints are gated; at launch we surface only public artist profile + top tracks for the linked user — confirm gating, mark `[OPEN]` if Spotify denies analytics scope.)
- **Token lifecycle**: access 1h, refresh long-lived. Store both KMS-encrypted.
- **Refresh**: POST `https://accounts.spotify.com/api/token` `grant_type=refresh_token`. Some refresh requests rotate the refresh token — always persist the new one if returned.
- **Revocation**: no API endpoint; user must revoke in Spotify settings. We mark sync_state revoked on first 401.
- **Gotcha**: PKCE required; can't use the implicit grant. Validate `state` AND `code_verifier` round-trip; store `code_verifier` in Redis keyed by state (TTL 10m).

### 10.5 Common security

- All redirect URIs registered against `${APP_DOMAIN}/oauth/{provider}/callback` over HTTPS only.
- `state` parameter = HMAC-signed JWT carrying `profile_id`, `nonce`, `exp=10min`.
- Tokens never logged. Sentry scrubber pattern `*_token` / `*_secret`.
- Tokens never returned over API; only `provider_handle`, `scopes`, `sync_state` are surfaced.

---

## 11. Implementation Tasks

Grouped by sub-area. `id / title / outcome / est_hours / blocks / blocked_by`.

### A. Database & migrations

- **DB-01** Enable extensions migration / postgis+vector+citext+pg_trgm enabled / 2h / DB-02 / —
- **DB-02** Profiles table + indexes / table live / 4h / DB-03,DB-04,DB-05,DB-06,DB-07,DB-08 / DB-01
- **DB-03** Vocations + taxonomy seed / categories + sub-tags loaded / 4h / API-04 / DB-02
- **DB-04** Skills + normalization queue / table + queue job stub / 3h / API-05 / DB-02
- **DB-05** Portfolio items + asset hash columns / table live with phash/ahash/chromaprint cols / 4h / SVC-04,API-06 / DB-02
- **DB-06** External links + KMS columns / table live, KMS DEK columns ready / 3h / SVC-06 / DB-02
- **DB-07** Personality questions + answers + seed / 6 Qs seeded / 3h / API-07 / DB-02
- **DB-08** Profile reviews + webhook receipts / tables live / 3h / SVC-05 / DB-02
- **DB-09** Vector indexes (HNSW) / both vector cols indexed / 3h / SVC-07 / DB-02,DB-05

### B. Services & workers

- **SVC-01** profile-svc scaffold (FastAPI + async SQLAlchemy + alembic + DI) / service boots, healthcheck / 6h / all API-* / —
- **SVC-02** Event consumer (RabbitMQ): `user.created`, `user.email_verified`, `identity.*` → state machine / events advance badge_state / 8h / API-09 / SVC-01, DB-02
- **SVC-03** Badge state machine module (pure-Python FSM, table-driven) / 100% transition test coverage / 6h / SVC-02,SVC-05 / —
- **SVC-04** S3 presigned-POST issuance + finalize verify (head_object, mime sniff, metadata extract via Pillow + ffprobe) / upload caps enforced server-side / 10h / API-06 / DB-05
- **SVC-05** AI review orchestrator (Celery): text + image + audio + video fan-out, aggregator, idempotent / aggregate score persisted; events emitted / 16h / SVC-03 / DB-08, SVC-04
- **SVC-06** OAuth provider clients (IG/YouTube/Spotify) + KMS envelope helper / 3 providers connect+refresh+disconnect / 12h / API-08 / DB-06
- **SVC-07** Embedding job (Celery): bio + obsessed + vocations + portfolio captions → 1536d vector / row updated; HNSW index used / 6h / matching-svc / DB-09
- **SVC-08** Health score computer (sync on update + nightly Celery Beat) / score persists, recomputes on feedback events / 8h / API-01 / DB-02
- **SVC-09** Vocation free-text → normalization queue worker / `other:<slug>` rows surfaced to admin / 5h / admin-svc / DB-04
- **SVC-10** PostHog onboarding event emitter (server-side mirror; client also emits) / funnel events appear in PostHog / 4h / — / SVC-01

### C. API endpoints

- **API-01** GET/PATCH /profile/me / endpoints live with validation / 6h / RN integration / SVC-01, DB-02
- **API-02** GET /profile/{handle} (public view + block honor + visibility) / endpoint live / 6h / discovery-svc / API-01
- **API-03** GET /internal/profile/* (service-auth) / endpoints live / 3h / matching-svc, discovery-svc / SVC-01
- **API-04** PUT /profile/me/vocations / endpoint live, taxonomy validated / 4h / — / DB-03
- **API-05** PUT /profile/me/skills / endpoint live, normalization queued / 3h / — / DB-04, SVC-09
- **API-06** Portfolio endpoints (upload-url, finalize, delete, reorder) / full flow works against S3 / 10h / SVC-05 / SVC-04, DB-05
- **API-07** POST /profile/me/personality / scoring + persistence / 5h / — / DB-07
- **API-08** OAuth endpoints (connect, callback, disconnect) for 3 providers / 3 providers round-trip / 12h / — / SVC-06
- **API-09** Badge endpoints (GET badge, POST recheck) / surfaces state machine; rate-limit 1/24h via Redis / 4h / RN / SVC-03

### D. Content & ops

- **CON-01** Vocation taxonomy seed (9 cats + 8–20 subtags ea.) committed as Alembic data migration / lookup table seeded / 4h / DB-03 / —
- **CON-02** Personality quiz content seed / 6 Qs + options committed / 3h / DB-07 / —
- **CON-03** MJML email templates: badge granted, badge held, OAuth reauth needed, AI flag soft warning / 4 emails compile, render to HTML at build time / 6h / notification-svc / —

### E. Tests

- **TST-01** Unit tests for FSM (all 20+ transitions) / pytest passes / 4h / — / SVC-03
- **TST-02** Contract tests for all API endpoints (schemathesis) / OpenAPI matches behavior / 6h / — / API-01..09
- **TST-03** Integration tests against localstack S3 + Postgres + Redis / upload flow E2E / 8h / — / SVC-04, API-06
- **TST-04** AI review pipeline test with stubbed providers + fixture media / aggregator routes correctly per tier / 6h / — / SVC-05
- **TST-05** Load test profile read at 300 RPS / P95 <100ms with cache hot / 4h / — / API-01

Estimated total ≈ 180 hours.

---

## 12. Acceptance Criteria & Test Commands

Each criterion is a self-contained `pytest` invocation runnable in `services/profile-svc/`.

1. **Profile shell auto-created on `user.created`** (idempotent)
   `pytest tests/integration/test_event_user_created.py::test_creates_shell_idempotent -q`
2. **Bio ≤280 / obsessed ≤140 enforced server-side**
   `pytest tests/api/test_profile_validation.py::test_bio_length_280 tests/api/test_profile_validation.py::test_obsessed_length_140 -q`
3. **Portfolio caps: image 10MB / audio 30MB / video 100MB → 413 on overage**
   `pytest tests/api/test_portfolio_caps.py -q`
4. **Portfolio cap of 12 items returns 409**
   `pytest tests/api/test_portfolio_caps.py::test_max_12 -q`
5. **City autocomplete proxies geo-svc and caches**
   `pytest tests/integration/test_geo_proxy.py::test_cache_hit -q`
6. **IG / YouTube / Spotify OAuth round-trip persists KMS-encrypted tokens**
   `pytest tests/integration/test_oauth_providers.py -q --providers=ig,youtube,spotify`
7. **`identity.verified` advances to `ai_review_pending` and review fires**
   `pytest tests/integration/test_event_identity_verified.py -q`
8. **AI review pass → `badge_granted`; flag → `badge_held` + mod queue entry**
   `pytest tests/integration/test_ai_review_routing.py -q`
9. **Badge recheck rate-limited 1/24h**
   `pytest tests/api/test_badge_recheck_ratelimit.py -q`
10. **Health score recomputes on update (≤200ms) and nightly**
    `pytest tests/integration/test_health_score.py -q`
11. **All 20+ FSM transitions covered**
    `pytest tests/unit/test_badge_fsm.py --cov=profile_svc.badge --cov-fail-under=100 -q`
12. **OpenAPI matches implementation (schemathesis)**
    `pytest tests/contract -q`
13. **Onboarding completion ≥70% in <8 min (PostHog funnel) — operational**
    `pytest tests/posthog/test_funnel_assertion.py -q` (asserts events emitted; real funnel measured in PostHog)
14. **Profile read P95 <100ms at 300 RPS (cache warm)**
    `pytest -q tests/load/test_profile_read_p95.py --rps=300 --p95-budget-ms=100`
15. **AI review pipeline P95 e2e <60s (async)**
    `pytest -q tests/load/test_ai_pipeline_latency.py --p95-budget-s=60`

A single rollup: `pytest -q` must be green pre-merge.

---

## 13. Open Risks

- **R-1** Spotify for Artists analytics scope may be denied at app review — fallback is public-artist data only. Track via `[OPEN]` in 10.4.
- **R-2** Rekognition v2 moderation taxonomy could shift again post-launch; mitigation: every `profile_reviews` row carries `provider_versions`. Action: write a re-score Celery job we can run on demand.
- **R-3** HNSW recall vs ivfflat tradeoffs — HNSW chosen for dimension cap, but accuracy on 1536d vs 3072d worth measuring once we have 5k+ profiles. Owner: matching-svc team, coordinate at P4.
- **R-4** PostGIS GiST tuning at 100k DAU — re-evaluate `WHERE last_active_at > now()-90d` partial-index pattern when feed traffic patterns are known.
- **R-5** OAuth refresh storms (3 providers × N users) could spike on Day 1 of launch + 60d; stagger Beat job by `user_id % 60` buckets.
- **R-6** Free-text "other" vocation could become a backdoor for handles/abuse — normalization queue must moderate before exposure.
- **R-7** Personality archetype mapping is hand-weighted; bias-audit before launch (sample 1k profiles, check archetype distribution doesn't collapse on one bucket).
- **R-8** DMCA agent deferred at platform level (master §0) — any portfolio-IP claim handled fully via human queue routing; profile-svc only flags, doesn't adjudicate.
