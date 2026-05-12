"""
profile-svc — OAuth provider linking endpoints.

POST /api/v1/profile/me/externals/{provider}/connect
GET  /api/v1/oauth/{provider}/callback
DELETE /api/v1/profile/me/externals/{provider}

KMS token encryption per plan §10.
State = HMAC-signed JWT carrying profile_id + nonce + exp=10min.
PKCE code_verifier for Spotify stored in Redis (TTL 10min).
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.models import Profile
from app.models.profile import ExternalLink
from app.schemas.profile import OAuthConnectResponse
from app.services.kms_crypto import encrypt_token
from app.services.oauth_providers import (
    InstagramOAuth,
    SpotifyOAuth,
    YouTubeOAuth,
    _sign_state,
    _verify_state,
)

router = APIRouter(tags=["oauth"])
SUPPORTED_PROVIDERS = ("instagram", "youtube", "spotify")


def _require_auth(request: Request) -> uuid.UUID:
    uid_header = request.headers.get("X-User-Id")
    if not uid_header:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return uuid.UUID(uid_header)


async def _get_profile(user_id: uuid.UUID, session: AsyncSession) -> Profile:
    result = await session.execute(select(Profile).where(Profile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile


def _get_redis():
    settings = get_settings()
    return aioredis.from_url(settings.redis_url, decode_responses=True)


@router.post("/api/v1/profile/me/externals/{provider}/connect", response_model=OAuthConnectResponse)
async def connect_provider(
    provider: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> OAuthConnectResponse:
    """Kick off OAuth flow for provider. Returns authorize_url + state."""
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported provider: {provider}")

    user_id = _require_auth(request)
    profile = await _get_profile(user_id, session)
    settings = get_settings()

    nonce = secrets.token_hex(16)
    state = _sign_state(str(profile.id), nonce, settings.internal_service_secret)

    redirect_uri = f"{settings.app_domain}/oauth/{provider}/callback"

    if provider == "instagram":
        ig = InstagramOAuth(settings.instagram_app_id, settings.instagram_app_secret, redirect_uri)
        authorize_url = ig.get_authorize_url(state)

    elif provider == "youtube":
        yt = YouTubeOAuth(settings.youtube_client_id, settings.youtube_client_secret, redirect_uri)
        authorize_url = yt.get_authorize_url(state)

    elif provider == "spotify":
        sp = SpotifyOAuth(settings.spotify_client_id, settings.spotify_client_secret, redirect_uri)
        authorize_url, code_verifier = sp.get_authorize_url(state)
        # Store PKCE verifier in Redis (TTL 10min)
        redis = _get_redis()
        await redis.setex(f"spotify:pkce:{state}", 600, code_verifier)
        await redis.aclose()

    return OAuthConnectResponse(authorize_url=authorize_url, state=state)


@router.get("/api/v1/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Response:
    """
    Handle OAuth redirect. Exchange code for tokens, KMS-encrypt, persist.
    Redirects to deep link colab://profile/externals?status=connected&provider=...
    """
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported provider: {provider}")

    settings = get_settings()
    code = request.query_params.get("code")
    state = request.query_params.get("state")

    if not code or not state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing code or state")

    # Verify state
    try:
        payload = _verify_state(state, settings.internal_service_secret)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    profile_id = uuid.UUID(payload["profile_id"])
    profile_result = await session.execute(select(Profile).where(Profile.id == profile_id))
    profile = profile_result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    redirect_uri = f"{settings.app_domain}/oauth/{provider}/callback"

    if provider == "instagram":
        ig = InstagramOAuth(settings.instagram_app_id, settings.instagram_app_secret, redirect_uri)
        token_data = await ig.exchange_code(code)
        access_token = token_data["access_token"]
        refresh_token = None
        expires_in = token_data.get("expires_in", 5184000)
        user_info = await ig.get_user_info(access_token)
        provider_handle = user_info.get("name", "")
        provider_id = user_info.get("id", "")
        scopes = ["instagram_basic", "pages_show_list", "business_management", "instagram_manage_insights"]

    elif provider == "youtube":
        yt = YouTubeOAuth(settings.youtube_client_id, settings.youtube_client_secret, redirect_uri)
        token_data = await yt.exchange_code(code)
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)
        provider_handle = token_data.get("email", "")
        provider_id = token_data.get("sub", "")
        scopes = ["https://www.googleapis.com/auth/youtube.readonly", "openid", "profile", "email"]

    elif provider == "spotify":
        sp = SpotifyOAuth(settings.spotify_client_id, settings.spotify_client_secret, redirect_uri)
        # Retrieve PKCE verifier
        redis = _get_redis()
        code_verifier = await redis.get(f"spotify:pkce:{state}")
        await redis.aclose()
        if not code_verifier:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PKCE verifier expired or missing")

        token_data = await sp.exchange_code(code, code_verifier)
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)
        user_profile = await sp.get_user_profile(access_token)
        provider_handle = user_profile.get("display_name", "") or user_profile.get("id", "")
        provider_id = user_profile.get("id", "")
        scopes = ["user-read-private", "user-read-email", "user-top-read"]
    else:
        raise HTTPException(status_code=400, detail="Unknown provider")

    # KMS-encrypt tokens
    pid_str = str(profile_id)
    ct_access = encrypt_token(access_token, provider, pid_str, "access")
    ct_refresh = None
    if refresh_token:
        ct_refresh = encrypt_token(refresh_token, provider, pid_str, "refresh")

    # Upsert ExternalLink
    existing_result = await session.execute(
        select(ExternalLink).where(
            ExternalLink.profile_id == profile_id,
            ExternalLink.provider == provider,
        )
    )
    link = existing_result.scalar_one_or_none()

    token_expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=expires_in)

    if link:
        link.provider_handle = provider_handle
        link.provider_id = provider_id
        link.encrypted_access_token = ct_access.ciphertext
        link.data_key_ciphertext = ct_access.data_key_ciphertext
        link.encrypted_refresh_token = ct_refresh.ciphertext if ct_refresh else None
        link.scopes = scopes
        link.token_expires_at = token_expires_at
        link.sync_state = "ok"
        link.last_synced_at = datetime.now(tz=timezone.utc)
    else:
        link = ExternalLink(
            profile_id=profile_id,
            provider=provider,
            provider_handle=provider_handle,
            provider_id=provider_id,
            encrypted_access_token=ct_access.ciphertext,
            data_key_ciphertext=ct_access.data_key_ciphertext,
            encrypted_refresh_token=ct_refresh.ciphertext if ct_refresh else None,
            scopes=scopes,
            token_expires_at=token_expires_at,
            sync_state="ok",
        )
        session.add(link)

    await session.commit()

    # Redirect to app deep link
    deep_link = f"colab://profile/externals?status=connected&provider={provider}"
    return RedirectResponse(url=deep_link, status_code=302)


@router.delete("/api/v1/profile/me/externals/{provider}", status_code=204)
async def disconnect_provider(
    provider: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> None:
    """Disconnect OAuth provider. Revokes token if supported, clears ciphertext."""
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported provider: {provider}")

    user_id = _require_auth(request)
    profile = await _get_profile(user_id, session)
    settings = get_settings()

    result = await session.execute(
        select(ExternalLink).where(
            ExternalLink.profile_id == profile.id,
            ExternalLink.provider == provider,
        )
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Provider {provider} not connected")

    # Attempt revocation
    try:
        from app.services.kms_crypto import decrypt_token
        if link.encrypted_access_token and link.data_key_ciphertext:
            access_token = decrypt_token(
                link.encrypted_access_token,
                link.data_key_ciphertext,
                provider,
                str(profile.id),
                "access",
            )
            redirect_uri = f"{settings.app_domain}/oauth/{provider}/callback"
            if provider == "instagram" and link.provider_id:
                ig = InstagramOAuth(settings.instagram_app_id, settings.instagram_app_secret, redirect_uri)
                await ig.revoke_token(link.provider_id, access_token)
            elif provider == "youtube" and link.encrypted_refresh_token:
                refresh_token = decrypt_token(
                    link.encrypted_refresh_token,
                    link.data_key_ciphertext,
                    provider,
                    str(profile.id),
                    "refresh",
                )
                yt = YouTubeOAuth(settings.youtube_client_id, settings.youtube_client_secret, redirect_uri)
                await yt.revoke(refresh_token)
    except Exception:
        pass  # best-effort revocation

    await session.delete(link)
    await session.commit()
