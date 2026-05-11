# 005 — Discovery + Matching

**Phase**: P4.
**Services**: `discovery-svc`, `matching-svc`, `geo-svc`.
**Mission**: Build the home feed (infinite scroll + swipeable card toggle), filters, "Hide for 3 months" list, "Picked for you" AI recommendations row, and the underlying ranking engine that combines embedding similarity, complementary-vocation, activity, health, and randomization.

## In scope (master Journey B FR-B-1 through FR-B-13)

- Home feed: two modes (infinite scroll list / swipeable card stack), user-preference persisted.
- Daily cap: Free 30/day, Premium unlimited (`billing-svc` provides entitlement).
- Ranking: 40% embedding similarity (pgvector) + 25% complementary-vocation score + 15% recent activity + 10% profile health + 10% randomization. Weights admin-tunable.
- Filters: vocation category, location radius, experience level, open-to-remote, last active, # successful collabs. Profile-health filter NOT exposed.
- "Hide profile for 3 months" per-user list.
- Profile detail view (consumes profile-svc; rendered fields per master FR-B-6).
- "Save" / "Like" → private saved list (visible to saver; saved-profile gets anonymized count; saver name visible to Premium-Pro per §013 entitlements).
- AI Recommended Profiles: top-of-feed "Picked for you" row (5–10 daily) + dedicated tab.
- Two-way discovery; Premium hide-from-non-premium toggle.
- Geospatial queries: PostGIS radius + Mapbox geocoding.

## Dependencies

- **Hard**: 002 Platform, 004 Profile (read profile + embedding), 003 Auth (current user identity).
- **Soft**: 013 Billing (entitlement check for caps + hide-from-non-premium + save-visibility).

## Owned entities

- `Hide3mo`: user_id, hidden_profile_id, hidden_until.
- `SavedProfile`: user_id, saved_profile_id, saved_at.
- `FeedPreference`: user_id, mode (scroll|swipe).
- `MatchScore`: from_profile_id, to_profile_id, score, computed_at, version. (Pre-computed nightly + on-demand for hot signals.)
- `RecommendationSet`: user_id, generated_at, profile_ids (array), rationale (jsonb).

## API surface

`discovery-svc`:
- `GET /feed?mode=scroll|swipe&cursor=...&filters=...` → paginated profile cards
- `POST /feed/preference/mode` — persist user choice
- `POST /profile/{id}/hide-3mo`, `DELETE /profile/{id}/hide-3mo`
- `POST /profile/{id}/save`, `DELETE /profile/{id}/save`
- `GET /me/saved`
- `GET /feed/picked-for-you` → top 5–10 recs of the day

`matching-svc` (internal mostly):
- `GET /match/score?from={profile_id}&to={profile_id}`
- `POST /match/reindex` (internal, scheduled via Celery Beat nightly)

`geo-svc`:
- `GET /geo/autocomplete?q=...&types=place,locality` → Mapbox-proxied results
- `GET /geo/reverse?lat=...&lng=...` → city + region

### Queue events

- `discovery.feed_viewed` (analytics)
- `match.score_recomputed` (when profile/portfolio changes trigger re-rank)

## Acceptance criteria

- Feed first paint <300ms P95.
- Free user hitting 31st profile of the day → cap reached UI; Premium → continues.
- Filter changes trigger debounced re-query; results paginated.
- "Hide for 3 months" excludes profile from feed + recs for 90 days.
- "Save" persists; my saved list returns most-recent-first.
- "Picked for you" returns 5–10 daily, refreshed once per 24h or on major profile-update events.
- Two-way discovery: anyone can send a Vibe Check unless blocked.
- Premium user's `hide_from_non_premium` toggle hides them from non-premium feeds in real time.

## NFRs

- Feed P95 <300ms (Redis hot cache + paginated Postgres query).
- Match recompute nightly job <30 min for 100k profiles.
- On-demand re-rank (hot signal) P95 <500ms.

## Open

- Exact randomization mechanism (Gaussian-noise vs slot reservation) — Phase 5 detail.
- Cold-start behavior for users with empty portfolios — Phase 5 detail (likely heuristic match on vocations only).
