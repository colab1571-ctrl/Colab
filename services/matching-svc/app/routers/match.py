"""
matching-svc — match router.

Endpoints:
  GET  /match/score?from={profile_id}&to={profile_id}  (internal)
  POST /match/reindex                                   (internal, Celery trigger)
  GET  /internal/candidates                             (internal, for discovery-svc)
  GET  /internal/recommendations/{profile_id}           (internal, cold-start fallback)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.schemas.matching import (
    MatchScoreResponse,
    ReindexResponse,
    CandidatesResponse,
    CandidateItem,
    RecommendationResponse,
)

router = APIRouter(tags=["match"])
logger = logging.getLogger(__name__)
_settings = get_settings()


def _require_internal(x_internal_service_token: str = Header(...)) -> None:
    if x_internal_service_token != _settings.internal_service_secret:
        raise HTTPException(status_code=403, detail="forbidden")


# ---------------------------------------------------------------------------
# GET /match/score
# ---------------------------------------------------------------------------

@router.get("/match/score", response_model=MatchScoreResponse)
async def get_match_score(
    from_: str = Query(..., alias="from"),
    to: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_require_internal),
) -> MatchScoreResponse:
    row = await db.execute(
        sa_text("""
            SELECT from_profile_id, to_profile_id, score,
                   emb_sim, comp_voc, activity, health, rand_component,
                   computed_at, version
            FROM matching.match_scores
            WHERE from_profile_id = :from_id AND to_profile_id = :to_id
        """),
        {"from_id": from_, "to_id": to},
    )
    result = row.fetchone()
    if not result:
        raise HTTPException(status_code=404, detail="score not found; trigger reindex")

    return MatchScoreResponse(
        from_profile_id=result[0],
        to_profile_id=result[1],
        score=result[2],
        components={
            "emb_sim": result[3],
            "comp_voc": result[4],
            "activity": result[5],
            "health": result[6],
            "rand": result[7],
        },
        computed_at=result[8],
        version=result[9],
    )


# ---------------------------------------------------------------------------
# POST /match/reindex
# ---------------------------------------------------------------------------

@router.post("/match/reindex", status_code=202, response_model=ReindexResponse)
async def trigger_reindex(
    _: None = Depends(_require_internal),
) -> ReindexResponse:
    from app.workers.tasks import nightly_rerank
    task = nightly_rerank.apply_async()
    return ReindexResponse(job_id=str(task.id), status="queued")


# ---------------------------------------------------------------------------
# GET /internal/candidates (consumed by discovery-svc feed assembly)
# ---------------------------------------------------------------------------

@router.get("/internal/candidates", response_model=CandidatesResponse)
async def get_candidates(
    viewer_profile_id: str = Query(...),
    filters: str = Query("{}"),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_require_internal),
) -> CandidatesResponse:
    """
    Return ranked candidate profile IDs for a viewer, with filter application.
    Filters are applied as additional WHERE clauses.
    """
    import json as _json
    filter_data = _json.loads(filters) if filters else {}

    vocation_categories = filter_data.get("vocation_categories", [])
    last_active_days = filter_data.get("last_active_days", 90)
    min_collabs = filter_data.get("min_successful_collabs", 0)
    experience_min = filter_data.get("experience_level_min")
    experience_max = filter_data.get("experience_level_max")
    open_to_remote = filter_data.get("open_to_remote")

    # Base query: join match_scores with profiles for filter application
    params: dict = {
        "viewer_id": viewer_profile_id,
        "last_active_cutoff": datetime.now(tz=timezone.utc) - timedelta(days=last_active_days),
        "limit": limit,
        "offset": offset,
    }

    vocation_filter = ""
    if vocation_categories:
        vocation_filter = """
            AND EXISTS (
                SELECT 1 FROM profile.profile_vocations pv2
                WHERE pv2.profile_id = ms.to_profile_id
                  AND pv2.category = ANY(:vocation_categories)
            )
        """
        params["vocation_categories"] = vocation_categories

    exp_filter = ""
    if experience_min is not None:
        exp_filter += " AND p.experience_level >= :exp_min"
        params["exp_min"] = experience_min
    if experience_max is not None:
        exp_filter += " AND p.experience_level <= :exp_max"
        params["exp_max"] = experience_max

    remote_filter = ""
    if open_to_remote is not None:
        remote_filter = " AND p.open_to_remote = :open_to_remote"
        params["open_to_remote"] = open_to_remote

    query = sa_text(f"""
        SELECT ms.to_profile_id::text, ms.score
        FROM matching.match_scores ms
        JOIN profile.profiles p ON p.id = ms.to_profile_id
        WHERE ms.from_profile_id = :viewer_id
          AND p.last_active_at > :last_active_cutoff
          AND p.badge_state = 'badge_granted'
          AND p.is_deleted = false
          {vocation_filter}
          {exp_filter}
          {remote_filter}
        ORDER BY ms.score DESC
        LIMIT :limit OFFSET :offset
    """)

    rows = (await db.execute(query, params)).fetchall()
    candidates = [CandidateItem(profile_id=r[0], score=r[1]) for r in rows]

    return CandidatesResponse(candidates=candidates, total=len(candidates))


# ---------------------------------------------------------------------------
# GET /internal/recommendations/{profile_id} (cold-start fallback)
# ---------------------------------------------------------------------------

@router.get("/internal/recommendations/{profile_id}", response_model=RecommendationResponse)
async def get_recommendations(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_require_internal),
) -> RecommendationResponse:
    now = datetime.now(tz=timezone.utc)

    # Try RecommendationSet first
    row = await db.execute(
        sa_text("""
            SELECT profile_ids, generated_at, rationale
            FROM matching.recommendation_sets
            WHERE user_id = (
                SELECT user_id FROM profile.profiles WHERE id = :pid
            )
        """),
        {"pid": profile_id},
    )
    rec = row.fetchone()
    if rec:
        return RecommendationResponse(
            profile_ids=[str(pid) for pid in rec[0]],
            generated_at=rec[1].isoformat(),
            rationale=rec[2] or {},
        )

    # Cold-start: top-10 from match_scores
    rows = await db.execute(
        sa_text("""
            SELECT to_profile_id::text, score
            FROM matching.match_scores
            WHERE from_profile_id = :pid
            ORDER BY score DESC
            LIMIT 10
        """),
        {"pid": profile_id},
    )
    profile_ids = [r[0] for r in rows.fetchall()]

    return RecommendationResponse(
        profile_ids=profile_ids,
        generated_at=now.isoformat(),
        rationale={},
    )
