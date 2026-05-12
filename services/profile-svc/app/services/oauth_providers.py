"""
profile-svc — OAuth provider flows for Instagram, YouTube, Spotify.

Per plan §10:
- Instagram: Meta Graph API v21.0 long-lived token flow
- YouTube: Google OAuth 2.0 with offline access + youtube.readonly scope
- Spotify: Authorization Code with PKCE

State param: HMAC-signed JWT carrying profile_id + nonce + exp=10min
PKCE verifier for Spotify stored in Redis keyed by state (TTL 10m)

Tokens KMS-encrypted via kms_crypto.py before persistence.
Tokens never returned over API.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from typing import Any
from urllib.parse import urlencode

import httpx


def _sign_state(profile_id: str, nonce: str, secret: str, exp_seconds: int = 600) -> str:
    """Create HMAC-signed state token carrying profile_id + nonce + exp."""
    payload = json.dumps({
        "profile_id": profile_id,
        "nonce": nonce,
        "exp": int(time.time()) + exp_seconds,
    })
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    combined = base64.urlsafe_b64encode(
        (payload + "." + sig).encode()
    ).decode()
    return combined


def _verify_state(state: str, secret: str) -> dict[str, Any]:
    """Verify and decode state token. Raises ValueError on invalid/expired."""
    try:
        decoded = base64.urlsafe_b64decode(state.encode()).decode()
        payload_str, sig = decoded.rsplit(".", 1)
        expected_sig = hmac.new(secret.encode(), payload_str.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            raise ValueError("Invalid state signature")
        payload = json.loads(payload_str)
        if payload.get("exp", 0) < int(time.time()):
            raise ValueError("State token expired")
        return payload
    except Exception as e:
        raise ValueError(f"Invalid state: {e}") from e


# ---------------------------------------------------------------------------
# Instagram
# ---------------------------------------------------------------------------

class InstagramOAuth:
    AUTH_URL = "https://www.facebook.com/v21.0/dialog/oauth"
    TOKEN_URL = "https://graph.facebook.com/v21.0/oauth/access_token"
    REFRESH_URL = "https://graph.facebook.com/v21.0/oauth/access_token"
    SCOPES = "instagram_basic,pages_show_list,business_management,instagram_manage_insights"

    def __init__(self, app_id: str, app_secret: str, redirect_uri: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.redirect_uri = redirect_uri

    def get_authorize_url(self, state: str) -> str:
        params = {
            "client_id": self.app_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.SCOPES,
            "response_type": "code",
            "state": state,
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict[str, Any]:
        """Exchange auth code for short-lived token, then long-lived token."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get short-lived token
            resp = await client.get(
                self.TOKEN_URL,
                params={
                    "client_id": self.app_id,
                    "client_secret": self.app_secret,
                    "redirect_uri": self.redirect_uri,
                    "code": code,
                },
            )
            resp.raise_for_status()
            short_token = resp.json()["access_token"]

            # Exchange for long-lived token (60d)
            resp2 = await client.get(
                self.REFRESH_URL,
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": self.app_id,
                    "client_secret": self.app_secret,
                    "fb_exchange_token": short_token,
                },
            )
            resp2.raise_for_status()
            data = resp2.json()
            return {
                "access_token": data["access_token"],
                "expires_in": data.get("expires_in", 5184000),  # 60 days default
                "token_type": "bearer",
            }

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://graph.facebook.com/v21.0/me",
                params={"fields": "id,name", "access_token": access_token},
            )
            resp.raise_for_status()
            return resp.json()

    async def refresh_token(self, token: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://graph.facebook.com/v21.0/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": self.app_id,
                    "client_secret": self.app_secret,
                    "fb_exchange_token": token,
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def revoke_token(self, user_id: str, access_token: str) -> None:
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.delete(
                f"https://graph.facebook.com/v21.0/{user_id}/permissions",
                params={"access_token": access_token},
            )


# ---------------------------------------------------------------------------
# YouTube (Google)
# ---------------------------------------------------------------------------

class YouTubeOAuth:
    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    REVOKE_URL = "https://oauth2.googleapis.com/revoke"
    SCOPES = "https://www.googleapis.com/auth/youtube.readonly openid profile email"

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def get_authorize_url(self, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.SCOPES,
            "response_type": "code",
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": self.redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            resp.raise_for_status()
            return resp.json()  # access_token + refresh_token + expires_in

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def revoke(self, token: str) -> None:
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(self.REVOKE_URL, params={"token": token})


# ---------------------------------------------------------------------------
# Spotify (PKCE)
# ---------------------------------------------------------------------------

def _pkce_pair() -> tuple[str, str]:
    """Generate (code_verifier, code_challenge) for PKCE."""
    verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


class SpotifyOAuth:
    AUTH_URL = "https://accounts.spotify.com/authorize"
    TOKEN_URL = "https://accounts.spotify.com/api/token"
    SCOPES = "user-read-private user-read-email user-top-read"

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def get_authorize_url(self, state: str) -> tuple[str, str]:
        """Returns (authorize_url, code_verifier). Store verifier in Redis."""
        verifier, challenge = _pkce_pair()
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "state": state,
            "scope": self.SCOPES,
        }
        return f"{self.AUTH_URL}?{urlencode(params)}", verifier

    async def exchange_code(self, code: str, code_verifier: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                    "client_id": self.client_id,
                    "code_verifier": code_verifier,
                },
            )
            resp.raise_for_status()
            return resp.json()  # access_token + refresh_token + expires_in

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            # Spotify may rotate the refresh token — always persist the new one
            return data

    async def get_user_profile(self, access_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://api.spotify.com/v1/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            return resp.json()
