"""
auth-svc — Pydantic request/response schemas.

All inputs validated and stripped; no raw model objects leaked to callers.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


# ---------------------------------------------------------------------------
# Shared token envelope
# ---------------------------------------------------------------------------


class TokenPair(BaseModel):
    user_id: uuid.UUID
    access_token: str
    refresh_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int = 900  # access token TTL seconds


# ---------------------------------------------------------------------------
# Signup schemas
# ---------------------------------------------------------------------------


class SignupEmailRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    age_attestation: Literal[True] = Field(..., description="Must be true — 18+ attestation")
    accept_tos: Literal[True]
    accept_privacy: Literal[True]
    accept_community: Literal[True]
    tos_version: str = Field(default="1.0")
    privacy_version: str = Field(default="1.0")
    community_version: str = Field(default="1.0")

    @field_validator("email", mode="before")
    @classmethod
    def lowercase_email(cls, v: str) -> str:
        return v.lower().strip()


class SignupOAuthRequest(BaseModel):
    provider: Literal["apple", "google"]
    id_token: str
    nonce: str | None = None  # required for Apple Sign-In
    age_attestation: Literal[True] = Field(..., description="Must be true — 18+ attestation")
    accept_tos: Literal[True]
    accept_privacy: Literal[True]
    accept_community: Literal[True]
    tos_version: str = Field(default="1.0")
    privacy_version: str = Field(default="1.0")
    community_version: str = Field(default="1.0")


class SignupPhoneRequest(BaseModel):
    phone: str = Field(pattern=r"^\+[1-9]\d{7,14}$", description="E.164 format")
    age_attestation: Literal[True] = Field(..., description="Must be true — 18+ attestation")
    accept_tos: Literal[True]
    accept_privacy: Literal[True]
    accept_community: Literal[True]


class PhoneOtpSentResponse(BaseModel):
    otp_sent: bool = True
    phone: str


class PhoneVerifyRequest(BaseModel):
    phone: str = Field(pattern=r"^\+[1-9]\d{7,14}$")
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


# ---------------------------------------------------------------------------
# Login schemas
# ---------------------------------------------------------------------------


class LoginEmailRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email", mode="before")
    @classmethod
    def lowercase_email(cls, v: str) -> str:
        return v.lower().strip()


class LoginOAuthRequest(BaseModel):
    provider: Literal["apple", "google"]
    id_token: str
    nonce: str | None = None


class LoginPhoneStartRequest(BaseModel):
    phone: str = Field(pattern=r"^\+[1-9]\d{7,14}$")


class LoginPhoneVerifyRequest(BaseModel):
    phone: str = Field(pattern=r"^\+[1-9]\d{7,14}$")
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


# ---------------------------------------------------------------------------
# Email verification schemas
# ---------------------------------------------------------------------------


class EmailVerifyStartRequest(BaseModel):
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def lowercase_email(cls, v: str) -> str:
        return v.lower().strip()


class EmailVerifyStartResponse(BaseModel):
    message: str = "Verification email sent."


class EmailVerifyFinishRequest(BaseModel):
    # Exactly one of token or code must be provided
    token: str | None = None
    code: str | None = Field(default=None, min_length=6, max_length=6, pattern=r"^\d{6}$")

    @field_validator("code", mode="before")
    @classmethod
    def check_one_provided(cls, v: str | None, info: object) -> str | None:
        return v


class EmailVerifyFinishResponse(BaseModel):
    email_verified: bool = True


# ---------------------------------------------------------------------------
# Password schemas
# ---------------------------------------------------------------------------


class PasswordResetStartRequest(BaseModel):
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def lowercase_email(cls, v: str) -> str:
        return v.lower().strip()


class PasswordResetStartResponse(BaseModel):
    message: str = "If that email is registered, a reset link has been sent."


class PasswordResetFinishRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class PasswordResetFinishResponse(BaseModel):
    password_reset: bool = True


# ---------------------------------------------------------------------------
# Token refresh + logout
# ---------------------------------------------------------------------------


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class LogoutResponse(BaseModel):
    logged_out: bool = True


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------


class SessionOut(BaseModel):
    id: uuid.UUID
    user_agent: str | None
    ip: str | None
    last_seen_at: datetime
    created_at: datetime
    is_current: bool = False

    model_config = {"from_attributes": True}


class SessionListResponse(BaseModel):
    sessions: list[SessionOut]


# ---------------------------------------------------------------------------
# Account management — email / phone change
# ---------------------------------------------------------------------------


class EmailChangeStartRequest(BaseModel):
    new_email: EmailStr

    @field_validator("new_email", mode="before")
    @classmethod
    def lowercase_email(cls, v: str) -> str:
        return v.lower().strip()


class EmailChangeStartResponse(BaseModel):
    message: str = "Verification email sent to new address."


class EmailChangeFinishRequest(BaseModel):
    token: str | None = None
    code: str | None = Field(default=None, min_length=6, max_length=6, pattern=r"^\d{6}$")


class EmailChangeFinishResponse(BaseModel):
    email_changed: bool = True


class PhoneChangeStartRequest(BaseModel):
    new_phone: str = Field(pattern=r"^\+[1-9]\d{7,14}$")


class PhoneChangeStartResponse(BaseModel):
    otp_sent: bool = True


class PhoneChangeFinishRequest(BaseModel):
    new_phone: str = Field(pattern=r"^\+[1-9]\d{7,14}$")
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class PhoneChangeFinishResponse(BaseModel):
    phone_changed: bool = True
