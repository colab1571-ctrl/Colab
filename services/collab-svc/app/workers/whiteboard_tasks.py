"""
Celery tasks for whiteboard export generation.

whiteboard_export_generate:
  - Updates export status to 'generating'
  - In production: spawns headless Playwright render in a Lambda/ECS task
    or calls the Playwright Node.js sidecar to render the tldraw page,
    export as PNG/PDF, and upload to S3.
  - Updates export status to 'ready' or 'failed'
  - Publishes whiteboard.export_ready event

For this implementation the headless render is stubbed.
The real render worker is a separate Node.js process (per plan §3.4 WB-BE-8).
This Celery task's role is to orchestrate and poll the external render job.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="whiteboard.export_generate",
    bind=True,
    max_retries=2,
    default_retry_delay=10,
)
def whiteboard_export_generate(self, export_id: str) -> None:
    """
    Orchestrate whiteboard export generation (async over asyncio.run).
    """
    try:
        asyncio.run(_async_generate_export(uuid.UUID(export_id)))
    except Exception as exc:
        logger.error("whiteboard_export_generate failed for %s: %s", export_id, exc)
        raise self.retry(exc=exc)


async def _async_generate_export(export_id: uuid.UUID) -> None:
    from app.db import AsyncSessionLocal
    from app.services.whiteboard_service import (
        get_export,
        mark_export_failed,
        mark_export_generating,
        mark_export_ready,
    )
    from app.workers.events import emit_event

    async with AsyncSessionLocal() as db:
        export = await get_export(db, export_id)
        if export is None:
            logger.error("Export %s not found", export_id)
            return

        await mark_export_generating(db, export)

        try:
            s3_key = await _render_and_upload(export)
            await mark_export_ready(db, export, s3_key)

            await emit_event(
                "whiteboard.export_ready",
                {
                    "export_id": str(export_id),
                    "collab_id": str(export.collab_id),
                    "requested_by": str(export.requested_by),
                    "format": export.format,
                    "resolution": export.resolution,
                    "s3_key": s3_key,
                },
            )
            logger.info("Whiteboard export ready: %s → %s", export_id, s3_key)

        except Exception as exc:
            await mark_export_failed(db, export, error=str(exc))
            logger.error("Whiteboard export failed: %s — %s", export_id, exc)
            raise


async def _render_and_upload(export) -> str:
    """
    Headless render stub. Real implementation calls the Node.js Playwright
    sidecar / Lambda endpoint, then receives the base64 PNG/PDF blob and
    uploads it to S3.

    Returns the S3 key of the exported file.
    """
    from app.config import get_collab_settings

    settings = get_collab_settings()
    collab_id = export.collab_id
    fmt = export.format
    resolution = export.resolution
    ts = int(datetime.now(UTC).timestamp())

    s3_key = f"whiteboard/exports/{collab_id}/{ts}-{resolution}.{fmt}"

    # --- Stub: in production call Node Playwright sidecar here ---
    # e.g.:
    #   async with httpx.AsyncClient(timeout=30) as client:
    #       resp = await client.post(
    #           settings.playwright_sidecar_url + "/render",
    #           json={
    #               "collab_id": str(collab_id),
    #               "format": fmt,
    #               "resolution": resolution,
    #               "s3_key": s3_key,
    #               "s3_bucket": settings.s3_bucket,
    #           }
    #       )
    #       resp.raise_for_status()
    # ------------------------------------------------------------

    logger.info(
        "Whiteboard render stub: collab=%s fmt=%s res=%s → %s",
        collab_id,
        fmt,
        resolution,
        s3_key,
    )
    return s3_key
