"""
Audio watermarking — two-layer approach:

Layer 1 — Inaudible 5 kHz sine tone injected every 10 seconds at −60 dBFS.
Layer 2 — ID3 TXXX metadata tag with asset/user identifiers.

Original Replicate audio artifact is discarded after watermarking.
"""

from __future__ import annotations

import io
import logging
import os
import tempfile
import uuid

logger = logging.getLogger(__name__)

TONE_HZ = 5000          # 5 kHz — above typical vocal range, imperceptible in context
TONE_DBFS = -60         # very quiet
TONE_DURATION_MS = 200  # 200 ms burst
TONE_INTERVAL_MS = 10_000  # every 10 seconds


def apply_audio_watermark(
    audio_bytes: bytes,
    asset_id: uuid.UUID,
    user_a_id: uuid.UUID,
    user_b_id: uuid.UUID,
    ts: str,
) -> tuple[bytes, dict]:
    """
    Apply tone watermark + ID3 metadata to MP3 audio bytes.

    Args:
        audio_bytes: Raw MP3 bytes from Replicate.
        asset_id: MockupAsset UUID for embedding.
        user_a_id: Party A user ID.
        user_b_id: Party B user ID.
        ts: ISO 8601 timestamp.

    Returns:
        (watermarked_mp3_bytes, watermark_meta_dict)
    """
    from pydub import AudioSegment
    from pydub.generators import Sine
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3, TXXX, error as ID3Error

    # --- Layer 1: Tone injection ---
    audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
    tone = Sine(TONE_HZ).to_audio_segment(duration=TONE_DURATION_MS).apply_gain(TONE_DBFS)

    result = audio
    pos = 0
    while pos < len(audio):
        result = result.overlay(tone, position=pos)
        pos += TONE_INTERVAL_MS

    # Export to temp file for mutagen ID3 tagging
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = tmp.name
        result.export(tmp_path, format="mp3")

    # --- Layer 2: ID3 metadata tag ---
    try:
        mp3 = MP3(tmp_path, ID3=ID3)
        if mp3.tags is None:
            mp3.add_tags()
        mp3.tags.add(TXXX(
            encoding=3,
            desc="COLAB_WATERMARK",
            text=(
                f"asset_id={asset_id};"
                f"user_a={user_a_id};"
                f"user_b={user_b_id};"
                f"ts={ts}"
            ),
        ))
        mp3.save()
    except ID3Error as exc:
        logger.warning("Failed to write ID3 tag: %s", exc)

    with open(tmp_path, "rb") as f:
        watermarked_bytes = f.read()
    os.unlink(tmp_path)

    meta = {
        "tone_hz": TONE_HZ,
        "tone_dbfs": TONE_DBFS,
        "tone_duration_ms": TONE_DURATION_MS,
        "tone_interval_ms": TONE_INTERVAL_MS,
        "metadata_key": "COLAB_WATERMARK",
        "metadata_value_template": (
            "asset_id={asset_id};user_a={user_a_id};user_b={user_b_id};ts={ts}"
        ),
    }
    return watermarked_bytes, meta
