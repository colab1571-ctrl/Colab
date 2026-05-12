"""
Whiteboard persistence service: snapshot save/load, Y.Doc Redis cache,
export job management.

Snapshot strategy (per plan §2.3):
1. Every incoming Y.js op → append WhiteboardOp row, update Redis hot doc.
2. 10s idle timer → encode full Y.Doc state → PUT to S3 → insert WhiteboardSnapshot.
3. On reconnect → fetch latest snapshot, apply delta ops since snapshot.version.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

import aiobotocore.session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_collab_settings
from app.models_tools import WhiteboardExport, WhiteboardOp, WhiteboardSnapshot

logger = logging.getLogger(__name__)
settings = get_collab_settings()

SNAPSHOT_TTL_SIGNED_URL_SECONDS = 300  # 5 min


# ---------------------------------------------------------------------------
# Redis hot-cache key helpers
# ---------------------------------------------------------------------------


def _redis_doc_key(collab_id: uuid.UUID) -> str:
    return f"wb:doc:{collab_id}"


def _redis_lamport_key(collab_id: uuid.UUID) -> str:
    return f"wb:lamport:{collab_id}"


# ---------------------------------------------------------------------------
# Snapshot persistence
# ---------------------------------------------------------------------------


async def save_snapshot(
    db: AsyncSession,
    collab_id: uuid.UUID,
    doc_binary: bytes,
    lamport: int,
) -> WhiteboardSnapshot:
    """
    Upload doc_binary to S3 and record a WhiteboardSnapshot row.
    Called by the idle-timer task in the ypy-websocket handler.
    """
    import io

    s3_key = f"whiteboard/{collab_id}/snap-{int(datetime.now(UTC).timestamp())}.bin"

    session = aiobotocore.session.get_session()
    async with session.create_client("s3", region_name=settings.s3_region) as s3:
        await s3.put_object(
            Bucket=settings.s3_bucket,
            Key=s3_key,
            Body=doc_binary,
            ContentType="application/octet-stream",
        )

    snapshot = WhiteboardSnapshot(
        collab_id=collab_id,
        s3_key=s3_key,
        version=lamport,
    )
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)
    logger.info("Whiteboard snapshot saved: collab=%s version=%d", collab_id, lamport)
    return snapshot


async def get_latest_snapshot(
    db: AsyncSession,
    collab_id: uuid.UUID,
) -> WhiteboardSnapshot | None:
    result = await db.execute(
        select(WhiteboardSnapshot)
        .where(WhiteboardSnapshot.collab_id == collab_id)
        .order_by(WhiteboardSnapshot.version.desc())
        .limit(1)
    )
    return result.scalars().first()


async def get_snapshot_binary(snapshot: WhiteboardSnapshot) -> bytes:
    """Download S3 blob for the given snapshot."""
    session = aiobotocore.session.get_session()
    async with session.create_client("s3", region_name=settings.s3_region) as s3:
        resp = await s3.get_object(Bucket=settings.s3_bucket, Key=snapshot.s3_key)
        async with resp["Body"] as stream:
            return await stream.read()


async def get_delta_ops(
    db: AsyncSession,
    collab_id: uuid.UUID,
    since_lamport: int,
) -> list[WhiteboardOp]:
    """Fetch all ops with lamport > since_lamport for incremental hydration."""
    result = await db.execute(
        select(WhiteboardOp)
        .where(
            WhiteboardOp.collab_id == collab_id,
            WhiteboardOp.lamport > since_lamport,
        )
        .order_by(WhiteboardOp.lamport.asc())
    )
    return list(result.scalars().all())


async def append_op(
    db: AsyncSession,
    collab_id: uuid.UUID,
    actor_profile_id: uuid.UUID,
    op_data: bytes,
    lamport: int,
) -> WhiteboardOp:
    op = WhiteboardOp(
        collab_id=collab_id,
        lamport=lamport,
        actor_profile_id=actor_profile_id,
        op_data=op_data,
    )
    db.add(op)
    await db.commit()
    return op


# ---------------------------------------------------------------------------
# Export management
# ---------------------------------------------------------------------------


async def create_export_record(
    db: AsyncSession,
    collab_id: uuid.UUID,
    requested_by: uuid.UUID,
    fmt: str,
    resolution: str,
) -> WhiteboardExport:
    export = WhiteboardExport(
        collab_id=collab_id,
        requested_by=requested_by,
        format=fmt,
        resolution=resolution,
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    db.add(export)
    await db.commit()
    await db.refresh(export)
    return export


async def get_export(
    db: AsyncSession,
    export_id: uuid.UUID,
    requested_by: uuid.UUID | None = None,
) -> WhiteboardExport | None:
    stmt = select(WhiteboardExport).where(WhiteboardExport.id == export_id)
    if requested_by is not None:
        stmt = stmt.where(WhiteboardExport.requested_by == requested_by)
    result = await db.execute(stmt)
    return result.scalars().first()


async def mark_export_generating(
    db: AsyncSession, export: WhiteboardExport
) -> None:
    export.status = "generating"
    await db.commit()


async def mark_export_ready(
    db: AsyncSession,
    export: WhiteboardExport,
    s3_key: str,
) -> None:
    export.status = "ready"
    export.s3_key = s3_key
    export.completed_at = datetime.now(UTC)
    export.expires_at = datetime.now(UTC) + timedelta(minutes=5)
    await db.commit()


async def mark_export_failed(
    db: AsyncSession,
    export: WhiteboardExport,
    error: str,
) -> None:
    export.status = "failed"
    export.error_detail = error
    export.completed_at = datetime.now(UTC)
    await db.commit()


def get_export_signed_url(export: WhiteboardExport) -> str | None:
    """Return a signed CloudFront URL or direct S3 URL for the export."""
    if not export.s3_key:
        return None
    # Simple S3 public URL — in production, generate a signed URL here.
    return f"https://{settings.cloudfront_domain}/{export.s3_key}"
