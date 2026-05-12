"""
matching-svc — Celery tasks.

Tasks:
  matching.nightly_rerank          — full nightly recompute (HNSW ANN top-200)
  matching.recommendation_set_gen  — build RecommendationSet for all active users
  matching.rerank_profile          — on-demand re-rank for a single profile
  discovery.cleanup_expired_hides  — weekly prune of expired hide_3mo rows
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import UUID

from celery import chord, group, shared_task

from app.config import get_settings
from app.services.affinity_cache import get_weights, warm_affinity_cache
from app.services.ranking import (
    AFFINITY_SEED,
    RankingWeights,
    activity_score,
    comp_voc_score,
    compute_score,
    rand_component,
)
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)
_settings = get_settings()


def _run(coro):  # type: ignore[no-untyped-def]
    """Run an async coroutine from a sync Celery task."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Nightly rerank — chunked parallel subtasks
# ---------------------------------------------------------------------------

@celery_app.task(name="matching.nightly_rerank", bind=True, max_retries=2)
def nightly_rerank(self: Any) -> dict:
    """
    Full nightly recompute.
    1. Fetch all active profile IDs from profile-svc.
    2. Chunk into groups of RERANK_CHUNK_SIZE.
    3. Fan-out as Celery subtasks via chord.
    4. Returns summary dict.
    """
    import httpx

    logger.info("nightly_rerank started")

    try:
        resp = httpx.get(
            f"{_settings.profile_svc_url}/internal/profiles/active-ids",
            headers={"X-Internal-Service-Token": _settings.internal_service_secret},
            timeout=30,
        )
        resp.raise_for_status()
        profile_ids: list[str] = resp.json().get("profile_ids", [])
    except Exception as exc:
        logger.error("Failed to fetch active profiles: %s", exc)
        raise self.retry(exc=exc, countdown=60)

    chunk_size = _settings.rerank_chunk_size
    chunks = [profile_ids[i : i + chunk_size] for i in range(0, len(profile_ids), chunk_size)]
    logger.info("nightly_rerank: %d profiles → %d chunks", len(profile_ids), len(chunks))

    # Fan out
    job = group(rerank_chunk.s(chunk) for chunk in chunks)
    result = job.apply_async()
    # Wait for completion (nightly job can afford to block)
    chunk_results = result.get(timeout=1800)

    total_processed = sum(r.get("processed", 0) for r in (chunk_results or []))
    logger.info("nightly_rerank complete: %d profiles processed", total_processed)
    return {"profiles_processed": total_processed, "chunks": len(chunks)}


