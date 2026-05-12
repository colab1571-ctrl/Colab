"""
profile-svc — Celery tasks for health score computation and OAuth refresh.

Tasks:
  - recompute_all_health_scores: nightly Celery Beat job
  - recompute_profile_health_score: single-profile recompute
  - refresh_expiring_oauth_tokens: daily token refresh check
"""

from __future__ import annotations

import logging
import uuid

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="app.workers.health_score_tasks.recompute_all_health_scores")
def recompute_all_health_scores() -> dict:
    """Nightly: recompute health scores for all active profiles."""
    from app.workers._runner import run_sync
    return run_sync(_async_recompute_all())


async def _async_recompute_all() -> dict:
    from app.db import async_session_factory
    from app.models import Profile
    from sqlalchemy import select

    updated = 0
    async with async_session_factory() as session:
        result = await session.execute(select(Profile.id))
        profile_ids = [row[0] for row in result]

    for pid in profile_ids:
        recompute_profile_health_score.delay(str(pid))
        updated += 1

    logger.info("Queued health score recompute for %d profiles", updated)
    return {"queued": updated}


@shared_task(bind=True, name="app.workers.health_score_tasks.recompute_profile_health_score", max_retries=3)
def recompute_profile_health_score(self, profile_id: str) -> dict:
    """Recompute health score for a single profile."""
    from app.workers._runner import run_sync
    try:
        return run_sync(_async_recompute_one(profile_id))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


async def _async_recompute_one(profile_id: str) -> dict:
    from app.db import async_session_factory
    from app.models import Profile
    from app.services.health_score import compute_health_score

    pid = uuid.UUID(profile_id)
    async with async_session_factory() as session:
        profile = await session.get(Profile, pid)
        if not profile:
            return {"skipped": True}

        # Determine if identity is approved (badge_state >= identity_approved)
        identity_approved = profile.badge_state in (
            "identity_approved", "ai_review_pending", "badge_granted"
        )

        new_score = compute_health_score(
            profile,
            identity_approved=identity_approved,
        )
        profile.profile_health_score = new_score
        await session.commit()

    return {"profile_id": profile_id, "score": new_score}


@shared_task(name="app.workers.health_score_tasks.refresh_expiring_oauth_tokens")
def refresh_expiring_oauth_tokens() -> dict:
    """Daily: refresh Instagram tokens expiring within 7 days."""
    from app.workers._runner import run_sync
    return run_sync(_async_refresh_expiring())


async def _async_refresh_expiring() -> dict:
    from datetime import datetime, timedelta, timezone
    from app.db import async_session_factory
    from app.models import ExternalLink
    from app.config import get_settings
    from sqlalchemy import select

    settings = get_settings()
    soon = datetime.now(tz=timezone.utc) + timedelta(days=7)
    refreshed = 0

    async with async_session_factory() as session:
        result = await session.execute(
            select(ExternalLink).where(
                ExternalLink.provider == "instagram",
                ExternalLink.token_expires_at <= soon,
                ExternalLink.sync_state == "ok",
            )
        )
        links = result.scalars().all()

        for link in links:
            try:
                from app.services.kms_crypto import decrypt_token, encrypt_token, TokenCiphertext
                from app.services.oauth_providers import InstagramOAuth
                from datetime import timedelta

                redirect_uri = f"{settings.app_domain}/oauth/instagram/callback"
                ig = InstagramOAuth(settings.instagram_app_id, settings.instagram_app_secret, redirect_uri)

                if link.encrypted_access_token and link.data_key_ciphertext:
                    current_token = decrypt_token(
                        link.encrypted_access_token,
                        link.data_key_ciphertext,
                        "instagram",
                        str(link.profile_id),
                        "access",
                    )
                    new_data = await ig.refresh_token(current_token)
                    new_token = new_data.get("access_token", current_token)
                    new_expires_in = new_data.get("expires_in", 5184000)

                    ct = encrypt_token(new_token, "instagram", str(link.profile_id), "access")
                    link.encrypted_access_token = ct.ciphertext
                    link.data_key_ciphertext = ct.data_key_ciphertext
                    link.token_expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=new_expires_in)
                    refreshed += 1
            except Exception:
                logger.exception("Failed to refresh Instagram token for link %s", link.id)
                link.sync_state = "needs_reauth"

        await session.commit()

    return {"refreshed": refreshed}
