"""
moderation-svc configuration — extends colab_common Settings with
moderation-specific admin-tunable values (backed by ModConfig in DB;
defaults here are the launch baseline).
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModerationSettings(BaseSettings):
    """Moderation-svc specific env-level configuration."""

    model_config = SettingsConfigDict(
        env_prefix="MOD_",
        extra="ignore",
        env_file=".env.local",
    )

    # Scan tool API keys
    openai_api_key: str = Field(default="")
    openai_model_mod: str = Field(default="omni-moderation-latest")
    openai_embedding_model: str = Field(default="text-embedding-3-large")

    # AWS Rekognition
    aws_rekognition_region: str = Field(default="us-east-1")
    rekognition_min_confidence: float = Field(default=50.0)

    # S3
    s3_bucket_audit_logs: str = Field(default="colab-audit-logs")

    # Thresholds (admin-tunable at runtime via ModConfig, these are defaults)
    tier1_threshold: float = Field(default=0.4)
    tier2_threshold: float = Field(default=0.7)
    tier3_threshold: float = Field(default=0.9)
    dup_bump: float = Field(default=0.3)
    phash_hamming_threshold: int = Field(default=6)
    chromaprint_sim_threshold: float = Field(default=0.85)
    semdup_cosine_threshold: float = Field(default=0.95)

    # Rate limiting
    reports_per_user_per_day: int = Field(default=20)
    dmca_per_ip_per_day: int = Field(default=5)
    dmca_per_email_per_day: int = Field(default=10)

    # DMCA statutory window (calendar days)
    dmca_statutory_window_days: int = Field(default=14)

    # SLA
    tier1_sla_hours: int = Field(default=24)
    tier2_sla_hours: int = Field(default=6)
    tier3_sla_hours: int = Field(default=1)


# Default category weights per plan §3.1
DEFAULT_CATEGORY_WEIGHTS: dict[str, float] = {
    "sexual/minors": 1.5,
    "harassment/threatening": 1.3,
    "hate/threatening": 1.3,
    "violence/graphic": 1.2,
    "self-harm/intent": 1.2,
    "Rekognition:Explicit": 1.2,
    "Rekognition:Hate Symbols": 1.3,
    "illicit/violent": 1.2,
    "sexual": 1.0,
    "harassment": 1.0,
    "violence": 1.0,
}

# Rekognition categories that always force human routing
ALWAYS_HUMAN_REKOGNITION: set[str] = {"Hate Symbols"}

# OpenAI categories that always force human routing
ALWAYS_HUMAN_OPENAI: set[str] = {
    "harassment/threatening",
    "violence/graphic",
    "sexual/minors",
}


@lru_cache(maxsize=1)
def get_mod_settings() -> ModerationSettings:
    return ModerationSettings()
