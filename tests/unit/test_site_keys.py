"""Tests for src/core/site_keys.py — the shared id/region extraction helper.

Thirteen stage adapters use this to build the two lists they later ``zip``
together. If those lists ever fall out of step, every measurement is attributed
to the wrong site, silently and with all values still in range. These tests
exist to make that impossible rather than unlikely.
"""

from __future__ import annotations

from typing import Any

from src.core.site_keys import site_ids_and_regions


def _site(site_id: str, chrom: str = "chr1", start: int = 1000) -> dict[str, Any]:
    return {
        "site_id": site_id,
        "gene": site_id.split(":")[0],
        "transcript_id": site_id.split(":")[1],
        "region": {"chrom": chrom, "start": start, "end": start + 20, "strand": "+"},
    }


class TestSiteIdsAndRegions:
    def test_returns_aligned_lists(self):
        sites = [
            _site("MTOR:ENST1:chr1:100", start=100),
            _site("BRCA1:ENST2:chr17:200", chrom="chr17", start=200),
        ]
        ids, regions = site_ids_and_regions(sites, caller="test")
        assert len(ids) == len(regions) == 2
        assert ids == ["MTOR:ENST1:chr1:100", "BRCA1:ENST2:chr17:200"]
        assert regions[0].start == 100
        assert regions[1].chrom == "chr17"

    def test_uses_stored_site_id_verbatim(self):
        """The helper must not rebuild the key — that is how stages drifted apart."""
        site = _site("MTOR:ENST1:chr1:100", start=100)
        site["site_id"] = "SOMETHING:ELSE:chr9:999"
        ids, _ = site_ids_and_regions([site], caller="test")
        assert ids == ["SOMETHING:ELSE:chr9:999"]

    def test_site_missing_id_is_skipped_whole(self):
        """A site without an id must drop its region too, or the lists desync.

        This is the failure that would mislabel every downstream measurement:
        append the region, fail on the id, and from then on zip() pairs each
        region with the *next* site's id.
        """
        good_a = _site("A:ENST1:chr1:100", start=100)
        bad = {"gene": "B", "transcript_id": "ENST2",
               "region": {"chrom": "chr1", "start": 200, "end": 220, "strand": "+"}}
        good_b = _site("C:ENST3:chr1:300", start=300)

        ids, regions = site_ids_and_regions([good_a, bad, good_b], caller="test")

        assert len(ids) == len(regions) == 2
        assert ids == ["A:ENST1:chr1:100", "C:ENST3:chr1:300"]
        # The surviving pairs must still describe their own sites.
        assert regions[0].start == 100
        assert regions[1].start == 300, "region 300 was paired with the wrong id"

    def test_site_with_unusable_region_is_skipped_whole(self):
        good = _site("A:ENST1:chr1:100", start=100)
        bad = {"site_id": "B:ENST2:chr1:200", "region": {"chrom": "chr1", "start": -5}}
        ids, regions = site_ids_and_regions([good, bad], caller="test")
        assert len(ids) == len(regions) == 1
        assert ids == ["A:ENST1:chr1:100"]

    def test_empty_input(self):
        ids, regions = site_ids_and_regions([], caller="test")
        assert ids == [] and regions == []

    def test_lists_stay_aligned_under_many_failures(self):
        """Interleaved good/bad sites must never shift the pairing."""
        sites = []
        expected = []
        for i in range(20):
            if i % 3 == 0:
                sites.append({"gene": "X", "region": {"chrom": "chr1", "start": i}})
            else:
                sid = f"G{i}:ENST{i}:chr1:{i * 10}"
                sites.append(_site(sid, start=i * 10))
                expected.append((sid, i * 10))

        ids, regions = site_ids_and_regions(sites, caller="test")
        assert len(ids) == len(regions) == len(expected)
        for (exp_id, exp_start), got_id, got_region in zip(expected, ids, regions, strict=True):
            assert got_id == exp_id
            assert got_region.start == exp_start
