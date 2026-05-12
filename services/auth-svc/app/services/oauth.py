"""
auth-svc — Apple Sign-In + Google Sign-In server-side token verification.

Apple: manual JWT verification against Apple's JWKS (no third-party lib).
Google: google-auth library (handles JWKS + sig + exp + aud).
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import httpx
import jwt

from colab_common.errors import AuthError

# ---------------------------------------------------------------------------
# Apple Sign-In
# ---------------------------------------------------------------------------

_APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
_APPLE_ISSUER = "https://appleid.apple.com"
_APPLE_JWKS_CACHE: tuple[dict[str, Any], float] | None = None
_APPLE_JWKS_TTL = 6 * 3600  # 6 hours


async def _fetch_apple_jwks() -> dict[str, Any]:
    global _APPLE_JWKS_CACHE
    now = time.monotonic()
    if _APPLE_JWKS_CACHE and (now - _APPLE_JWKS_CACHE[1]) < _APPLE_JWKS_TTL:
        return _APPLE_JWKS_CACHE[0]

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(_APPLE_JWKS_URL)
        resp.raise_for_status()
        jwks: dict[str, Any] = resp.json()
        _APPLE_JWKS_CACHE = (jwks, now)
        return jwks


def _get_apple_key_sync(kid: str, jwks: dict[str, Any]) -> Any:
    """Find the JWK matching kid and return a public key object."""
    from jwt.algorithms import RSAAlgorithm

    for key_data in jwks.get("keys", []):
        if key_data.get("kid") == kid:
            return RSAAlgorithm.from_jwk(key_data)
    raise AuthError("Apple public key not found for kid.")


async def verify_apple_id_token(
    id_token: str,
    nonce: str | None = None,
) -> dict[str, Any]:
    """
    Verify Apple ID token. Returns decoded claims dict.
    Raises AuthError on any failure.
    """
    client_id = os.environ.get("APPLE_SIGN_IN_CLIENT_ID", "")
    if not client_id:
        raise AuthError("Apple Sign-In not configured.")

    # Decode header without verification to get kid
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.DecodeError as exc:
        raise AuthError("Malformed Apple ID token.") from exc

    if header.get("alg") != "RS256":
        raise AuthError("Apple token must use RS256.")

    kid = header.get("kid", "")
    jwks = await _fetch_apple_jwks()

    try:
        pub_key = _get_apple_key_sync(kid, jwks)
    except AuthError:
        # Refresh JWKS once and retry
        global _APPLE_JWKS_CACHE
        _APPLE_JWKS_CACHE = None
        jwks = await _fetch_apple_jwks()
        pub_key = _get_apple_key_sync(kid, jwks)

    try:
        claims: dict[str, Any] = jwt.decode(
            id_token,
            pub_key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=_APPLE_ISSUER,
            options={"leeway": 30},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Apple ID token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError(f"Apple ID token invalid: {exc}") from exc

    # Validate nonce if provided (replay protection)
    if nonce is not None:
        import hashlib

        expected_nonce_hash = hashlib.sha256(nonce.encode()).hexdigest()
        if claims.get("nonce") != expected_nonce_hash:
            raise AuthError("Apple ID token nonce mismatch.")

    return {
        "provider": "apple",
        "provider_subject": claims["sub"],
        "email": claims.get("email"),
        "email_verified": claims.get("email_verified", False),
        "is_private_email": claims.get("is_private_email", False),
    }


# ---------------------------------------------------------------------------
# Google Sign-In
# ---------------------------------------------------------------------------

_GOOGLE_VALID_AUDIENCES: list[str] = []


def _get_google_audiences() -> list[str]:
    global _GOOGLE_VALID_AUDIENCES
    if not _GOOGLE_VALID_AUDIENCES:
        ids = [
            os.environ.get("GOOGLE_CLIENT_ID_IOS", ""),
            os.environ.get("GOOGLE_CLIENT_ID_ANDROID", ""),
            os.environ.get("GOOGLE_CLIENT_ID_WEB", ""),
        ]
        _GOOGLE_VALID_AUDIENCES = [i for i in ids if i]
    return _GOOGLE_VALID_AUDIENCES


def _verify_google_token_sync(id_token: str) -> dict[str, Any]:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token

    audiences = _get_google_audiences()
    if not audiences:
        raise AuthError("Google Sign-In not configured.")

    # Try each audience
    last_exc: Exception | None = None
    for audience in audiences:
        try:
            idinfo: dict[str, Any] = google_id_token.verify_oauth2_token(
                id_token,
                google_requests.Request(),
                audience=audience,
            )
            if not idinfo.get("email_verified"):
                raise AuthError("Google account email is not verified.")
            return {
                "provider": "google",
                "provider_subject": idinfo["sub"],
                "email": idinfo.get("email"),
                "email_verified": idinfo.get("email_verified", False),
            }
        except ValueError as exc:
            last_exc = exc
            continue

    raise AuthError(f"Google ID token invalid: {last_exc}")


async def verify_google_id_token(id_token: str) -> dict[str, Any]:
    """Verify Google ID token. Returns claims dict. Raises AuthError on failure."""
    try:
        return await asyncio.to_thread(_verify_google_token_sync, id_token)
    except AuthError:
        raise
    except Exception as exc:
        raise AuthError(f"Google token verification failed: {exc}") from exc