@celery_app.task(name="matching.rerank_chunk", bind=True)
def rerank_chunk(self: Any, profile_ids: list[str]) -> dict:
    """
    Rerank a chunk of profiles.
    For each profile, fetch HNSW ANN top-200 candidates and compute scores.
    """
    import httpx
    from sqlalchemy import create_engine, text as sa_text
    from sqlalchemy.pool import NullPool

    # Use sync engine for Celery task
    sync_url = _settings.database_url.replace("+asyncpg", "")
    from sqlalchemy import create_engine as sync_engine_factory
    engine = sync_engine_factory(sync_url, poolclass=NullPool)

    weights_data = asyncio.get_event_loop().run_until_complete(get_weights())
    weights = RankingWeights(**{k: v for k, v in weights_data.items() if hasattr(RankingWeights, k)})

    processed = 0
    with engine.connect() as conn:
        for profile_id in profile_ids:
            try:
                # Fetch viewer embedding + vocations
                viewer_row = conn.execute(
                    sa_text("""
                        SELECT pe.embedding, p.last_active_at, p.profile_health_score,
                               array_agg(DISTINCT pv.category) AS vocation_categories
                        FROM profile.profiles p
                        LEFT JOIN profile.profile_embeddings pe ON pe.profile_id = p.id
                        LEFT JOIN profile.profile_vocations pv ON pv.profile_id = p.id
                        WHERE p.id = :pid
                        GROUP BY pe.embedding, p.last_active_at, p.profile_health_score
                    """),
                    {"pid": profile_id},
                ).fetchone()

                if not viewer_row:
                    continue

                viewer_embedding = viewer_row[0]
                viewer_vocations = [v for v in (viewer_row[3] or []) if v]

                # HNSW ANN top-K candidates
                # ef_search = 100 for nightly (quality over speed)
                conn.execute(sa_text("SET hnsw.ef_search = 100"))
                candidates = conn.execute(
                    sa_text("""
                        SELECT p.id::text,
                               CASE WHEN pe.embedding IS NOT NULL AND :has_embedding
                                    THEN 1 - (pe.embedding <=> :viewer_vec::vector)
                                    ELSE 0.0
                               END AS emb_sim,
                               p.last_active_at,
                               p.profile_health_score,
                               array_agg(DISTINCT pv.category) AS vocations
                        FROM profile.profile_embeddings pe
                        JOIN profile.profiles p ON p.id = pe.profile_id
                        LEFT JOIN profile.profile_vocations pv ON pv.profile_id = p.id
                        WHERE p.id != :pid
                          AND p.badge_state = 'badge_granted'
                          AND p.is_deleted = false
                        GROUP BY p.id, pe.embedding, p.last_active_at, p.profile_health_score
                        ORDER BY pe.embedding <=> :viewer_vec::vector
                        LIMIT :top_k
                    """),
                    {
                        "pid": profile_id,
                        "viewer_vec": str(viewer_embedding) if viewer_embedding else "[0]",
                        "has_embedding": viewer_embedding is not None,
                        "top_k": _settings.rerank_top_k,
                    },
                ).fetchall()

                now = datetime.now(tz=timezone.utc)
                upserts = []
                for row in candidates:
                    cand_id = row[0]
                    emb_sim = float(row[1]) if row[1] else 0.0
                    last_active = row[2]
                    health = float(row[3]) if row[3] else 0.0
                    cand_vocations = [v for v in (row[4] or []) if v]

                    cvoc = comp_voc_score(viewer_vocations, cand_vocations)
                    total, es, cv, act, rnd = compute_score(
                        viewer_id=profile_id,
                        candidate_id=cand_id,
                        emb_sim=emb_sim,
                        comp_voc=cvoc,
                        last_active_at=last_active,
                        health=health,
                        weights=weights,
                    )
                    upserts.append({
                        "from_id": profile_id,
                        "to_id": cand_id,
                        "score": total,
                        "emb_sim": es,
                        "comp_voc": cv,
                        "activity": act,
                        "health": health,
                        "rand_component": rnd,
                        "computed_at": now,
                    })

                if upserts:
                    conn.execute(
                        sa_text("""
                            INSERT INTO matching.match_scores
                              (from_profile_id, to_profile_id, score, emb_sim, comp_voc,
                               activity, health, rand_component, computed_at, version)
                            VALUES
                              (:from_id, :to_id, :score, :emb_sim, :comp_voc,
                               :activity, :health, :rand_component, :computed_at,
                               COALESCE((SELECT version FROM matching.match_scores
                                         WHERE from_profile_id = :from_id AND to_profile_id = :to_id), 0) + 1)
                            ON CONFLICT (from_profile_id, to_profile_id) DO UPDATE
                              SET score = EXCLUDED.score,
                                  emb_sim = EXCLUDED.emb_sim,
                                  comp_voc = EXCLUDED.comp_voc,
                                  activity = EXCLUDED.activity,
                                  health = EXCLUDED.health,
                                  rand_component = EXCLUDED.rand_component,
                                  computed_at = EXCLUDED.computed_at,
                                  version = matching.match_scores.version + 1
                        """),
                        upserts,
                    )
                    conn.commit()

                processed += 1
            except Exception as exc:
                logger.error("Error processing profile %s: %s", profile_id, exc)

    engine.dispose()
    return {"processed": processed}


# ---------------------------------------------------------------------------
# Recommendation set generation
# ---------------------------------------------------------------------------

