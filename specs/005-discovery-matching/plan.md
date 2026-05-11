# 005 — Discovery + Matching — Implementation Plan

**Spec**: `005-discovery-matching/spec.md`
**Depends on**: 002 Platform, 003 Auth+Identity, 004 Profile+Badge, 013 Billing (soft)
**Services built here**: `discovery-svc`, `matching-svc`, `geo-svc`
**Phase**: P4 (after P2/P3 profile + badge work lands)
**Date drafted**: 2026-05-11

---

## 1. Mission Recap

Build the home feed and the AI-ranking engine that powers it. Users (Free or Premium) see a ranked list of other creators selected by a five-signal score. The feed renders in two UX modes — infinite scroll list and a swipeable card stack — with the choice persisted per user. Free users are hard-capped at 30 profiles per rolling calendar day; Premium users see no cap. An "AI Recommended Profiles" section ("Picked for you") sits at the top of the feed and in its own tab, refreshed nightly. Users can hide a profile for 3 months or save it to a private list. Geospatial radius filtering is PostGIS-backed; city autocomplete goes through a Mapbox proxy. The entire ranking pipeline runs in Postgres with pgvector; Redis caches hot feed pages. Profile health is an internal ranking signal only — it is never surfaced in filter controls or API responses to clients.

The anti-pattern the platform is designed to avoid: engagement farming. The feed must be productive-first; randomization (10 %) prevents filter-bubble lock-in without sacrificing match quality.

---

## 2. Research

### 2.1 pgvector Index: HNSW vs IVFFlat

**Recommendation: HNSW.**

| Dimension | HNSW | IVFFlat |
|---|---|---|
| Recall at k=10 | ~98 % (high) | ~90–95 % (tunable, lower by default) |
| Build time | Longer (~2–4× slower) | Fast |
| Query latency (1M vectors) | ~5–20 ms | ~10–40 ms (with probes tuning) |
| Index size | Larger (~1.4–1.8× raw) | Smaller |
| Incremental inserts | Supported (no rebuild) | Requires periodic rebuild or `lists` re-tune |
| Cold-start (few vectors) | Works fine | Needs `lists` = sqrt(n) calibration |

IVFFlat requires knowing approximate cardinality at build time to set `lists` correctly, and degrades with new inserts unless periodically rebuilt. HNSW handles the incremental profile-creation pattern cleanly (new users register continuously), maintains consistently high recall without probes tuning, and query latency is lower for the k values we need (k=200 for nightly recompute; k=20 for on-demand). The storage penalty (~1.4× versus IVFFlat) is acceptable.

**DDL**:
```sql
CREATE INDEX idx_profile_embedding_hnsw
  ON profile_embeddings
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
```

Set `SET hnsw.ef_search = 100` at query time for the nightly job; `SET hnsw.ef_search = 40` for on-demand latency-sensitive queries.

### 2.2 PostGIS GIST Index for `location_point`

```sql
CREATE INDEX idx_profile_location_gist
  ON profiles
  USING GIST (location_point);
```

`ST_DWithin` with a geography cast is index-accelerated against this GIST index. For radius queries the geography variant is required because it handles spherical distance correctly across large distances (e.g., "Anywhere" mode).

```sql
-- 80 km radius example
SELECT p.id FROM profiles p
WHERE ST_DWithin(
  p.location_point::geography,
  ST_MakePoint($lng, $lat)::geography,
  80000  -- metres
);
```

Unit conversion: US/CA → 50 mi (80 467 m), AU/NZ/IN → 80 km (80 000 m). Locale inferred from `Profile.radius_unit` (set at signup via `FEATURE_REGION_ALLOWLIST` + IP hint). "Anywhere" = no spatial filter applied (unlimited radius).

### 2.3 Redis Sorted Sets for Hot Feed Cache

Feed pages are stored as Redis Sorted Sets keyed by:
```
feed:<user_id>:<mode>:<filter_hash>
```
Members are `profile_id` strings; score is the descending `match_score` (stored as negative so `ZRANGE ... REV` with offset/count gives natural pagination).

**Cursor pagination** is an integer offset into the sorted set. The client receives an opaque base64 cursor that encodes `(filter_hash, offset)`. On cursor advance: `ZRANGE feed:<uid>:<mode>:<fhash> <offset> <offset+page_size-1> REV`.

TTL: **30 seconds** for live feed pages. This means a user who scrolls continuously sees fresh-enough data without a Postgres hit on every page flip. On filter change or mode toggle the cursor resets and a new cache entry is generated.

Daily cap counter lives in a separate key:
```
feed_cap:<user_id>:<YYYY-MM-DD>
```
TTL = end of UTC day. Value is an integer incremented with `INCR`. Checked before serving each page; gate is enforced server-side in `discovery-svc`.

### 2.4 OpenAI `text-embedding-3-large` — Dimensions, Cost, Storage

**Dimensions**: 3072 (default, full fidelity). Truncation to 1536 is supported and roughly halves storage at ~5 % recall loss. **Recommendation: keep 3072 for v1** — the match quality delta is meaningful for a quality-first platform.

**Cost estimate** (OpenAI pricing as of knowledge cutoff):
- `text-embedding-3-large`: $0.13 / 1M tokens.
- Average profile text (bio + obsessed_with + vocation tags + portfolio captions): ~300 tokens.
- 100k profiles × 300 tokens = 30M tokens → **~$3.90 for full corpus re-embed**. Negligible.
- Incremental on profile update: per-event, nearly zero.
- Nightly re-rank does **not** re-embed unless profile text changed; it re-scores using stored vectors.

**Storage**:
- 3072 × 4 bytes (float32) = 12 288 bytes per vector.
- 100k profiles → ~1.2 GB raw vectors in Postgres. Well within RDS gp3 volume headroom.
- Pgvector stores vectors inline in the heap page; HNSW index adds ~1.7 GB at m=16. Total: ~3 GB for the vector subsystem at 100k profiles.

### 2.5 Mapbox Geocoding — Free Tier Limits

Mapbox Geocoding API (v6, Geocoding JS): **100 000 requests/month free** on the free tier (as of 2026). Beyond that: $0.50 / 1000 requests.

