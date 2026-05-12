"""
Tests: AI review risk aggregation + routing decisions.
Run: pytest tests/integration/test_ai_review_routing.py -q
"""

import pytest

from app.services.ai_review import (
    aggregate_risk,
    compute_phash_dup_signal,
    routing_decision,
)


class TestRiskAggregation:
    def test_all_zero_inputs(self):
        score = aggregate_risk(0.0, 0.0, 0.0, 0.0)
        assert score == pytest.approx(0.0)

    def test_max_all_inputs(self):
        score = aggregate_risk(1.0, 1.0, 1.0, 1.0)
        assert score == pytest.approx(1.0)

    def test_weights_sum(self):
        """Weights 0.35 + 0.35 + 0.20 + 0.10 = 1.0."""
        score = aggregate_risk(1.0, 1.0, 1.0, 1.0, 0.35, 0.35, 0.20, 0.10)
        assert score == pytest.approx(1.0)

    def test_only_openai_contribution(self):
        score = aggregate_risk(0.5, 0.0, 0.0, 0.0, 0.35, 0.35, 0.20, 0.10)
        assert score == pytest.approx(0.35 * 0.5)


class TestRoutingDecision:
    def test_below_threshold_auto_allow(self):
        d = routing_decision(0.0)
        assert d["action"] == "auto_allow"
        assert d["sla_hours"] is None

    def test_039_auto_allow(self):
        assert routing_decision(0.39)["action"] == "auto_allow"

    def test_040_soft_warn(self):
        d = routing_decision(0.40)
        assert d["action"] == "soft_warn"
        assert d["sla_hours"] == 24
        assert d["queue_priority"] == "MEDIUM"

    def test_069_soft_warn(self):
        assert routing_decision(0.69)["action"] == "soft_warn"

    def test_070_hide_content(self):
        d = routing_decision(0.70)
        assert d["action"] == "hide_content"
        assert d["sla_hours"] == 6
        assert d["queue_priority"] == "HIGH"

    def test_089_hide_content(self):
        assert routing_decision(0.89)["action"] == "hide_content"

    def test_090_auto_hide_temp_mute(self):
        d = routing_decision(0.90)
        assert d["action"] == "auto_hide_temp_mute"
        assert d["sla_hours"] == 1
        assert d["queue_priority"] == "URGENT"

    def test_always_human_overrides_score(self):
        d = routing_decision(0.10, always_human=True)
        assert d["action"] == "human_queue"
        assert d["queue_priority"] == "HIGH"
        assert d["sla_hours"] == 1


class TestPHashDupSignal:
    def test_identical_hashes_are_dup(self):
        phash = 0b1010101010101010
        signal = compute_phash_dup_signal(phash, None, [(phash, None)])
        assert signal == 1.0

    def test_hamming_distance_5_is_dup(self):
        base = 0b0000000000000000
        # Flip 5 bits
        other = base ^ ((1 << 5) - 1)
        signal = compute_phash_dup_signal(other, None, [(base, None)])
        assert signal == 1.0  # Hamming distance 5 ≤ threshold 6

    def test_hamming_distance_7_is_not_dup(self):
        base = 0b0000000000000000
        # Flip 7 bits
        other = base ^ ((1 << 7) - 1)
        signal = compute_phash_dup_signal(other, None, [(base, None)])
        assert signal == 0.0  # 7 > 6 threshold

    def test_no_hashes_no_signal(self):
        signal = compute_phash_dup_signal(None, None, [])
        assert signal == 0.0

    def test_empty_existing_no_dup(self):
        signal = compute_phash_dup_signal(12345, 67890, [])
        assert signal == 0.0
