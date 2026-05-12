"""
profile-svc — Celery task for generating profile text embeddings.

Uses OpenAI text-embedding-3-large at dimensions=1536 for pgvector HNSW.
Embedded text: normalized(display_name + bio + obsessed_with + vocations + portfolio captions)
"""

from __future__ import annotations

import logging
import uuid

from celery import shared_task

logger = logging.getLogger(__name__)


def _normalize_text(text: str) -> str:
    """Lowercase, NFC-normalize, strip excess whitespace."""
    import unicodedata
    return unicodedata.normalize("NFC", text.lower()).strip()


@shared_task(bind=True, name="app.workers.embedding_tasks.generate_profile_embedding", max_retries=3)
def generate_profile_embedding(self, profile_id: str) -> dict:
    """Generate and persist 1536-d embedding for a profile."""
    from app.workers._runner import run_sync
    try:
        return run_sync(_async_generate_embedding(profile_id))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


async def _async_generate_embedding(profile_id: str) -> dict:
    from app.config import get_settings
    from app.db import async_session_factory
    from app.models import Profile

    settings = get_settings()
    pid = uuid.UUID(profile_id)

    if not settings.openai_api_key:
        logger.warning("OpenAI API key not configured; skipping embedding for %s", profile_id)
        return {"skipped": True, "reason": "no_api_key"}

    async with async_session_factory() as session:
        profile = await session.get(Profile, pid)
        if not profile:
            return {"skipped": True}

        # Build embedding text
        parts = []
        if profile.display_name:
            parts.append(profile.display_name)
        if profile.bio:
            parts.append(profile.bio)
        if profile.obsessed_with:
            parts.append(profile.obsessed_with)
        for voc in profile.vocations:
            parts.append(f"{voc.category} {voc.subtag}")
        for item in profile.portfolio_items:
            if item.caption and item.ai_review_status == "passed":
                parts.append(item.caption)

        embed_text = _normalize_text(" ".join(parts))
        if not embed_text:
            return {"skipped": True, "reason": "empty_text"}

        import httpx
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": settings.embedding_model,
                    "input": embed_text,
                    "dimensions": settings.embedding_dimensions,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            vector = data["data"][0]["embedding"]

        profile.embedding = vector
        await session.commit()

    return {"profile_id": profile_id, "dim": len(vector)}
