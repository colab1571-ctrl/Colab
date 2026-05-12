"""
matching-svc — vocation affinity matrix cache.

Redis key pattern: vocation_affinity:<cat_a>:<cat_b>  TTL 1h
Falls back to in-memory AFFINITY_SEED if Redis miss.
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

_redis: Optional[aioredis.Redis] = None
AFFINITY_TTL = 3600  # 1 hour
WEIGHTS_TTL = 300    # 5 minutes


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(_settings.redis_url, decode_responses=True)
    return _redis


async def warm_affinity_cache(matrix: dict | None = None) -> None:
    """Write affinity matrix cells to Redis."""
    if matrix is None:
        matrix = AFFINITY_SEED
    r = get_redis()
    pipe = r.pipeline()
    for cat_a, row in matrix.items():
        for cat_b, val in row.items():
            pipe.set(f"vocation_affinity:{cat_a}:{cat_b}", str(val), ex=AFFINITY_TTL)
    await pipe.execute()
    logger.info("Affinity matrix warmed in Redis (%d cells)", len(VOCATION_CATEGORIES) ** 2)


async def get_affinity(cat_a: str, cat_b: str) -> float:
    """Get a single affinity cell from Redis, falling back to seed."""
    r = get_redis()
    val = await r.get(f"vocation_affinity:{cat_a}:{cat_b}")
    if val is not None:
        return float(val)
    # Fallback to seed
    return AFFINITY_SEED.get(cat_a, {}).get(cat_b, 0.50)


async def get_weights() -> dict:
    """Load ranking weights from Redis; return defaults if missing."""
    r = get_redis()
    raw = await r.get("ranking_weights")
    if raw:
        return json.loads(raw)
    return {
        "weight_emb_sim": 0.40,
        "weight_comp_voc": 0.25,
        "weight_activity": 0.15,
        "weight_health": 0.10,
        "weight_rand": 0.10,
        "activity_lambda": 0.05,
    }


async def set_weights(weights: dict) -> None:
    """Cache ranking weights in Redis."""
    r = get_redis()
    await r.set("ranking_weights", json.dumps(weights), ex=WEIGHTS_TTL)
