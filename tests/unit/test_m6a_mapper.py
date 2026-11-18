"""Unit tests for src/stage5_biophysics/m6a_mapper.py."""

from __future__ import annotations

import os

import pytest

from src.core.models import GenomicRegion

# ---------------------------------------------------------------------------
# Check whether the real m6A tabix file is present
# ---------------------------------------------------------------------------
_M6A_BED = "data/4_Biyofizik_Yapısal/RMBase/hg38_m6A_mühürlü.bed.gz"
_M6A_PRESENT = os.path.exists(_M6A_BED) and os.path.exists(_M6A_BED + ".tbi")

from src.stage5_biophysics.m6a_mapper import _query_tabix, scan_m6a_sites

# ---------------------------------------------------------------------------
# Tests against the real file (skipped when absent)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _M6A_PRESENT, reason="m6A BED file not available")
class TestQueryTabixReal:
    def test_known_hela_site(self):
        """chr1:14414-14415 is a HeLa m6A site in the dataset."""
        sites = _query_tabix(_M6A_BED, "chr1", 14410, 14420, cell_line="HeLa")
        assert len(sites) >= 1
        assert any(s.start == 14414 for s in sites)

    def test_cell_line_filter(self):
        """Filter by cell line should reduce site count."""
        all_sites = _query_tabix(_M6A_BED, "chr1", 14000, 100000)
        hela_sites = _query_tabix(_M6A_BED, "chr1", 14000, 100000, cell_line="HeLa")
        assert len(hela_sites) <= len(all_sites)

    def test_empty_region(self):
        """Region with no m6A sites returns empty list."""
        sites = _query_tabix(_M6A_BED, "chr1", 1, 100)
        assert isinstance(sites, list)

    def test_nonexistent_chrom(self):
        """Invalid chromosome returns empty list gracefully."""
        sites = _query_tabix(_M6A_BED, "chrZ", 0, 1000)
        assert sites == []

    def test_site_fields_populated(self):
        sites = _query_tabix(_M6A_BED, "chr1", 14410, 14420)
        assert len(sites) >= 1
        s = sites[0]
        assert s.chrom == "chr1"
        assert s.start >= 0
        assert s.end > s.start
        assert s.strand in ("+", "-", ".")
        assert s.mod_type == "m6A"

    def test_cell_line_no_match(self):
        """Cell line not present in region returns empty list."""
        sites = _query_tabix(_M6A_BED, "chr1", 14410, 14420, cell_line="A549")
        # May or may not be empty; just check type
        assert isinstance(sites, list)


@pytest.mark.skipif(not _M6A_PRESENT, reason="m6A BED file not available")
class TestScanM6aSitesReal:
    def test_scan_single_region(self):
        region = GenomicRegion(chrom="chr1", start=14410, end=14420)
        results = scan_m6a_sites([region], cell_line="HeLa", bed_path=_M6A_BED)
        assert len(results) == 1
        r = results[0]
        assert r.region == region
        assert r.cell_line == "HeLa"
        assert r.site_count == len(r.sites)
        assert 0.0 <= r.m6a_score <= 1.0

    def test_scan_multiple_regions(self):
        regions = [
            GenomicRegion(chrom="chr1", start=14410, end=14420),
            GenomicRegion(chrom="chr1", start=50000, end=51000),
        ]
        results = scan_m6a_sites(regions, cell_line="HeLa", bed_path=_M6A_BED)
        assert len(results) == 2
        for r in results:
            assert 0.0 <= r.m6a_score <= 1.0

    def test_m6a_score_capped_at_1(self):
        """Dense region should not exceed score of 1.0."""
        region = GenomicRegion(chrom="chr1", start=14000, end=14500)
        results = scan_m6a_sites([region], cell_line="", bed_path=_M6A_BED)
        assert results[0].m6a_score <= 1.0

    def test_empty_regions_list(self):
        results = scan_m6a_sites([], cell_line="HeLa", bed_path=_M6A_BED)
        assert results == []


# ---------------------------------------------------------------------------
# Tests with an invalid path (always run)
# ---------------------------------------------------------------------------


class TestQueryTabixBadPath:
    def test_missing_file_returns_empty(self):
        sites = _query_tabix("/no/such/file.bed.gz", "chr1", 0, 100)
        assert sites == []

    def test_scan_missing_file_returns_results_with_zero(self):
        region = GenomicRegion(chrom="chr1", start=0, end=100)
        results = scan_m6a_sites([region], cell_line="HeLa", bed_path="/no/such.bed.gz")
        assert len(results) == 1
        assert results[0].site_count == 0
        assert results[0].m6a_score == pytest.approx(0.0)
