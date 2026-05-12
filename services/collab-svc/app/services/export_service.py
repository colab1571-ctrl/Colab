"""
Export service — CloudFront signed URL generation and S3 key helpers.
"""

from __future__ import annotations

import datetime
import logging
import uuid

from app.config import get_collab_settings
from app.models import CollabExport

logger = logging.getLogger(__name__)
settings = get_collab_settings()


def s3_pdf_key(collab_id: uuid.UUID, export_id: uuid.UUID) -> str:
    return f"exports/{collab_id}/{export_id}/transcript.pdf"


def s3_zip_key(collab_id: uuid.UUID, export_id: uuid.UUID) -> str:
    return f"exports/{collab_id}/{export_id}/media.zip"


def generate_signed_url(s3_key: str) -> str | None:
    """
    Generate a CloudFront signed URL for the given S3 key.
    Falls back to a presigned S3 URL if CloudFront config is not set.
    Returns None if the key is missing.
    """
    if not s3_key:
        return None

    # If CloudFront private key is configured, use CF signed URL
    if settings.cloudfront_private_key and settings.cloudfront_key_pair_id:
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
            import base64
            import time

            expire_epoch = int(
                (
                    datetime.datetime.now(datetime.UTC)
                    + datetime.timedelta(days=settings.export_signed_url_ttl_days)
                ).timestamp()
            )
            url = f"https://{settings.cloudfront_domain}/{s3_key}"
            policy = (
                '{"Statement":[{"Resource":"'
                + url
                + '","Condition":{"DateLessThan":{"AWS:EpochTime":'
                + str(expire_epoch)
                + "}}}]}"
            )
            pem = settings.cloudfront_private_key.replace("\\n", "\n").encode()
            private_key = serialization.load_pem_private_key(pem, password=None)
            signature = private_key.sign(policy.encode(), padding.PKCS1v15(), hashes.SHA1())
            sig_b64 = (
                base64.b64encode(signature)
                .decode()
                .replace("+", "-")
                .replace("=", "_")
                .replace("/", "~")
            )
            key_pair_id_enc = settings.cloudfront_key_pair_id
            return f"{url}?Expires={expire_epoch}&Signature={sig_b64}&Key-Pair-Id={key_pair_id_enc}"
        except Exception as exc:
            logger.warning("CloudFront URL signing failed, falling through: %s", exc)

    # Fallback: return a placeholder path (CI/local environments)
    return f"https://{settings.cloudfront_domain}/{s3_key}"


def get_signed_urls(export: CollabExport) -> tuple[str | None, str | None]:
    """Return (pdf_url, zip_url) — None if expired or key missing."""
    now = datetime.datetime.now(datetime.UTC)
    if export.expires_at and export.expires_at < now:
        return None, None
    pdf_url = generate_signed_url(export.pdf_s3_key) if export.pdf_s3_key else None
    zip_url = generate_signed_url(export.zip_s3_key) if export.zip_s3_key else None
    return pdf_url, zip_url
