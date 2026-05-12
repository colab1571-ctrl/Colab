"""matching-svc request/response schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class MatchScoreResponse(BaseModel):
    from_profile_id: UUID
    to_profile_id: UUID
    score: float
    components: dict
    computed_at: datetime
    version: int


class ReindexResponse(BaseModel):
    job_id: str
    status: str


class CandidateItem(BaseModel):
    profile_id: str
    score: float


class CandidatesResponse(BaseModel):
    candidates: list[CandidateItem]
    total: int


class RecommendationResponse(BaseModel):
    profile_ids: list[str]
    generated_at: str
    rationale: dict
