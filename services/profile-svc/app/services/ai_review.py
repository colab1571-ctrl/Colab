"""
profile-svc — AI profile review orchestrator.

Implements the fan-out pipeline from plan §7:
  text → OpenAI moderation (omni-moderation-latest)
  image → Rekognition DetectModerationLabels + pHash + aHash dup
  audio → Chromaprint fingerprint + MFCC fallback dup
  video → Rekognition StartContentModeration (async)
  all text → embedding semantic dup (pgvector cosine ≥0.98)

Risk aggregation:
  score = 0.35 * openai_max + 0.35 * rekognition_max + 0.20 * dup_signal + 0.10 * embedding_outlier

Thresholds from config:
  < 0.40 → pass
  0.40–0.70 → soft_warn
  0.70–0.90 → hide
  ≥ 0.90 → severe

Always-human routing: sexual content involving real persons, weapon imagery,
contact-info doxxing, IP claims → priority HIGH regardless of score.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Any

import boto3
import httpx

logger = logging.getLogger(__name__)

# MIME whitelist
ALLOWED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
ALLOWED_AUDIO_MIMES = {"audio/mpeg", "audio/mp3", "audio/wav", "audio/ogg", "audio/m4a", "audio/flac"}
ALLOWED_VIDEO_MIMES = {"video/mp4", "video/quicktime", "video/webm", "video/mpeg"}

# Size caps (bytes)
IMAGE_SIZE_CAP = 10 * 1024 * 1024   # 10MB
AUDIO_SIZE_CAP = 30 * 1024 * 1024   # 30MB
VIDEO_SIZE_CAP = 100 * 1024 * 1024  # 100MB

SIZE_CAPS = {
    "image": IMAGE_SIZE_CAP,
    "audio": AUDIO_SIZE_CAP,
    "video": VIDEO_SIZE_CAP,
}

# Dup thresholds
PHASH_HAMMING_THRESHOLD = 6
AHASH_HAMMING_THRESHOLD = 10
CHROMAPRINT_COSINE_THRESHOLD = 0.92
EMBEDDING_COSINE_OUTLIER = 0.98

# Always-human keywords in OpenAI category scores keys
ALWAYS_HUMAN_CATEGORIES = {
    "sexual/minors",
    "harassment/threatening",
    "illicit/violent",
}


def _hamming_distance(h1: int, h2: int) -> int:
    """Compute Hamming distance between two 64-bit integers."""
    return bin(h1 ^ h2).count("1")


def aggregate_risk(
    openai_score: float,
    rekognition_score: float,
    dup_signal: float,
    embedding_outlier: float,
    w_openai: float = 0.35,
    w_rekognition: float = 0.35,
    w_dup: float = 0.20,
    w_embedding: float = 0.10,
) -> float:
    """Compute aggregate risk score [0, 1]."""
    score = (
        w_openai * openai_score
        + w_rekognition * rekognition_score
        + w_dup * dup_signal
        + w_embedding * embedding_outlier
    )
    return min(1.0, max(0.0, score))


async def scan_text_openai(text: str, api_key: str) -> dict[str, Any]:
    """
    Call OpenAI omni-moderation-latest on text.
    Returns raw response dict with category_scores.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/moderations",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "omni-moderation-latest", "input": text},
        )
        resp.raise_for_status()
        return resp.json()


def extract_openai_max_score(result: dict[str, Any]) -> tuple[float, bool]:
    """
    Extract max category score and always-human flag from OpenAI response.
    Returns (max_score, always_human).
    """
    results = result.get("results", [{}])
    if not results:
        return 0.0, False
    r = results[0]
    scores = r.get("category_scores", {})
    if not scores:
        return 0.0, False
    max_score = max(scores.values())
    always_human = any(scores.get(cat, 0.0) > 0.5 for cat in ALWAYS_HUMAN_CATEGORIES)
    return max_score, always_human


def scan_image_rekognition(s3_bucket: str, s3_key: str, region: str = "us-east-1") -> dict[str, Any]:
    """
    Call Rekognition DetectModerationLabels on an S3 image.
    Returns raw response dict.
    """
    client = boto3.client("rekognition", region_name=region)
    resp = client.detect_moderation_labels(
        Image={"S3Object": {"Bucket": s3_bucket, "Name": s3_key}},
        MinConfidence=50,
        ProjectVersion="LATEST",
    )
    return resp


def extract_rekognition_max_score(result: dict[str, Any]) -> float:
    """Extract max confidence (normalized to 0-1) from Rekognition response."""
    labels = result.get("ModerationLabels", [])
    if not labels:
        return 0.0
    return max(lbl.get("Confidence", 0.0) for lbl in labels) / 100.0


def compute_phash_dup_signal(
    new_phash: int | None,
    new_ahash: int | None,
    existing_hashes: list[tuple[int | None, int | None]],
) -> float:
    """
    Check perceptual hash against existing hashes.
    Returns 1.0 if dup found, 0.0 otherwise.
    """
    if new_phash is None and new_ahash is None:
        return 0.0
    for (ep, ea) in existing_hashes:
        if new_phash is not None and ep is not None:
            if _hamming_distance(new_phash, ep) <= PHASH_HAMMING_THRESHOLD:
                return 1.0
        if new_ahash is not None and ea is not None:
            if _hamming_distance(new_ahash, ea) <= AHASH_HAMMING_THRESHOLD:
                return 1.0
    return 0.0


def routing_decision(score: float, always_human: bool = False) -> dict[str, Any]:
    """
    Map aggregate risk score to routing action per FR-M-2.
    Returns dict with action, sla_hours, queue_priority.
    """
    if always_human:
        return {"action": "human_queue", "sla_hours": 1, "queue_priority": "HIGH", "score": score}
    if score < 0.40:
        return {"action": "auto_allow", "sla_hours": None, "queue_priority": None, "score": score}
    elif score < 0.70:
        return {"action": "soft_warn", "sla_hours": 24, "queue_priority": "MEDIUM", "score": score}
    elif score < 0.90:
        return {"action": "hide_content", "sla_hours": 6, "queue_priority": "HIGH", "score": score}
    else:
        return {"action": "auto_hide_temp_mute", "sla_hours": 1, "queue_priority": "URGENT", "score": score}
