"""
S3 upload and CloudFront signed URL generation for MockupAsset storage.

All assets stored with server-side encryption (AES256).
ACL: private. CloudFront signed URLs with 5-minute TTL.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError

from app.config import get_ai_settings

logger = logging.getLogger(__name__)

_s3_client = None


def get_s3_client():
    global _s3_client
    if _s3_client is None:
        settings = get_ai_settings()
        _s3_client = boto3.client("s3", region_name=settings.aws_region)
    return _s3_client


async def upload_asset(
    data: bytes,
    s3_key: str,
    content_type: str,
) -> int:
    """
    Upload asset bytes to S3 with SSE-AES256.
    Returns file size in bytes.
    """
    settings = get_ai_settings()
    s3 = get_s3_client()
    try:
        s3.put_object(
            Bucket=settings.s3_bucket,
            Key=s3_key,
            Body=data,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )
        return len(data)
    except ClientError as exc:
        logger.error("S3 upload failed for key %s: %s", s3_key, exc)
        raise


def generate_signed_url(s3_key: str) -> tuple[str, datetime]:
    """
    Generate a 5-minute presigned S3 URL.
    Returns (url, expires_at_datetime).

    Note: In production, use CloudFront signed URLs with a key pair.
    Presigned S3 URLs are used here for simplicity; replace with
    CloudFront signing in the gateway layer.
    """
    settings = get_ai_settings()
    s3 = get_s3_client()
    ttl = settings.s3_signed_url_ttl_seconds

    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": s3_key},
        ExpiresIn=ttl,
    )
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
    return url, expires_at
