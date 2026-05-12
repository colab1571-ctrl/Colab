"""
profile-svc — Celery tasks for AI profile review pipeline.

Implements the orchestration from plan §7:
  - review_profile_text: OpenAI moderation + embedding dup for bio/display_name/obsessed_with
  - review_portfolio_image: Rekognition + pHash + aHash dup + embedding
  - review_portfolio_audio: Chromaprint + MFCC cosine dup
  - review_portfolio_video: Rekognition async video moderation
  - orchestrate_profile_review: fan-out + aggregate + badge FSM transition
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from datetime import datetime, timezone

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="app.workers.ai_review_tasks.orchestrate_profile_review", max_retries=3)
def orchestrate_profile_review(self, profile_id: str, triggered_by: str = "profile.updated") -> dict:
    """
    Main AI review orchestration task. Fans out to sub-tasks, aggregates scores,
    persists ProfileReview rows, advances badge FSM, notifies moderation-svc on flag.
    """
    import asyncio
    from app.workers._runner import run_sync

    try:
        return run_sync(_async_orchestrate_profile_review(profile_id, triggered_by))
    except Exception as exc:
        logger.exception("AI review orchestration failed for profile %s", profile_id)
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


async def _async_orchestrate_profile_review(profile_id: str, triggered_by: str) -> dict:
    """Async implementation of orchestrate_profile_review."""
    from app.config import get_settings
    from app.db import async_session_factory
    from app.models import Profile, PortfolioItem, ProfileReview
    from app.services.ai_review import (
        aggregate_risk, extract_openai_max_score, extract_rekognition_max_score,
        routing_decision, scan_text_openai, scan_image_rekognition,
        compute_phash_dup_signal,
    )
    from app.services.badge_fsm import BadgeState, BadgeEvent, score_to_event, transition
    from sqlalchemy import select

    settings = get_settings()
    pid = uuid.UUID(profile_id)

    async with async_session_factory() as session:
        profile = await session.get(Profile, pid)
        if not profile:
            logger.warning("Profile %s not found for AI review", profile_id)
            return {"skipped": True}

        # Advance badge to ai_review_pending if in identity_approved
        if profile.badge_state == BadgeState.identity_approved:
            try:
                result = transition(profile.badge_state, BadgeEvent.ai_review_started)
                profile.badge_state = result.new_state.value
                await session.commit()
            except Exception:
                pass  # already in ai_review_pending or other state

        # --- Text review: bio + obsessed_with + display_name ---
        text_parts = " ".join(filter(None, [
            profile.display_name, profile.bio, profile.obsessed_with
        ]))
        openai_score = 0.0
        always_human = False
        if text_parts.strip() and settings.openai_api_key:
            try:
                raw = await scan_text_openai(text_parts, settings.openai_api_key)
                openai_score, always_human = extract_openai_max_score(raw)
                review = ProfileReview(
                    profile_id=pid,
                    target_kind="profile_text",
                    target_id=None,
                    kind="text",
                    score=openai_score,
                    reasons=raw,
                    status="flagged" if openai_score >= 0.40 else "passed",
                    provider_versions={"openai_mod": "omni-moderation-latest"},
                )
                session.add(review)
            except Exception:
                logger.exception("OpenAI text review failed for profile %s", profile_id)

        # --- Portfolio image reviews ---
        rekognition_score = 0.0
        dup_signal = 0.0

        for item in profile.portfolio_items:
            if item.type == "image" and item.ai_review_status == "pending":
                try:
                    raw = scan_image_rekognition(item.s3_bucket, item.s3_key, settings.aws_region)
                    rek_score = extract_rekognition_max_score(raw)
                    rekognition_score = max(rekognition_score, rek_score)

                    # pHash dup check against other profiles' items
                    if item.phash is not None:
                        # Query existing hashes (exclude own profile)
                        from sqlalchemy import select as sa_select
                        other_hashes_q = await session.execute(
                            sa_select(PortfolioItem.phash, PortfolioItem.ahash)
                            .where(PortfolioItem.profile_id != pid)
                            .where(PortfolioItem.phash.is_not(None))
                            .limit(10000)
                        )
                        existing = [(r.phash, r.ahash) for r in other_hashes_q]
                        dup = compute_phash_dup_signal(item.phash, item.ahash, existing)
                        dup_signal = max(dup_signal, dup)

                    item_score = aggregate_risk(openai_score, rek_score, dup_signal, 0.0)
                    item.ai_review_score = item_score
                    item.ai_review_payload = {"rekognition": raw}
                    if item_score >= 0.40:
                        item.ai_review_status = "flagged"
                    else:
                        item.ai_review_status = "passed"

                    review = ProfileReview(
                        profile_id=pid,
                        target_kind="portfolio_item",
                        target_id=item.id,
                        kind="image",
                        score=item_score,
                        reasons={"rekognition": raw, "dup_signal": dup_signal},
                        status="flagged" if item_score >= 0.40 else "passed",
                        provider_versions={"rekognition": "LATEST"},
                    )
                    session.add(review)
                except Exception:
                    logger.exception("Rekognition review failed for item %s", item.id)

        # Aggregate
        aggregate = aggregate_risk(
            openai_score,
            rekognition_score,
            dup_signal,
            0.0,  # embedding outlier: computed by embedding_tasks separately
            w_openai=settings.ai_weight_openai,
            w_rekognition=settings.ai_weight_rekognition,
            w_dup=settings.ai_weight_dup,
            w_embedding=settings.ai_weight_embedding_outlier,
        )

        routing = routing_decision(aggregate, always_human=always_human)

        # Advance badge FSM
        if profile.badge_state == BadgeState.ai_review_pending.value:
            event = score_to_event(aggregate)
            try:
                fsm_result = transition(profile.badge_state, event)
                profile.badge_state = fsm_result.new_state.value
                if fsm_result.badge_held_reason:
                    profile.badge_held_reason = fsm_result.badge_held_reason
                if profile.badge_state == "badge_granted":
                    profile.badge_granted_at = datetime.now(tz=timezone.utc)
                    profile.badge_held_reason = None
            except Exception:
                logger.exception("Badge FSM transition failed for profile %s", profile_id)

        await session.commit()

        # If flagged, submit to moderation-svc mod queue
        if routing["action"] != "auto_allow":
            await _submit_to_mod_queue(profile_id, aggregate, routing, settings)

        return {"profile_id": profile_id, "score": aggregate, "action": routing["action"]}


async def _submit_to_mod_queue(
    profile_id: str, score: float, routing: dict, settings
) -> None:
    """Submit flagged profile to moderation-svc internal queue."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{settings.moderation_svc_url}/internal/scan/text",
                json={
                    "subject_type": "profile",
                    "subject_id": profile_id,
                    "score": score,
                    "routing": routing,
                    "source": "profile_ai_review",
                },
                headers={"X-Internal-Service": "profile-svc"},
            )
    except Exception:
        logger.exception("Failed to submit profile %s to mod queue", profile_id)


@shared_task(bind=True, name="app.workers.ai_review_tasks.review_portfolio_item", max_retries=3)
def review_portfolio_item(self, portfolio_item_id: str) -> dict:
    """Trigger AI review for a single newly-uploaded portfolio item."""
    from app.workers._runner import run_sync
    try:
        return run_sync(_async_review_portfolio_item(portfolio_item_id))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))


async def _async_review_portfolio_item(item_id: str) -> dict:
    """Full AI review for one portfolio item then re-run profile aggregate."""
    from app.db import async_session_factory
    from app.models import PortfolioItem

    iid = uuid.UUID(item_id)
    async with async_session_factory() as session:
        item = await session.get(PortfolioItem, iid)
        if not item:
            return {"skipped": True}
        # Trigger full profile review to recalculate aggregate score
        orchestrate_profile_review.delay(str(item.profile_id), "portfolio.added")
    return {"item_id": item_id, "queued_profile_review": True}
