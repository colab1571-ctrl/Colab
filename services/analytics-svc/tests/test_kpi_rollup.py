"""
analytics-svc — KPI rollup SQL correctness tests.

Tests verify:
1. rollup_day returns status dicts with expected keys
2. All 7 metrics are attempted
3. Backfill iterates correctly over date range
4. Individual metric functions call _upsert_rollup with correct keys
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from unittest.mock import MagicMock, call, patch

import pytest

from app.tasks.rollup import (
    rollup_day,
    _run_onboarding_completion,
    _run_dau_split,
    _run_profile_health_dist,
    _run_request_ratio,
    _run_collab_feedback,
    _run_support_csat,
    _run_pct_reported,
    _upsert_rollup,
)

TODAY = date(2026, 5, 10)


class TestUpsertRollup:
    def test_upsert_rollup_executes_query(self):
        conn = MagicMock()
        _upsert_rollup(conn, TODAY, "test_metric", {"dim": "a"}, 0.42, 100)
        assert conn.execute.called
        call_args = conn.execute.call_args
        params = call_args[0][1]
        assert params["day"] == TODAY
        assert params["key"] == "test_metric"
        assert json.loads(params["dims"]) == {"dim": "a"}
        assert params["value"] == 0.42
        assert params["count_n"] == 100


class TestOnboardingCompletion:
    def test_calls_upsert_for_each_step(self):
        conn = MagicMock()
        # Mock query returning rows for known steps
        mock_rows = [
            MagicMock(step="signup", value=1.0, count_n=100),
            MagicMock(step="verify_email", value=0.9, count_n=90),
            MagicMock(step="badge", value=0.5, count_n=50),
        ]
        conn.execute.return_value = mock_rows

        with patch("app.tasks.rollup._upsert_rollup") as mock_upsert:
            _run_onboarding_completion(conn, TODAY)

        assert mock_upsert.call_count == 3
        keys_seen = {c.args[2] for c in mock_upsert.call_args_list}
        assert "onboarding_completion" in keys_seen


class TestDauSplit:
    def test_produces_new_and_existing_dims(self):
        conn = MagicMock()
        conn.execute.return_value = [
            MagicMock(segment="new", value=100, count_n=100),
            MagicMock(segment="existing", value=900, count_n=900),
        ]
        with patch("app.tasks.rollup._upsert_rollup") as mock_upsert:
            _run_dau_split(conn, TODAY)
        assert mock_upsert.call_count == 2
        dims_seen = [c.args[3] for c in mock_upsert.call_args_list]
        assert {"segment": "new"} in dims_seen
        assert {"segment": "existing"} in dims_seen


class TestPctReported:
    def test_pct_reported_calculates_ratio(self):
        conn = MagicMock()
        row = MagicMock(reported_n=50, dau_n=1000)
        conn.execute.return_value.one.return_value = row

        with patch("app.tasks.rollup._upsert_rollup") as mock_upsert:
            _run_pct_reported(conn, TODAY)

        mock_upsert.assert_called_once()
        args = mock_upsert.call_args.args
        assert args[3] == {}  # dims = {}
        assert abs(args[4] - 0.05) < 0.001  # 50/1000 = 0.05

    def test_pct_reported_zero_dau(self):
        """Should not divide by zero when DAU is 0."""
        conn = MagicMock()
        row = MagicMock(reported_n=0, dau_n=0)
        conn.execute.return_value.one.return_value = row

        with patch("app.tasks.rollup._upsert_rollup") as mock_upsert:
            _run_pct_reported(conn, TODAY)

        args = mock_upsert.call_args.args
        assert args[4] is None  # value = None when dau=0


class TestRollupDay:
    def test_all_7_metrics_attempted(self):
        """rollup_day should attempt all 7 metrics and return status for each."""
        with patch("app.tasks.rollup._get_sync_engine") as mock_engine:
            conn = MagicMock()
            mock_engine.return_value.begin.return_value.__enter__ = MagicMock(return_value=conn)
            mock_engine.return_value.begin.return_value.__exit__ = MagicMock(return_value=False)

            with patch("app.tasks.rollup._run_onboarding_completion"):
                with patch("app.tasks.rollup._run_dau_split"):
                    with patch("app.tasks.rollup._run_profile_health_dist"):
                        with patch("app.tasks.rollup._run_request_ratio"):
                            with patch("app.tasks.rollup._run_collab_feedback"):
                                with patch("app.tasks.rollup._run_support_csat"):
                                    with patch("app.tasks.rollup._run_pct_reported"):
                                        result = rollup_day(TODAY)

        expected_keys = {
            "onboarding_completion",
            "dau_split",
            "profile_health_dist",
            "request_ratio",
            "collab_feedback",
            "support_csat",
            "pct_reported",
        }
        assert set(result.keys()) == expected_keys

    def test_one_metric_failure_does_not_abort_others(self):
        """A failure in one metric should be logged but not abort others."""
        with patch("app.tasks.rollup._get_sync_engine") as mock_engine:
            conn = MagicMock()
            mock_engine.return_value.begin.return_value.__enter__ = MagicMock(return_value=conn)
            mock_engine.return_value.begin.return_value.__exit__ = MagicMock(return_value=False)

            call_tracker: list[str] = []

            def good_fn(c, d):
                call_tracker.append("called")

            def bad_fn(c, d):
                raise RuntimeError("simulated DB failure")

            patches = [
                patch("app.tasks.rollup._run_onboarding_completion", side_effect=bad_fn),
                patch("app.tasks.rollup._run_dau_split", side_effect=good_fn),
                patch("app.tasks.rollup._run_profile_health_dist", side_effect=good_fn),
                patch("app.tasks.rollup._run_request_ratio", side_effect=good_fn),
                patch("app.tasks.rollup._run_collab_feedback", side_effect=good_fn),
                patch("app.tasks.rollup._run_support_csat", side_effect=good_fn),
                patch("app.tasks.rollup._run_pct_reported", side_effect=good_fn),
            ]

            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
                result = rollup_day(TODAY)

        assert "error" in result["onboarding_completion"]
        assert result["dau_split"] == "ok"
        assert len(call_tracker) == 6  # 6 good ones called


class TestBackfill:
    def test_backfill_iterates_date_range(self):
        from app.tasks.rollup import backfill

        with patch("app.tasks.rollup.rollup_day") as mock_rollup:
            mock_rollup.return_value = {"onboarding_completion": "ok"}
            # Simulate Celery task call without actual Celery
            result = backfill.__wrapped__("2026-01-01", "2026-01-03")

        assert mock_rollup.call_count == 3
        dates_called = [str(c.args[0]) for c in mock_rollup.call_args_list]
        assert "2026-01-01" in dates_called
        assert "2026-01-02" in dates_called
        assert "2026-01-03" in dates_called
