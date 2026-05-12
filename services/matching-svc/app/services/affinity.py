"""
matching-svc — vocation affinity matrix loader and application.

The 9×9 affinity matrix is stored as a JSONB singleton in
`matching.vocation_affinity`. It is loaded into Redis at startup and
refreshed every hour (TTL 3600 s). Admin edits via admin-svc invalidate
the Redis keys immediately.

This module provides:
  - load_matrix_from_db(db)  — read singleton from Postgres
  - get_matrix()             — cached Redis fetch (fallback: seed)
  - comp_voc_score(...)      — max-affinity across vocation cross-product
  - get_affinity_value(a, b) — single cell lookup

Plan §4:
  - Diagonal (same-category) = 0.50
  - Film/Video ↔ Music = 0.95 (top pair)
  - Design ↔ Digital/Tech = 0.90
  - When profile has multiple vocations: max over all viewer × candidate pairs
"""

from __future__ import annotations

import json
import logging
from typing import Optional

import redis.asyncio as aioredis

from app.config import get_settings
from app.services.ranking import AFFINITY_SEED, VOCATION_CATEGORIES

logger = logging.getLogger(__name__)
_settings = get_settings()

# ---------------------------------------------------------------------------
# Redis helpers (module-level singleton)
# ---------------------------------------------------------------------------

_redis: Optional[aioredis.Redis] = None
AFFINITY_TTL = 3600  # 1 hour
_DB_KEY = "vocation_affinity:_matrix"  # full JSON blob key
_CELL_PREFIX = "vocation_affinity:"     # cell key prefix


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(_settings.redis_url, decode_responses=True)
    return _redis


# ---------------------------------------------------------------------------
# DB load
# ---------------------------------------------------------------------------

async def load_matrix_from_db(db) -> dict[str, dict[str, float]]:  # type: ignore[no-untyped-def]
    """
    Load the affinity matrix from the `matching.vocation_affinity` singleton.
    Returns AFFINITY_SEED as default if no row exists yet.
    """
    from sqlalchemy import text as sa_text
    row = await db.execute(
        sa_text("SELECT matrix FROM matching.vocation_affinity LIMIT 1")
    )
    result = row.fetchone()
    if result and result[0]:
        return result[0]
    logger.warning("No vocation_affinity row in DB; using seed matrix")
    return AFFINITY_SEED


# ---------------------------------------------------------------------------
# Redis warm / fetch
# ---------------------------------------------------------------------------

async def warm_matrix_cache(matrix: dict[str, dict[str, float]] | None = None) -> None:
    """
    Write the full matrix to Redis as individual cell keys AND as a single
    JSON blob key for bulk retrieval. Called on startup and after admin edits.
    """
    if matrix is None:
        matrix = AFFINITY_SEED
    r = _get_redis()
    pipe = r.pipeline()
    # Per-cell keys for individual lookups
    for cat_a, row in matrix.items():
        for cat_b, val in row.items():
            pipe.set(f"{_CELL_PREFIX}{cat_a}:{cat_b}", str(val), ex=AFFINITY_TTL)
    # Full JSON blob for bulk fetch
    pipe.set(_DB_KEY, json.dumps(matrix), ex=AFFINITY_TTL)
    await pipe.execute()
    logger.info(
        "Affinity matrix warmed in Redis: %d categories × %d = %d cells",
        len(VOCATION_CATEGORIES),
        len(VOCATION_CATEGORIES),
        len(VOCATION_CATEGORIES) ** 2,
    )


async def get_matrix() -> dict[str, dict[str, float]]:
    """
    Fetch the full affinity matrix from Redis.
    Falls back to AFFINITY_SEED on cache miss (should not happen in normal ops).
    """
    r = _get_redis()
    raw = await r.get(_DB_KEY)
    if raw:
        return json.loads(raw)
    logger.warning("Affinity matrix not in Redis; falling back to seed")
    return AFFINITY_SEED


async def get_affinity_value(cat_a: str, cat_b: str) -> float:
    """
    Get a single affinity cell. Tries Redis cell key first, then full matrix,
    then falls back to in-memory seed.
    """
    r = _get_redis()
    val = await r.get(f"{_CELL_PREFIX}{cat_a}:{cat_b}")
    if val is not None:
        return float(val)
    # Try the full matrix blob
    matrix = await get_matrix()
    return matrix.get(cat_a, {}).get(cat_b, 0.50)


async def invalidate_matrix_cache() -> None:
    """
    Delete all affinity cache keys from Redis. Called after admin matrix update.
    The next read will repopulate from DB.
    """
    r = _get_redis()
    keys: list[str] = []
    async for key in r.scan_iter(f"{_CELL_PREFIX}*"):
        keys.append(key)
    if keys:
        await r.delete(*keys)
    await r.delete(_DB_KEY)
    logger.info("Affinity matrix cache invalidated (%d keys deleted)", len(keys) + 1)


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def comp_voc_score_sync(
    viewer_vocations: list[str],
    candidate_vocations: list[str],
    matrix: dict[str, dict[str, float]] | None = None,
) -> float:
    """
    Synchronous (in-process) comp_voc score using an already-loaded matrix.

    Plan §4.2:
      Return the max affinity value across all viewer × candidate vocation pairs.
      Multi-vocation: rewards cross-disciplinary candidates.
      Unknown vocation category: default to 0.50.
    """
    if matrix is None:
        matrix = AFFINITY_SEED
    if not viewer_vocations or not candidate_vocations:
        return 0.50  # moderate default when vocations unknown

    scores: list[float] = []
    for v in viewer_vocations:
        row = matrix.get(v, {})
        for c in candidate_vocations:
            scores.append(row.get(c, 0.50))
    return max(scores) if scores else 0.50


async def comp_voc_score_async(
    viewer_vocations: list[str],
    candidate_vocations: list[str],
) -> float:
    """
    Async version: loads matrix from Redis, then computes max affinity.
    Prefer this in async contexts to use admin-updated matrix.
    """
    matrix = await get_matrix()
    return comp_voc_score_sync(viewer_vocations, candidate_vocations, matrix)