@celery_app.task(name="matching.recommendation_set_gen")
def recommendation_set_gen() -> dict:
    """
    Nightly recommendation set generation at 03:00 UTC.
    Reads fresh match_scores; applies diversity reshuffle; writes RecommendationSet.
    """
    from sqlalchemy import create_engine as sync_engine_factory, text as sa_text
    from sqlalchemy.pool import NullPool
    import json
    import redis as sync_redis

    sync_url = _settings.database_url.replace("+asyncpg", "")
    engine = sync_engine_factory(sync_url, poolclass=NullPool)
    r = sync_redis.from_url(_settings.redis_url, decode_responses=True)

    now = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(days=90)

    processed = 0
    with engine.connect() as conn:
        active_users = conn.execute(
            sa_text("""
                SELECT DISTINCT p.user_id::text, p.id::text
                FROM profile.profiles p
                WHERE p.badge_state = 'badge_granted'
                  AND p.last_active_at > :cutoff
                  AND p.is_deleted = false
            """),
            {"cutoff": cutoff},
        ).fetchall()

        for user_id, profile_id in active_users:
            try:
                # Top-50 pool from match_scores (excluding hidden/blocked)
                pool_rows = conn.execute(
                    sa_text("""
                        SELECT ms.to_profile_id::text, ms.score,
                               array_agg(DISTINCT pv.category) AS vocations,
                               p.location_city
                        FROM matching.match_scores ms
                        JOIN profile.profiles p ON p.id = ms.to_profile_id
                        LEFT JOIN profile.profile_vocations pv ON pv.profile_id = ms.to_profile_id
                        WHERE ms.from_profile_id = :pid
                          AND p.last_active_at > :cutoff
                          AND p.badge_state = 'badge_granted'
                          AND NOT EXISTS (
                              SELECT 1 FROM discovery.hide_3mo h
                              WHERE h.user_id = :uid AND h.hidden_profile_id = ms.to_profile_id
                                AND h.hidden_until > now()
                          )
                          AND NOT EXISTS (
                              SELECT 1 FROM discovery.saved_profiles sp
                              WHERE sp.user_id = :uid AND sp.saved_profile_id = ms.to_profile_id
                          )
                        GROUP BY ms.to_profile_id, ms.score, p.location_city
                        ORDER BY ms.score DESC
                        LIMIT 50
                    """),
                    {"pid": profile_id, "uid": user_id, "cutoff": cutoff},
                ).fetchall()

                if not pool_rows:
                    continue

                # Stratified sample: 5–10 profiles
                # At least 1 cross-discipline (diff vocation from viewer)
                viewer_vocations = conn.execute(
                    sa_text("SELECT array_agg(category) FROM profile.profile_vocations WHERE profile_id = :pid"),
                    {"pid": profile_id},
                ).scalar() or []

                selected = []
                seen_ids = set()

                # Cross-discipline first
                for row in pool_rows:
                    cand_id, score, vocations, city = row
                    vocations = vocations or []
                    if set(vocations).isdisjoint(set(viewer_vocations)) and cand_id not in seen_ids:
                        selected.append(cand_id)
                        seen_ids.add(cand_id)
                        break

                # Fill remaining slots with top-scoring
                for row in pool_rows:
                    if len(selected) >= 10:
                        break
                    cand_id = row[0]
                    if cand_id not in seen_ids:
                        selected.append(cand_id)
                        seen_ids.add(cand_id)

                selected = selected[:10]
                if len(selected) < 5:
                    # Not enough candidates; take whatever we have
                    pass

                rationale = {
                    cid: {"dominant_signal": "emb_sim", "score": float(pool_rows[i][1])}
                    for i, cid in enumerate(selected)
                    if i < len(pool_rows)
                }

                conn.execute(
                    sa_text("""
                        INSERT INTO matching.recommendation_sets
                          (user_id, generated_at, profile_ids, rationale)
                        VALUES (:uid, :now, :pids, :rationale)
                        ON CONFLICT (user_id) DO UPDATE
                          SET generated_at = EXCLUDED.generated_at,
                              profile_ids = EXCLUDED.profile_ids,
                              rationale = EXCLUDED.rationale
                    """),
                    {
                        "uid": user_id,
                        "now": now,
                        "pids": selected,
                        "rationale": json.dumps(rationale),
                    },
                )
                conn.commit()

                # Cache in Redis
                r.set(f"recs:{user_id}", json.dumps(selected), ex=86400)
                processed += 1

            except Exception as exc:
                logger.error("Error generating recs for user %s: %s", user_id, exc)

    engine.dispose()
    logger.info("recommendation_set_gen complete: %d users processed", processed)
    return {"users_processed": processed}


# ---------------------------------------------------------------------------
# On-demand re-rank (hot signal)
# ---------------------------------------------------------------------------

