"""
discovery-svc — feed assembly service.

Responsibilities:
- Build candidate profile list (PostGIS radius + filters + block + hide)
- Integrate with matching-svc for ranked scores
- Hydrate profile cards from profile-svc
- Cursor pagination
- Entitlement / cap enforcement
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone, timedelta
from uuid import UUID

import httpx

from app.config import get_settings
from app.schemas.feed import (
    FeedCursor,
    FeedFilters,
    FeedResponse,
    ProfileCard,
    VocationCard,
    PortfolioPreviewItem,
    encode_cursor,
    decode_cursor,
)
from app.services.cache import (
    check_and_increment_cap,
    get_feed_page,
    get_feed_mode,
    set_feed_mode,
    set_feed_page,
)

logger = logging.getLogger(__name__)
_settings = get_settings()

_http = httpx.AsyncClient(timeout=5.0)

CAP_FREE = _settings.rate_limit_feed_profiles_free_per_day


def _relative_time(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    now = datetime.now(tz=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    days = delta.days
    if days == 0:
        return "today"
    elif days == 1:
        return "1 day ago"
    elif days < 7:
        return f"{days} days ago"
    elif days < 30:
        weeks = days // 7
        return f"{weeks} week{'s' if weeks > 1 else ''} ago"
    elif days < 365:
        months = days // 30
        return f"{months} month{'s' if months > 1 else ''} ago"
    else:
        return "over a year ago"


async def get_entitlement_tier(user_id: str, jwt: str) -> str:
    """Fetch billing entitlement tier for user. Returns 'free' on error or if feature flag off."""
    if not _settings.feature_billing_entitlement_check:
        return "free"  # default until billing-svc lands (§013)
    try:
        resp = await _http.get(
            f"{_settings.billing_svc_url}/entitlements/me",
            headers={"Authorization": f"Bearer {jwt}"},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("tier", "free")
    except Exception:
        logger.warning("billing-svc entitlement check failed; defaulting to free")
        return "free"


async def _fetch_profile_cards(
    profile_ids: list[str], viewer_user_id: str, jwt: str, saved_ids: set[str]
) -> list[ProfileCard]:
    """Batch-fetch profile cards from profile-svc."""
    if not profile_ids:
        return []
    try:
        resp = await _http.post(
            f"{_settings.profile_svc_url}/internal/profiles/batch",
            json={"profile_ids": profile_ids},
            headers={
                "X-Internal-Service-Token": _settings.internal_service_secret,
                "Authorization": f"Bearer {jwt}",
            },
        )
        resp.raise_for_status()
        profiles_data = resp.json().get("profiles", [])
    except Exception as exc:
        logger.error("profile-svc batch fetch failed: %s", exc)
        return []

    cards = []
    for p in profiles_data:
        vocations = [
            VocationCard(category=v["category"], subtag=v["subtag"])
            for v in p.get("vocations", [])
        ]
        portfolio_preview = [
            PortfolioPreviewItem(
                type=item["type"],
                url=item.get("url", ""),
                caption=item.get("caption"),
            )
            for item in p.get("portfolio_preview", [])
        ]
        cards.append(
            ProfileCard(
                id=p["id"],
                display_name=p.get("display_name"),
                location_city=p.get("location_city"),
                badge_state=p.get("badge_state", "badge_granted"),
                vocations=vocations,
                bio=p.get("bio"),
                obsessed_with=p.get("obsessed_with"),
                experience_level=p.get("experience_level"),
                open_to_remote=p.get("open_to_remote", False),
                portfolio_preview=portfolio_preview,
                collab_count=p.get("collab_count", 0),
                last_active_relative=_relative_time(
                    datetime.fromisoformat(p["last_active_at"])
                    if p.get("last_active_at")
                    else None
                ),
                saved=str(p["id"]) in saved_ids,
            )
        )
    return cards


async def get_ranked_candidates(
    viewer_profile_id: str,
    filters: FeedFilters,
    limit: int,
    offset: int,
) -> list[tuple[str, float]]:
    """Fetch ranked candidates from matching-svc."""
    try:
        resp = await _http.get(
            f"{_settings.matching_svc_url}/internal/candidates",
            params={
                "viewer_profile_id": viewer_profile_id,
                "filters": filters.model_dump_json(),
                "limit": limit,
                "offset": offset,
            },
            headers={"X-Internal-Service-Token": _settings.internal_service_secret},
        )
        resp.raise_for_status()
        data = resp.json()
        return [(c["profile_id"], c["score"]) for c in data.get("candidates", [])]
    except Exception as exc:
        logger.error("matching-svc candidates fetch failed: %s", exc)
        return []


async def build_feed(
    viewer_user_id: str,
    viewer_profile_id: str,
    jwt: str,
    mode: str,
    cursor_token: str | None,
    page_size: int,
    filters: FeedFilters,
) -> tuple[FeedResponse, int]:
    """
    Build the feed response.
    Returns (FeedResponse, http_status_code).
    Status 402 when cap reached.
    """
    tier = await get_entitlement_tier(viewer_user_id, jwt)
    filter_hash = filters.filter_hash()
    today_str = date.today().isoformat()

    # Decode / validate cursor
    offset = 0
    if cursor_token:
        cursor = decode_cursor(cursor_token)
        if cursor is None or cursor.fh != filter_hash or cursor.d != today_str:
            # Invalid or stale cursor — reset
            offset = 0
        else:
            offset = cursor.o

    # Check cap before serving
    allowed, remaining = await check_and_increment_cap(viewer_user_id, tier, page_size)
    if not allowed:
        from datetime import timezone as tz

        resets_at = (
            datetime.now(tz=timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            + timedelta(days=1)
        )
        return (
            FeedResponse(
                mode=mode,
                profiles=[],
                next_cursor=None,
                remaining_today=0,
                cap=CAP_FREE,
            ),
            402,
        )

    # Try Redis cache first
    profile_ids = await get_feed_page(viewer_user_id, mode, filter_hash, offset, page_size)

    if profile_ids is None:
        # Cache miss — fetch from matching-svc
        scored = await get_ranked_candidates(
            viewer_profile_id=viewer_profile_id,
            filters=filters,
            limit=200,  # fetch large pool for caching
            offset=0,
        )
        if scored:
            await set_feed_page(viewer_user_id, mode, filter_hash, scored)
        profile_ids = [pid for pid, _ in scored[offset : offset + page_size]]

    # Fetch saved IDs for this user (to mark cards)
    saved_ids: set[str] = set()
    try:
        resp = await _http.get(
            f"{_settings.profile_svc_url}/internal/saved-ids/{viewer_user_id}",
            headers={"X-Internal-Service-Token": _settings.internal_service_secret},
        )
        if resp.status_code == 200:
            saved_ids = set(resp.json().get("saved_ids", []))
    except Exception:
        pass

    cards = await _fetch_profile_cards(profile_ids, viewer_user_id, jwt, saved_ids)

    next_offset = offset + len(cards)
    next_cursor_token: str | None = None
    if cards and len(cards) == page_size:
        next_cursor_token = encode_cursor(
            FeedCursor(fh=filter_hash, o=next_offset, d=today_str)
        )

    return (
        FeedResponse(
            mode=mode,
            profiles=cards,
            next_cursor=next_cursor_token,
            remaining_today=remaining if tier == "free" else None,
            cap=CAP_FREE if tier == "free" else None,
        ),
        200,
    )
