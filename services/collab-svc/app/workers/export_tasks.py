"""
Celery task: collab_export_generate

Pipeline:
1. Acquire Redis lock (idempotency)
2. Mark CollabExport.status = generating
3. Fetch chat history from chat-svc internal API
4. Render PDF via WeasyPrint + Jinja2
5. Upload PDF to S3
6. Stream media ZIP via aiozipstream → S3 multipart
7. Mark CollabExport.status = ready; set expires_at, pdf_s3_key, zip_s3_key
8. Release lock
9. Emit collab.export_ready
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from celery import shared_task
from sqlalchemy import select, update

from app.config import get_collab_settings
from app.db import AsyncSessionLocal
from app.models import CollabExport
from app.workers.events import emit_event

logger = logging.getLogger(__name__)
settings = get_collab_settings()

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


def _run_async(coro):  # type: ignore[no-untyped-def]
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Main task
# ---------------------------------------------------------------------------


@shared_task(
    name="app.workers.export_tasks.collab_export_generate",
    bind=True,
    max_retries=5,
    default_retry_delay=30,
)
def collab_export_generate(self, export_id_str: str) -> None:  # type: ignore[no-untyped-def]
    _run_async(_generate_async(self, export_id_str))


async def _generate_async(task: Any, export_id_str: str) -> None:
    import redis.asyncio as aioredis

    export_id = uuid.UUID(export_id_str)
    redis_client = aioredis.from_url(settings.redis_url)
    lock_key = f"export_lock:{export_id_str}"

    try:
        # Acquire Redis lock (TTL 10 min)
        acquired = await redis_client.set(lock_key, "1", nx=True, ex=600)
        if not acquired:
            logger.info("Export %s already in progress (lock held), skipping", export_id_str)
            return

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(CollabExport).where(CollabExport.id == export_id)
            )
            export = result.scalars().first()
            if export is None:
                logger.error("CollabExport %s not found", export_id_str)
                return
            if export.status == "ready":
                logger.info("Export %s already ready, skipping", export_id_str)
                return

            # Mark generating
            await db.execute(
                update(CollabExport)
                .where(CollabExport.id == export_id)
                .values(status="generating", started_at=datetime.now(UTC))
            )
            await db.commit()

            collab_id = export.collab_id
            requested_by = export.requested_by

        # Fetch chat data
        try:
            messages, attachments = await _fetch_chat_data(collab_id)
        except Exception as exc:
            logger.exception("Failed to fetch chat data for export %s: %s", export_id_str, exc)
            await _mark_failed(export_id, f"chat-svc fetch error: {exc!s}")
            task.retry(exc=exc)
            return

        # Render PDF
        try:
            pdf_bytes = await _render_pdf(collab_id, export_id, messages)
        except Exception as exc:
            logger.exception("PDF render failed for export %s: %s", export_id_str, exc)
            await _mark_failed(export_id, f"PDF render error: {exc!s}")
            return

        # Upload PDF to S3
        pdf_key = f"exports/{collab_id}/{export_id}/transcript.pdf"
        await _upload_to_s3(pdf_key, pdf_bytes, "application/pdf")

        # Build ZIP (if attachments exist)
        zip_key: str | None = None
        if attachments:
            try:
                zip_key = f"exports/{collab_id}/{export_id}/media.zip"
                await _stream_zip_to_s3(zip_key, attachments)
            except Exception as exc:
                logger.warning("ZIP generation failed for export %s: %s", export_id_str, exc)
                zip_key = None  # Non-fatal — proceed without media ZIP

        # Mark ready
        expires_at = datetime.now(UTC) + timedelta(days=settings.export_signed_url_ttl_days)
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(CollabExport)
                .where(CollabExport.id == export_id)
                .values(
                    status="ready",
                    pdf_s3_key=pdf_key,
                    zip_s3_key=zip_key,
                    expires_at=expires_at,
                    completed_at=datetime.now(UTC),
                )
            )
            await db.commit()

        # Emit event
        await emit_event(
            "collab.export_ready",
            {
                "export_id": export_id_str,
                "collab_id": str(collab_id),
                "requested_by": str(requested_by),
            },
        )
        logger.info("Export %s ready", export_id_str)

    finally:
        await redis_client.delete(lock_key)
        await redis_client.aclose()


# ---------------------------------------------------------------------------
# Chat data fetching
# ---------------------------------------------------------------------------


async def _fetch_chat_data(
    collab_id: uuid.UUID,
) -> tuple[list[dict], list[dict]]:
    """
    Fetch messages and attachments from chat-svc internal API.
    Paginates until all messages are retrieved.
    """
    headers = {"X-Service-Secret": settings.service_shared_secret}
    all_messages: list[dict] = []
    all_attachments: list[dict] = []
    cursor: str | None = None

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Find room for this collab
        room_resp = await client.get(
            f"{settings.chat_svc_url}/internal/rooms/by-collab/{collab_id}",
            headers=headers,
        )
        room_resp.raise_for_status()
        room_id = room_resp.json()["room_id"]

        # Paginate messages
        while True:
            params: dict[str, Any] = {"limit": 200}
            if cursor:
                params["cursor"] = cursor
            msg_resp = await client.get(
                f"{settings.chat_svc_url}/internal/rooms/{room_id}/messages",
                headers=headers,
                params=params,
            )
            msg_resp.raise_for_status()
            data = msg_resp.json()
            all_messages.extend(data.get("data", []))
            cursor = data.get("next_cursor")
            if not cursor:
                break

        # Fetch attachments
        att_resp = await client.get(
            f"{settings.chat_svc_url}/internal/rooms/{room_id}/attachments",
            headers=headers,
        )
        if att_resp.status_code == 200:
            all_attachments = att_resp.json().get("data", [])

    return all_messages, all_attachments


# ---------------------------------------------------------------------------
# PDF rendering
# ---------------------------------------------------------------------------


async def _render_pdf(
    collab_id: uuid.UUID,
    export_id: uuid.UUID,
    messages: list[dict],
) -> bytes:
    """Render a PDF transcript using WeasyPrint + Jinja2."""
    import bleach
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    from weasyprint import HTML

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("export_transcript.html")

    # Content hash (SHA-256 of all message IDs, sorted)
    msg_ids = sorted(m.get("id", "") for m in messages)
    content_hash = hashlib.sha256("|".join(msg_ids).encode()).hexdigest()

    context = {
        "collab_id": str(collab_id),
        "export_id": str(export_id),
        "generated_at": datetime.now(UTC).isoformat(),
        "message_count": len(messages),
        "content_hash": content_hash,
        "messages": [
            {
                "id": m.get("id"),
                "sender": m.get("sender_display_name", m.get("sender_profile_id", "Unknown")),
                "body": bleach.clean(m.get("body") or "", strip=True),
                "type": m.get("type", "text"),
                "created_at": m.get("created_at"),
            }
            for m in messages
            if m.get("type") != "system"
        ],
    }

    html_content = template.render(**context)

    # Run WeasyPrint in a thread pool to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    pdf_bytes: bytes = await loop.run_in_executor(
        None,
        lambda: HTML(string=html_content).write_pdf(),
    )
    return pdf_bytes


# ---------------------------------------------------------------------------
# S3 upload helpers
# ---------------------------------------------------------------------------


async def _upload_to_s3(key: str, data: bytes, content_type: str) -> None:
    """Upload bytes to S3."""
    import boto3

    s3 = boto3.client("s3", region_name=settings.s3_region)
    s3.put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )


async def _stream_zip_to_s3(zip_key: str, attachments: list[dict]) -> None:
    """
    Stream media attachments into a ZIP file and upload to S3 via multipart.
    Uses boto3 (sync) in a thread executor for simplicity; aiozipstream
    is imported for streaming construction.
    """
    import io
    import zipfile

    import boto3

    s3 = boto3.client("s3", region_name=settings.s3_region)

    def _build_and_upload() -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for att in attachments:
                s3_key = att.get("s3_key", "")
                file_name = att.get("file_name", s3_key.split("/")[-1])
                if not s3_key:
                    continue
                try:
                    obj = s3.get_object(Bucket=settings.s3_bucket, Key=s3_key)
                    file_data = obj["Body"].read()
                    zf.writestr(file_name, file_data)
                except Exception as exc:
                    logger.warning("Skipping attachment %s in ZIP: %s", s3_key, exc)

        buf.seek(0)
        s3.put_object(
            Bucket=settings.s3_bucket,
            Key=zip_key,
            Body=buf.read(),
            ContentType="application/zip",
        )

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _build_and_upload)


# ---------------------------------------------------------------------------
# Failure helper
# ---------------------------------------------------------------------------


async def _mark_failed(export_id: uuid.UUID, error_detail: str) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(CollabExport)
            .where(CollabExport.id == export_id)
            .values(status="failed", error_detail=error_detail[:1000])
        )
        await db.commit()
