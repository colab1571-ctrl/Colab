"""
matching-svc tests — affinity matrix lookup.

Tests:
  - Matrix bounds (all cells in [0.0, 1.0])
  - Diagonal = 0.50 for all categories
  - Film/Video ↔ Music = 0.95
  - Design ↔ Digital/Tech = 0.90
  - Multi-vocation: max over all pairs
  - Redis cache warm / fetch / invalidation
  - affinity.py comp_voc_score_sync matches ranking.comp_voc_score
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.ranking import (
    AFFINITY_SEED,
    VOCATION_CATEGORIES,
    comp_voc_score,
)
from app.services.affinity import (
    comp_voc_score_sync,
    warm_matrix_cache,
    get_matrix,
    get_affinity_value,
    invalidate_matrix_cache,
)


# ---------------------------------------------------------------------------
# Seed matrix integrity
# ---------------------------------------------------------------------------

class TestAffinityMatrixIntegrity:
    def test_all_categories_present(self):
        for cat in VOCATION_CATEGORIES:
            assert cat in AFFINITY_SEED, f"Missing category: {cat}"

    def test_all_cells_bounded_0_to_1(self):
        for cat_a in VOCATION_CATEGORIES:
            for cat_b in VOCATION_CATEGORIES:
                val = AFFINITY_SEED[cat_a][cat_b]
                assert 0.0 <= val <= 1.0, (
                    f"Out of bounds: {cat_a} → {cat_b} = {val}"
                )

    def test_diagonal_is_0_50(self):
        """Same-category affinity = 0.50 (modest; not hero case)."""
        for cat in VOCATION_CATEGORIES:
            val = AFFINITY_SEED[cat][cat]
            assert val == 0.50, f"Diagonal {cat} expected 0.50 got {val}"

    def test_film_music_is_0_95(self):
        """Film/Video ↔ Music is 0.95 — canonical collab pair."""
        assert AFFINITY_SEED["Film/Video"]["Music"] == 0.95
        assert AFFINITY_SEED["Music"]["Film/Video"] == 0.95

    def test_design_digital_is_0_90(self):
        """Design ↔ Digital/Tech is 0.90."""
        assert AFFINITY_SEED["Design"]["Digital/Tech"] == 0.90
        assert AFFINITY_SEED["Digital/Tech"]["Design"] == 0.90

    def test_matrix_size_9x9(self):
        assert len(AFFINITY_SEED) == 9
        for cat, row in AFFINITY_SEED.items():
            assert len(row) == 9, f"Row {cat} has {len(row)} cells, expected 9"


# ---------------------------------------------------------------------------
# comp_voc_score function
# ---------------------------------------------------------------------------

class TestCompVocScore:
    def test_single_vocation_lookup(self):
        score = comp_voc_score(["Film/Video"], ["Music"])
        assert score == 0.95

    def test_same_vocation_moderate(self):
        score = comp_voc_score(["Music"], ["Music"])
        assert score == 0.50

    def test_multi_vocation_max(self):
        """Multi-vocation: take max across all pairs."""
        # Film/Video ↔ Music = 0.95, Visual Arts ↔ Music = 0.55
        # Max = 0.95
        score = comp_voc_score(["Film/Video", "Visual Arts"], ["Music"])
        assert score == 0.95

    def test_multi_vocation_candidate_max(self):
        """Candidate multi-vocation: rewards cross-disciplinary candidates."""
        # Film/Video ↔ Music = 0.95, Film/Video ↔ Craft & Maker = 0.40
        # Max = 0.95
        score = comp_voc_score(["Film/Video"], ["Craft & Maker", "Music"])
        assert score == 0.95

    def test_unknown_vocation_defaults_to_0_50(self):
        score = comp_voc_score(["Film/Video"], ["Unknown Vocation"])
        assert score == 0.50

    def test_empty_viewer_defaults_to_0_50(self):
        score = comp_voc_score([], ["Music"])
        assert score == 0.50

    def test_empty_candidate_defaults_to_0_50(self):
        score = comp_voc_score(["Film/Video"], [])
        assert score == 0.50

    def test_custom_matrix(self):
        custom = {"A": {"B": 0.99}, "B": {"A": 0.99}}
        score = comp_voc_score(["A"], ["B"], matrix=custom)
        assert score == 0.99

    def test_affinity_sync_matches_ranking_module(self):
        """affinity.comp_voc_score_sync must match ranking.comp_voc_score."""
        for cat_a in VOCATION_CATEGORIES:
            for cat_b in VOCATION_CATEGORIES:
                expected = comp_voc_score([cat_a], [cat_b])
                actual = comp_voc_score_sync([cat_a], [cat_b])
                assert abs(actual - expected) < 1e-9, (
                    f"Mismatch {cat_a}→{cat_b}: {expected} vs {actual}"
                )


# ---------------------------------------------------------------------------
# Redis cache tests
# ---------------------------------------------------------------------------

class TestAffinityRedisCache:
    @pytest.mark.asyncio
    async def test_warm_matrix_cache_writes_cells_and_blob(self):
        mock_redis = AsyncMock()
        mock_pipe = AsyncMock()
        mock_pipe.set = AsyncMock()
        mock_pipe.execute = AsyncMock(return_value=[True] * (81 + 1))
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        with patch("app.services.affinity._get_redis", return_value=mock_redis):
            await warm_matrix_cache(AFFINITY_SEED)

        # Should write 9×9 = 81 cells + 1 blob = 82 set calls
        assert mock_pipe.set.call_count == 82

    @pytest.mark.asyncio
    async def test_get_matrix_returns_cached_blob(self):
        cached_json = json.dumps(AFFINITY_SEED)
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=cached_json)

        with patch("app.services.affinity._get_redis", return_value=mock_redis):
            matrix = await get_matrix()

        assert matrix["Film/Video"]["Music"] == 0.95

    @pytest.mark.asyncio
    async def test_get_matrix_fallback_to_seed(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch("app.services.affinity._get_redis", return_value=mock_redis):
            matrix = await get_matrix()

        assert matrix is AFFINITY_SEED

    @pytest.mark.asyncio
    async def test_get_affinity_value_from_redis_cell(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="0.95")

        with patch("app.services.affinity._get_redis", return_value=mock_redis):
            val = await get_affinity_value("Film/Video", "Music")

        assert val == 0.95

    @pytest.mark.asyncio
    async def test_get_affinity_value_fallback_to_seed(self):
        mock_redis = AsyncMock()
        # Both cell key and blob key miss
        mock_redis.get = AsyncMock(return_value=None)

        with patch("app.services.affinity._get_redis", return_value=mock_redis):
            val = await get_affinity_value("Film/Video", "Music")

        # Falls back to seed
        assert val == 0.95

    @pytest.mark.asyncio
    async def test_invalidate_matrix_cache(self):
        mock_redis = AsyncMock()
        mock_redis.scan_iter = AsyncMock()

        async def _scan(*args, **kwargs):
            yield "vocation_affinity:Film/Video:Music"
            yield "vocation_affinity:Music:Film/Video"

        mock_redis.scan_iter.side_effect = _scan
        mock_redis.delete = AsyncMock(return_value=2)

        with patch("app.services.affinity._get_redis", return_value=mock_redis):
            await invalidate_matrix_cache()

        # delete called once with the 2 cell keys + once for blob key
        assert mock_redis.delete.call_count == 2


# ---------------------------------------------------------------------------
# Helpers missing from top-level import
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock
