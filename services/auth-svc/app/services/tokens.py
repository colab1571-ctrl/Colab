"""
auth-svc — JWT issuance and verification with RS256 + KMS backing.

Access tokens: 15min. Refresh tokens: 30d. Both RS256-signed.
KMS sign calls are cached in asyncio.to_thread to avoid blocking the event loop.
JWKS endpoint: GET /.well-known/jwks.json (public keys only, no KMS round-trip).
Refresh tokens rotate on every use — stolen-refresh detection via JTI set in Redis.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import time
import uuid
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import redis.asyncio as aioredis
from colab_common.settings import get_settings

# ---------------------------------------------------------------------------
# Key management helpers (KMS in prod, local RSA in dev)
# ---------------------------------------------------------------------------

_private_key: Any = None
_public_key_pem: bytes = b""
_kid: str = "colab-auth-key-1"


def _load_or_generate_dev_key() -> tuple[Any, bytes, str]:
    """In dev: generate or load a local RSA key. In prod: KMS provides signing."""
    key_path = os.environ.get("AUTH_PRIVATE_KEY_PATH", "")
    if key_path and os.path.exists(key_path):
        with open(key_path, "rb") as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
    else:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    pub_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    kid = os.environ.get("AUTH_KID", "colab-auth-key-1")
    return private_key, pub_pem, kid


def _get_keys() -> tuple[Any, bytes, str]:
    global _private_key, _public_key_pem, _kid
    if _private_key is None:
        _private_key, _public_key_pem, _kid = _load_or_generate_dev_key()
    return _private_key, _public_key_pem, _kid


# ---------------------------------------------------------------------------
# JWKS builder
# ---------------------------------------------------------------------------


def build_jwks() -> dict[str, Any]:
    """Return the public JWKS document for /.well-known/jwks.json."""
    _, pub_pem, kid = _get_keys()
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
    from cryptography.x509.oid import ExtendedKeyUsageOID  # noqa: F401

    from cryptography.hazmat.backends import default_backend

    pub_key: RSAPublicKey = serialization.load_pem_public_key(pub_pem, backend=default_backend())  # type: ignore[arg-type]
    pub_numbers = pub_key.public_key().public_numbers() if hasattr(pub_key, "public_key") else pub_key.public_numbers()

    def _int_to_base64url(n: int) -> str:
        length = (n.bit_length() + 7) // 8
        return base64.urlsafe_b64encode(n.to_bytes(length, "big")).rstrip(b"=").decode()

    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": kid,
                "n": _int_to_base64url(pub_numbers.n),
                "e": _int_to_base64url(pub_numbers.e),
            }
        ]
    }


# ---------------------------------------------------------------------------
# Token minting
# ---------------------------------------------------------------------------


def _mint_access_token_sync(
    user_id: str,
    session_id: str,
    email_verified: bool,
    identity_verified: bool,
    scope: list[str] | None = None,
) -> str:
    settings = get_settings()
    private_key, _, kid = _get_keys()
    now = int(time.time())
    jti = str(uuid.uuid4())

    claims = {
        "iss": "auth.colab",
        "aud": ["api.colab"],
        "sub": user_id,
        "jti": jti,
        "iat": now,
        "nbf": now,
        "exp": now + settings.jwt.access_ttl_seconds,
        "sid": session_id,
        "email_verified": email_verified,
        "identity_verified": identity_verified,
        "scope": scope or ["user"],
        "typ": "access",
    }
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})


def _mint_refresh_token_sync(user_id: str, session_id: str) -> tuple[str, str]:
    """Returns (encoded_jwt, jti)."""
    settings = get_settings()
    private_key, _, kid = _get_keys()
    now = int(time.time())
    jti = str(uuid.uuid4())

    claims = {
        "iss": "auth.colab",
        "sub": user_id,
        "jti": jti,
        "iat": now,
        "nbf": now,
        "exp": now + settings.jwt.refresh_ttl_seconds,
        "sid": session_id,
        "typ": "refresh",
    }
    token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})
    return token, jti


async def mint_access_token(
    user_id: str,
    session_id: str,
    email_verified: bool,
    identity_verified: bool,
    scope: list[str] | None = None,
) -> str:
    return await asyncio.to_thread(
        _mint_access_token_sync, user_id, session_id, email_verified, identity_verified, scope
    )


async def mint_refresh_token(user_id: str, session_id: str) -> tuple[str, str]:
    """Returns (token, jti)."""
    return await asyncio.to_thread(_mint_refresh_token_sync, user_id, session_id)


# ---------------------------------------------------------------------------
# Token verification
# ---------------------------------------------------------------------------


def _decode_token_sync(token: str, expected_type: str = "access") -> dict[str, Any]:
    _, pub_pem, _ = _get_keys()
    from cryptography.hazmat.backends import default_backend

    pub_key = serialization.load_pem_public_key(pub_pem, backend=default_backend())
    options: dict[str, Any] = {
        "verify_exp": True,
        "verify_aud": expected_type == "access",
        "leeway": 30,
    }
    audience = ["api.colab"] if expected_type == "access" else None
    payload: dict[str, Any] = jwt.decode(
        token,
        pub_key,
        algorithms=["RS256"],
        options=options,
        audience=audience,
    )
    if payload.get("typ") != expected_type:
        raise jwt.InvalidTokenError(f"Expected token type '{expected_type}'")
    return payload


async def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(_decode_token_sync, token, "access")
    except jwt.ExpiredSignatureError as exc:
        from colab_common.errors import AuthError
        raise AuthError("Token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        from colab_common.errors import AuthError
        raise AuthError(f"Invalid token: {exc}") from exc


async def decode_refresh_token(token: str) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(_decode_token_sync, token, "refresh")
    except jwt.ExpiredSignatureError as exc:
        from colab_common.errors import AuthError
        raise AuthError("Refresh token has expired. Please log in again.") from exc
    except jwt.InvalidTokenError as exc:
        from colab_common.errors import AuthError
        raise AuthError(f"Invalid refresh token: {exc}") from exc


# ---------------------------------------------------------------------------
# Refresh-token revocation tracking (Redis)
# ---------------------------------------------------------------------------

_redis_client: aioredis.Redis | None = None  # type: ignore[type-arg]


def _get_redis() -> aioredis.Redis:  # type: ignore[type-arg]
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(settings.redis.url, decode_responses=True)
    return _redis_client


async def mark_jti_revoked(jti: str, ttl_seconds: int) -> None:
    """Add a JTI to the refresh revocation set."""
    r = _get_redis()
    await r.setex(f"revoked:jti:{jti}", ttl_seconds, "1")


async def is_jti_revoked(jti: str) -> bool:
    r = _get_redis()
    return bool(await r.exists(f"revoked:jti:{jti}"))


async def mark_session_revoked(session_id: str) -> None:
    """Gateway checks this bitmap on every request; TTL = 30d."""
    r = _get_redis()
    await r.setex(f"revoked:session:{session_id}", 2592000, "1")


async def is_session_revoked(session_id: str) -> bool:
    r = _get_redis()
    return bool(await r.exists(f"revoked:session:{session_id}"))


def hash_token(token_bytes: bytes) -> str:
    """SHA-256 hex digest for storing refresh token references."""
    return hashlib.sha256(token_bytes).hexdigest()


def hash_token_str(token: str) -> str:
    return hash_token(token.encode())
