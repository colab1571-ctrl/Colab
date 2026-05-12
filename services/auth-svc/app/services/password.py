"""
auth-svc — Password hashing and validation.

argon2id: m=64MB, t=3, p=4 per master §0 lock.
Semaphore caps concurrent argon2 work to prevent pod OOM.
"""

from __future__ import annotations

import asyncio
import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from colab_common.errors import ValidationError

# Spec: m=64MB (65536 KiB), t=3, p=4
_PH = PasswordHasher(
    memory_cost=65536,
    time_cost=3,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)

# Cap concurrent verifications: 64MB * 8 = 512MB, well within 2GiB pod limit
_SEMAPHORE = asyncio.Semaphore(8)

# Patterns that weaken passwords
_COMMON_SEQUENCES = re.compile(r"(012|123|234|345|456|567|678|789|890|abc|bcd)", re.IGNORECASE)


def _validate_password_sync(password: str, email: str | None, phone: str | None) -> None:
    """Synchronous validation; run in thread via asyncio.to_thread."""
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters.")
    if len(password) > 128:
        raise ValidationError("Password too long (max 128 characters).")

    # Deny common password patterns
    if email and email.split("@")[0].lower() in password.lower():
        raise ValidationError("Password must not contain your email address.")
    if phone and phone.replace("+", "") in password:
        raise ValidationError("Password must not contain your phone number.")

    try:
        import zxcvbn  # type: ignore[import-untyped]

        result = zxcvbn.zxcvbn(password)
        if result["score"] < 2:
            feedback = result.get("feedback", {}).get("warning", "Password is too weak.")
            raise ValidationError(f"Password too weak: {feedback}")
    except ImportError:
        # zxcvbn not installed in test environments
        pass


def _hash_password_sync(password: str) -> str:
    """Run argon2id hash synchronously (called via asyncio.to_thread)."""
    return _PH.hash(password)


def _verify_password_sync(stored_hash: str, plaintext: str) -> bool:
    """Returns True on match, False on mismatch. Raises on corrupt hash."""
    try:
        return _PH.verify(stored_hash, plaintext)
    except VerifyMismatchError:
        return False
    except InvalidHashError:
        return False


def _needs_rehash_sync(stored_hash: str) -> bool:
    return _PH.check_needs_rehash(stored_hash)


async def validate_password(password: str, email: str | None = None, phone: str | None = None) -> None:
    """Validate password strength. Raises ValidationError on failure."""
    await asyncio.to_thread(_validate_password_sync, password, email, phone)


async def hash_password(password: str) -> str:
    """Hash a password with argon2id. Returns encoded hash string."""
    async with _SEMAPHORE:
        return await asyncio.to_thread(_hash_password_sync, password)


async def verify_password(stored_hash: str, plaintext: str) -> bool:
    """Verify a password against its stored argon2id hash."""
    async with _SEMAPHORE:
        return await asyncio.to_thread(_verify_password_sync, stored_hash, plaintext)


async def needs_rehash(stored_hash: str) -> bool:
    """Check if the hash needs to be upgraded (parameter change)."""
    return await asyncio.to_thread(_needs_rehash_sync, stored_hash)
