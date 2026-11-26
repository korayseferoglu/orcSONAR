"""Tests for the empirical 7-mer null (roadmap H13, used by E1).

This is the measurement the whole hit list is judged against, so the failure
that matters is a null that flatters the hypothesis. Three ways that happens,
each pinned here:

* counting the observed seed by one rule and the null by another,
* dropping k-mers absent from the background, which compares the seed only
  against seeds that occur — the easier comparison,
* a one-sided p-value that excludes the observation itself and so reads
  slightly more significant than it is.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".claude" / "skills" / "null-check" / "scripts" / "null_check.py"


def _load():  # type: ignore[no-untyped-def]
    """Import the null-check script as a module."""
    spec = importlib.util.spec_from_file_location("null_check", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["null_check"] = module
    spec.loader.exec_module(module)
    return module


nc = _load()


class TestReverseComplement:
    """The null must use the pipeline's own matching rule."""

    def test_it_reverses_and_complements(self) -> None:
        """`seed_aligner` indexes reverse_complement(seed); so does the null."""
        assert nc.reverse_complement("CAACCAU") == "AUGGUUG"

    def test_it_is_an_involution(self) -> None:
        """Applying it twice returns the original."""
        assert nc.reverse_complement(nc.reverse_complement("ACGUACG")) == "ACGUACG"


class TestCounting:
    """Transcript counts and occurrence counts are different questions."""

    def test_a_repeated_kmer_counts_once_per_transcript(self) -> None:
        """Candidacy is per transcript, however many times the seed appears."""
        per_tx, per_occ = nc.kmer_counts(["AAAAAAAAA"], k=7)
        # "AAAAAAA" appears at three positions in a 9-mer of A.
        assert per_occ["AAAAAAA"] == 3
        assert per_tx["AAAAAAA"] == 1

    def test_two_transcripts_each_add_one(self) -> None:
        """The transcript count is a count of transcripts, not of sequences."""
        per_tx, _ = nc.kmer_counts(["ACGUACG", "ACGUACG"], k=7)
        assert per_tx["ACGUACG"] == 2

    def test_a_sequence_shorter_than_k_contributes_nothing(self) -> None:
        """No window, no count — and no crash."""
        per_tx, per_occ = nc.kmer_counts(["ACG"], k=7)
        assert not per_tx and not per_occ


class TestDistribution:
    """Every possible k-mer is in the null, including the absent ones."""

    def test_the_null_covers_the_whole_space(self) -> None:
        """4^7 = 16384. The roadmap's "16.384 7-mer" is this, exactly."""
        counts, _ = nc.kmer_counts(["ACGUACGUACGU"], k=7)
        assert len(nc.distribution(counts, 7)) == 16384

    def test_absent_kmers_are_zero_not_dropped(self) -> None:
        """Dropping them would compare the seed only against seeds that occur.

        That is the easier comparison and it inflates the observed seed's
        apparent ordinariness or significance depending on direction — either
        way it is not the null the claim needs.
        """
        counts, _ = nc.kmer_counts(["AAAAAAA"], k=2)
        null = nc.distribution(counts, 2)
        assert len(null) == 16
        assert sum(1 for value in null if value == 0) == 15


class TestSummarise:
    """Rank statistics, and no verdict."""

    def test_the_p_value_includes_the_observation(self) -> None:
        """One-sided and inclusive: the fraction at least as extreme.

        Excluding the observation would report a smaller p than the data
        support, which is the direction that manufactures significance.
        """
        stats = nc.summarise(5, [1, 2, 3, 4, 5])
        assert stats["p_empirical_ge"] == round(1 / 5, 6)

    def test_an_ordinary_value_lands_mid_distribution(self) -> None:
        """The real measurement's shape: observed below the mean, p near 0.5."""
        stats = nc.summarise(3, [1, 2, 3, 4, 5])
        assert stats["percentile_of_observed"] == 40.0
        assert stats["p_empirical_ge"] == round(3 / 5, 6)

    def test_no_threshold_or_verdict_is_produced(self) -> None:
        """Choosing a cutoff after seeing the distribution is invariant 7.

        If a `significant` or `verdict` key ever appears here, the threshold was
        picked by whoever wrote the code rather than by the pre-registration.
        """
        stats = nc.summarise(3, [1, 2, 3])
        assert "significant" not in stats
        assert "verdict" not in stats
        assert "threshold" not in stats
        assert "interpretation_is_not_here" in stats

    def test_the_mean_and_median_are_reported(self) -> None:
        """Both, because a skewed null makes them disagree and that matters."""
        stats = nc.summarise(1, [0, 0, 0, 10])
        assert stats["null_mean"] == 2.5
        assert stats["null_median"] == 0
        assert stats["null_max"] == 10
