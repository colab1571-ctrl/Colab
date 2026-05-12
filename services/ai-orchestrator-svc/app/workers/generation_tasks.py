"""
Celery tasks for Replicate prediction creation.

Enqueued when a user invokes /mockup-image or /mockup-audio,
or when AI Collab Preview consent is approved.
"""

from __future__ import annotations

import logging
import uuid

import httpx

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.generation_tasks.enqueue_image_prediction",
    bind=True,
    max_retries=2,
    default_retry_delay=5,
)
def enqueue_image_prediction(
    self,
    interaction_id: str,
    asset_id: str,
    prompt: str,
    tier: str,
    webhook_url: str,
) -> None:
    """Create a Replicate image prediction and update AIInteraction."""
    import asyncio
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    import os

    from app.models import AIInteraction, MockupAsset
    from app.services.replicate_client import create_image_prediction

    db_url = os.environ.get(
        "DATABASE_URL", "postgresql://colab:colab@localhost:5432/colab"
    ).replace("postgresql+asyncpg://", "postgresql://")

    try:
        async def _run():
            async with httpx.AsyncClient() as http:
                return await create_image_prediction(prompt, tier, webhook_url, http)

        prediction_id = asyncio.get_event_loop().run_until_complete(_run())

        engine = create_engine(db_url, pool_pre_ping=True)
        with Session(engine) as session:
            interaction = session.get(AIInteraction, uuid.UUID(interaction_id))
            asset = session.get(MockupAsset, uuid.UUID(asset_id))
            if interaction:
                interaction.replicate_prediction_id = prediction_id
                interaction.status = "processing"
            if asset:
                asset.replicate_prediction_id = prediction_id
            session.commit()

        logger.info("Image prediction %s enqueued for interaction %s", prediction_id, interaction_id)
    except Exception as exc:
        logger.error("enqueue_image_prediction failed: %s", exc)
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.workers.generation_tasks.enqueue_audio_prediction",
    bind=True,
    max_retries=2,
    default_retry_delay=5,
)
def enqueue_audio_prediction(
    self,
    interaction_id: str,
    asset_id: str,
    prompt: str,
    tier: str,
    webhook_url: str,
) -> None:
    """Create a Replicate audio prediction and update AIInteraction."""
    import asyncio
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    import os

    from app.models import AIInteraction, MockupAsset
    from app.services.replicate_client import create_audio_prediction

    db_url = os.environ.get(
        "DATABASE_URL", "postgresql://colab:colab@localhost:5432/colab"
    ).replace("postgresql+asyncpg://", "postgresql://")

    try:
        async def _run():
            async with httpx.AsyncClient() as http:
                return await create_audio_prediction(prompt, tier, webhook_url, http)

        prediction_id = asyncio.get_event_loop().run_until_complete(_run())

        engine = create_engine(db_url, pool_pre_ping=True)
        with Session(engine) as session:
            interaction = session.get(AIInteraction, uuid.UUID(interaction_id))
            asset = session.get(MockupAsset, uuid.UUID(asset_id))
            if interaction:
                interaction.replicate_prediction_id = prediction_id
                interaction.status = "processing"
            if asset:
                asset.replicate_prediction_id = prediction_id
            session.commit()

        logger.info("Audio prediction %s enqueued for interaction %s", prediction_id, interaction_id)
    except Exception as exc:
        logger.error("enqueue_audio_prediction failed: %s", exc)
        raise self.retry(exc=exc)
