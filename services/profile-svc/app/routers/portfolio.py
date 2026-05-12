"""
profile-svc — Portfolio upload/management endpoints.

POST /api/v1/profile/me/portfolio/upload-url  — request presigned POST
POST /api/v1/profile/me/portfolio/{id}/finalize — confirm upload
DELETE /api/v1/profile/me/portfolio/{id}
PATCH /api/v1/profile/me/portfolio/reorder
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import boto3
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.models import Profile
from app.models.profile import PortfolioItem
from app.schemas.profile import (
    PortfolioFinalizeRequest,
    PortfolioItemPublic,
    PortfolioUploadRequest,
    PortfolioUploadResponse,
    ReorderRequest,
)
from app.services.ai_review import (
    ALLOWED_AUDIO_MIMES,
    ALLOWED_IMAGE_MIMES,
    ALLOWED_VIDEO_MIMES,
    AUDIO_SIZE_CAP,
    IMAGE_SIZE_CAP,
    VIDEO_SIZE_CAP,
)

router = APIRouter(prefix="/api/v1/profile/me/portfolio", tags=["portfolio"])

PORTFOLIO_ITEM_LIMIT = 12

_MIME_CAPS: dict[str, tuple[set[str], int]] = {
    "image": (ALLOWED_IMAGE_MIMES, IMAGE_SIZE_CAP),
    "audio": (ALLOWED_AUDIO_MIMES, AUDIO_SIZE_CAP),
    "video": (ALLOWED_VIDEO_MIMES, VIDEO_SIZE_CAP),
}


def _require_auth(request: Request) -> uuid.UUID:
    uid_header = request.headers.get("X-User-Id")
    if not uid_header:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return uuid.UUID(uid_header)


async def _get_profile(user_id: uuid.UUID, session: AsyncSession) -> Profile:
    result = await session.execute(select(Profile).where(Profile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile


@router.post("/upload-url", response_model=PortfolioUploadResponse, status_code=200)
async def request_upload_url(
    body: PortfolioUploadRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> PortfolioUploadResponse:
    """Issue presigned POST policy for direct S3 upload. Enforces MIME + size caps."""
    user_id = _require_auth(request)
    profile = await _get_profile(user_id, session)
    settings = get_settings()

    # Validate type/mime/size
    allowed_mimes, size_cap = _MIME_CAPS.get(body.type, (set(), 0))
    if body.mime not in allowed_mimes:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=f"MIME {body.mime!r} not allowed for type {body.type!r}")
    if body.size_bytes > size_cap:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=f"File exceeds {body.type} size cap of {size_cap // (1024*1024)}MB")

    # Check 12-item cap
    count_result = await session.execute(
        select(func.count()).select_from(PortfolioItem).where(
            PortfolioItem.profile_id == profile.id,
        )
    )
    current_count = count_result.scalar_one()
    if current_count >= PORTFOLIO_ITEM_LIMIT:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Portfolio already at maximum of 12 items")

    # Find next available position
    position = current_count  # 0-indexed

    # Pre-allocate portfolio item row
    item_id = uuid.uuid4()
    s3_key = f"portfolio/{profile.id}/{item_id}"

    item = PortfolioItem(
        id=item_id,
        profile_id=profile.id,
        position=position,
        type=body.type,
        s3_bucket=settings.s3_portfolio_bucket,
        s3_key=s3_key,
        mime=body.mime,
        size_bytes=body.size_bytes,
        ai_review_status="pending",
    )
    session.add(item)
    await session.commit()

    # Generate presigned POST (enforces Content-Length-Range server-side)
    s3 = boto3.client("s3", region_name=settings.s3_region)
    presigned = s3.generate_presigned_post(
        Bucket=settings.s3_portfolio_bucket,
        Key=s3_key,
        Fields={"Content-Type": body.mime},
        Conditions=[
            {"Content-Type": body.mime},
            ["content-length-range", 0, size_cap],
        ],
        ExpiresIn=settings.presigned_url_ttl_seconds,
    )

    expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=settings.presigned_url_ttl_seconds)

    return PortfolioUploadResponse(
        upload=presigned,
        portfolio_item_id=item_id,
        expires_at=expires_at,
    )


@router.post("/{item_id}/finalize", response_model=PortfolioItemPublic)
async def finalize_upload(
    item_id: uuid.UUID,
    body: PortfolioFinalizeRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> PortfolioItemPublic:
    """
    Confirm S3 upload: verify object exists, extract metadata, trigger AI review.
    """
    user_id = _require_auth(request)
    profile = await _get_profile(user_id, session)
    settings = get_settings()

    result = await session.execute(
        select(PortfolioItem).where(
            PortfolioItem.id == item_id,
            PortfolioItem.profile_id == profile.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio item not found")

    # Verify S3 object exists
    s3 = boto3.client("s3", region_name=settings.s3_region)
    try:
        head = s3.head_object(Bucket=item.s3_bucket, Key=item.s3_key)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="S3 object not found; upload first")

    actual_size = head.get("ContentLength", 0)
    actual_mime = head.get("ContentType", "")

    # Validate size matches
    allowed_mimes, size_cap = _MIME_CAPS.get(item.type, (set(), 0))
    if actual_size > size_cap:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Uploaded file exceeds size cap")

    item.size_bytes = actual_size
    item.mime = actual_mime

    if body.caption is not None:
        item.caption = body.caption
    if body.position is not None:
        item.position = body.position

    await session.commit()

    # Fire AI review pipeline async
    from app.workers.ai_review_tasks import review_portfolio_item
    review_portfolio_item.delay(str(item.id))

    # Emit portfolio.portfolio_added event (via event outbox or direct)
    # In production this goes to RabbitMQ via colab_common.events

    return PortfolioItemPublic(
        id=item.id,
        position=item.position,
        type=item.type,
        s3_key=item.s3_key,
        mime=item.mime,
        size_bytes=item.size_bytes,
        caption=item.caption,
        ai_review_status=item.ai_review_status,
        created_at=item.created_at,
    )


@router.delete("/{item_id}", status_code=204)
async def delete_portfolio_item(
    item_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete: S3 versioned bucket retains for 30d. Row deleted immediately."""
    user_id = _require_auth(request)
    profile = await _get_profile(user_id, session)
    settings = get_settings()

    result = await session.execute(
        select(PortfolioItem).where(
            PortfolioItem.id == item_id,
            PortfolioItem.profile_id == profile.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio item not found")

    # Add delete marker in S3 (versioned bucket keeps the file for 30d)
    try:
        s3 = boto3.client("s3", region_name=settings.s3_region)
        s3.delete_object(Bucket=item.s3_bucket, Key=item.s3_key)
    except Exception:
        pass  # best-effort S3 cleanup

    await session.delete(item)
    await session.commit()


@router.patch("/reorder", status_code=200)
async def reorder_portfolio(
    body: ReorderRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Reorder portfolio items. body.order is list of item IDs in desired order."""
    user_id = _require_auth(request)
    profile = await _get_profile(user_id, session)

    result = await session.execute(
        select(PortfolioItem).where(PortfolioItem.profile_id == profile.id)
    )
    items = {i.id: i for i in result.scalars().all()}

    for pos, item_id in enumerate(body.order):
        if item_id in items:
            items[item_id].position = pos

    await session.commit()
    return {"reordered": True}
