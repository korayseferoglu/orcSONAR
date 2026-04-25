"""Unit tests for src/stage6_execution/circrna_sponge.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.models import CircRNAResult, GenomicRegion
from src.stage6_execution.circrna_sponge import (
    _find_overlaps,
    _load_circrna_bed,
    _overlaps,
    check_circrna_overlap,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REGION_A = GenomicRegion(chrom="chr1", start=100_000, end=110_000, strand="+")
REGION_B = GenomicRegion(chrom="chr2", start=200_000, end=210_000, strand="-")
REGION_C = GenomicRegion(chrom="chr1", start=500_000, end=510_000, strand="+")

BED_CONTENT = "\n".join([
    "# circAtlas BED comment line",
    "chr1\t99000\t105000\thsa_circ_0001\t0\t+",   # overlaps REGION_A
    "chr1\t108000\t115000\thsa_circ_0002\t0\t-",  # overlaps REGION_A
    "chr2\t205000\t220000\thsa_circ_0003\t0\t+",  # overlaps REGION_B
    "chr3\t100000\t110000\thsa_circ_0004\t0\t.",  # different chrom — no overlap with any
])


def _write_bed(tmp_path: Path, content: str = BED_CONTENT) -> Path:
    bed = tmp_path / "hg38_circRNAs.bed"
    bed.write_text(content, encoding="utf-8")
    return bed


# ---------------------------------------------------------------------------
# _load_circrna_bed
# ---------------------------------------------------------------------------


class TestLoadCircrnaBed:
    def test_parses_standard_bed6(self, tmp_path: Path) -> None:
        bed = _write_bed(tmp_path)
        index = _load_circrna_bed(bed)
        assert "chr1" in index
        assert len(index["chr1"]) == 2
        assert len(index["chr2"]) == 1
        assert len(index["chr3"]) == 1

    def test_skips_comment_and_blank_lines(self, tmp_path: Path) -> None:
        bed = _write_bed(tmp_path)
        index = _load_circrna_bed(bed)
        # comment line not counted
        total = sum(len(v) for v in index.values())
        assert total == 4

    def test_parses_bed4_no_strand(self, tmp_path: Path) -> None:
        content = "chr1\t100000\t200000\thsa_circ_X"
        bed = tmp_path / "test.bed"
        bed.write_text(content, encoding="utf-8")
        index = _load_circrna_bed(bed)
        assert index["chr1"][0].strand == "."

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        index = _load_circrna_bed(tmp_path / "nonexistent.bed")
        assert index == {}

    def test_skips_malformed_lines(self, tmp_path: Path) -> None:
        content = "chr1\t100000\n"  # only 2 columns
        bed = tmp_path / "bad.bed"
        bed.write_text(content, encoding="utf-8")
        index = _load_circrna_bed(bed)
        assert index == {}

    def test_entry_fields(self, tmp_path: Path) -> None:
        bed = _write_bed(tmp_path)
        index = _load_circrna_bed(bed)
        entry = index["chr1"][0]
        assert entry.chrom == "chr1"
        assert entry.start == 99_000
        assert entry.end == 105_000
        assert entry.circ_id == "hsa_circ_0001"
        assert entry.strand == "+"


# ---------------------------------------------------------------------------
# _overlaps
# ---------------------------------------------------------------------------


class TestOverlaps:
    def test_full_containment(self) -> None:
        from src.core.models import CircRNAEntry
        e = CircRNAEntry(chrom="chr1", start=99_000, end=120_000, circ_id="x")
        assert _overlaps(REGION_A, e) is True

    def test_partial_left_overlap(self) -> None:
        from src.core.models import CircRNAEntry
        e = CircRNAEntry(chrom="chr1", start=95_000, end=105_000, circ_id="x")
        assert _overlaps(REGION_A, e) is True

    def test_partial_right_overlap(self) -> None:
        from src.core.models import CircRNAEntry
        e = CircRNAEntry(chrom="chr1", start=108_000, end=115_000, circ_id="x")
        assert _overlaps(REGION_A, e) is True

    def test_adjacent_but_no_overlap(self) -> None:
        from src.core.models import CircRNAEntry
        # circ ends exactly where region starts — BED is half-open, no overlap
        e = CircRNAEntry(chrom="chr1", start=90_000, end=100_000, circ_id="x")
        assert _overlaps(REGION_A, e) is False

    def test_different_chrom_no_overlap(self) -> None:
        from src.core.models import CircRNAEntry
        e = CircRNAEntry(chrom="chr2", start=100_000, end=110_000, circ_id="x")
        assert _overlaps(REGION_A, e) is False

    def test_completely_before(self) -> None:
        from src.core.models import CircRNAEntry
        e = CircRNAEntry(chrom="chr1", start=50_000, end=90_000, circ_id="x")
        assert _overlaps(REGION_A, e) is False

    def test_completely_after(self) -> None:
        from src.core.models import CircRNAEntry
        e = CircRNAEntry(chrom="chr1", start=120_000, end=130_000, circ_id="x")
        assert _overlaps(REGION_A, e) is False

    def test_single_base_overlap(self) -> None:
        from src.core.models import CircRNAEntry
        # circ: [109999, 110001) ∩ region: [100000, 110000) → overlap at 109999
        e = CircRNAEntry(chrom="chr1", start=109_999, end=110_001, circ_id="x")
        assert _overlaps(REGION_A, e) is True


# ---------------------------------------------------------------------------
# _find_overlaps
# ---------------------------------------------------------------------------


class TestFindOverlaps:
    def test_returns_all_overlapping_entries(self, tmp_path: Path) -> None:
        bed = _write_bed(tmp_path)
        index = _load_circrna_bed(bed)
        hits = _find_overlaps(REGION_A, index)
        assert len(hits) == 2
        ids = {h.circ_id for h in hits}
        assert ids == {"hsa_circ_0001", "hsa_circ_0002"}

    def test_no_hits_for_non_overlapping_region(self, tmp_path: Path) -> None:
        bed = _write_bed(tmp_path)
        index = _load_circrna_bed(bed)
        hits = _find_overlaps(REGION_C, index)
        assert hits == []

    def test_empty_index_returns_empty(self) -> None:
        hits = _find_overlaps(REGION_A, {})
        assert hits == []


# ---------------------------------------------------------------------------
# check_circrna_overlap
# ---------------------------------------------------------------------------


class TestCheckCircrnaOverlap:
    def test_empty_regions_returns_empty(self) -> None:
        result = check_circrna_overlap([], None)
        assert result == []

    def test_none_path_returns_no_data_results(self) -> None:
        results = check_circrna_overlap([REGION_A, REGION_B], circrna_path=None)
        assert len(results) == 2
        for r in results:
            assert isinstance(r, CircRNAResult)
            assert r.data_available is False
            assert r.sponge_risk is False
            assert r.overlap_count == 0

    def test_missing_file_returns_no_data_results(self, tmp_path: Path) -> None:
        results = check_circrna_overlap(
            [REGION_A], circrna_path=str(tmp_path / "missing.bed")
        )
        assert results[0].data_available is False
        assert results[0].sponge_risk is False

    def test_sponge_risk_flagged_when_overlap(self, tmp_path: Path) -> None:
        bed = _write_bed(tmp_path)
        results = check_circrna_overlap([REGION_A], circrna_path=str(bed))
        assert results[0].sponge_risk is True
        assert results[0].overlap_count == 2
        assert results[0].data_available is True

    def test_no_sponge_risk_when_no_overlap(self, tmp_path: Path) -> None:
        bed = _write_bed(tmp_path)
        results = check_circrna_overlap([REGION_C], circrna_path=str(bed))
        assert results[0].sponge_risk is False
        assert results[0].overlap_count == 0
        assert results[0].data_available is True

    def test_preserves_region_order(self, tmp_path: Path) -> None:
        bed = _write_bed(tmp_path)
        regions = [REGION_A, REGION_C, REGION_B]
        results = check_circrna_overlap(regions, circrna_path=str(bed))
        assert results[0].region == REGION_A
        assert results[1].region == REGION_C
        assert results[2].region == REGION_B

    def test_overlapping_circ_ids_correct(self, tmp_path: Path) -> None:
        bed = _write_bed(tmp_path)
        results = check_circrna_overlap([REGION_B], circrna_path=str(bed))
        ids = {e.circ_id for e in results[0].overlapping_circrnas}
        assert ids == {"hsa_circ_0003"}

    def test_mixed_results_in_one_call(self, tmp_path: Path) -> None:
        bed = _write_bed(tmp_path)
        results = check_circrna_overlap([REGION_A, REGION_C], circrna_path=str(bed))
        assert results[0].sponge_risk is True   # REGION_A has hits
        assert results[1].sponge_risk is False  # REGION_C has no hits

    def test_empty_bed_data_available_false(self, tmp_path: Path) -> None:
        """An empty BED (no parseable entries) → data_available=False."""
        bed = tmp_path / "empty.bed"
        bed.write_text("# only a comment\n", encoding="utf-8")
        results = check_circrna_overlap([REGION_A], circrna_path=str(bed))
        # Empty index → data_available=False
        assert results[0].data_available is False
        assert results[0].sponge_risk is False
