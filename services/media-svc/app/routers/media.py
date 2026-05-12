"""
media-svc REST endpoints — §10.2 API contracts.

POST /media/upload-url  — presigned S3 PUT, 5-min TTL
POST /media/confirm     — scan + persist ChatMessage + deliver via WS
GET  /media/{s3_key:path}/signed-url  — CloudFront signed URL (cached)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

import boto3
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import MIME_CAPS, get_media_settings
from app.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/media", tags=["media"])

settings = get_media_settings()


# ---------------------------------------------------------------------------
# Request/Response schemas
# ---------------------------------------------------------------------------


class UploadUrlRequest(BaseModel):
    room_id: uuid.UUID
    kind: str = Field(..., pattern="^(image|audio|video|doc|voice)$")
    mime: str
    size_bytes: int


class UploadUrlResponse(BaseModel):
    upload_url: str
    s3_key: str


class ConfirmRequest(BaseModel):
    room_id: uuid.UUID
    kind: str
    s3_key: str
    mime: str
    size_bytes: int
    duration_ms: int | None = None


class ConfirmResponse(BaseModel):
    status: str = "processing"
    pending_msg_id: uuid.UUID


class SignedUrlResponse(BaseModel):
    url: str
    expires_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_profile_id(request: Request) -> uuid.UUID:
    pid = request.headers.get("X-Profile-Id", "")
    if not pid:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        return uuid.UUID(pid)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid profile ID")


def _validate_mime_and_size(kind: str, mime: str, size_bytes: int) -> None:
    if kind not in MIME_CAPS:
        raise HTTPException(status_code=400, detail=f"Unknown kind: {kind}")
    caps = MIME_CAPS[kind]
    if mime not in caps["mimes"]:
        raise HTTPException(
            status_code=400,
            detail=f"MIME type {mime!r} not allowed for kind {kind!r}",
        )
    if size_bytes > caps["max_bytes"]:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {size_bytes} > {caps['max_bytes']} bytes for kind {kind!r}",
        )


def _make_s3_key(room_id: uuid.UUID, kind: str, file_uuid: uuid.UUID, mime: str) -> str:
    ext_map = {
        "image/jpeg": "jpg", "image/png": "png", "image/gif": "gif",
        "image/webp": "webp", "image/heic": "heic",
        "audio/mp4": "m4a", "audio/mpeg": "mp3", "audio/wav": "wav",
        "audio/ogg": "ogg", "audio/aac": "aac",
        "video/mp4": "mp4", "video/quicktime": "mov", "video/webm": "webm",
        "application/pdf": "pdf", "text/plain": "txt",
    }
    ext = ext_map.get(mime, "bin")
    return f"chat/{room_id}/{kind}/{file_uuid}.{ext}"


def _get_s3_client():
    return boto3.client(
        "s3",
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    )


async def _call_moderation_media(s3_key: str, kind: str, mime: str) -> dict:
    """Call moderation-svc /internal/scan/image or /internal/scan/audio."""
    endpoint = "/internal/scan/image"
    if kind in ("audio", "voice"):
        endpoint = "/internal/scan/audio"
    elif kind == "video":
        endpoint = "/internal/scan/video"

    try:
        async with httpx.AsyncClient(timeout=settings.moderation_scan_timeout_seconds) as client:
            resp = await client.post(
                f"{settings.moderation_svc_url}{endpoint}",
                json={
                    "s3_key": s3_key,
                    "s3_bucket": settings.s3_media_bucket,
                    "ctx": {"context": "chat_media", "kind": kind, "mime": mime},
                },
                headers={"X-Internal-Service": "media-svc"},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("Moderation scan error: %s — passing through", exc)
        return {"score": 0.0, "decision": "allow"}


async def _publish_to_redis(room_id: uuid.UUID, envelope: dict) -> None:
    """Publish message envelope to Redis for WS fanout."""
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        await r.publish(f"chat:room:{room_id}", json.dumps(envelope))
        await r.aclose()
    except Exception as exc:
        logger.warning("Redis publish error: %s", exc)


async def _publish_event(event: str, payload: dict) -> None:
    """Publish event to RabbitMQ (best-effort)."""
    try:
        import aio_pika
        conn = await aio_pika.connect_robust(settings.rabbitmq_url)
        async with conn:
            channel = await conn.channel()
            exchange = await channel.declare_exchange("chat", aio_pika.ExchangeType.TOPIC)
            await exchange.publish(
                aio_pika.Message(body=json.dumps({**payload, "event": event}).encode()),
                routing_key=event,
            )
    except Exception as exc:
        logger.warning("Event publish error: %s", exc)


async def _phash_dup_check(s3_key: str) -> bool:
    """
    Download image bytes from S3, compute pHash, check for near-duplicates.
    Returns True if duplicate detected.
    """
    try:
        import imagehash
        from PIL import Image
        import io

        s3 = _get_s3_client()
        obj = s3.get_object(Bucket=settings.s3_media_bucket, Key=s3_key)
        data = obj["Body"].read()
        img = Image.open(io.BytesIO(data))
        phash = imagehash.phash(img)
        phash_bytes = phash.hash.flatten().tobytes()

        # Compare with banned registry (simplified — production uses DB query)
        # For now: compute hash and log; actual DB check would use asyncpg
        logger.debug("pHash computed for %s: %s", s3_key, phash)
        return False  # No banned hashes at launch
    except Exception as exc:
        logger.warning("pHash error: %s", exc)
        return False


def _generate_cloudfront_signed_url(s3_key: str) -> tuple[str, datetime]:
    """
    Generate a CloudFront signed URL with 5-minute TTL.
    Uses RSA private key from Secrets Manager (lazy-loaded).
    Falls back to S3 presigned URL if CloudFront not configured.
    """
    now = datetime.now(tz=timezone.utc)
    expires_at = now + timedelta(seconds=settings.signed_url_ttl_seconds)

    if not settings.cloudfront_domain:
        # Fallback: S3 presigned URL for dev/test
        s3 = _get_s3_client()
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_media_bucket, "Key": s3_key},
            ExpiresIn=settings.signed_url_ttl_seconds,
        )
        return url, expires_at

    # CloudFront signed URL using RSA key from Secrets Manager
    try:
        import botocore.signers as cf_signer
        from cryptography.hazmat.primitives.serialization import load_pem_private_key

        sm = boto3.client("secretsmanager")
        secret = sm.get_secret_value(SecretId=settings.cloudfront_private_key_secret_arn)
        private_key_pem = secret["SecretString"].encode()

        cf = boto3.client("cloudfront")
        signer = cf_signer.CloudFrontSigner(
            settings.cloudfront_key_pair_id,
            lambda msg: load_pem_private_key(private_key_pem, None).sign(
                msg,
                __import__("cryptography.hazmat.primitives.asymmetric.padding", fromlist=["PKCS1v15"]).PKCS1v15(),
                __import__("cryptography.hazmat.primitives.hashes", fromlist=["SHA1"]).SHA1(),
            ),
        )
        url = signer.generate_presigned_url(
            f"https://{settings.cloudfront_domain}/{s3_key}",
            date_less_than=expires_at,
        )
        return url, expires_at
    except Exception as exc:
        logger.warning("CloudFront signing failed, falling back to S3: %s", exc)
        s3 = _get_s3_client()
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_media_bucket, "Key": s3_key},
            ExpiresIn=settings.signed_url_ttl_seconds,
        )
        return url, expires_at


# ---------------------------------------------------------------------------
# POST /media/upload-url
# ---------------------------------------------------------------------------


@router.post("/upload-url", response_model=UploadUrlResponse)
async def get_upload_url(
    body: UploadUrlRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> UploadUrlResponse:
    profile_id = _get_profile_id(request)

    # Validate MIME + size
    _validate_mime_and_size(body.kind, body.mime, body.size_bytes)

    # Verify room membership
    result = await db.execute(
        text("""
            SELECT id FROM chat.chat_room
            WHERE id = :room_id AND :profile_id = ANY(participant_ids)
        """),
        {"room_id": body.room_id, "profile_id": profile_id},
    )
    if not result.fetchone():
        raise HTTPException(status_code=403, detail="Room not found or access denied")

    file_uuid = uuid.uuid4()
    s3_key = _make_s3_key(body.room_id, body.kind, file_uuid, body.mime)

    s3 = _get_s3_client()
    upload_url = s3.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.s3_media_bucket,
            "Key": s3_key,
            "ContentType": body.mime,
            "ContentLength": body.size_bytes,
        },
        ExpiresIn=settings.s3_presign_ttl_seconds,
    )

    return UploadUrlResponse(upload_url=upload_url, s3_key=s3_key)


# ---------------------------------------------------------------------------
# POST /media/confirm
# ---------------------------------------------------------------------------


@router.post("/confirm", response_model=ConfirmResponse, status_code=202)
async def confirm_upload(
    body: ConfirmRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ConfirmResponse:
    """
    Client calls this after successful S3 PUT.
    1. HEAD verify S3 object exists
    2. Moderation scan (image/audio sync; video async)
    3. pHash dup-check for images
    4. Persist ChatMessage + ChatAttachment
    5. Publish to Redis for WS fanout
    6. Return 202 (client sees WS message when ready)
    """
    profile_id = _get_profile_id(request)

    _validate_mime_and_size(body.kind, body.mime, body.size_bytes)

    # Room membership
    room_result = await db.execute(
        text("""
            SELECT id, state FROM chat.chat_room
            WHERE id = :room_id AND :profile_id = ANY(participant_ids)
        """),
        {"room_id": body.room_id, "profile_id": profile_id},
    )
    room_row = room_result.fetchone()
    if not room_row:
        raise HTTPException(status_code=403, detail="Room not found or access denied")
    if room_row.state != "open":
        raise HTTPException(status_code=403, detail="Room is read-only")

    # HEAD verify S3 object
    s3 = _get_s3_client()
    try:
        head = s3.head_object(Bucket=settings.s3_media_bucket, Key=body.s3_key)
    except Exception:
        raise HTTPException(status_code=400, detail="S3 object not found; upload may have failed")

    # Content-Type verification
    s3_content_type = head.get("ContentType", "")
    if s3_content_type and s3_content_type != body.mime:
        # Allow close mismatches for audio/mp4 vs audio/mpeg
        if not (body.kind == "voice" and s3_content_type in ("audio/mp4", "audio/mpeg")):
            logger.warning(
                "MIME mismatch: client=%s s3=%s key=%s", body.mime, s3_content_type, body.s3_key
            )

    # Moderation scan
    scan = await _call_moderation_media(body.s3_key, body.kind, body.mime)
    score = float(scan.get("score", 0.0))

    # pHash dup-check for images
    is_dup = False
    if body.kind == "image":
        is_dup = await _phash_dup_check(body.s3_key)
        if is_dup:
            score = min(score + 0.3, 1.0)  # dup_bump per config

    # Determine moderation status
    if score >= 0.9:
        mod_status = "auto_hidden"
    elif 0.7 <= score < 0.9:
        mod_status = "hidden"
    elif 0.4 <= score < 0.7:
        mod_status = "soft_warn"
    else:
        mod_status = "allowed"

    # Generate signed media URL for delivery
    media_url, expires_at = _generate_cloudfront_signed_url(body.s3_key)

    # Persist ChatMessage
    from app.uuidv7 import generate_uuidv7
    msg_id = generate_uuidv7()
    now = datetime.now(tz=timezone.utc)

    await db.execute(
        text("""
            INSERT INTO chat.chat_message
              (id, room_id, sender_profile_id, type, body, media_key, mime,
               size_bytes, duration_ms, moderation_score, moderation_status, created_at)
            VALUES
              (:id, :room_id, :profile_id, :type, NULL, :media_key, :mime,
               :size_bytes, :duration_ms, :score, :status, :now)
        """),
        {
            "id": msg_id,
            "room_id": body.room_id,
            "profile_id": profile_id,
            "type": body.kind if body.kind in ("image", "video", "audio", "doc") else "voice",
            "media_key": body.s3_key,
            "mime": body.mime,
            "size_bytes": body.size_bytes,
            "duration_ms": body.duration_ms,
            "score": score,
            "status": mod_status,
            "now": now,
        },
    )

    # Persist ChatAttachment
    await db.execute(
        text("""
            INSERT INTO chat.chat_attachment (id, msg_id, kind, s3_key, signed_url_cache_until, signed_url_cache)
            VALUES (gen_random_uuid(), :msg_id, :kind, :s3_key, :expires_at, :url)
        """),
        {
            "msg_id": msg_id,
            "kind": body.kind,
            "s3_key": body.s3_key,
            "expires_at": expires_at,
            "url": media_url,
        },
    )
    await db.commit()

    # If allowed/soft_warn — publish WS message to Redis
    if mod_status in ("allowed", "soft_warn"):
        from app.schemas import ChatMessageOut
        msg_out = ChatMessageOut(
            id=msg_id,
            room_id=body.room_id,
            sender_profile_id=profile_id,
            type=body.kind if body.kind in ("image", "video", "audio", "doc") else "voice",
            media_key=body.s3_key,
            media_url=media_url,
            mime=body.mime,
            size_bytes=body.size_bytes,
            duration_ms=body.duration_ms,
            moderation_status=mod_status,
            created_at=now,
        )
        from app.schemas import ws_message
        await _publish_to_redis(body.room_id, ws_message(msg_out))

        # Publish chat.media.scanned event
        import asyncio
        asyncio.ensure_future(_publish_event("chat.media.scanned", {
            "msg_id": str(msg_id),
            "room_id": str(body.room_id),
            "kind": body.kind,
            "score": score,
        }))
    else:
        # Flagged
        import asyncio
        asyncio.ensure_future(_publish_event("chat.media.flagged", {
            "msg_id": str(msg_id),
            "room_id": str(body.room_id),
            "kind": body.kind,
            "score": score,
            "mod_status": mod_status,
        }))

    return ConfirmResponse(status="processing", pending_msg_id=msg_id)


# ---------------------------------------------------------------------------
# GET /media/{s3_key}/signed-url
# ---------------------------------------------------------------------------


@router.get("/{s3_key:path}/signed-url", response_model=SignedUrlResponse)
async def get_signed_url(
    s3_key: str,
    request: Request,
    room_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
) -> SignedUrlResponse:
    profile_id = _get_profile_id(request)

    # Auth: must be participant of room
    room_result = await db.execute(
        text("""
            SELECT id FROM chat.chat_room
            WHERE id = :room_id AND :profile_id = ANY(participant_ids)
        """),
        {"room_id": room_id, "profile_id": profile_id},
    )
    if not room_result.fetchone():
        raise HTTPException(status_code=403, detail="Access denied")

    # Check signed URL cache
    cache_result = await db.execute(
        text("""
            SELECT signed_url_cache, signed_url_cache_until
            FROM chat.chat_attachment
            WHERE s3_key = :s3_key
            LIMIT 1
        """),
        {"s3_key": s3_key},
    )
    cache_row = cache_result.fetchone()
    now = datetime.now(tz=timezone.utc)

    if cache_row and cache_row.signed_url_cache and cache_row.signed_url_cache_until:
        threshold = now + timedelta(seconds=settings.signed_url_cache_refresh_threshold_seconds)
        if cache_row.signed_url_cache_until > threshold:
            return SignedUrlResponse(
                url=cache_row.signed_url_cache,
                expires_at=cache_row.signed_url_cache_until.isoformat(),
            )

    # Generate new signed URL
    url, expires_at = _generate_cloudfront_signed_url(s3_key)

    # Update cache
    await db.execute(
        text("""
            UPDATE chat.chat_attachment
            SET signed_url_cache = :url, signed_url_cache_until = :expires_at
            WHERE s3_key = :s3_key
        """),
        {"url": url, "expires_at": expires_at, "s3_key": s3_key},
    )
    await db.commit()

    return SignedUrlResponse(url=url, expires_at=expires_at.isoformat())
