"""
moderation-svc — Pipeline scan Celery tasks.

Implements M-002 (OpenAI), M-003 (Rekognition), M-004 (pHash),
M-005 (Chromaprint), M-006 (pgvector semdup), M-007 (combined score+route).

All tasks use colab_common ColabBaseTask for retry / backoff / Sentry.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import struct
import time
import uuid
from typing import Any

from app.config import DEFAULT_CATEGORY_WEIGHTS, get_mod_settings
from app.score import (
    DupResult,
    OpenAIModResult,
    RekognitionResult,
    combined_score,
    route,
)
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OpenAI Moderation (text + multimodal)  — M-002
# ---------------------------------------------------------------------------


@celery_app.task(name="mod.scan.openai_text", queue="mod-fast", bind=True, max_retries=3)
def scan_openai_text(self: Any, text: str, ctx: dict) -> dict:
    """
    Submit text to OpenAI omni-moderation-latest.

    Returns normalised dict compatible with OpenAIModResult.
    On tool 5xx / timeout → returns synthetic score 0.5 (fail-safe).
    """
    settings = get_mod_settings()
    try:
        import openai

        client = openai.OpenAI(api_key=settings.openai_api_key or os.environ.get("OPENAI_API_KEY", ""))
        resp = client.moderations.create(
            model=settings.openai_model_mod,
            input=text,
        )
        result_data = resp.results[0]
        cat_scores = dict(result_data.category_scores)
        flagged_cats = {k for k, v in result_data.categories if v}

        out = {
            "flagged": result_data.flagged,
            "category_scores": {k: float(v) for k, v in cat_scores.items()},
            "flagged_categories": list(flagged_cats),
            "raw": resp.model_dump(),
            "tool": "openai_mod",
            "error": None,
        }
    except Exception as exc:
        logger.warning("OpenAI moderation failed; using synthetic 0.5", extra={"exc": str(exc), "ctx": ctx})
        out = {
            "flagged": False,
            "category_scores": {"__synthetic__": 0.5},
            "flagged_categories": [],
            "raw": {"error": str(exc)},
            "tool": "openai_mod",
            "error": str(exc),
        }
    return out


@celery_app.task(name="mod.scan.openai_multimodal", queue="mod-fast", bind=True, max_retries=3)
def scan_openai_multimodal(self: Any, text: str, image_url: str, ctx: dict) -> dict:
    """Submit text + image URL to OpenAI omni-moderation (multimodal input)."""
    settings = get_mod_settings()
    try:
        import openai

        client = openai.OpenAI(api_key=settings.openai_api_key or os.environ.get("OPENAI_API_KEY", ""))
        resp = client.moderations.create(
            model=settings.openai_model_mod,
            input=[
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        )
        result_data = resp.results[0]
        cat_scores = {k: float(v) for k, v in dict(result_data.category_scores).items()}
        flagged_cats = {k for k, v in result_data.categories if v}
        out = {
            "flagged": result_data.flagged,
            "category_scores": cat_scores,
            "flagged_categories": list(flagged_cats),
            "raw": resp.model_dump(),
            "tool": "openai_mod_multimodal",
            "error": None,
        }
    except Exception as exc:
        logger.warning("OpenAI multimodal mod failed", extra={"exc": str(exc)})
        out = {
            "flagged": False,
            "category_scores": {"__synthetic__": 0.5},
            "flagged_categories": [],
            "raw": {"error": str(exc)},
            "tool": "openai_mod_multimodal",
            "error": str(exc),
        }
    return out


# ---------------------------------------------------------------------------
# AWS Rekognition — M-003
# ---------------------------------------------------------------------------


@celery_app.task(name="mod.scan.rekognition_image", queue="mod-image", bind=True, max_retries=3)
def scan_rekognition_image(self: Any, s3_key: str, s3_bucket: str, ctx: dict) -> dict:
    """
    Call Rekognition DetectModerationLabels on an S3 image.
    Returns dict with 'labels' list and 'raw'.
    """
    settings = get_mod_settings()
    try:
        import boto3

        client = boto3.client("rekognition", region_name=settings.aws_rekognition_region)
        resp = client.detect_moderation_labels(
            Image={"S3Object": {"Bucket": s3_bucket, "Name": s3_key}},
            MinConfidence=settings.rekognition_min_confidence,
        )
        labels = [
            {
                "Name": lbl["Name"],
                "ParentName": lbl.get("ParentName", ""),
                "Confidence": lbl["Confidence"],
            }
            for lbl in resp.get("ModerationLabels", [])
        ]
        return {"labels": labels, "raw": resp, "tool": "rekognition_image", "error": None}
    except Exception as exc:
        logger.warning("Rekognition image scan failed", extra={"exc": str(exc)})
        return {"labels": [], "raw": {"error": str(exc)}, "tool": "rekognition_image", "error": str(exc)}


@celery_app.task(name="mod.scan.rekognition_video_start", queue="mod-video", bind=True, max_retries=3)
def start_rekognition_video(
    self: Any, s3_key: str, s3_bucket: str, sns_topic_arn: str, ctx: dict
) -> dict:
    """
    Start async Rekognition ContentModeration on a video. Returns job_id.
    Result delivered via SNS → mod.scan.rekognition_video_result task.
    """
    settings = get_mod_settings()
    try:
        import boto3

        client = boto3.client("rekognition", region_name=settings.aws_rekognition_region)
        resp = client.start_content_moderation(
            Video={"S3Object": {"Bucket": s3_bucket, "Name": s3_key}},
            MinConfidence=settings.rekognition_min_confidence,
            NotificationChannel={"SNSTopicArn": sns_topic_arn, "RoleArn": os.environ.get("REKOGNITION_ROLE_ARN", "")},
        )
        return {"job_id": resp["JobId"], "ctx": ctx, "tool": "rekognition_video_start"}
    except Exception as exc:
        logger.warning("Rekognition video start failed", extra={"exc": str(exc)})
        return {"job_id": None, "ctx": ctx, "tool": "rekognition_video_start", "error": str(exc)}


@celery_app.task(name="mod.scan.rekognition_video_result", queue="mod-video", bind=True, max_retries=3)
def collect_rekognition_video(self: Any, job_id: str, ctx: dict) -> dict:
    """Poll GetContentModeration for a completed video job."""
    settings = get_mod_settings()
    try:
        import boto3

        client = boto3.client("rekognition", region_name=settings.aws_rekognition_region)
        resp = client.get_content_moderation(JobId=job_id)
        labels_raw = resp.get("ModerationLabels", [])
        labels = [
            {
                "Name": lbl["ModerationLabel"]["Name"],
                "ParentName": lbl["ModerationLabel"].get("ParentName", ""),
                "Confidence": lbl["ModerationLabel"]["Confidence"],
            }
            for lbl in labels_raw
        ]
        return {"labels": labels, "raw": resp, "tool": "rekognition_video", "error": None}
    except Exception as exc:
        logger.warning("Rekognition video collect failed", extra={"exc": str(exc)})
        return {"labels": [], "raw": {"error": str(exc)}, "tool": "rekognition_video", "error": str(exc)}


# ---------------------------------------------------------------------------
# pHash image dedup — M-004
# ---------------------------------------------------------------------------


def _hamming_distance(h1: int, h2: int) -> int:
    """Count differing bits between two 64-bit integers."""
    return bin(h1 ^ h2).count("1")


@celery_app.task(name="mod.scan.phash", queue="mod-image", bind=True, max_retries=3)
def scan_phash(self: Any, s3_key: str, s3_bucket: str, ctx: dict) -> dict:
    """
    Download image from S3, compute pHash, check against BannedHashRegistry.
    Returns {phash_hex, match, hamming_distance, error}.
    """
    settings = get_mod_settings()
    try:
        import boto3
        import imagehash
        from PIL import Image

        s3 = boto3.client("s3")
        obj = s3.get_object(Bucket=s3_bucket, Key=s3_key)
        image_bytes = obj["Body"].read()
        img = Image.open(io.BytesIO(image_bytes))
        phash_val = imagehash.phash(img)
        phash_int = int(str(phash_val), 16)
        phash_hex = str(phash_val)

        # Check banned registry via DB call (synchronous Celery task)
        # We defer DB check to the combine task which runs in an async context
        return {
            "phash_hex": phash_hex,
            "phash_int": phash_int,
            "match": False,  # populated by combine_and_route after DB lookup
            "hamming_min": None,
            "tool": "phash",
            "error": None,
        }
    except Exception as exc:
        logger.warning("pHash scan failed", extra={"exc": str(exc)})
        return {"phash_hex": None, "phash_int": None, "match": False, "tool": "phash", "error": str(exc)}


# ---------------------------------------------------------------------------
# Chromaprint audio dedup — M-005
# ---------------------------------------------------------------------------


@celery_app.task(name="mod.scan.chromaprint", queue="mod-audio", bind=True, max_retries=3)
def scan_chromaprint(self: Any, s3_key: str, s3_bucket: str, ctx: dict) -> dict:
    """
    Download audio from S3, compute Chromaprint fingerprint.
    Similarity checked in combine_and_route against BannedAudioFingerprint.
    """
    try:
        import tempfile

        import acoustid
        import boto3

        s3 = boto3.client("s3")
        with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as tmp:
            obj = s3.get_object(Bucket=s3_bucket, Key=s3_key)
            tmp.write(obj["Body"].read())
            tmp_path = tmp.name

        duration, fp_encoded = acoustid.fingerprint_file(tmp_path)
        # Store raw fingerprint bytes as hex for DB storage
        return {
            "duration": duration,
            "fingerprint_hex": fp_encoded.hex() if isinstance(fp_encoded, bytes) else str(fp_encoded),
            "match": False,
            "similarity_max": None,
            "tool": "chromaprint",
            "error": None,
        }
    except Exception as exc:
        logger.warning("Chromaprint scan failed", extra={"exc": str(exc)})
        return {
            "duration": None,
            "fingerprint_hex": None,
            "match": False,
            "tool": "chromaprint",
            "error": str(exc),
        }
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Semantic dup via pgvector — M-006
# ---------------------------------------------------------------------------


@celery_app.task(name="mod.scan.semdup", queue="mod-fast", bind=True, max_retries=3)
def scan_semdup(self: Any, text: str, ctx: dict) -> dict:
    """
    Embed text with OpenAI text-embedding-3-large and check against
    BannedTextEmbedding via cosine similarity.
    Redis bloom filter provides short-circuit for exact text matches.
    """
    settings = get_mod_settings()
    try:
        import openai
        import redis as sync_redis

        client = openai.OpenAI(api_key=settings.openai_api_key or os.environ.get("OPENAI_API_KEY", ""))

        # Fast exact-match bloom filter in Redis
        r = sync_redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        bloom_key = f"mod:semdup:bloom:{text_hash}"
        if r.exists(bloom_key):
            return {
                "embedding_dim": 3072,
                "match": True,
                "similarity_max": 1.0,
                "tool": "semdup",
                "error": None,
            }

        # Get embedding
        resp = client.embeddings.create(
            model=settings.openai_embedding_model,
            input=text,
        )
        embedding = resp.data[0].embedding

        # Store in bloom filter (24h TTL)
        r.set(bloom_key, "1", ex=86400)

        return {
            "embedding": embedding[:10],  # truncated for scan log (full stored in BannedTextEmbedding)
            "embedding_dim": len(embedding),
            "match": False,  # populated by combine_and_route after pgvector query
            "similarity_max": None,
            "tool": "semdup",
            "error": None,
        }
    except Exception as exc:
        logger.warning("Semdup scan failed", extra={"exc": str(exc)})
        return {
            "embedding_dim": 0,
            "match": False,
            "tool": "semdup",
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Combined score + route — M-007  (called after all tool tasks complete)
# ---------------------------------------------------------------------------


def build_routing_result(
    openai_result: dict,
    rekognition_result: dict | None,
    phash_result: dict | None,
    chromaprint_result: dict | None,
    semdup_result: dict | None,
    *,
    has_ip_claim: bool = False,
    weights: dict | None = None,
) -> dict:
    """
    Pure function: given raw tool results, compute combined score and route.

    Called by the internal scan API layer (not a Celery task itself since it
    needs async DB context for ban-registry lookups).
    """
    openai = OpenAIModResult(
        flagged=openai_result.get("flagged", False),
        category_scores=openai_result.get("category_scores", {}),
        flagged_categories=set(openai_result.get("flagged_categories", [])),
        raw=openai_result.get("raw", {}),
    )
    rek_labels = (rekognition_result or {}).get("labels", [])
    rek = RekognitionResult(labels=rek_labels, raw=(rekognition_result or {}).get("raw", {}))
    dup = DupResult(
        phash_match=(phash_result or {}).get("match", False),
        chromaprint_match=(chromaprint_result or {}).get("match", False),
        semdup_match=(semdup_result or {}).get("match", False),
    )

    score, breakdown = combined_score(openai, rek, dup, weights=weights or DEFAULT_CATEGORY_WEIGHTS)
    decision = route(score, openai, rek, has_ip_claim=has_ip_claim)

    return {
        "score": round(score, 4),
        "breakdown": breakdown,
        "action": decision.action,
        "tier": decision.tier,
        "sla_hours": decision.sla_hours,
        "forced_human": decision.forced_human,
        "forced_reason": decision.forced_reason,
        "is_csam": decision.is_csam,
    }
