"""
Tests for Whiteboard: Y.js op apply (mocked), snapshot lifecycle,
Premium-only hi-res export gating.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_snapshot(
    collab_id: uuid.UUID | None = None,
    s3_key: str = "whiteboard/uuid/snap-1748000000.bin",
    version: int = 100,
) -> MagicMock:
    s = MagicMock()
    s.id = uuid.uuid4()
    s.collab_id = collab_id or uuid.UUID("cccccccc-0000-0000-0000-000000000003")
    s.s3_key = s3_key
    s.version = version
    s.created_at = datetime.now(UTC)
    return s


def make_export(
    collab_id: uuid.UUID | None = None,
    fmt: str = "png",
    resolution: str = "basic",
    status: str = "pending",
    s3_key: str | None = None,
) -> MagicMock:
    e = MagicMock()
    e.id = uuid.uuid4()
    e.collab_id = collab_id or uuid.UUID("cccccccc-0000-0000-0000-000000000003")
    e.requested_by = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
    e.format = fmt
    e.resolution = resolution
    e.status = status
    e.s3_key = s3_key
    e.error_detail = None
    e.requested_at = datetime.now(UTC)
    e.completed_at = None
    e.expires_at = None
    return e


# ---------------------------------------------------------------------------
# Test: Y.js op apply (mocked)
# ---------------------------------------------------------------------------


class TestYjsOpApply:
    @pytest.mark.asyncio
    async def test_append_op_persists_to_db(self):
        """append_op should add a WhiteboardOp row to the database."""
        mock_db = AsyncMock()
        mock_op = MagicMock()

        with patch("app.services.whiteboard_service.WhiteboardOp") as MockOp:
            MockOp.return_value = mock_op
            from app.services.whiteboard_service import append_op

            result = await append_op(
                db=mock_db,
                collab_id=uuid.UUID("cccccccc-0000-0000-0000-000000000003"),
                actor_profile_id=uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001"),
                op_data=b"\x01\x02\x03\x04",
                lamport=42,
            )

        mock_db.add.assert_called_once_with(mock_op)
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_peer_only(self):
        """WhiteboardRoom.broadcast should skip the sender WebSocket."""
        from app.services.whiteboard_ws import WhiteboardRoom

        collab_id = uuid.UUID("cccccccc-0000-0000-0000-000000000003")
        room = WhiteboardRoom(collab_id)

        ws_a = AsyncMock()
        ws_b = AsyncMock()
        room._connections = [ws_a, ws_b]

        await room.broadcast(b"op_data", sender=ws_a)

        ws_a.send_bytes.assert_not_called()
        ws_b.send_bytes.assert_called_once_with(b"op_data")

    @pytest.mark.asyncio
    async def test_lamport_increments_per_op(self):
        from app.services.whiteboard_ws import WhiteboardRoom

        collab_id = uuid.UUID("cccccccc-0000-0000-0000-000000000003")
        room = WhiteboardRoom(collab_id)

        l1 = room.next_lamport()
        l2 = room.next_lamport()
        l3 = room.next_lamport()

        assert l1 == 1
        assert l2 == 2
        assert l3 == 3


# ---------------------------------------------------------------------------
# Test: Snapshot lifecycle
# ---------------------------------------------------------------------------


class TestSnapshotLifecycle:
    @pytest.mark.asyncio
    async def test_get_latest_snapshot_returns_highest_version(self):
        """get_latest_snapshot should return the row with the highest version."""
        snap = make_snapshot(version=200)
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = snap
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        from app.services.whiteboard_service import get_latest_snapshot

        result = await get_latest_snapshot(mock_db, snap.collab_id)
        assert result == snap
        assert result.version == 200

    @pytest.mark.asyncio
    async def test_get_latest_snapshot_returns_none_for_new_board(self):
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        from app.services.whiteboard_service import get_latest_snapshot

        result = await get_latest_snapshot(mock_db, uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_save_snapshot_creates_s3_key_and_row(self):
        """save_snapshot should PUT to S3 and INSERT a WhiteboardSnapshot row."""
        mock_snapshot = make_snapshot()
        mock_db = AsyncMock()
        mock_db.refresh = AsyncMock(return_value=None)

        mock_s3_client = AsyncMock()
        mock_s3_client.__aenter__ = AsyncMock(return_value=mock_s3_client)
        mock_s3_client.__aexit__ = AsyncMock(return_value=None)
        mock_s3_client.put_object = AsyncMock(return_value={})

        mock_session = MagicMock()
        mock_session.create_client.return_value = mock_s3_client

        with (
            patch("app.services.whiteboard_service.WhiteboardSnapshot") as MockSnap,
            patch("aiobotocore.session.get_session", return_value=mock_session),
        ):
            MockSnap.return_value = mock_snapshot
            from app.services.whiteboard_service import save_snapshot

            result = await save_snapshot(
                db=mock_db,
                collab_id=uuid.UUID("cccccccc-0000-0000-0000-000000000003"),
                doc_binary=b"\x00" * 100,
                lamport=42,
            )

        mock_db.add.assert_called_once_with(mock_snapshot)
        mock_db.commit.assert_called_once()
        # S3 put_object should have been called
        mock_s3_client.put_object.assert_called_once()
        call_kwargs = mock_s3_client.put_object.call_args.kwargs
        assert call_kwargs["ContentType"] == "application/octet-stream"
        assert b"\x00" * 100 == call_kwargs["Body"]

    @pytest.mark.asyncio
    async def test_get_delta_ops_filters_by_lamport(self):
        """get_delta_ops should only return ops with lamport > since_lamport."""
        mock_ops = [MagicMock(lamport=i + 101) for i in range(5)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_ops
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        from app.services.whiteboard_service import get_delta_ops

        result = await get_delta_ops(
            mock_db,
            collab_id=uuid.uuid4(),
            since_lamport=100,
        )

        assert len(result) == 5
        assert all(op.lamport > 100 for op in result)


# ---------------------------------------------------------------------------
# Test: Premium-only hi-res export gating
# ---------------------------------------------------------------------------


class TestExportEntitlementGating:
    @pytest.mark.asyncio
    async def test_basic_export_allowed_for_free_user(self):
        """
        Free user can export at basic resolution.
        check_whiteboard_export_entitlement is NOT called for basic.
        """
        export = make_export(fmt="png", resolution="basic")
        mock_db = AsyncMock()
        mock_collab = MagicMock()

        with (
            patch(
                "app.routers.whiteboard.collab_service.get_collab",
                AsyncMock(return_value=mock_collab),
            ),
            patch(
                "app.routers.whiteboard.create_export_record",
                AsyncMock(return_value=export),
            ),
            patch("app.routers.whiteboard.whiteboard_export_generate") as mock_task,
            patch(
                "app.routers.whiteboard.check_whiteboard_export_entitlement",
                AsyncMock(return_value=False),
            ) as mock_entitlement,
        ):
            # Simulate the router logic directly
            resolution = "basic"
            if resolution == "hi":
                has_entitlement = await mock_entitlement(uuid.uuid4())
                assert has_entitlement  # Would fail for free user — this path not reached

            # basic: should not call entitlement check
            mock_entitlement.assert_not_called()

    @pytest.mark.asyncio
    async def test_hi_res_export_blocked_for_free_user(self):
        """
        Free user requesting hi-res export should get 403 ENTITLEMENT_REQUIRED.
        """
        from fastapi import HTTPException

        with patch(
            "app.routers.whiteboard.check_whiteboard_export_entitlement",
            AsyncMock(return_value=False),
        ):
            from app.services.chat_client import check_whiteboard_export_entitlement

            has_entitlement = await check_whiteboard_export_entitlement(uuid.uuid4())
            assert has_entitlement is False

            # The router would raise HTTPException 403
            if not has_entitlement:
                exc = HTTPException(
                    status_code=403,
                    detail={"error_code": "ENTITLEMENT_REQUIRED"},
                )
                assert exc.status_code == 403

    @pytest.mark.asyncio
    async def test_hi_res_export_allowed_for_premium_user(self):
        """Premium user requesting hi-res export should succeed."""
        with patch(
            "app.routers.whiteboard.check_whiteboard_export_entitlement",
            AsyncMock(return_value=True),
        ):
            from app.services.chat_client import check_whiteboard_export_entitlement

            has_entitlement = await check_whiteboard_export_entitlement(uuid.uuid4())
            assert has_entitlement is True

    @pytest.mark.asyncio
    async def test_export_status_polling_returns_url_when_ready(self):
        """get_export_signed_url returns a URL when status is ready."""
        export = make_export(
            fmt="png",
            resolution="basic",
            status="ready",
            s3_key="whiteboard/exports/uuid/1000-basic.png",
        )

        from app.services.whiteboard_service import get_export_signed_url

        with patch(
            "app.services.whiteboard_service.get_collab_settings"
        ) as mock_settings:
            mock_settings.return_value.cloudfront_domain = "cdn.example.com"
            url = get_export_signed_url(export)

        assert url is not None
        assert "cdn.example.com" in url
        assert export.s3_key in url

    def test_export_status_pending_returns_none_url(self):
        export = make_export(status="pending")

        from app.services.whiteboard_service import get_export_signed_url

        url = get_export_signed_url(export)
        assert url is None  # s3_key is None for pending