Usage pattern for Colab:
- City autocomplete during onboarding and profile edits: ~3–5 API calls per onboarding session.
- At 10k DAU with 5 % editing location/day → ~1 500 calls/day → **~45 000/month**. Comfortably within free tier at launch.
- At 100k DAU → ~450 000/month → ~$175/month overage. Budget line item for M6+.
- Mitigation: cache autocomplete results in Redis for 24 h by query string. Reverse-geocode results cached by (lat, lng) truncated to 4 decimal places. `geo-svc` owns this cache.

`MAPBOX_SECRET_TOKEN` and `MAPBOX_PUBLIC_TOKEN` are in `.env.example`. The public token is safe for mobile client use (Mapbox enforces URL-scope restrictions). Server-side calls use the secret token through `geo-svc`.

### 2.6 Celery Beat Scheduling

Two scheduled tasks registered in `matching-svc`:

| Task | Schedule | Beat config key |
|---|---|---|
| `matching.nightly_rerank` | 02:00 UTC daily | `CELERY_BEAT_NIGHTLY_RERANK_CRON` |
| `matching.recommendation_set_generation` | 03:00 UTC daily | `CELERY_BEAT_RECS_CRON` |

Rationale: rerank completes first; recommendation set generation consumes the fresh `MatchScore` rows. 1-hour gap is conservative buffer.

Nightly rerank target: **<30 min for 100k profiles**. Achieved by:
1. Chunked parallel Celery subtasks (1 000 profiles/chunk → 100 subtasks).
2. HNSW ANN query per profile retrieves top-200 candidates (not all 100k × 100k pairs).
3. Each chunk fans out as a Celery chord; results aggregated with `UPSERT` on `MatchScore`.

Recommendation set generation reads the top-K `MatchScore` rows per user filtered by active/visible/non-hidden profiles, applies a daily reshuffle (see §6), and writes to `RecommendationSet`.

---

## 3. Ranking Algorithm

### 3.1 Formula

```
score = 0.40 × emb_sim
      + 0.25 × comp_voc
      + 0.15 × activity
      + 0.10 × health
      + 0.10 × rand
```

All terms are normalized to **[0.0, 1.0]** before weighting.

Weights are **admin-configurable** via a `RankingWeightConfig` row in the database (loaded into Redis at boot; refreshed every 5 minutes). Changes take effect on the next nightly rerank or on-demand re-rank; the live feed cache (30 s TTL) expires naturally.

### 3.2 Term Definitions

**`emb_sim` — Embedding Similarity (weight 0.40)**
Cosine similarity between `viewer.embedding` and `candidate.embedding` using pgvector `<=>` operator.
```sql
1 - (viewer_vec <=> candidate_vec) AS emb_sim
```
Range: naturally [-1, 1] for cosine; in practice [0, 1] for non-negative text embeddings. Clamp to [0, 1].

Embedding is generated from the concatenation of:
```
{bio}\n{obsessed_with}\n{vocation_tags_joined}\n{portfolio_captions_joined}
```
Regenerated async whenever any of those fields change (event: `profile.updated`). Stored in `ProfileEmbedding(profile_id, embedding vector(3072), updated_at)`.

**`comp_voc` — Complementary Vocation Score (weight 0.25)**
Looked up from a 9×9 affinity matrix (see §4). Returns a value in [0, 1]. Same-vocation pairs return a moderate value (0.5) rather than 1.0, because the platform favors cross-disciplinary collaboration over same-field networking.

**`activity` — Recent Activity Score (weight 0.15)**
Computed from `Profile.last_active_at`:
```
activity = exp(-λ × days_since_active)
```
where `λ = 0.05` (half-life ~14 days). A user active today scores 1.0; one inactive for 30 days scores ~0.22; 90 days → ~0.011 (effectively filtered out of top results).

Clamped to [0, 1]. Updated nightly from `last_active_at` column on `Profile`.

**`health` — Profile Health Score (weight 0.10)**
Stored as `Profile.profile_health_score` (float, computed nightly by `profile-svc`). **Not exposed in API responses or filter controls.** Passed internally from `profile-svc` to `matching-svc` via internal gRPC/HTTP call or pre-joined in the nightly rerank query. Approximate components (exact formula owned by §004):
- Has avatar: +0.15
- Bio filled: +0.20
- Portfolio items ≥ 3: +0.25
- At least one vocation tag: +0.15
- Valid Profile Badge granted: +0.20
- External link connected: +0.05

**`rand` — Randomization (weight 0.10)**
Gaussian noise per (viewer, candidate, day) pair. Seeded with `hash(viewer_id || candidate_id || calendar_date)` so the same pair has stable jitter within a day but different jitter the next day. This prevents filter-bubble lock-in while keeping results reproducible within a session.

```python
import hashlib, struct, random
seed = hashlib.sha256(f"{viewer_id}:{candidate_id}:{date.today().isoformat()}".encode()).digest()
rand_val = random.Random(struct.unpack("<Q", seed[:8])[0]).gauss(0.5, 0.15)
rand_val = max(0.0, min(1.0, rand_val))
```

### 3.3 Worked Example

**Profile A — the viewer**: Indie Filmmaker, Los Angeles, portfolio captions about "cinematic storytelling", last active today, health score 0.85, Premium user.

**Profile B — candidate 1**: Composer/Music Producer, Los Angeles, portfolio captions about "film scoring and ambient soundscapes", last active 3 days ago, health score 0.75.

**Profile C — candidate 2**: Another Filmmaker, Austin TX (within 1000 mi "Anywhere" mode), last active 45 days ago, health score 0.40.

