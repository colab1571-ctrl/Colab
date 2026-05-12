"""
Tests: credit reservation + refund-on-failure pattern.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.billing_client import (
    InsufficientCreditsError,
    commit_reservation,
    release_reservation,
    reserve_credits,
)


@pytest.mark.asyncio
async def test_reserve_credits_success():
    reservation_id = uuid.uuid4()
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"reservation_id": str(reservation_id)}
    mock_resp.raise_for_status = AsyncMock()

    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=mock_resp)

    result = await reserve_credits(
        user_id=uuid.uuid4(),
        amount=20,
        reference_id=uuid.uuid4(),
        http=mock_http,
    )
    assert result == reservation_id
    mock_http.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_reserve_credits_insufficient():
    mock_resp = AsyncMock()
    mock_resp.status_code = 402
    mock_resp.json.return_value = {"balance": 5, "requested": 20}

    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=mock_resp)

    with pytest.raises(InsufficientCreditsError) as exc_info:
        await reserve_credits(
            user_id=uuid.uuid4(),
            amount=20,
            reference_id=uuid.uuid4(),
            http=mock_http,
        )
    assert exc_info.value.balance == 5
    assert exc_info.value.requested == 20


@pytest.mark.asyncio
async def test_commit_reservation():
    mock_resp = AsyncMock()
    mock_resp.status_code = 204
    mock_resp.raise_for_status = AsyncMock()

    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=mock_resp)

    reservation_id = uuid.uuid4()
    await commit_reservation(reservation_id, mock_http)
    mock_http.post.assert_awaited_once()
    call_kwargs = mock_http.post.call_args
    assert str(reservation_id) in str(call_kwargs)


@pytest.mark.asyncio
async def test_release_reservation_on_failure():
    """Verify release is called with correct reason on failure."""
    mock_resp = AsyncMock()
    mock_resp.status_code = 204
    mock_resp.raise_for_status = AsyncMock()

    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=mock_resp)

    reservation_id = uuid.uuid4()
    await release_reservation(reservation_id, "replicate_failed", mock_http)
    mock_http.post.assert_awaited_once()
    call_json = mock_http.post.call_args.kwargs.get("json", {})
    assert call_json.get("reason") == "replicate_failed"
    assert call_json.get("reservation_id") == str(reservation_id)


@pytest.mark.asyncio
async def test_release_swallows_500():
    """release_reservation must not raise even if billing-svc returns 500."""
    mock_resp = AsyncMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"
    mock_resp.raise_for_status = AsyncMock()

    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=mock_resp)

    # Should not raise
    await release_reservation(uuid.uuid4(), "test_reason", mock_http)