@celery_app.task(name="matching.rerank_profile", bind=True)
def rerank_profile(self: Any, profile_id: str, viewer_user_id: str) -> dict:
    """
    On-demand re-rank triggered by profile.updated event.
    P95 target: <500ms.
    Uses ef_search=40 for lower latency.
    """
    from sqlalchemy import create_engine as sync_engine_factory, text as sa_text
    from sqlalchemy.pool import NullPool

    sync_url = _settings.database_url.replace("+asyncpg", "")
    engine = sync_engine_factory(sync_url, poolclass=NullPool)

    weights_data = asyncio.get_event_loop().run_until_complete(get_weights())
    weights = RankingWeights(**{k: v for k, v in weights_data.items() if hasattr(RankingWeights, k)})

    with engine.connect() as conn:
        # ef_search=40 for on-demand latency
        conn.execute(sa_text("SET hnsw.ef_search = 40"))

        viewer_row = conn.execute(
            sa_text("""
                SELECT pe.embedding, p.last_active_at, p.profile_health_score,
                       array_agg(DISTINCT pv.category) AS vocation_categories
                FROM profile.profiles p
                LEFT JOIN profile.profile_embeddings pe ON pe.profile_id = p.id
                LEFT JOIN profile.profile_vocations pv ON pv.profile_id = p.id
                WHERE p.id = :pid
                GROUP BY pe.embedding, p.last_active_at, p.profile_health_score
            """),
            {"pid": profile_id},
        ).fetchone()

        if not viewer_row:
            engine.dispose()
            return {"status": "profile_not_found"}

        viewer_embedding = viewer_row[0]
        viewer_vocations = [v for v in (viewer_row[3] or []) if v]

        candidates = conn.execute(
            sa_text("""
                SELECT p.id::text, p.last_active_at, p.profile_health_score,
                       CASE WHEN :has_emb THEN 1 - (pe.embedding <=> :viewer_vec::vector)
                            ELSE 0.0 END AS emb_sim,
                       array_agg(DISTINCT pv.category) AS vocations
                FROM profile.profile_embeddings pe
                JOIN profile.profiles p ON p.id = pe.profile_id
                LEFT JOIN profile.profile_vocations pv ON pv.profile_id = p.id
                WHERE p.id != :pid AND p.badge_state = 'badge_granted'
                GROUP BY p.id, pe.embedding, p.last_active_at, p.profile_health_score
                ORDER BY pe.embedding <=> :viewer_vec::vector
                LIMIT :top_k
            """),
            {
                "pid": profile_id,
                "viewer_vec": str(viewer_embedding) if viewer_embedding else "[0]",
                "has_emb": viewer_embedding is not None,
                "top_k": _settings.rerank_top_k,
            },
        ).fetchall()

        now = datetime.now(tz=timezone.utc)
        for row in candidates:
            cand_id, last_active, health, emb_sim, cand_vocations = row
            cand_vocations = [v for v in (cand_vocations or []) if v]
            cvoc = comp_voc_score(viewer_vocations, cand_vocations)
            total, es, cv, act, rnd = compute_score(
                viewer_id=profile_id,
                candidate_id=cand_id,
                emb_sim=float(emb_sim) if emb_sim else 0.0,
                comp_voc=cvoc,
                last_active_at=last_active,
                health=float(health) if health else 0.0,
                weights=weights,
            )
            conn.execute(
                sa_text("""
                    INSERT INTO matching.match_scores
                      (from_profile_id, to_profile_id, score, emb_sim, comp_voc,
                       activity, health, rand_component, computed_at, version)
                    VALUES (:from_id, :to_id, :score, :emb_sim, :comp_voc,
                            :activity, :health, :rand_component, :now, 1)
                    ON CONFLICT (from_profile_id, to_profile_id) DO UPDATE
                      SET score = EXCLUDED.score,
                          emb_sim = EXCLUDED.emb_sim,
                          comp_voc = EXCLUDED.comp_voc,
                          activity = EXCLUDED.activity,
                          health = EXCLUDED.health,
                          rand_component = EXCLUDED.rand_component,
                          computed_at = EXCLUDED.computed_at,
                          version = matching.match_scores.version + 1
                """),
                {
                    "from_id": profile_id, "to_id": cand_id,
                    "score": total, "emb_sim": es, "comp_voc": cv,
                    "activity": act, "health": float(health) if health else 0.0,
                    "rand_component": rnd, "now": now,
                },
            )
        conn.commit()

    engine.dispose()
    return {"status": "ok", "profile_id": profile_id}


# ---------------------------------------------------------------------------
# Cleanup expired hides (weekly)
# ---------------------------------------------------------------------------

@celery_app.task(name="discovery.cleanup_expired_hides")
def cleanup_expired_hides() -> dict:
    from sqlalchemy import create_engine as sync_engine_factory, text as sa_text
    from sqlalchemy.pool import NullPool

    sync_url = _settings.database_url.replace("+asyncpg", "")
    engine = sync_engine_factory(sync_url, poolclass=NullPool)

    with engine.connect() as conn:
        result = conn.execute(
            sa_text("DELETE FROM discovery.hide_3mo WHERE hidden_until < now()")
        )
        conn.commit()
        deleted = result.rowcount

    engine.dispose()
    logger.info("cleanup_expired_hides: deleted %d rows", deleted)
    return {"deleted": deleted}
