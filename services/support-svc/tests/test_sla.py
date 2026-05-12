"""
Tests for SLA computation and timer breach logic.

Covers:
- SLA values per category (free vs premium_pro)
- Pro tier ack halving (exactly)
- Breach detection in sla_scan task (mocked DB)
- SLA pause/resume accounting
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from app.sla import SLA_MAP, adjusted_due, compute_sla_due


# ---------------------------------------------------------------------------
# Unit tests for compute_sla_due
# ---------------------------------------------------------------------------


class TestComputeSlaDue:
    def _ts(self, **kwargs) -> datetime:
        return datetime(2026, 5, 11, 10, 0, 0, tzinfo=timezone.utc)

    @pytest.mark.parametrize(
        "category,tier,expected_ack_h,expected_resolve_h",
        [
            ("harassment_threats", "free", 4, 24),
            ("ip_dmca", "free", 24, 168),
            ("payment", "free", 24, 72),
            ("technical", "free", 24, 120),
            ("other", "free", 48, 168),
            # Premium Pro: ack halved
            ("harassment_threats", "premium_pro", 2, 24),
            ("ip_dmca", "premium_pro", 12, 168),
            ("payment", "premium_pro", 12, 72),
            ("technical", "premium_pro", 12, 120),
            ("other", "premium_pro", 24, 168),
            # Regular premium: same as free
            ("payment", "premium", 24, 72),
        ],
    )
    def test_sla_values(
        self,
        category: str,
        tier: str,
        expected_ack_h: int,
        expected_resolve_h: int,
    ) -> None:
        now = self._ts()
        ack_due, resolve_due = compute_sla_due(category, tier, now)

        assert ack_due == now + timedelta(hours=expected_ack_h), (
            f"{category}/{tier} ack: expected +{expected_ack_h}h"
        )
        assert resolve_due == now + timedelta(hours=expected_resolve_h), (
            f"{category}/{tier} resolve: expected +{expected_resolve_h}h"
        )

    def test_pro_ack_exactly_halved(self) -> None:
        """Pro ack must be exactly half the free ack (integer division, per spec §5.2)."""
        now = datetime(2026, 5, 11, 0, 0, 0, tzinfo=timezone.utc)
        for category, (ack_h, _) in SLA_MAP.items():
            free_ack, _ = compute_sla_due(category, "free", now)
            pro_ack, _ = compute_sla_due(category, "premium_pro", now)
            expected_pro_h = ack_h // 2
            assert pro_ack == now + timedelta(hours=expected_pro_h), (
                f"{category}: pro ack should be {expected_pro_h}h"
            )

    def test_unknown_category_defaults(self) -> None:
        """Unknown categories fall back to 'other' SLA."""
        now = datetime(2026, 5, 11, 0, 0, 0, tzinfo=timezone.utc)
        ack_due, resolve_due = compute_sla_due("unknown_cat", "free", now)
        # Falls back to (48, 168)
        assert ack_due == now + timedelta(hours=48)
        assert resolve_due == now + timedelta(hours=168)

    def test_default_created_at_is_now(self) -> None:
        before = datetime.now(tz=timezone.utc)
        ack_due, _ = compute_sla_due("payment", "free")
        after = datetime.now(tz=timezone.utc)
        assert before + timedelta(hours=24) <= ack_due <= after + timedelta(hours=24)


class TestAdjustedDue:
    def test_no_pause(self) -> None:
        due = datetime(2026, 5, 11, 10, 0, 0, tzinfo=timezone.utc)
        assert adjusted_due(due, 0) == due

    def test_with_pause(self) -> None:
        due = datetime(2026, 5, 11, 10, 0, 0, tzinfo=timezone.utc)
        result = adjusted_due(due, 3600)  # 1 hour paused
        assert result == due + timedelta(hours=1)


# ---------------------------------------------------------------------------
# SLA scan task tests (sync, mocked DB engine)
# ---------------------------------------------------------------------------


class TestSlaScanTask:
    """
    Tests for the sla_scan Celery task.
    Uses patch to avoid real DB/RabbitMQ connections.
    """

    def _make_row(
        self,
        ticket_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        category: str = "payment",
    ) -> MagicMock:
        row = MagicMock()
        row.id = ticket_id or uuid.uuid4()
        row.user_id = user_id or uuid.uuid4()
        row.category = category
        return row

    @patch("app.workers.sla_tasks._emit_sync")
    @patch("app.workers.sla_tasks.create_engine")
    def test_ack_breach_detected(self, mock_engine_cls, mock_emit) -> None:
        """
        Tickets past sla_ack_due with no first_response_at should trigger
        sla_breach events and support.sla.ack_breached emissions.
        """
        row = self._make_row()

        mock_engine = MagicMock()
        mock_engine_cls.return_value = mock_engine

        mock_sess = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_sess)

        # Make Session context manager work
        mock_session_ctx = MagicMock()
        mock_session_ctx.__enter__ = MagicMock(return_value=mock_sess)
        mock_session_ctx.__exit__ = MagicMock(return_value=False)

        ack_result = MagicMock()
        ack_result.fetchall.return_value = [row]
        resolve_result = MagicMock()
        resolve_result.fetchall.return_value = []

        # First execute → ack rows, second → resolve rows
        mock_sess.execute.side_effect = [ack_result, MagicMock(), MagicMock(), resolve_result]

        with patch("app.workers.sla_tasks.Session", return_value=mock_session_ctx):
            from app.workers.sla_tasks import sla_scan
            result = sla_scan()

        assert result["ack_breached"] == 1
        assert result["resolve_breached"] == 0
        mock_emit.assert_called_with(
            "support.sla.ack_breached",
            {
                "ticket_id": str(row.id),
                "user_id": str(row.user_id),
                "category": row.category,
            },
        )

    @patch("app.workers.sla_tasks._emit_sync")
    @patch("app.workers.sla_tasks.create_engine")
    def test_resolve_breach_detected(self, mock_engine_cls, mock_emit) -> None:
        """
        Tickets past sla_resolve_due with no resolved_at should trigger
        sla_resolve_breached events.
        """
        row = self._make_row(category="ip_dmca")

        mock_engine = MagicMock()
        mock_engine_cls.return_value = mock_engine

        mock_sess = MagicMock()
        mock_session_ctx = MagicMock()
        mock_session_ctx.__enter__ = MagicMock(return_value=mock_sess)
        mock_session_ctx.__exit__ = MagicMock(return_value=False)

        ack_result = MagicMock()
        ack_result.fetchall.return_value = []
        resolve_result = MagicMock()
        resolve_result.fetchall.return_value = [row]

        mock_sess.execute.side_effect = [ack_result, resolve_result, MagicMock(), MagicMock()]

        with patch("app.workers.sla_tasks.Session", return_value=mock_session_ctx):
            from app.workers.sla_tasks import sla_scan
            result = sla_scan()

        assert result["ack_breached"] == 0
        assert result["resolve_breached"] == 1
        mock_emit.assert_called_with(
            "support.sla.resolve_breached",
            {
                "ticket_id": str(row.id),
                "user_id": str(row.user_id),
                "category": row.category,
            },
        )

    @patch("app.workers.sla_tasks._emit_sync")
    @patch("app.workers.sla_tasks.create_engine")
    def test_no_breaches_returns_zeros(self, mock_engine_cls, mock_emit) -> None:
        """Empty result set → no events, no errors."""
        mock_engine = MagicMock()
        mock_engine_cls.return_value = mock_engine

        mock_sess = MagicMock()
        mock_session_ctx = MagicMock()
        mock_session_ctx.__enter__ = MagicMock(return_value=mock_sess)
        mock_session_ctx.__exit__ = MagicMock(return_value=False)

        empty_result = MagicMock()
        empty_result.fetchall.return_value = []
        mock_sess.execute.return_value = empty_result

        with patch("app.workers.sla_tasks.Session", return_value=mock_session_ctx):
            from app.workers.sla_tasks import sla_scan
            result = sla_scan()

        assert result == {"ack_breached": 0, "resolve_breached": 0}
        mock_emit.assert_not_called()
