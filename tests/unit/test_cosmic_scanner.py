"""Unit tests for src/stage3_variant_tox/cosmic_scanner.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.models import CosmicMutation, CosmicResult, GenomicRegion
from src.stage3_variant_tox.cosmic_scanner import (
    _calculate_mutation_density,
    _fetch_mutations,
    _parse_info,
    _parse_vcf_record,
    scan_cosmic,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COSMIC_VCF = "data/2_Varyant_Toksisite/COSMIC/Cosmic_GenomeScreensMutant_v103_GRCh38.vcf.gz"

# Known record: chr1:65797 (OR4F5, SNV, sample_count=1, no TIER)
REGION_KNOWN = GenomicRegion(chrom="chr1", start=65790, end=65810, strand="+")

# TP53 region on chr17 — many TIER=1 mutations
REGION_TP53 = GenomicRegion(chrom="chr17", start=7668400, end=7668500, strand="-")

# Region with no mutations in COSMIC
REGION_EMPTY = GenomicRegion(chrom="chr1", start=1, end=100, strand=".")


# ---------------------------------------------------------------------------
# Raw VCF record fixtures
# ---------------------------------------------------------------------------

RAW_SNV = (
    "1\t65797\tCOSV58737189\tT\tC\t.\t.\t"
    "GENE=OR4F5;TRANSCRIPT=ENST00000641515.2;STRAND=+;"
    "GENOME_SCREEN_SAMPLE_COUNT=1;IS_CANONICAL=n;SO_TERM=SNV"
)

RAW_SNV_TIER1 = (
    "17\t7668438\tCOSV106382782\tT\tG\t.\t.\t"
    "GENE=TP53;TRANSCRIPT=ENST00000610538.4;STRAND=-;"
    "GENOME_SCREEN_SAMPLE_COUNT=5;IS_CANONICAL=n;TIER=1;SO_TERM=SNV"
)

RAW_DELETION = (
    "1\t66173\tCOSV58736766\tTAT\tT\t.\t.\t"
    "GENE=OR4F5;TRANSCRIPT=ENST00000641515.2;STRAND=+;"
    "GENOME_SCREEN_SAMPLE_COUNT=3;SO_TERM=deletion"
)

RAW_MALFORMED_COLS = "1\t65797\tCOSV1"  # only 3 columns

RAW_MALFORMED_POS = "1\tABC\tCOSV1\tT\tC\t.\t.\tGENE=X;SO_TERM=SNV"


# ---------------------------------------------------------------------------
# _parse_info
# ---------------------------------------------------------------------------


class TestParseInfo:
    def test_basic_key_value(self) -> None:
        result = _parse_info("GENE=TP53;SO_TERM=SNV;TIER=1")
        assert result["GENE"] == "TP53"
        assert result["SO_TERM"] == "SNV"
        assert result["TIER"] == "1"

    def test_flag_fields_without_value_ignored(self) -> None:
        # Fields without "=" (flag-style) should be absent from dict
        result = _parse_info("GENE=TP53;FLAGONLY;SO_TERM=SNV")
        assert "FLAGONLY" not in result
        assert result["GENE"] == "TP53"

    def test_empty_info_string(self) -> None:
        assert _parse_info("") == {}

    def test_value_with_equals_sign(self) -> None:
        # partition("=") takes only the first "=", rest goes to value
        result = _parse_info("HGVSC=ENST00000610538.4:c.*1372A>C")
        assert result["HGVSC"] == "ENST00000610538.4:c.*1372A>C"


# ---------------------------------------------------------------------------
# _parse_vcf_record
# ---------------------------------------------------------------------------


class TestParseVcfRecord:
    def test_snv_no_tier(self) -> None:
        mut = _parse_vcf_record(RAW_SNV)
        assert mut is not None
        assert mut.position == 65797
        assert mut.ref == "T"
        assert mut.alt == "C"
        assert mut.gene == "OR4F5"
        assert mut.so_term == "SNV"
        assert mut.sample_count == 1
        assert mut.tier is None

    def test_snv_tier1(self) -> None:
        mut = _parse_vcf_record(RAW_SNV_TIER1)
        assert mut is not None
        assert mut.gene == "TP53"
        assert mut.tier == 1
        assert mut.sample_count == 5
        assert mut.so_term == "SNV"

    def test_deletion(self) -> None:
        mut = _parse_vcf_record(RAW_DELETION)
        assert mut is not None
        assert mut.ref == "TAT"
        assert mut.alt == "T"
        assert mut.so_term == "deletion"

    def test_malformed_too_few_columns(self) -> None:
        assert _parse_vcf_record(RAW_MALFORMED_COLS) is None

    def test_malformed_non_integer_pos(self) -> None:
        assert _parse_vcf_record(RAW_MALFORMED_POS) is None

    def test_returns_cosmic_mutation_instance(self) -> None:
        mut = _parse_vcf_record(RAW_SNV)
        assert isinstance(mut, CosmicMutation)


# ---------------------------------------------------------------------------
# _calculate_mutation_density
# ---------------------------------------------------------------------------


class TestCalculateMutationDensity:
    def _make_mutations(self, n: int) -> list[CosmicMutation]:
        return [
            CosmicMutation(position=i, ref="A", alt="T", gene="X", so_term="SNV")
            for i in range(n)
        ]

    def test_no_mutations_returns_zero(self) -> None:
        assert _calculate_mutation_density([], 1000) == pytest.approx(0.0)

    def test_zero_region_length_returns_zero(self) -> None:
        muts = self._make_mutations(5)
        assert _calculate_mutation_density(muts, 0) == pytest.approx(0.0)

    def test_negative_region_length_returns_zero(self) -> None:
        muts = self._make_mutations(3)
        assert _calculate_mutation_density(muts, -100) == pytest.approx(0.0)

    def test_density_1kb_5mut_gives_0_5(self) -> None:
        # 5 mutations / 1 kb = 5/kb, saturation=10 → score 0.5
        muts = self._make_mutations(5)
        assert _calculate_mutation_density(muts, 1000) == pytest.approx(0.5)

    def test_density_saturates_at_1_0(self) -> None:
        # 20 mutations / 1 kb = 20/kb > saturation(10) → capped at 1.0
        muts = self._make_mutations(20)
        assert _calculate_mutation_density(muts, 1000) == pytest.approx(1.0)

    def test_small_region_density(self) -> None:
        # 1 mutation / 100 bp = 10/kb → density_score = 1.0
        muts = self._make_mutations(1)
        assert _calculate_mutation_density(muts, 100) == pytest.approx(1.0)

    def test_large_region_low_density(self) -> None:
        # 1 mutation / 100 kb = 0.01/kb → score 0.001
        muts = self._make_mutations(1)
        assert _calculate_mutation_density(muts, 100_000) == pytest.approx(0.001)


# ---------------------------------------------------------------------------
# scan_cosmic — integration test against real VCF
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not Path(COSMIC_VCF).exists(),
    reason="COSMIC VCF not available in this environment",
)
class TestScanCosmicRealVcf:
    def test_known_snv_chr1_65797(self) -> None:
        """Real VCF must contain COSV58737189 (T→C) at chr1:65797."""
        results = scan_cosmic([REGION_KNOWN], COSMIC_VCF)
        assert len(results) == 1
        r = results[0]
        assert isinstance(r, CosmicResult)
        assert r.mutation_count == 1
        assert r.region == REGION_KNOWN
        assert r.has_tier1_gene is False
        mut = r.mutations[0]
        assert mut.position == 65797
        assert mut.ref == "T"
        assert mut.alt == "C"
        assert mut.so_term == "SNV"
        assert mut.sample_count == 1
        assert mut.tier is None

    def test_tier1_tp53_region(self) -> None:
        """TP53 region must have TIER=1 mutations."""
        results = scan_cosmic([REGION_TP53], COSMIC_VCF)
        assert len(results) == 1
        r = results[0]
        assert r.mutation_count > 0
        assert r.has_tier1_gene is True
        assert all(m.gene == "TP53" for m in r.mutations)

    def test_empty_region_gives_zero_mutations(self) -> None:
        """Region with no COSMIC entries → mutation_count=0, density=0."""
        results = scan_cosmic([REGION_EMPTY], COSMIC_VCF)
        assert results[0].mutation_count == 0
        assert results[0].density_score == pytest.approx(0.0)
        assert results[0].has_tier1_gene is False

    def test_preserves_input_order(self) -> None:
        results = scan_cosmic([REGION_EMPTY, REGION_KNOWN], COSMIC_VCF)
        assert len(results) == 2
        assert results[0].region == REGION_EMPTY
        assert results[1].region == REGION_KNOWN

    def test_chr_prefix_stripped_correctly(self) -> None:
        """Region with chr-prefix must still hit the correct VCF contigs."""
        region_chrprefixed = GenomicRegion(chrom="chr1", start=65790, end=65810)
        results = scan_cosmic([region_chrprefixed], COSMIC_VCF)
        assert results[0].mutation_count == 1

    def test_density_score_bounded(self) -> None:
        results = scan_cosmic([REGION_KNOWN, REGION_TP53], COSMIC_VCF)
        for r in results:
            assert 0.0 <= r.density_score <= 1.0

    def test_result_is_cosmic_result_instance(self) -> None:
        results = scan_cosmic([REGION_KNOWN], COSMIC_VCF)
        assert isinstance(results[0], CosmicResult)


# ---------------------------------------------------------------------------
# scan_cosmic — unit tests with mocked pysam
# ---------------------------------------------------------------------------


class TestScanCosmicMocked:
    def test_invalid_vcf_path_returns_neutral(self) -> None:
        results = scan_cosmic(
            [REGION_KNOWN],
            "/nonexistent/path/file.vcf.gz",
        )
        assert len(results) == 1
        assert results[0].mutation_count == 0
        assert results[0].density_score == pytest.approx(0.0)
        assert results[0].has_tier1_gene is False

    def test_empty_input_returns_empty_list(self) -> None:
        results = scan_cosmic([], COSMIC_VCF)
        assert results == []

    @patch("src.stage3_variant_tox.cosmic_scanner.pysam.TabixFile")
    def test_missing_contig_returns_empty_mutations(self, MockTabix) -> None:
        mock_tbx = MagicMock()
        mock_tbx.fetch.side_effect = ValueError("unknown sequence name")
        MockTabix.return_value = mock_tbx

        results = scan_cosmic([REGION_EMPTY], "fake.vcf.gz")
        assert results[0].mutation_count == 0

    @patch("src.stage3_variant_tox.cosmic_scanner.pysam.TabixFile")
    def test_tier1_detection(self, MockTabix) -> None:
        mock_tbx = MagicMock()
        mock_tbx.fetch.return_value = iter([RAW_SNV_TIER1])
        MockTabix.return_value = mock_tbx

        region = GenomicRegion(chrom="chr17", start=7668430, end=7668450)
        results = scan_cosmic([region], "fake.vcf.gz")
        assert results[0].has_tier1_gene is True
        assert results[0].mutations[0].tier == 1

    @patch("src.stage3_variant_tox.cosmic_scanner.pysam.TabixFile")
    def test_multiple_records_counted(self, MockTabix) -> None:
        mock_tbx = MagicMock()
        mock_tbx.fetch.return_value = iter([RAW_SNV, RAW_DELETION])
        MockTabix.return_value = mock_tbx

        region = GenomicRegion(chrom="chr1", start=65700, end=66200)
        results = scan_cosmic([region], "fake.vcf.gz")
        assert results[0].mutation_count == 2

    @patch("src.stage3_variant_tox.cosmic_scanner.pysam.TabixFile")
    def test_malformed_records_skipped_gracefully(self, MockTabix) -> None:
        mock_tbx = MagicMock()
        # One good, one bad
        mock_tbx.fetch.return_value = iter([RAW_SNV, RAW_MALFORMED_COLS])
        MockTabix.return_value = mock_tbx

        region = GenomicRegion(chrom="chr1", start=65790, end=65810)
        results = scan_cosmic([region], "fake.vcf.gz")
        assert results[0].mutation_count == 1  # only the good record
