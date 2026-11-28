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
#: score_phylop now requires an explicit cache path — the hardcoded
#: default sent callers to the live database (audit 2026-11-19).
CACHE_DB = ":memory:"

REGION_CHR1 = GenomicRegion(chrom="chr1", start=65_790, end=65_810, strand="+")
REGION_CHR17 = GenomicRegion(chrom="chr17", start=7_668_400, end=7_668_500, strand="-")
REGION_CHRX = GenomicRegion(chrom="chrX", start=50_000, end=51_000, strand=".")


def _make_bw(
    stats_value: float | None, coverage: float | None = None
) -> MagicMock:
    """A mock pyBigWig handle, faithful to the live file's two stats types.

    Roadmap `R14`. This used to answer every `stats` call with the same value,
    which was fine while only ``type="mean"`` was asked for. Measured against
    hg38.phyloP100way.bw: a window with a mean also has a ``coverage`` in
    ``(0, 1]``, and a window with no mean has no coverage figure either. The
    default mirrors that, so a mock cannot report a coverage of 3.5.

    Args:
        stats_value: What ``type="mean"`` returns.
        coverage: What ``type="coverage"`` returns; defaults to 1.0 when there
            is a mean and ``None`` when there is not.

    Returns:
        The mock handle.
    """
    if coverage is None:
        coverage = 1.0 if stats_value is not None else None
    bw = MagicMock()
    bw.stats.side_effect = lambda *a, **kw: (
        [coverage] if kw.get("type") == "coverage" else [stats_value]
    )
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
        score, _ = _get_conservation_score(bw, "chr1", 65_790, 65_810)
        assert score == pytest.approx(3.5)
        # `R14` added a second `stats` call for coverage, so the mean is no
        # longer the only one; it is still the first.
        assert bw.stats.call_args_list[0].args == ("chr1", 65_790, 65_810)
        assert bw.stats.call_args_list[0].kwargs == {"type": "mean"}

    def test_negative_score_returned(self) -> None:
        bw = _make_bw(-2.1)
        mean, _ = _get_conservation_score(bw, "chr1", 0, 100)
        assert mean == pytest.approx(-2.1)

    # ⚠️ Roadmap R14 rewrote the three tests that used to live here —
    # `test_none_value_returns_neutral`, `test_empty_stats_list_returns_neutral`
    # and `test_exception_returns_neutral`, each asserting 0.0. They pinned the
    # defect rather than the behaviour: they are the shape of "917 tests green
    # while three known bugs were live". What replaces them is below.

    def test_passes_chr_prefix_to_bigwig(self) -> None:
        bw = _make_bw(1.0)
        _get_conservation_score(bw, "chr17", 7_668_400, 7_668_500)
        assert bw.stats.call_args_list[0].args == ("chr17", 7_668_400, 7_668_500)
        assert bw.stats.call_args_list[0].kwargs == {"type": "mean"}


