"""Unit tests for Stage 1 TSS mapper and promoter region definer."""

from __future__ import annotations

from pathlib import Path

import pytest
import responses as resp_mock

from src.core.config import OrcSonarConfig
from src.core.exceptions import DataSourceError
from src.core.models import TSSInfo
from src.stage1_genomic_map.promoter_region import define_promoter
from src.stage1_genomic_map.tss_mapper import (
    _get_gene_coordinates_ensembl,
    _search_epdnew,
    _search_fantom5,
    find_tss,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def epdnew_bed() -> Path:
    return FIXTURES / "sample_epdnew.bed"


@pytest.fixture
def fantom5_bed() -> Path:
    return FIXTURES / "sample_fantom5.bed"


@pytest.fixture
def test_config(tmp_path: Path) -> OrcSonarConfig:
    """Config pointing at fixture BED files and a temp cache."""
    return OrcSonarConfig(
        data_paths={
            "epdnew_bed": str(FIXTURES / "sample_epdnew.bed"),
            "fantom5_bed": str(FIXTURES / "sample_fantom5.bed"),
            "cache_db": str(tmp_path / "test_cache.db"),
        }
    )


# ---------------------------------------------------------------------------
# _search_epdnew
# ---------------------------------------------------------------------------


def test_epdnew_known_gene_minus_strand(epdnew_bed: Path) -> None:
    tss = _search_epdnew("NOC2L", epdnew_bed)
    assert tss is not None
    assert tss.gene == "NOC2L"
    assert tss.chrom == "chr1"
    assert tss.strand == "-"
    assert tss.source == "EPDnew"
    # - strand → thickEnd column (959256 from fixture)
    assert tss.position == 959256


def test_epdnew_known_gene_plus_strand(epdnew_bed: Path) -> None:
    tss = _search_epdnew("KLHL17", epdnew_bed)
    assert tss is not None
    assert tss.gene == "KLHL17"
    assert tss.chrom == "chr1"
    assert tss.strand == "+"
    assert tss.source == "EPDnew"
    # + strand → thickStart column (960632 from fixture)
    assert tss.position == 960632


def test_epdnew_vegfa_picks_best_isoform(epdnew_bed: Path) -> None:
    """VEGFA has two isoforms; both have score 900 so first one is returned."""
    tss = _search_epdnew("VEGFA", epdnew_bed)
    assert tss is not None
    assert tss.gene == "VEGFA"
    assert tss.chrom == "chr6"
    assert tss.strand == "+"
    # thickStart of VEGFA_1 (first record, score 900)
    assert tss.position == 43770210


def test_epdnew_case_insensitive(epdnew_bed: Path) -> None:
    assert _search_epdnew("vegfa", epdnew_bed) is not None
    assert _search_epdnew("VeGfA", epdnew_bed) is not None


def test_epdnew_missing_gene_returns_none(epdnew_bed: Path) -> None:
    assert _search_epdnew("GENENOTINEPDNEW", epdnew_bed) is None


def test_epdnew_missing_file_returns_none(tmp_path: Path) -> None:
    result = _search_epdnew("VEGFA", tmp_path / "nonexistent.bed")
    assert result is None


# ---------------------------------------------------------------------------
# _search_fantom5 (with mocked Ensembl API)
# ---------------------------------------------------------------------------

# The mock Ensembl will say "GENENOTINEPDNEW" is at chr1:620000–635000.
# The FANTOM5 fixture has peaks in chr1:629191–631543.
# Peak with highest score: chr1:630129-630161, score=5172, thickStart=630143.
_MOCK_ENSEMBL_RESPONSE = {
    "seq_region_name": "1",  # Ensembl returns without "chr" prefix
    "start": 620000,
    "end": 635000,
    "strand": 1,
}


@resp_mock.activate
def test_fantom5_fallback_returns_highest_score_peak(
    fantom5_bed: Path, test_config: OrcSonarConfig
) -> None:
    resp_mock.add(
        resp_mock.GET,
        "https://rest.ensembl.org/lookup/symbol/homo_sapiens/GENENOTINEPDNEW"
        "?expand=0&content-type=application/json",
        json=_MOCK_ENSEMBL_RESPONSE,
        status=200,
    )

    tss = _search_fantom5("GENENOTINEPDNEW", fantom5_bed, test_config)

    assert tss is not None
    assert tss.source == "FANTOM5"
    assert tss.chrom == "chr1"
    assert tss.score == 5172.0
    # Peak at chr1:630129-630161, strand="+", thickStart=630143
    assert tss.position == 630143
    assert tss.strand == "+"


@resp_mock.activate
def test_fantom5_adds_chr_prefix(fantom5_bed: Path, test_config: OrcSonarConfig) -> None:
    """Ensembl returns seq_region_name without 'chr'; mapper must prepend it."""
    resp_mock.add(
        resp_mock.GET,
        "https://rest.ensembl.org/lookup/symbol/homo_sapiens/GENENOTINEPDNEW"
        "?expand=0&content-type=application/json",
        json=_MOCK_ENSEMBL_RESPONSE,
        status=200,
    )
    tss = _search_fantom5("GENENOTINEPDNEW", fantom5_bed, test_config)
    assert tss is not None
    assert tss.chrom.startswith("chr")


@resp_mock.activate
def test_fantom5_returns_none_when_ensembl_fails(
    fantom5_bed: Path, test_config: OrcSonarConfig
) -> None:
    resp_mock.add(
        resp_mock.GET,
        "https://rest.ensembl.org/lookup/symbol/homo_sapiens/BADGENE"
        "?expand=0&content-type=application/json",
        status=404,
    )
    # tenacity will retry 4 times but all fail → returns None (graceful)
    tss = _search_fantom5("BADGENE", fantom5_bed, test_config)
    assert tss is None


# ---------------------------------------------------------------------------
# find_tss integration: EPDnew hit → no Ensembl call needed
# ---------------------------------------------------------------------------


def test_find_tss_uses_epdnew_without_api_call(test_config: OrcSonarConfig) -> None:
    """VEGFA is in the EPDnew fixture; no HTTP call should be made."""
    # No responses registered, so any HTTP call would fail the block — that is
    # the assertion. The handle itself is unused on purpose (H15).
    with resp_mock.RequestsMock(assert_all_requests_are_fired=False):
        tss = find_tss("VEGFA", test_config)
    assert tss.source == "EPDnew"
    assert tss.gene == "VEGFA"


@resp_mock.activate
def test_find_tss_raises_when_both_sources_fail(test_config: OrcSonarConfig) -> None:
    resp_mock.add(
        resp_mock.GET,
        "https://rest.ensembl.org/lookup/symbol/homo_sapiens/UNKNOWNGENE"
        "?expand=0&content-type=application/json",
        status=404,
    )
    with pytest.raises(DataSourceError, match="UNKNOWNGENE"):
        find_tss("UNKNOWNGENE", test_config)


# ---------------------------------------------------------------------------
# Ensembl cache behaviour
# ---------------------------------------------------------------------------


@resp_mock.activate
def test_ensembl_result_is_cached(test_config: OrcSonarConfig) -> None:
    """Second call must not issue a second HTTP request."""
    resp_mock.add(
        resp_mock.GET,
        "https://rest.ensembl.org/lookup/symbol/homo_sapiens/CACHEDGENE"
        "?expand=0&content-type=application/json",
        json={"seq_region_name": "6", "start": 1000, "end": 2000, "strand": 1},
        status=200,
    )

    _get_gene_coordinates_ensembl("CACHEDGENE", test_config)
    _get_gene_coordinates_ensembl("CACHEDGENE", test_config)

    # responses library would raise if a second HTTP call were made beyond
    # what was registered (only one response registered above).
    assert len(resp_mock.calls) == 1


# ---------------------------------------------------------------------------
# define_promoter
# ---------------------------------------------------------------------------


def test_promoter_forward_strand() -> None:
    tss = TSSInfo(
        gene="VEGFA", chrom="chr6", position=43770210, strand="+", source="EPDnew"
    )
    region = define_promoter(tss, upstream=1000, downstream=200)
    assert region.chrom == "chr6"
    assert region.start == 43770210 - 1000  # 43769210
    assert region.end == 43770210 + 200     # 43770410
    assert region.strand == "+"


def test_promoter_reverse_strand() -> None:
    tss = TSSInfo(
        gene="NOC2L", chrom="chr1", position=959256, strand="-", source="EPDnew"
    )
    region = define_promoter(tss, upstream=1000, downstream=200)
    assert region.chrom == "chr1"
    assert region.start == 959256 - 200    # 959056
    assert region.end == 959256 + 1000     # 960256
    assert region.strand == "-"


def test_promoter_default_window_size() -> None:
    tss = TSSInfo(
        gene="GAPDH", chrom="chr12", position=6534516, strand="+", source="EPDnew"
    )
    region = define_promoter(tss)
    assert region.end - region.start == 1200  # 1000 + 200


def test_promoter_clamps_to_zero_at_chromosome_start() -> None:
    tss = TSSInfo(
        gene="NEARSTART", chrom="chr1", position=50, strand="+", source="EPDnew"
    )
    region = define_promoter(tss, upstream=1000, downstream=200)
    assert region.start == 0   # clamped, not negative
    assert region.end == 250


def test_promoter_reverse_strand_near_zero_clamped() -> None:
    tss = TSSInfo(
        gene="NEARSTART", chrom="chr1", position=100, strand="-", source="EPDnew"
    )
    region = define_promoter(tss, upstream=1000, downstream=200)
    assert region.start == 0   # 100 - 200 clamped to 0
    assert region.end == 1100