**Computing scores for A → B**:
- `emb_sim`: cosine("cinematic storytelling" context, "film scoring ambient soundscapes" context) → high semantic overlap → **0.82**
- `comp_voc`: Filmmaker ↔ Composer/Music Producer → affinity matrix cell → **0.95** (top complementary pair)
- `activity`: 3 days → exp(-0.05 × 3) = **0.86**
- `health`: 0.75 (Profile B's health score) → **0.75**
- `rand`: deterministic jitter → **0.52**

```
score_B = 0.40×0.82 + 0.25×0.95 + 0.15×0.86 + 0.10×0.75 + 0.10×0.52
        = 0.328 + 0.238 + 0.129 + 0.075 + 0.052
        = 0.822
```

**Computing scores for A → C**:
- `emb_sim`: Filmmaker ↔ Filmmaker, similar bio language → **0.71**
- `comp_voc`: Filmmaker ↔ Filmmaker → same-vocation moderate → **0.50**
- `activity`: 45 days → exp(-0.05 × 45) = **0.105**
- `health`: 0.40 → **0.40**
- `rand`: jitter → **0.48**

```
score_C = 0.40×0.71 + 0.25×0.50 + 0.15×0.105 + 0.10×0.40 + 0.10×0.48
        = 0.284 + 0.125 + 0.016 + 0.040 + 0.048
        = 0.513
```

**Result**: Profile B (Composer) ranks at 0.822, Profile C (inactive same-vocation filmmaker) at 0.513. Profile B surfaces first — exactly the productive cross-disciplinary partnership the platform is designed to surface.

---

## 4. Complementary-Vocation Function

### 4.1 Vocation Categories (9)

Based on master spec FR-A-4 and the 9-category taxonomy:

1. Visual Arts (Painter, Illustrator, Photographer, Graphic Designer)
2. Performing Arts (Actor, Dancer, Comedian, Voice Actor)
3. Literary Arts (Poet, Author, Screenwriter, Copywriter)
4. Music (Musician, Singer, Composer, DJ/Producer)
5. Film & Video (Filmmaker, Videographer, Editor, Cinematographer)
6. Design (UI/UX Designer, Industrial Designer, Fashion Designer, Art Director)
7. Digital / Tech (Animator, Motion Designer, Game Dev, XR/AR)
8. Media & Journalism (Journalist, Podcaster, Content Creator, Broadcaster)
9. Craft & Maker (Sculptor, Ceramicist, Textile Artist, Woodworker)

### 4.2 Affinity Matrix (9 × 9)

Values are in [0.0, 1.0]. Diagonal (same-category) = **0.50** (modest; same-field collaboration is fine but not the hero case). Off-diagonal values represent editorial judgment on creative complementarity. **This matrix is a content artifact — the team should tune it before v1 nightly rerank runs.**

|  | Visual | Performing | Literary | Music | Film/Video | Design | Digital | Media | Craft |
|---|---|---|---|---|---|---|---|---|---|
| **Visual** | 0.50 | 0.60 | 0.65 | 0.55 | 0.80 | 0.85 | 0.75 | 0.70 | 0.70 |
| **Performing** | 0.60 | 0.50 | 0.70 | 0.80 | 0.85 | 0.45 | 0.55 | 0.80 | 0.35 |
| **Literary** | 0.65 | 0.70 | 0.50 | 0.75 | 0.80 | 0.55 | 0.50 | 0.85 | 0.40 |
| **Music** | 0.55 | 0.80 | 0.75 | 0.50 | 0.95 | 0.45 | 0.65 | 0.70 | 0.35 |
| **Film/Video** | 0.80 | 0.85 | 0.80 | 0.95 | 0.50 | 0.60 | 0.75 | 0.80 | 0.40 |
| **Design** | 0.85 | 0.45 | 0.55 | 0.45 | 0.60 | 0.50 | 0.90 | 0.55 | 0.75 |
| **Digital** | 0.75 | 0.55 | 0.50 | 0.65 | 0.75 | 0.90 | 0.50 | 0.65 | 0.50 |
| **Media** | 0.70 | 0.80 | 0.85 | 0.70 | 0.80 | 0.55 | 0.65 | 0.50 | 0.40 |
| **Craft** | 0.70 | 0.35 | 0.40 | 0.35 | 0.40 | 0.75 | 0.50 | 0.40 | 0.50 |

**Highlighted high-affinity pairs (≥ 0.90)**:
- Film/Video ↔ Music: **0.95** (film scoring is the canonical collab)
- Design ↔ Digital: **0.90** (UI/UX + motion/animation)

**Highlighted notable pairs**:
- Poet ↔ Composer (Literary ↔ Music): 0.75 — song lyrics
- Filmmaker ↔ Musician (Film/Video ↔ Music): 0.95 — scores/soundtracks
- Filmmaker ↔ Actor (Film/Video ↔ Performing): 0.85
- Screenwriter ↔ Filmmaker (Literary ↔ Film/Video): 0.80
- Journalist ↔ Filmmaker (Media ↔ Film/Video): 0.80 — documentary
- Designer ↔ Visual Artist (Design ↔ Visual): 0.85 — brand + art direction

**Implementation**: Store matrix as `VocationAffinityMatrix` in Postgres (singleton jsonb row + admin-console editor). Loaded into Redis at startup: `vocation_affinity:<cat_a>:<cat_b>` (string key → float). Cache TTL 1 hour; invalidated on admin update.

When a profile has **multiple vocations**: take the maximum affinity across all viewer × candidate vocation pairs. This rewards multi-disciplinary candidates.

```python
def comp_voc_score(viewer_vocations: list[str], candidate_vocations: list[str]) -> float:
    return max(
        affinity_matrix[v][c]
        for v in viewer_vocations
        for c in candidate_vocations
    )
```

---

## 5. Feed APIs

### 5.1 Paginated Cursor Format

The cursor is a **base64url-encoded JSON object** (no padding):

```json
{
  "fh": "<filter_hash_8chars>",
  "o": 40,
  "d": "2026-05-11"
}
```

- `fh`: SHA-256 of the canonical filter parameters string, first 8 hex chars. Used to detect filter change (invalidate cursor on mismatch).
- `o`: integer offset into the sorted Redis set for this feed page.
- `d`: the calendar date the cursor was created. Used to invalidate cross-day cursors (daily cap resets).

**Client sends**: `GET /feed?cursor=<token>&page_size=20`
**Server returns**:
```json
{
  "profiles": [...],
  "next_cursor": "<token_or_null>",
  "remaining_today": 12,
  "cap": 30,
  "mode": "scroll"
}
```

`next_cursor` is `null` when the feed is exhausted or the daily cap is reached. `remaining_today` is omitted for Premium users (no cap).

### 5.2 Mode Toggle Persistence

`POST /feed/preference/mode` body: `{"mode": "scroll" | "swipe"}`

- Writes to `FeedPreference(user_id, mode)` (upsert).
- Also caches in Redis: `feed_pref:<user_id>` → `"scroll"` or `"swipe"`, TTL 7 days.
- `GET /feed` reads mode from Redis first, falls back to DB.
- Mode is returned in every feed response so the client knows which UX to render on cold start.

### 5.3 Filter URL Schema

Filters are passed as a single `filters` query parameter containing a **URI-encoded JSON object**:

```
GET /feed?filters=<urlencode(json)>&cursor=...&page_size=20
```

Filter object schema:
```json
{
  "vocation_categories": ["Music", "Film/Video"],
  "radius_km": 80,
  "anywhere": false,
  "experience_level_min": 1,
  "experience_level_max": 5,
  "open_to_remote": true,
  "last_active_days": 30,
  "min_successful_collabs": 0
}
```

All fields optional. Defaults: all vocations, user's saved radius, all experience levels, remote=false (not filtered), last_active=90 days, min_collabs=0.

**Filter hash** (for cursor and Redis key):
```python
import hashlib, json
filter_hash = hashlib.sha256(
    json.dumps(filters, sort_keys=True).encode()
).hexdigest()[:8]
```

**Excluded from filters**: `profile_health_score` (internal only; never a client filter param).

**Debounce**: Client-side 400 ms debounce before firing filter-change requests. Server validates and ignores unknown filter keys (forward-compat).

---

## 6. "Picked for You" Generator

### 6.1 Algorithm

Nightly Celery Beat task (`03:00 UTC`) runs `matching.recommendation_set_generation`:

1. **Fetch top-K candidates**: For each active user, query `MatchScore` WHERE `from_profile_id = user_id` AND `to_profile_id NOT IN (hidden_3mo list, saved list, blocked list)` AND `candidate.last_active_at > now() - 90 days` ORDER BY `score DESC` LIMIT 50. This is the "pool" for the day.

2. **Diversity reshuffle**: From the pool of 50, select **5–10 profiles** using a stratified sample:
   - At least 1 from a different vocation super-group (cross-discipline guarantee).
   - At least 1 within the user's stated radius (local discovery guarantee).
   - Remaining slots: top-scoring, subject to deduplication against yesterday's `RecommendationSet` (no repeating the same profile two days in a row unless the pool is exhausted).

3. **Premium priority** (`picked_for_you_priority` entitlement from §013): Premium users get 10 profiles (not 5) and the pool query depth increases to 100.

4. **Write `RecommendationSet`**: Upsert `(user_id, generated_at, profile_ids jsonb array, rationale jsonb)`. Rationale field stores per-profile dominant signal for potential future transparency UI.

5. **Cache**: Write `recs:<user_id>` → serialized profile_ids to Redis, TTL 24 h. Invalidated early if the user's own profile changes significantly (event: `profile.updated` with `embedding_changed=true`).

### 6.2 Trigger Events

| Event | Action |
|---|---|
| `profile.updated` (embedding changed) | Enqueue on-demand `match.score_recomputed` for affected user; clear `recs:<user_id>` cache |
| `profile.badge_granted` | Same as above |
| Nightly 03:00 UTC | Full `RecommendationSet` regeneration for all active users |

### 6.3 Endpoint

```
GET /feed/picked-for-you
```
Returns today's `RecommendationSet` for the authenticated user. If none exists yet (new user, first login before nightly job), falls back to a real-time top-10 query on `MatchScore` (or, for zero-score cold-start users, falls back to vocation-only heuristic match).

**Cold-start handling**: Users with no portfolio (embedding is zero-vector or absent) skip `emb_sim` and use a modified formula: `score = 0.45×comp_voc + 0.25×activity + 0.20×health + 0.10×rand`. This ensures new users immediately see relevant profiles.

---

## 7. Detailed Data Model

All tables live in the `discovery` Postgres schema (owned by `discovery-svc`) and `matching` schema (owned by `matching-svc`).

### 7.1 `discovery.hide_3mo`

```sql
CREATE TABLE discovery.hide_3mo (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    hidden_profile_id UUID NOT NULL REFERENCES profile.profiles(id) ON DELETE CASCADE,
    hidden_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    hidden_until  TIMESTAMPTZ NOT NULL,  -- hidden_at + 90 days
    UNIQUE (user_id, hidden_profile_id)
);
CREATE INDEX ON discovery.hide_3mo (user_id, hidden_until);
```

- `hidden_until` is computed server-side: `now() + interval '90 days'`. Feed queries filter `hidden_until > now()`.
- Re-hiding a profile that is already hidden resets `hidden_until` to 90 days from now (upsert with conflict on unique constraint).
- Expired rows are cleaned up by a weekly Celery task (`discovery.cleanup_expired_hides`).

### 7.2 `discovery.saved_profiles`

```sql
CREATE TABLE discovery.saved_profiles (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    saved_profile_id UUID NOT NULL REFERENCES profile.profiles(id) ON DELETE CASCADE,
    saved_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, saved_profile_id)
);
CREATE INDEX ON discovery.saved_profiles (user_id, saved_at DESC);
```

- `GET /me/saved` returns most-recent-first (index supports this).
- Saved count per profile is a materialized counter in `profile.profiles.saved_count` (incremented/decremented via event). Exposed as anonymized count in profile detail view.
- Saver name/identity visible to Premium-Pro users only (§013 `see_who_saved_you` entitlement); requires JOIN with `auth.users` gated by entitlement check.

### 7.3 `discovery.feed_preferences`

```sql
CREATE TABLE discovery.feed_preferences (
    user_id  UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    mode     VARCHAR(10) NOT NULL DEFAULT 'scroll' CHECK (mode IN ('scroll', 'swipe')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Single row per user. Upserted on `POST /feed/preference/mode`.

### 7.4 `matching.match_scores`

```sql
CREATE TABLE matching.match_scores (
    from_profile_id UUID NOT NULL REFERENCES profile.profiles(id) ON DELETE CASCADE,
    to_profile_id   UUID NOT NULL REFERENCES profile.profiles(id) ON DELETE CASCADE,
    score           FLOAT NOT NULL,
    emb_sim         FLOAT,
    comp_voc        FLOAT,
    activity        FLOAT,
    health          FLOAT,
    rand_component  FLOAT,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    version         INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (from_profile_id, to_profile_id)
);
CREATE INDEX ON matching.match_scores (from_profile_id, score DESC);
CREATE INDEX ON matching.match_scores (computed_at);
```

- Individual component scores stored for debuggability and admin tooling.
- `version` incremented on each recompute (for cache invalidation comparisons).
- Only top-200 candidates per user are stored (nightly job prunes rows where this profile's `score` is below the 200th-rank score for the viewer).

### 7.5 `matching.recommendation_sets`

```sql
CREATE TABLE matching.recommendation_sets (
    user_id      UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    profile_ids  UUID[] NOT NULL,
    rationale    JSONB NOT NULL DEFAULT '{}'
);
```

- `profile_ids` is a Postgres array (ordered, position = rank).
- `rationale` example: `{"<profile_id>": {"dominant_signal": "emb_sim", "score": 0.822}}`
- Only today's set is kept (upsert replaces previous).

### 7.6 `matching.profile_embeddings` (cross-service read; written by `profile-svc`)

```sql
-- Owned by profile-svc but queried by matching-svc via cross-schema read role
CREATE TABLE profile.profile_embeddings (
    profile_id  UUID PRIMARY KEY REFERENCES profile.profiles(id) ON DELETE CASCADE,
    embedding   VECTOR(3072) NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_profile_embedding_hnsw
  ON profile.profile_embeddings
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
```

`matching-svc` is granted a read-only role on `profile.profile_embeddings` and `profile.profiles`.

### 7.7 `matching.ranking_weight_config`

```sql
CREATE TABLE matching.ranking_weight_config (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    weight_emb_sim  FLOAT NOT NULL DEFAULT 0.40,
    weight_comp_voc FLOAT NOT NULL DEFAULT 0.25,
    weight_activity FLOAT NOT NULL DEFAULT 0.15,
    weight_health   FLOAT NOT NULL DEFAULT 0.10,
    weight_rand     FLOAT NOT NULL DEFAULT 0.10,
    activity_lambda FLOAT NOT NULL DEFAULT 0.05,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by      UUID REFERENCES auth.users(id),
    CONSTRAINT weights_sum_to_one CHECK (
        abs(weight_emb_sim + weight_comp_voc + weight_activity + weight_health + weight_rand - 1.0) < 0.001
    )
);
```

Admin console writes to this table via `admin-svc`. Loaded into Redis key `ranking_weights` on startup and on write. `matching-svc` reads from Redis with a 5-minute TTL fallback to DB.

### 7.8 `matching.vocation_affinity` (matrix storage)

```sql
CREATE TABLE matching.vocation_affinity (
    id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    matrix    JSONB NOT NULL,  -- {"Visual": {"Music": 0.55, ...}, ...}
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by UUID REFERENCES auth.users(id)
);
-- Only one row; singleton enforced by application logic + unique partial index
CREATE UNIQUE INDEX ON matching.vocation_affinity ((true));
```

---

## 8. Caching

### 8.1 Redis Key Layout

| Key pattern | Type | TTL | Owner | Description |
|---|---|---|---|---|
| `feed:<user_id>:<mode>:<filter_hash>` | Sorted Set | 30 s | discovery-svc | Ranked profile_id set for active feed page |
| `feed_cap:<user_id>:<YYYY-MM-DD>` | String (int) | Until end of UTC day | discovery-svc | Daily profile view counter |
| `feed_pref:<user_id>` | String | 7 days | discovery-svc | Preferred feed mode (`scroll`/`swipe`) |
| `recs:<user_id>` | String (JSON array) | 24 h | matching-svc | Today's "Picked for you" profile_ids |
| `ranking_weights` | String (JSON) | 5 min | matching-svc | Current weight config |
| `vocation_affinity:<cat_a>:<cat_b>` | String (float) | 1 h | matching-svc | Affinity matrix cell lookup |
| `geo_autocomplete:<query_hash>` | String (JSON) | 24 h | geo-svc | Mapbox autocomplete cache |
| `geo_reverse:<lat4>:<lng4>` | String (JSON) | 24 h | geo-svc | Reverse geocode cache |

### 8.2 Feed Cache Population

On `GET /feed` with no valid cursor (or expired cursor):
1. Attempt `EXISTS feed:<user_id>:<mode>:<filter_hash>`.
2. If miss: run Postgres feed query (filtered, radius-bounded, sorted by match score). Write results as `ZADD feed:<uid>:<mode>:<fhash> NX <score> <profile_id>` for all candidates. `EXPIRE ... 30`.
3. On hit: `ZRANGE feed:<uid>:<mode>:<fhash> <offset> <offset+page_size-1> REV` → fetch profile cards from `profile-svc`.

Profile card data is **not** stored in Redis (stale profile data risk). Only the ranked list of `profile_id` values is cached. Profile card fetch is a batched HTTP call to `profile-svc` with the page's profile IDs; `profile-svc` maintains its own profile read cache at 5-minute TTL (§004 NFR: P95 <100ms cached).

### 8.3 Invalidation Events

| Event (RabbitMQ) | Invalidation action |
|---|---|
| `profile.updated` (any field) | Delete `feed:*:<user_id>:*` pattern (use Redis SCAN + DEL; or tag with user's profile_id in a set for targeted delete) |
| `profile.updated` (embedding changed) | Additionally delete `recs:<user_id>` |
| `billing.entitlement_changed` | Delete `feed_cap:<user_id>:*` (cap tier changed) |
| `match.score_recomputed` | Delete `feed:<user_id>:*:*` for affected viewer |
| Admin weight config change | Delete `ranking_weights`; Celery task re-runs on-demand rerank for active users |
| `hide_3mo.created` | Delete `feed:<user_id>:*:*` (hidden profile must disappear immediately) |
| `profile.blocked` | Delete `feed:<user_id>:*:*` + `feed:<blocked_id>:*:*` |

Pattern-delete strategy: maintain a Redis Set `feed_keys:<user_id>` tracking active feed cache keys. On invalidation, `SMEMBERS` → `DEL` each. Cleaned up on TTL expiry via a Lua script that removes expired members.

### 8.4 Daily Cap Enforcement (Redis)

```python
async def check_and_increment_cap(user_id: str, tier: str, count: int) -> tuple[bool, int]:
    """Returns (allowed, remaining). count = number of profiles about to be served."""
    if tier != "free":
        return True, -1  # Premium: no cap

    cap = int(os.environ["RATE_LIMIT_FEED_PROFILES_FREE_PER_DAY"])  # 30
    today = date.today().isoformat()
    key = f"feed_cap:{user_id}:{today}"

    pipe = redis.pipeline()
    pipe.incrby(key, count)
    pipe.ttl(key)
    current, ttl = await pipe.execute()

    if ttl < 0:
        # Key just created without TTL; set it
        end_of_day_seconds = seconds_until_utc_midnight()
        await redis.expire(key, end_of_day_seconds)

    if current > cap:
        # Roll back the increment by the overage
        overage = current - cap
        await redis.decrby(key, overage)
        return False, 0

    return True, cap - current
```

Entitlement check calls `billing-svc` `GET /entitlements/me` at session start and caches result in Redis for 5 minutes to avoid hot-path latency.

---

## 9. Geospatial

### 9.1 PostGIS Index and Radius Query

Index (created in §7.6 above):
```sql
CREATE INDEX idx_profile_location_gist ON profile.profiles USING GIST (location_point);
```

Canonical radius filter query used inside the nightly rerank and feed assembly:

```sql
SELECT p.id, p.display_name, p.location_city, p.last_active_at,
       p.profile_health_score, p.is_visible_to_non_premium,
       pe.embedding
FROM profile.profiles p
JOIN profile.profile_embeddings pe ON pe.profile_id = p.id
WHERE
    p.id != $viewer_id
    AND p.is_deleted = false
    AND p.badge_state = 'badge_granted'  -- only verified profiles in feed
    AND (
        $anywhere = true
        OR ST_DWithin(
            p.location_point::geography,
            ST_MakePoint($lng, $lat)::geography,
            $radius_metres
        )
    )
    AND NOT EXISTS (
        SELECT 1 FROM discovery.hide_3mo h
        WHERE h.user_id = $viewer_id AND h.hidden_profile_id = p.id AND h.hidden_until > now()
    )
    AND NOT EXISTS (
        SELECT 1 FROM auth.blocks b
        WHERE (b.blocker_id = $viewer_id AND b.blocked_id = p.id)
           OR (b.blocker_id = p.id AND b.blocked_id = $viewer_id)
    )
    AND (
        $viewer_tier != 'free'
        OR p.is_visible_to_non_premium = true
    );
```

### 9.2 Unit Conversion

| Locale | Default radius | Metres |
|---|---|---|
| US, Canada | 50 mi | 80 467 m |
| AU, NZ, India | 80 km | 80 000 m |

`Profile.radius_unit` stores `mi` or `km`. At query time:
```python
radius_metres = radius_value * 1609.34 if radius_unit == "mi" else radius_value * 1000.0
```

"Anywhere" is stored as `open_to_remote = true` + `radius_value = NULL`. Feed query receives `anywhere = True` → spatial filter skipped.

### 9.3 Mapbox Geocoding via `geo-svc`

`geo-svc` is a thin FastAPI proxy with caching. It does not call Mapbox on cache hit.

```
GET /geo/autocomplete?q=Los+Ange&types=place,locality&limit=5
→ Mapbox Geocoding API v6 → cached 24h → return to client
```

```
GET /geo/reverse?lat=34.0522&lng=-118.2437
→ Mapbox reverse geocode → city + region → cached 24h by (lat4, lng4)
```

`lat4` / `lng4` = lat/lng rounded to 4 decimal places (~11m precision; sufficient for city-level cache keys).

Free-tier limit: 100 000 requests/month. Cache hit rate expected >90 % for autocomplete (common city names repeated many times during onboarding). Monitor via `geo_svc_mapbox_calls_total` Prometheus counter exposed to CloudWatch.

---

## 10. API Contracts

### 10.1 `GET /feed`

**Request**
```
GET /feed?mode=scroll&cursor=<base64url>&page_size=20&filters=<urlencode_json>
Authorization: Bearer <jwt>
```

**Response 200**
```json
{
  "mode": "scroll",
  "profiles": [
    {
      "id": "uuid",
      "display_name": "string",
      "location_city": "string",
      "badge_state": "badge_granted",
      "vocations": [{"category": "Music", "subtag": "Composer"}],
      "bio": "string (280ch max)",
      "obsessed_with": "string (140ch max)",
      "experience_level": 3,
      "open_to_remote": true,
      "portfolio_preview": [{"type": "image", "url": "cloudfront_signed_url", "caption": "string"}],
      "collab_count": 2,
      "last_active_relative": "3 days ago",
      "saved": false,
      "match_score": null
    }
  ],
  "next_cursor": "eyJmaCI6ImFiY2QxMjM0IiwibyI6MjAsImQiOiIyMDI2LTA1LTExIn0",
  "remaining_today": 10,
  "cap": 30
}
```

Notes:
- `match_score` is always `null` in client responses (internal only).
- `profile_health_score` is never returned.
- `remaining_today` omitted for Premium users.
- `next_cursor` is `null` at cap or feed exhaustion.

**Response 402** (Free user, daily cap reached):
```json
{"error": "daily_cap_reached", "cap": 30, "resets_at": "2026-05-12T00:00:00Z"}
```

### 10.2 `POST /feed/preference/mode`

```json
// Request
{"mode": "swipe"}

// Response 200
{"mode": "swipe", "updated_at": "2026-05-11T14:23:00Z"}
```

### 10.3 `POST /profile/{id}/hide-3mo`

```json
// Response 200
{"hidden_until": "2026-08-09T14:23:00Z"}
```

**Response 409** if already hidden (returns current `hidden_until`).

### 10.4 `GET /feed/picked-for-you`

**Response 200**
```json
{
  "profiles": [...],  // same profile card schema as /feed
  "generated_at": "2026-05-11T03:00:00Z",
  "next_refresh_at": "2026-05-12T03:00:00Z"
}
```

### 10.5 `GET /match/score` (internal)

```
GET /match/score?from=<profile_id>&to=<profile_id>
X-Internal-Service-Token: <secret>
```

```json
{
  "from_profile_id": "uuid",
  "to_profile_id": "uuid",
  "score": 0.822,
  "components": {
    "emb_sim": 0.82,
    "comp_voc": 0.95,
    "activity": 0.86,
    "health": 0.75,
    "rand": 0.52
  },
  "computed_at": "2026-05-11T02:47:00Z",
  "version": 4
}
```

### 10.6 `POST /match/reindex` (internal, Celery Beat triggered)

```
POST /match/reindex
X-Internal-Service-Token: <secret>
Body: {} (empty; triggers full nightly rerank)
```

```json
// Response 202
{"job_id": "celery-task-uuid", "status": "queued"}
```

### 10.7 Error Schema (all endpoints)

```json
{
  "error": "<snake_case_code>",
  "message": "Human-readable description",
  "details": {}
}
```

Common error codes: `unauthorized`, `not_found`, `daily_cap_reached`, `already_hidden`, `invalid_cursor`, `invalid_filter`, `rate_limited`.

---

## 11. Implementation Tasks

| ID | Title | Outcome | Est Hours | Blocks | Blocked By |
|---|---|---|---|---|---|
| T001 | DB schema — discovery schema | `hide_3mo`, `saved_profiles`, `feed_preferences` tables + indexes created via Alembic migration | 3 | T005, T007 | 004 (profile schema live) |
| T002 | DB schema — matching schema | `match_scores`, `recommendation_sets`, `ranking_weight_config`, `vocation_affinity`, `profile_embeddings` index | 4 | T006, T008 | T001 |
| T003 | `geo-svc` scaffold + Mapbox proxy | FastAPI service with `/geo/autocomplete` and `/geo/reverse`; Redis cache; Prometheus counter | 6 | T005 | 002 (platform base) |
| T004 | Affinity matrix seed | Populate `vocation_affinity` table with 9×9 matrix; Redis warm-up on startup | 2 | T008 | T002 |
| T005 | Feed assembly query | Postgres filtered + radius + block + hide query; no ranking yet; pagination | 8 | T009 | T001, T003 |
| T006 | Embedding generation pipeline | `profile-svc` emits embedding to `profile_embeddings` on `profile.updated`; HNSW index build | 8 | T008 | T002, 004 |
| T007 | Redis feed cache layer | Sorted Set population, cursor encode/decode, TTL management, invalidation on profile events | 6 | T009 | T001 |
| T008 | Ranking score computation | Five-term formula; `RankingWeightConfig` load from Redis; `VocationAffinity` lookup; `MatchScore` UPSERT | 10 | T010, T011 | T002, T004, T006 |
| T009 | `discovery-svc` `/feed` endpoint | Mode toggle, cursor pagination, filter parsing, entitlement check (cap), profile card assembly | 12 | T013, T014 | T005, T007, T008 |
| T010 | Nightly rerank Celery task | Chunked subtasks, HNSW top-200, `match_scores` UPSERT, <30 min SLA | 10 | T011 | T008 |
| T011 | Nightly recs generation Celery task | Reads `match_scores`, stratified reshuffle, Premium depth bump, writes `recommendation_sets` | 8 | T012 | T010 |
| T012 | `GET /feed/picked-for-you` endpoint | Read `recommendation_sets`; cold-start fallback; vocation-only heuristic | 6 | T013 | T011 |
| T013 | Hide-3mo endpoints | `POST/DELETE /profile/{id}/hide-3mo`; feed cache invalidation; TTL logic | 4 | T015 | T009 |
| T014 | Save profile endpoints | `POST/DELETE /profile/{id}/save`; `GET /me/saved`; saved_count increment on profile | 4 | T015 | T009 |
| T015 | Mode toggle persistence | `POST /feed/preference/mode`; Redis + DB write; mode returned in feed response | 2 | — | T009 |
| T016 | On-demand re-rank (hot signal) | `match.score_recomputed` event handler; P95 <500ms; only for changed profile's viewers | 6 | — | T008 |
| T017 | Premium entitlement gate | Integrate billing-svc entitlement check; hide-from-non-premium filter in feed query | 5 | — | T009, 013 |
| T018 | `geo-svc` unit tests + integration | pytest: autocomplete cache hit/miss; reverse geocode; 100 % coverage on service layer | 4 | — | T003 |
| T019 | `matching-svc` unit tests | pytest: score formula, affinity matrix lookup, activity decay, cold-start formula | 6 | — | T008 |
| T020 | `discovery-svc` unit + integration tests | pytest: cursor encode/decode, filter hash, cap enforcement, hide/save logic | 8 | — | T009 |
| T021 | k6 load test — feed endpoint | Feed P95 <300ms at 500 RPS; nightly rerank <30 min for 100k profiles (seeded) | 8 | — | T009, T010 |
| T022 | Admin — weight config endpoint | `admin-svc` CRUD for `ranking_weight_config`; Redis invalidation; audit log | 4 | — | T002 |
| T023 | Admin — affinity matrix editor | `admin-svc` endpoint to update `vocation_affinity`; Redis invalidation | 3 | — | T004 |
| T024 | PostHog events — feed | `discovery.feed_viewed`, `discovery.profile_saved`, `discovery.profile_hidden`, `discovery.mode_toggled` | 3 | — | T009 |
| T025 | OpenAPI spec + TS client codegen | Generate typed TS client for `discovery-svc` endpoints; validate against RN + web consumers | 4 | — | T009, T012 |
| T026 | Celery Beat registration | Register `nightly_rerank` (02:00 UTC) and `recommendation_set_generation` (03:00 UTC) in Beat schedule | 2 | — | T010, T011 |
| T027 | Cleanup task — expired hides | Weekly Celery task: `DELETE FROM discovery.hide_3mo WHERE hidden_until < now()` | 2 | — | T001 |
| T028 | Cold-start profile detection | Logic to detect zero/null embedding; route to vocation-only formula in both rerank and recs | 3 | — | T008 |

**Total estimated hours**: ~156 h (~4 engineering-weeks for 1 engineer; ~2 weeks for a pair)

**Critical path**: T001 → T002 → T006 → T008 → T010 → T011 → T012 (recs tab). Parallelize T003, T004, T005, T007 against the critical path.

---

## 12. Acceptance Criteria

All criteria must pass before this phase is marked complete.

### 12.1 Functional

**AC-001: Feed first paint under cap**
- Given: authenticated Free user, 0 profiles viewed today
- When: `GET /feed?page_size=20`
- Then: P95 response time <300 ms; 20 profile cards returned; `remaining_today=10` (after serving 20 of cap 30)

**AC-002: Daily cap enforcement — Free**
- Given: Free user has already viewed 30 profiles today
- When: `GET /feed`
- Then: HTTP 402, `error=daily_cap_reached`, `resets_at` = midnight UTC

**AC-003: Daily cap bypass — Premium**
- Given: Premium user, 100 profiles viewed today
- When: `GET /feed`
- Then: HTTP 200, profiles returned, no `remaining_today` field in response

**AC-004: Hide for 3 months**
- Given: viewer hides profile B
- When: `GET /feed` (any page), `GET /feed/picked-for-you`
- Then: profile B absent from all feed results for 90 days; returns after 90 days

**AC-005: Save profile**
- Given: viewer saves profile B
- When: `GET /me/saved`
- Then: profile B is first result (most recent); subsequent saves appear in order

**AC-006: Mode toggle**
- Given: user toggles mode to `swipe`
- When: new session, `GET /feed`
- Then: `mode=swipe` in response; `FeedPreference` row confirms `swipe` in DB

**AC-007: Filter — vocation**
- Given: filter `{"vocation_categories": ["Music"]}`
- When: `GET /feed?filters=<encoded>`
- Then: all returned profiles have at least one vocation in Music category

**AC-008: Filter — radius**
- Given: viewer in LA (US), filter `{"radius_km": 80, "anywhere": false}`
- When: `GET /feed`
- Then: all returned profiles have `location_point` within 80 km of viewer's point (verified via ST_DWithin query check)

**AC-009: Hide-from-non-premium**
- Given: Premium user P sets `is_visible_to_non_premium = false`
- When: Free user queries feed
- Then: P is absent. When Premium user queries feed, P may appear.

**AC-010: Picked-for-you — daily refresh**
- Given: nightly job completes at 03:00 UTC
- When: `GET /feed/picked-for-you` at 03:01 UTC
- Then: `generated_at` is within last 10 minutes; 5–10 profiles returned; no profile appears that is hidden or blocked

**AC-011: Ranking order**
- Given: two candidates with pre-known scores (seeded test data)
- When: `GET /match/score` for each pair
- Then: scores match expected formula output within ±0.001 floating point tolerance

**AC-012: Cold-start user**
- Given: new user with no portfolio (no embedding)
- When: nightly recs job runs
- Then: `RecommendationSet` is generated using vocation-only formula; 5+ profiles returned

### 12.2 Performance (pytest + k6)

**AC-013: k6 — feed P95 latency**
```javascript
// k6 scenario
export const options = {
  vus: 100,
  duration: "60s",
  thresholds: { "http_req_duration{name:feed}": ["p(95)<300"] }
};
export default function () {
  const res = http.get(`${BASE_URL}/feed?page_size=20`, { tags: { name: "feed" } });
  check(res, { "status 200": (r) => r.status === 200 });
}
```
Pass condition: p95 < 300 ms under 100 VU sustained load.

**AC-014: k6 — on-demand re-rank P95**
```javascript
// Single re-rank trigger; P95 measured over 50 requests
thresholds: { "http_req_duration{name:rerank}": ["p(95)<500"] }
```

**AC-015: pytest — nightly rerank duration**
```python
@pytest.mark.slow
def test_nightly_rerank_completes_in_time(seeded_100k_profiles):
    start = time.monotonic()
    result = celery_app.send_task("matching.nightly_rerank").get(timeout=1800)
    elapsed = time.monotonic() - start
    assert elapsed < 1800  # 30 minutes
    assert result["profiles_processed"] == 100_000
```

**AC-016: pytest — feed cap atomicity**
```python
def test_cap_not_exceeded_under_concurrent_requests(free_user_client):
    # Fire 40 concurrent requests each asking for 1 profile
    with concurrent.futures.ThreadPoolExecutor(max_workers=40) as ex:
        futures = [ex.submit(free_user_client.get, "/feed?page_size=1") for _ in range(40)]
        results = [f.result() for f in futures]
    cap_reached = [r for r in results if r.status_code == 402]
    ok = [r for r in results if r.status_code == 200]
    assert len(ok) == 30
    assert len(cap_reached) == 10
```

**AC-017: pytest — cursor decode determinism**
```python
def test_cursor_round_trip():
    original = {"fh": "abcd1234", "o": 40, "d": "2026-05-11"}
    encoded = encode_cursor(original)
    decoded = decode_cursor(encoded)
    assert decoded == original
```

**AC-018: pytest — affinity matrix symmetry (not required but verified)**
```python
def test_affinity_matrix_bounds(affinity_matrix):
    for cat_a in VOCATION_CATEGORIES:
        for cat_b in VOCATION_CATEGORIES:
            val = affinity_matrix[cat_a][cat_b]
            assert 0.0 <= val <= 1.0
            # Symmetry is editorial choice, not enforced, but log asymmetries
```

**AC-019: pytest — embedding HNSW recall**
```python
def test_hnsw_recall_vs_exact(profile_embeddings_1k):
    # Query top-10 via HNSW; compare against exact cosine brute-force
    hnsw_ids = query_hnsw(query_vec, k=10)
    exact_ids = query_exact(query_vec, k=10)
    recall = len(set(hnsw_ids) & set(exact_ids)) / 10
    assert recall >= 0.90  # ≥90% recall at k=10
```

---

## 13. Open Risks

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R-001 | Mapbox free tier exhausted at 100k DAU (~450k calls/month) | High (at scale) | Medium (cost, not downtime) | Aggressive Redis cache on `geo-svc`; budget $175/month in M6 cost plan; evaluate Nominatim OSM as fallback |
| R-002 | Nightly rerank >30 min at 100k profiles under write contention | Medium | High (stale scores) | Chunk parallelization (100 Celery subtasks); read replica for rerank queries; HNSW ef_search tuned to 40 for speed |
| R-003 | Cold-start recommendation quality low for new users | High (every new signup) | Medium (first impression) | Vocation-only heuristic formula; onboarding encourages portfolio upload; review at 30-day post-launch |
| R-004 | Redis Sorted Set memory at 100k users × many filter combinations | Medium | Low-Medium (memory cost) | 30 s TTL limits accumulation; key-scan + deletion on filter change; monitor `redis_memory_used_bytes` |
| R-005 | Complementary-vocation matrix tuning produces poor UX | Medium | High (core value prop) | Matrix is admin-configurable; monitor `comp_voc` score distribution in PostHog; A/B via weight config |
| R-006 | pgvector HNSW build time on initial 100k profile import | Low (one-time) | Low (startup only) | Build index after bulk insert with `maintenance_work_mem = 2GB`; disable index during bulk load |
| R-007 | Free 30/day cap Redis counter race (concurrent requests) | Low | Medium (cap violated) | `INCRBY` is atomic; pipeline in single roundtrip; overage rollback in same pipeline |
| R-008 | `billing-svc` (§013) not yet available at P4 start | High (soft dep) | Low if gated | Feature-flag `FEATURE_BILLING_ENTITLEMENT_CHECK=false` defaults all users to Free cap until §013 lands |
| R-009 | Embedding model upgrade (3-large → future model) | Low near-term | High (full re-embed required) | Version column on `profile_embeddings`; `OPENAI_EMBEDDING_MODEL` env var; re-embed pipeline ready |
| R-010 | profile_health_score leaking via API | Medium (dev error) | High (privacy + spec violation) | `health` field excluded from all `ProfileCard` Pydantic response models via `exclude`; CI lint rule checking for `health_score` in OpenAPI output |