class TestMissingAlignmentIsNotNeutrality:
    """Roadmap R14. A phyloP of 0 is a result; an absent phyloP is not.

    `_get_conservation_score` returned ``_NEUTRAL_MEAN_SCORE = 0.0`` both when
    the BigWig had no value for the window and when the read raised. `0.0`
    normalises to ``conservation_score = 0.0``, the **lowest** risk the channel
    can report, so a window the file does not cover looked maximally
    unconserved — the thing invariant 2 forbids, on the success path rather
    than the failure path.

    What made it indistinguishable is specific to this source. UCSC states
    that "Both phastCons and phyloP treat alignment gaps and unaligned
    nucleotides as missing data", and that "the absolute values of the scores
    represent -log p-values under a null hypothesis of neutral evolution"
    (hg38 cons100way track description). So **0 is a measurement** — p = 1, no
    detectable departure from neutrality — and a sentinel of 0.0 is a result
    nobody can tell from a real one.

    Measured against the live file (hg38.phyloP100way.bw, 2026-11-28):

    * a normal window returns a mean with ``coverage`` 1.0;
    * a centromeric or telomeric window returns ``stats`` of ``None`` with
      every base NaN — the file genuinely omits those positions, so there is
      no "contig present but silent" case here as there is for an ENCODE
      signal track;
    * a chromosome name without the ``chr`` prefix raises
      ``RuntimeError: Invalid interval bounds!`` — and so does an interval
      past the end of a contig, which is where `Bulgu-8`'s splice-blind
      coordinates land;
    * a window straddling the alignment boundary returns a mean over **part**
      of itself: chr1:121,609,785-121,609,805 gives mean 0.213 at
      ``coverage`` 0.6, and nothing recorded that.
    """

    def test_a_window_outside_the_alignment_is_unknown_not_zero(self) -> None:
        bw = _make_bw(None)
        mean, covered = _get_conservation_score(bw, "chr1", 0, 100)
        assert mean is None, (
            "an unaligned window reported phyloP 0.0, which normalises to the "
            "lowest risk the channel can express (invariant 2)"
        )
        assert covered == 0.0, (
            "zero covered bases should be recorded as such, so the reason for "
            "the unknown is in the record"
        )

    def test_an_empty_stats_list_is_unknown_not_zero(self) -> None:
        bw = MagicMock()
        bw.stats.return_value = []
        mean, _ = _get_conservation_score(bw, "chr1", 0, 100)
        assert mean is None

    def test_a_failed_read_is_unknown_not_zero(self) -> None:
        """The landing spot for a chr-prefix error and an out-of-range span."""
        bw = MagicMock()
        bw.stats.side_effect = RuntimeError("Invalid interval bounds!")
        mean, covered = _get_conservation_score(bw, "1", 0, 100)
        assert mean is None
        assert covered is None, (
            "a failed read knows nothing, not even how much was covered"
        )

    def test_a_measured_zero_survives(self) -> None:
        """The control. phyloP 0 means p = 1, which is a result.

        Without this, the fix could pass by turning every zero into None —
        which would delete real measurements of neutral evolution.
        """
        bw = _make_bw(0.0)
        mean, covered = _get_conservation_score(bw, "chr1", 0, 100)
        assert mean == 0.0
        assert mean is not None
        assert covered == pytest.approx(1.0)

    def test_a_measured_negative_survives(self) -> None:
        """Accelerated evolution is also a result, and it is negative."""
        bw = _make_bw(-2.1)
        mean, _ = _get_conservation_score(bw, "chr1", 0, 100)
        assert mean == pytest.approx(-2.1)

    def test_partial_coverage_is_recorded(self) -> None:
        """The straddling window measured on the live file."""
        bw = MagicMock()
        bw.stats.side_effect = lambda *a, **kw: (
            [0.21333333104848862] if kw.get("type") == "mean" else [0.6]
        )
        mean, covered = _get_conservation_score(
            bw, "chr1", 121_609_785, 121_609_805
        )
        assert mean == pytest.approx(0.2133, abs=1e-4)
        assert covered == pytest.approx(0.6), (
            "a mean over 60% of the window was reported as if fully measured"
        )


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

        results = score_phylop([REGION_CHR1], BIGWIG_URL, cache_db=CACHE_DB)
        assert len(results) == 1
        assert results[0].conservation_score == pytest.approx(1.0)

    @patch("src.stage3_variant_tox.phylop_scorer.Cache")
    @patch("src.stage3_variant_tox.phylop_scorer.pyBigWig.open")
    def test_fast_evolving_region(self, mock_open, MockCache) -> None:
        mock_bw = _make_bw(-5.0)
        mock_open.return_value = mock_bw
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        results = score_phylop([REGION_CHR17], BIGWIG_URL, cache_db=CACHE_DB)
        assert results[0].conservation_score == pytest.approx(0.0)

    @patch("src.stage3_variant_tox.phylop_scorer.Cache")
    @patch("src.stage3_variant_tox.phylop_scorer.pyBigWig.open")
    def test_no_coverage_is_unknown_end_to_end(self, mock_open, MockCache) -> None:
        """Roadmap R14. This test used to assert 0.0 for both fields.

        It pinned the defect: a region the alignment does not cover came back
        with the lowest conservation score the channel can emit, and the
        number was indistinguishable from a real phyloP of 0 (p = 1).
        """
        mock_bw = _make_bw(None)
        mock_open.return_value = mock_bw
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        results = score_phylop([REGION_CHRX], BIGWIG_URL, cache_db=CACHE_DB)
        assert results[0].mean_score is None
        assert results[0].conservation_score is None
        assert results[0].covered_fraction == 0.0

    @patch("src.stage3_variant_tox.phylop_scorer.Cache")
    @patch("src.stage3_variant_tox.phylop_scorer.pyBigWig.open")
    def test_an_unknown_is_not_written_to_the_cache(
        self, mock_open, MockCache
    ) -> None:
        """Caching an unknown would outlive the condition that caused it.

        Settled in `B2` and it applies here: the TTL is a week, so one bad
        read would keep answering for a week after the cause was gone.
        """
        mock_open.return_value = _make_bw(None)
        cache = _mock_cache(hit=None)
        MockCache.return_value.__enter__ = lambda s: cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        score_phylop([REGION_CHRX], BIGWIG_URL, cache_db=CACHE_DB)
        assert cache.set.call_count == 0, (
            f"an unknown was cached: {cache.set.call_args_list}"
        )

    @patch("src.stage3_variant_tox.phylop_scorer.Cache")
    @patch("src.stage3_variant_tox.phylop_scorer.pyBigWig.open")
    def test_a_measurement_is_still_cached(self, mock_open, MockCache) -> None:
        """The control for the test above: real values must still be cached."""
        mock_open.return_value = _make_bw(2.0)
        cache = _mock_cache(hit=None)
        MockCache.return_value.__enter__ = lambda s: cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        score_phylop([REGION_CHRX], BIGWIG_URL, cache_db=CACHE_DB)
        assert cache.set.call_count == 1

    @patch("src.stage3_variant_tox.phylop_scorer.pyBigWig.open")
    def test_bigwig_open_failure_is_unknown(self, mock_open) -> None:
        mock_open.side_effect = OSError("connection refused")
        results = score_phylop([REGION_CHR1], BIGWIG_URL, cache_db=CACHE_DB)
        assert len(results) == 1
        # Inverted 2026-11-19 (audit Bulgu 2/5). This asserted the
        # fallback *numbers*, pinning "a dead source reads as a measurement"
        # as the contract. The name said "returns neutral"; there is no
        # neutral value on a risk channel, only an unknown one.
        assert results[0].conservation_score is None
        assert results[0].mean_score is None

    @patch("src.stage3_variant_tox.phylop_scorer.pyBigWig.open")
    def test_empty_input_returns_empty_list(self, mock_open) -> None:
        results = score_phylop([], BIGWIG_URL, cache_db=CACHE_DB)
        assert results == []
        mock_open.assert_not_called()

    @patch("src.stage3_variant_tox.phylop_scorer.Cache")
    @patch("src.stage3_variant_tox.phylop_scorer.pyBigWig.open")
    def test_bigwig_opened_once_for_multiple_regions(self, mock_open, MockCache) -> None:
        mock_bw = _make_bw(1.0)
        mock_open.return_value = mock_bw
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        score_phylop([REGION_CHR1, REGION_CHR17, REGION_CHRX], BIGWIG_URL, cache_db=CACHE_DB)
        mock_open.assert_called_once()  # only one handle opened
        # Two `stats` calls per region since `R14`: the mean, then how much of
        # the window the alignment covers.
        assert mock_bw.stats.call_count == 6

    @patch("src.stage3_variant_tox.phylop_scorer.Cache")
    @patch("src.stage3_variant_tox.phylop_scorer.pyBigWig.open")
    def test_preserves_input_order(self, mock_open, MockCache) -> None:
        # Different scores per region. Since `R14` each region asks for the
        # mean and then the coverage, so the sequence interleaves the two —
        # and a coverage must be a fraction, which is why the old flat list
        # of three means stopped working.
        means = iter([4.0, -1.0, 2.0])
        mock_bw = MagicMock()
        mock_bw.stats.side_effect = lambda *a, **kw: (
            [1.0] if kw.get("type") == "coverage" else [next(means)]
        )
        mock_open.return_value = mock_bw
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        results = score_phylop([REGION_CHR1, REGION_CHR17, REGION_CHRX], BIGWIG_URL, cache_db=CACHE_DB)
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

        results = score_phylop([REGION_CHR1], BIGWIG_URL, cache_db=CACHE_DB)
        assert all(isinstance(r, PhylopResult) for r in results)

    @patch("src.stage3_variant_tox.phylop_scorer.Cache")
    @patch("src.stage3_variant_tox.phylop_scorer.pyBigWig.open")
    def test_bigwig_closed_after_use(self, mock_open, MockCache) -> None:
        mock_bw = _make_bw(1.0)
        mock_open.return_value = mock_bw
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        score_phylop([REGION_CHR1], BIGWIG_URL, cache_db=CACHE_DB)
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
        results = score_phylop([REGION_CHR1], BIGWIG_URL, cache_db=CACHE_DB)
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

        results = score_phylop([REGION_CHR1], BIGWIG_URL, cache_db=CACHE_DB)
        assert results[0].conservation_score == pytest.approx(0.75)
        mock_bw.stats.assert_not_called()
