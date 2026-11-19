"""Unit tests for src/stage3_variant_tox/phylop_scorer.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.core.models import GenomicRegion, PhylopResult
from src.stage3_variant_tox.phylop_scorer import (
    _get_conservation_score,
    _normalize_phylop,
    _score_region,
    score_phylop,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BIGWIG_URL = "https://hgdownload.soe.ucsc.edu/goldenPath/hg38/phyloP100way/hg38.phyloP100way.bw"

REGION_CHR1 = GenomicRegion(chrom="chr1", start=65_790, end=65_810, strand="+")
REGION_CHR17 = GenomicRegion(chrom="chr17", start=7_668_400, end=7_668_500, strand="-")
REGION_CHRX = GenomicRegion(chrom="chrX", start=50_000, end=51_000, strand=".")


def _make_bw(stats_value: float | None) -> MagicMock:
    """Create a mock pyBigWig handle that returns stats_value."""
    bw = MagicMock()
    bw.stats.return_value = [stats_value]
    return bw


def _mock_cache(hit: dict | None = None) -> MagicMock:
    cache = MagicMock()
    cache.get.return_value = hit
    return cache


# ---------------------------------------------------------------------------
# _normalize_phylop
# ---------------------------------------------------------------------------


class TestNormalizePhylop:
    def test_negative_score_gives_zero(self) -> None:
        assert _normalize_phylop(-5.0) == pytest.approx(0.0)

    def test_zero_score_gives_zero(self) -> None:
        assert _normalize_phylop(0.0) == pytest.approx(0.0)

    def test_score_at_saturation_gives_one(self) -> None:
        # _PHYLOP_SATURATION = 4.0
        assert _normalize_phylop(4.0) == pytest.approx(1.0)

    def test_score_above_saturation_capped_at_one(self) -> None:
        assert _normalize_phylop(10.0) == pytest.approx(1.0)
        assert _normalize_phylop(30.0) == pytest.approx(1.0)

    def test_score_at_2_gives_half(self) -> None:
        # 2.0 / 4.0 = 0.5 — the user-defined "high conservation" threshold
        assert _normalize_phylop(2.0) == pytest.approx(0.5)

    def test_score_at_1_gives_quarter(self) -> None:
        assert _normalize_phylop(1.0) == pytest.approx(0.25)

    def test_midpoint_of_range(self) -> None:
        assert _normalize_phylop(2.0) == pytest.approx(0.5)

    def test_output_always_in_unit_interval(self) -> None:
        for raw in [-20.0, -1.0, 0.0, 1.0, 2.0, 4.0, 8.0, 30.0]:
            assert 0.0 <= _normalize_phylop(raw) <= 1.0

    def test_slightly_negative_gives_zero(self) -> None:
        assert _normalize_phylop(-0.001) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _get_conservation_score
# ---------------------------------------------------------------------------


class TestGetConservationScore:
    def test_positive_score_returned(self) -> None:
        bw = _make_bw(3.5)
        score = _get_conservation_score(bw, "chr1", 65_790, 65_810)
        assert score == pytest.approx(3.5)
        bw.stats.assert_called_once_with("chr1", 65_790, 65_810, type="mean")

    def test_negative_score_returned(self) -> None:
        bw = _make_bw(-2.1)
        assert _get_conservation_score(bw, "chr1", 0, 100) == pytest.approx(-2.1)

    def test_none_value_returns_neutral(self) -> None:
        bw = _make_bw(None)
        assert _get_conservation_score(bw, "chr1", 0, 100) == pytest.approx(0.0)

    def test_empty_stats_list_returns_neutral(self) -> None:
        bw = MagicMock()
        bw.stats.return_value = []
        assert _get_conservation_score(bw, "chr1", 0, 100) == pytest.approx(0.0)

    def test_exception_returns_neutral(self) -> None:
        bw = MagicMock()
        bw.stats.side_effect = RuntimeError("BigWig read error")
        assert _get_conservation_score(bw, "chr1", 0, 100) == pytest.approx(0.0)

    def test_passes_chr_prefix_to_bigwig(self) -> None:
        bw = _make_bw(1.0)
        _get_conservation_score(bw, "chr17", 7_668_400, 7_668_500)
        bw.stats.assert_called_once_with("chr17", 7_668_400, 7_668_500, type="mean")


# ---------------------------------------------------------------------------
# _score_region
# ---------------------------------------------------------------------------


class TestScoreRegion:
    def test_high_conservation_score(self) -> None:
        bw = _make_bw(5.0)  # 5.0 / 4.0 → capped at 1.0
        cache = _mock_cache(hit=None)
        result = _score_region(bw, REGION_CHR1, cache)
        assert result.mean_score == pytest.approx(5.0)
        assert result.conservation_score == pytest.approx(1.0)

    def test_fast_evolving_score_zero(self) -> None:
        bw = _make_bw(-3.0)
        cache = _mock_cache(hit=None)
        result = _score_region(bw, REGION_CHR1, cache)
        assert result.mean_score == pytest.approx(-3.0)
        assert result.conservation_score == pytest.approx(0.0)

    def test_cache_hit_skips_bigwig(self) -> None:
        bw = _make_bw(9.0)
        cache = _mock_cache(hit={"mean_score": 2.0, "conservation_score": 0.5})
        result = _score_region(bw, REGION_CHR1, cache)
        assert result.mean_score == pytest.approx(2.0)
        assert result.conservation_score == pytest.approx(0.5)
        bw.stats.assert_not_called()

    def test_cache_set_on_miss(self) -> None:
        bw = _make_bw(2.0)
        cache = _mock_cache(hit=None)
        _score_region(bw, REGION_CHR1, cache)
        cache.set.assert_called_once()
        key = cache.set.call_args[0][0]
        assert "phylop" in key
        assert "chr1" in key

    def test_returns_phylop_result_instance(self) -> None:
        bw = _make_bw(1.5)
        cache = _mock_cache(hit=None)
        result = _score_region(bw, REGION_CHR17, cache)
        assert isinstance(result, PhylopResult)
        assert result.region == REGION_CHR17


# ---------------------------------------------------------------------------
# score_phylop — top-level
# ---------------------------------------------------------------------------


class TestScorePhylop:
    @patch("src.stage3_variant_tox.phylop_scorer.Cache")
    @patch("src.stage3_variant_tox.phylop_scorer.pyBigWig.open")
    def test_single_region_high_conservation(self, mock_open, MockCache) -> None:
        mock_bw = _make_bw(6.0)  # > saturation → score = 1.0
        mock_open.return_value = mock_bw
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        results = score_phylop([REGION_CHR1], BIGWIG_URL)
        assert len(results) == 1
        assert results[0].conservation_score == pytest.approx(1.0)

    @patch("src.stage3_variant_tox.phylop_scorer.Cache")
    @patch("src.stage3_variant_tox.phylop_scorer.pyBigWig.open")
    def test_fast_evolving_region(self, mock_open, MockCache) -> None:
        mock_bw = _make_bw(-5.0)
        mock_open.return_value = mock_bw
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        results = score_phylop([REGION_CHR17], BIGWIG_URL)
        assert results[0].conservation_score == pytest.approx(0.0)

    @patch("src.stage3_variant_tox.phylop_scorer.Cache")
    @patch("src.stage3_variant_tox.phylop_scorer.pyBigWig.open")
    def test_no_coverage_gives_neutral(self, mock_open, MockCache) -> None:
        mock_bw = _make_bw(None)
        mock_open.return_value = mock_bw
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        results = score_phylop([REGION_CHRX], BIGWIG_URL)
        assert results[0].mean_score == pytest.approx(0.0)
        assert results[0].conservation_score == pytest.approx(0.0)

    @patch("src.stage3_variant_tox.phylop_scorer.pyBigWig.open")
    def test_bigwig_open_failure_is_unknown(self, mock_open) -> None:
        mock_open.side_effect = OSError("connection refused")
        results = score_phylop([REGION_CHR1], BIGWIG_URL)
        assert len(results) == 1
        # Inverted 2026-11-19 (audit Bulgu 2/5). This asserted the
        # fallback *numbers*, pinning "a dead source reads as a measurement"
        # as the contract. The name said "returns neutral"; there is no
        # neutral value on a risk channel, only an unknown one.
        assert results[0].conservation_score is None
        assert results[0].mean_score is None

    @patch("src.stage3_variant_tox.phylop_scorer.pyBigWig.open")
    def test_empty_input_returns_empty_list(self, mock_open) -> None:
        results = score_phylop([], BIGWIG_URL)
        assert results == []
        mock_open.assert_not_called()

    @patch("src.stage3_variant_tox.phylop_scorer.Cache")
    @patch("src.stage3_variant_tox.phylop_scorer.pyBigWig.open")
    def test_bigwig_opened_once_for_multiple_regions(self, mock_open, MockCache) -> None:
        mock_bw = _make_bw(1.0)
        mock_open.return_value = mock_bw
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        score_phylop([REGION_CHR1, REGION_CHR17, REGION_CHRX], BIGWIG_URL)
        mock_open.assert_called_once()  # only one handle opened
        assert mock_bw.stats.call_count == 3

    @patch("src.stage3_variant_tox.phylop_scorer.Cache")
    @patch("src.stage3_variant_tox.phylop_scorer.pyBigWig.open")
    def test_preserves_input_order(self, mock_open, MockCache) -> None:
        # Different scores per region via side_effect
        mock_bw = MagicMock()
        mock_bw.stats.side_effect = [[4.0], [-1.0], [2.0]]
        mock_open.return_value = mock_bw
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        results = score_phylop([REGION_CHR1, REGION_CHR17, REGION_CHRX], BIGWIG_URL)
        assert len(results) == 3
        assert results[0].region == REGION_CHR1
        assert results[1].region == REGION_CHR17
        assert results[2].region == REGION_CHRX
        assert results[0].conservation_score == pytest.approx(1.0)   # 4.0/4.0
        assert results[1].conservation_score == pytest.approx(0.0)   # negative
        assert results[2].conservation_score == pytest.approx(0.5)   # 2.0/4.0

    @patch("src.stage3_variant_tox.phylop_scorer.Cache")
    @patch("src.stage3_variant_tox.phylop_scorer.pyBigWig.open")
    def test_returns_phylop_result_instances(self, mock_open, MockCache) -> None:
        mock_bw = _make_bw(1.0)
        mock_open.return_value = mock_bw
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        results = score_phylop([REGION_CHR1], BIGWIG_URL)
        assert all(isinstance(r, PhylopResult) for r in results)

    @patch("src.stage3_variant_tox.phylop_scorer.Cache")
    @patch("src.stage3_variant_tox.phylop_scorer.pyBigWig.open")
    def test_bigwig_closed_after_use(self, mock_open, MockCache) -> None:
        mock_bw = _make_bw(1.0)
        mock_open.return_value = mock_bw
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        score_phylop([REGION_CHR1], BIGWIG_URL)
        mock_bw.close.assert_called_once()

    @patch("src.stage3_variant_tox.phylop_scorer.Cache")
    @patch("src.stage3_variant_tox.phylop_scorer.pyBigWig.open")
    def test_bigwig_closed_even_on_exception(self, mock_open, MockCache) -> None:
        mock_bw = MagicMock()
        mock_bw.stats.side_effect = RuntimeError("unexpected error")
        mock_open.return_value = mock_bw
        mock_cache = _mock_cache(hit=None)
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        # Should not raise; graceful degradation returns neutral via _get_conservation_score
        results = score_phylop([REGION_CHR1], BIGWIG_URL)
        assert len(results) == 1
        mock_bw.close.assert_called_once()

    @patch("src.stage3_variant_tox.phylop_scorer.Cache")
    @patch("src.stage3_variant_tox.phylop_scorer.pyBigWig.open")
    def test_cache_hit_does_not_call_bigwig_stats(self, mock_open, MockCache) -> None:
        mock_bw = _make_bw(9.0)
        mock_open.return_value = mock_bw
        cached = {"mean_score": 3.0, "conservation_score": 0.75}
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=cached)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        results = score_phylop([REGION_CHR1], BIGWIG_URL)
        assert results[0].conservation_score == pytest.approx(0.75)
        mock_bw.stats.assert_not_called()
