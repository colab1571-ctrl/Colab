"""
moderation-svc Pydantic schemas for API request/response validation.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Subject types
# ---------------------------------------------------------------------------

SubjectType = Literal["msg", "profile_field", "portfolio_item", "invite_synopsis", "mockup", "user"]
ActionType = Literal[
    "warn", "hide", "restore", "temp_mute_1h", "temp_mute_24h", "temp_mute_7d",
    "permanent_ban", "delete_account", "dismiss", "escalate_to_legal"
]
Tier = Literal["tier_0_allow", "tier_1_24h", "tier_2_6h", "tier_3_1h"]
CaseStatus = Literal["open", "in_review", "actioned", "dismissed", "escalated"]
CaseKind = Literal["auto", "report", "dmca"]


# ---------------------------------------------------------------------------
# Report intake
# ---------------------------------------------------------------------------

class ReportCreate(BaseModel):
    subject_type: SubjectType
    subject_id: uuid.UUID
    description: str = Field(..., min_length=10, max_length=1000)
    screenshot_s3_key: str | None = None


class ReportResponse(BaseModel):
    report_id: uuid.UUID
    case_id: uuid.UUID | None
    created_at: datetime
    status: str = "open"


# ---------------------------------------------------------------------------
# DMCA
# ---------------------------------------------------------------------------

class DMCANoticeCreate(BaseModel):
    claimant_name: str = Field(..., min_length=2, max_length=200)
    claimant_address: str = Field(..., min_length=10)
    claimant_phone: str = Field(..., min_length=7, max_length=40)
    claimant_email: str = Field(..., min_length=6, max_length=320)
    is_authorized_agent: bool
    sworn_statement_text: str = Field(..., min_length=50)
    signature_full_name: str = Field(..., min_length=2, max_length=200)
    copyrighted_work_description: str = Field(..., min_length=10)
    copyrighted_work_url_or_registration: str | None = None
    target_subject_type: SubjectType
    target_subject_id: uuid.UUID
    target_url_on_colab: str = Field(..., min_length=10)

    @field_validator("is_authorized_agent")
    @classmethod
    def must_be_authorized(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Claimant must be authorized to act on behalf of the rights holder")
        return v

    @field_validator("sworn_statement_text")
    @classmethod
    def must_contain_penalty_of_perjury(cls, v: str) -> str:
        if "penalty of perjury" not in v.lower():
            raise ValueError("Sworn statement must include 'under penalty of perjury' attestation")
        return v


class DMCANoticeResponse(BaseModel):
    dmca_id: uuid.UUID
    case_id: uuid.UUID | None
    received_at: datetime
    state: str
    hide_at: datetime | None


class CounterNoticeCreate(BaseModel):
    counter_claimant_legal_name: str = Field(..., min_length=2, max_length=200)
    counter_claimant_address: str = Field(..., min_length=10)
    counter_claimant_phone: str = Field(..., min_length=7, max_length=40)
    counter_statement_text: str = Field(..., min_length=50)
    consent_to_jurisdiction: bool
    consent_to_service_of_process: bool
    signature_full_name: str = Field(..., min_length=2, max_length=200)
    counter_token: str  # single-use token from email link

    @field_validator("consent_to_jurisdiction", "consent_to_service_of_process")
    @classmethod
    def must_consent(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Consent is required to file a counter-notice")
        return v


class CounterNoticeResponse(BaseModel):
    counter_id: uuid.UUID
    dmca_id: uuid.UUID
    statutory_window_end: datetime
    state: str


# ---------------------------------------------------------------------------
# Moderation case management
# ---------------------------------------------------------------------------

class CaseActionRequest(BaseModel):
    action_type: ActionType
    reason: str = Field(..., min_length=12, max_length=2000)
    evidence_refs: list[Any] = Field(default_factory=list)
    second_reviewer_id: uuid.UUID | None = None

    @field_validator("second_reviewer_id", mode="before")
    @classmethod
    def validate_second_reviewer(cls, v: Any, info: Any) -> Any:
        return v  # enforced at endpoint layer with reviewer identity check


class CaseSummary(BaseModel):
    id: uuid.UUID
    kind: CaseKind
    subject_type: SubjectType
    subject_id: uuid.UUID
    subject_owner_user_id: uuid.UUID
    score: float | None
    forced_human: bool
    forced_reason: str | None
    status: CaseStatus
    priority_tier: Tier
    sla_due_at: datetime | None
    sla_breached_at: datetime | None
    opened_at: datetime
    claimed_by: uuid.UUID | None


class CaseDetail(CaseSummary):
    scores_breakdown: dict
    actions: list[ActionSummary]


class ActionSummary(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    action_type: ActionType
    reviewer_id: uuid.UUID
    reason: str
    target_user_id: uuid.UUID
    created_at: datetime
    propagation_status: str


class ActionResponse(BaseModel):
    action_id: uuid.UUID
    propagation_id: str
    status: str = "pending"


# ---------------------------------------------------------------------------
# Internal scan API
# ---------------------------------------------------------------------------

class TextScanRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)
    ctx: dict  # {subject_type, subject_id, owner_user_id, idempotency_key?}


class ImageScanRequest(BaseModel):
    s3_key: str
    s3_bucket: str | None = None  # defaults to media bucket
    ctx: dict


class AudioScanRequest(BaseModel):
    s3_key: str
    s3_bucket: str | None = None
    ctx: dict
    callback_url: str | None = None


class VideoScanRequest(BaseModel):
    s3_key: str
    s3_bucket: str | None = None
    ctx: dict
    sns_topic_arn: str | None = None


ScanDecision = Literal["allow", "soft_warn", "hide", "auto_hide_mute"]


class ScanResponse(BaseModel):
    score: float
    breakdown: dict
    decision: str  # ScanDecision
    case_id: uuid.UUID | None = None
    action: str
    tier: str
    forced_human: bool


class AsyncScanResponse(BaseModel):
    job_id: str
    status: str = "queued"


class UserStateResponse(BaseModel):
    user_id: uuid.UUID
    is_banned: bool
    is_muted: bool
    mute_expires_at: datetime | None
    active_cases_count: int


# Allow forward references
CaseDetail.model_rebuild()
