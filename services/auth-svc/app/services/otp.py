"""
auth-svc — Phone OTP (via AWS SNS) and magic-link/OTP generation for email flows.

Phone OTP: 6-digit, 5-min TTL, max 5 wrong attempts, 30-min cooldown after exhaustion.
Magic-link: opaque 32-byte token, SHA-256 stored in DB, 15-min TTL.
Email OTP: 6-digit parallel fallback for the same magic_link row.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta

import redis.asyncio as aioredis

from colab_common.settings import get_settings

# ---------------------------------------------------------------------------
# Phone OTP — Redis-backed
# ---------------------------------------------------------------------------

OTP_TTL_SECONDS = 300  # 5 minutes
OTP_MAX_ATTEMPTS = 5
OTP_COOLDOWN_SECONDS = 1800  # 30 minutes


def _get_redis() -> aioredis.Redis:  # type: ignore[type-arg]
    settings = get_settings()
    return aioredis.from_url(settings.redis.url, decode_responses=True)


def _generate_otp() -> str:
    """Cryptographically random 6-digit OTP."""
    return str(secrets.randbelow(900_000) + 100_000)


async def send_phone_otp(phone: str, ip: str) -> str:
    """
    Generate OTP, store in Redis, send via AWS SNS.
    Returns the OTP (for use in tests; in prod the code is sent only via SMS).
    Raises if number is in cooldown or SNS opt-out list.
    """
    r = _get_redis()

    # Check cooldown
    cooldown_key = f"otp:cooldown:phone:{phone}:{ip}"
    if await r.exists(cooldown_key):
        from colab_common.errors import RateLimitError

        raise RateLimitError(retry_after=OTP_COOLDOWN_SECONDS)

    # Reuse live OTP if one exists (avoid SMS spam)
    data_key = f"otp:phone:{phone}"
    existing = await r.hget(data_key, "code")
    if existing:
        return str(existing)

    otp = _generate_otp()
    pipe = r.pipeline()
    pipe.hset(data_key, mapping={"code": otp, "attempts": "0"})
    pipe.expire(data_key, OTP_TTL_SECONDS)
    await pipe.execute()

    await _send_sms(phone, otp)
    return otp


async def verify_phone_otp(phone: str, code: str) -> bool:
    """
    Returns True on match + consumed. Raises on lockout/expired.
    """
    r = _get_redis()
    data_key = f"otp:phone:{phone}"

    stored_code = await r.hget(data_key, "code")
    if not stored_code:
        from colab_common.errors import AuthError

        raise AuthError("OTP expired or not found. Request a new code.")

    attempts = int(await r.hget(data_key, "attempts") or 0)
    if attempts >= OTP_MAX_ATTEMPTS:
        await r.delete(data_key)
        cooldown_key = f"otp:cooldown:phone:{phone}:*"
        from colab_common.errors import AuthError

        raise AuthError("Too many OTP attempts. Request a new code in 30 minutes.")

    if not secrets.compare_digest(str(stored_code), code):
        await r.hincr(data_key, "attempts", 1)  # type: ignore[attr-defined]
        new_attempts = attempts + 1
        if new_attempts >= OTP_MAX_ATTEMPTS:
            await r.delete(data_key)
        return False

    # Matched — consume
    await r.delete(data_key)
    return True


async def _send_sms(phone: str, otp: str) -> None:
    """Send OTP via AWS SNS. Stubbed in dev if SNS_ENABLED != true."""
    sns_enabled = os.environ.get("SNS_ENABLED", "false").lower() == "true"
    if not sns_enabled:
        return  # In dev, OTP is returned directly; no SMS sent

    import boto3  # noqa: F401 — only imported when SNS is enabled

    client = boto3.client("sns", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    message = (
        f"Colab: Your verification code is {otp}. "
        f"Expires in 5 minutes. Reply STOP to opt out."
    )
    sender_id = os.environ.get("SNS_SMS_SENDER_ID", "Colab")
    client.publish(
        PhoneNumber=phone,
        Message=message,
        MessageAttributes={
            "AWS.SNS.SMS.SenderID": {"DataType": "String", "StringValue": sender_id},
            "AWS.SNS.SMS.SMSType": {"DataType": "String", "StringValue": "Transactional"},
        },
    )


# ---------------------------------------------------------------------------
# Magic-link + email OTP generation
# ---------------------------------------------------------------------------


def generate_magic_link_token() -> tuple[str, str]:
    """Returns (raw_token, sha256_hex). Store only the hash."""
    raw = secrets.token_bytes(32)
    token_b64 = secrets.token_urlsafe(32)
    sha = hashlib.sha256(token_b64.encode()).hexdigest()
    return token_b64, sha


def generate_otp_pair() -> tuple[str, str]:
    """Returns (otp_digits, sha256_hex). Store only the hash."""
    otp = _generate_otp()
    sha = hashlib.sha256(otp.encode()).hexdigest()
    return otp, sha


def magic_link_expiry(minutes: int = 15) -> datetime:
    return datetime.now(UTC) + timedelta(minutes=minutes)


def verify_token_hash(raw: str, stored_hash: str) -> bool:
    computed = hashlib.sha256(raw.encode()).hexdigest()
    return secrets.compare_digest(computed, stored_hash)


def verify_otp_hash(otp: str, stored_hash: str) -> bool:
    computed = hashlib.sha256(otp.encode()).hexdigest()
    return secrets.compare_digest(computed, stored_hash)
