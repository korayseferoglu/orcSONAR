"""Unit tests for src/stage3_variant_tox/clinvar_client.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import responses as resp_mock

from src.core.config import OrcSonarConfig
from src.core.models import ClinvarResult, ClinvarVariant, GenomicRegion
from src.stage3_variant_tox.clinvar_client import (
    _esearch,
    _esummary,
    _parse_esummary_entry,
    _search_clinvar_region,
    check_clinvar,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
ESEARCH_URL = f"{EUTILS_BASE}esearch.fcgi"
ESUMMARY_URL = f"{EUTILS_BASE}esummary.fcgi"

REGION_A = GenomicRegion(chrom="chr1", start=100_000, end=101_000, strand="+")
REGION_B = GenomicRegion(chrom="chr17", start=7_668_400, end=7_668_500, strand="-")
REGION_EMPTY = GenomicRegion(chrom="chrX", start=50_000, end=51_000, strand=".")


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------


def _esearch_payload(uids: list[str]) -> dict:
    return {
        "esearchresult": {
            "count": str(len(uids)),
            "idlist": uids,
        }
    }


def _esummary_payload(entries: dict[str, dict]) -> dict:
    """Build a minimal esummary response with the given uid→entry mapping."""
    result: dict = {"uids": list(entries.keys())}
    result.update(entries)
    return {"result": result}


def _variant_entry(
    uid: str = "12345",
    significance: str = "Pathogenic",
    gene: str = "BRCA1",
    condition: str = "Hereditary breast cancer",
    position: int = 100_500,
) -> dict:
    return {
        "uid": uid,
        "germline_classification": {"description": significance},
        "genes": [{"symbol": gene}],
        "trait_set": [{"trait": [{"trait_name": condition}]}],
        "variation_set": [
            {
                "variation_loc": [
                    {"assembly_name": "GRCh38", "start": position},
                ]
            }
        ],
    }


def _mock_cache(hit: dict | None = None) -> MagicMock:
    cache = MagicMock()
    cache.get.return_value = hit
    return cache


# ---------------------------------------------------------------------------
# _parse_esummary_entry
# ---------------------------------------------------------------------------


class TestParseEsummaryEntry:
    def test_pathogenic_variant(self) -> None:
        entry = _variant_entry()
        v = _parse_esummary_entry("12345", entry)
        assert v is not None
        assert v.uid == "12345"
        assert v.significance == "Pathogenic"
        assert v.gene == "BRCA1"
        assert v.condition == "Hereditary breast cancer"
        assert v.position == 100_500

    def test_likely_pathogenic_variant(self) -> None:
        entry = _variant_entry(significance="Likely pathogenic", gene="TP53")
        v = _parse_esummary_entry("99999", entry)
        assert v is not None
        assert v.significance == "Likely pathogenic"
        assert v.gene == "TP53"

    def test_empty_entry_returns_none(self) -> None:
        assert _parse_esummary_entry("0", {}) is None

    def test_no_genes_field(self) -> None:
        entry = _variant_entry()
        del entry["genes"]
        v = _parse_esummary_entry("1", entry)
        assert v is not None
        assert v.gene == ""

    def test_no_trait_set_falls_back_to_title(self) -> None:
        entry = _variant_entry()
        del entry["trait_set"]
        entry["title"] = "Fallback condition title"
        v = _parse_esummary_entry("1", entry)
        assert v is not None
        assert v.condition == "Fallback condition title"

    def test_position_from_grch38_loc(self) -> None:
        entry = _variant_entry(position=7_668_450)
        v = _parse_esummary_entry("2", entry)
        assert v is not None
        assert v.position == 7_668_450

    def test_no_grch38_loc_position_is_none(self) -> None:
        entry = _variant_entry()
        entry["variation_set"] = [
            {"variation_loc": [{"assembly_name": "GRCh37", "start": 12345}]}
        ]
        v = _parse_esummary_entry("3", entry)
        assert v is not None
        assert v.position is None

    def test_returns_clinvar_variant_instance(self) -> None:
        v = _parse_esummary_entry("1", _variant_entry())
        assert isinstance(v, ClinvarVariant)

    def test_legacy_clinical_significance_field(self) -> None:
        """Older API format uses 'clinical_significance' instead of 'germline_classification'."""
        entry = {
            "genes": [{"symbol": "MLH1"}],
            "trait_set": [],
            "variation_set": [],
            "clinical_significance": {"description": "Pathogenic"},
        }
        v = _parse_esummary_entry("7", entry)
        assert v is not None
        assert v.significance == "Pathogenic"


# ---------------------------------------------------------------------------
# _esearch
# ---------------------------------------------------------------------------


class TestEsearch:
    @resp_mock.activate
    def test_returns_uids(self) -> None:
        resp_mock.add(resp_mock.GET, ESEARCH_URL, json=_esearch_payload(["111", "222"]), status=200)
        uids = _esearch(REGION_A, EUTILS_BASE)
        assert uids == ["111", "222"]

    @resp_mock.activate
    def test_no_hits_returns_empty_list(self) -> None:
        resp_mock.add(resp_mock.GET, ESEARCH_URL, json=_esearch_payload([]), status=200)
        uids = _esearch(REGION_EMPTY, EUTILS_BASE)
        assert uids == []

    @resp_mock.activate
    def test_chr_prefix_stripped_in_query(self) -> None:
        resp_mock.add(resp_mock.GET, ESEARCH_URL, json=_esearch_payload(["1"]), status=200)
        _esearch(REGION_A, EUTILS_BASE)  # region has "chr1"
        call_url = resp_mock.calls[0].request.url
        # The term must use "1[CHR]" not "chr1[CHR]"
        assert "1%5BCHR%5D" in call_url or "1[CHR]" in call_url
        assert "chr1" not in call_url.lower().split("term=")[1].split("&")[0]

    @resp_mock.activate
    def test_http_error_raises(self) -> None:
        resp_mock.add(resp_mock.GET, ESEARCH_URL, status=500)
        with pytest.raises(Exception):
            _esearch(REGION_A, EUTILS_BASE)


# ---------------------------------------------------------------------------
# _esummary
# ---------------------------------------------------------------------------


class TestEsummary:
    @resp_mock.activate
    def test_returns_clinvar_variants(self) -> None:
        payload = _esummary_payload({"12345": _variant_entry(uid="12345")})
        resp_mock.add(resp_mock.GET, ESUMMARY_URL, json=payload, status=200)
        variants = _esummary(["12345"], EUTILS_BASE)
        assert len(variants) == 1
        assert variants[0].uid == "12345"
        assert variants[0].significance == "Pathogenic"

    @resp_mock.activate
    def test_multiple_variants(self) -> None:
        payload = _esummary_payload(
            {
                "111": _variant_entry(uid="111", significance="Pathogenic", gene="BRCA1"),
                "222": _variant_entry(uid="222", significance="Likely pathogenic", gene="TP53"),
            }
        )
        resp_mock.add(resp_mock.GET, ESUMMARY_URL, json=payload, status=200)
        variants = _esummary(["111", "222"], EUTILS_BASE)
        assert len(variants) == 2
        sigs = {v.significance for v in variants}
        assert "Pathogenic" in sigs
        assert "Likely pathogenic" in sigs

    @resp_mock.activate
    def test_empty_result_block(self) -> None:
        resp_mock.add(resp_mock.GET, ESUMMARY_URL, json={"result": {"uids": []}}, status=200)
        variants = _esummary(["999"], EUTILS_BASE)
        assert variants == []

    @resp_mock.activate
    def test_http_error_raises(self) -> None:
        resp_mock.add(resp_mock.GET, ESUMMARY_URL, status=503)
        with pytest.raises(Exception):
            _esummary(["1"], EUTILS_BASE)


# ---------------------------------------------------------------------------
# _search_clinvar_region — cache hit
# ---------------------------------------------------------------------------


class TestSearchClinvarRegion:
    def test_cache_hit_returns_without_http(self) -> None:
        cached_data = {
            "variants": [
                {
                    "uid": "42",
                    "position": 100_500,
                    "significance": "Pathogenic",
                    "condition": "Cancer",
                    "gene": "BRCA2",
                }
            ]
        }
        mock_cache = _mock_cache(hit=cached_data)
        config = OrcSonarConfig()

        variants = _search_clinvar_region(REGION_A, config, mock_cache)
        assert len(variants) == 1
        assert variants[0].uid == "42"
        assert variants[0].gene == "BRCA2"
        # No HTTP calls should have been made
        mock_cache.get.assert_called_once()

    @resp_mock.activate
    def test_api_failure_returns_empty_gracefully(self) -> None:
        resp_mock.add(resp_mock.GET, ESEARCH_URL, status=500)
        mock_cache = _mock_cache(hit=None)
        config = OrcSonarConfig()

        # Should not raise — graceful degradation
        variants = _search_clinvar_region(REGION_A, config, mock_cache)
        assert variants == []

    @resp_mock.activate
    def test_results_are_stored_in_cache(self) -> None:
        resp_mock.add(resp_mock.GET, ESEARCH_URL, json=_esearch_payload(["7"]), status=200)
        resp_mock.add(
            resp_mock.GET,
            ESUMMARY_URL,
            json=_esummary_payload({"7": _variant_entry(uid="7")}),
            status=200,
        )
        mock_cache = _mock_cache(hit=None)
        config = OrcSonarConfig()

        variants = _search_clinvar_region(REGION_A, config, mock_cache)
        assert len(variants) == 1
        mock_cache.set.assert_called_once()
        # Verify the key contains the region coordinates
        key_used = mock_cache.set.call_args[0][0]
        assert "clinvar" in key_used
        assert "chr1" in key_used


# ---------------------------------------------------------------------------
# check_clinvar — top-level
# ---------------------------------------------------------------------------


class TestCheckClinvar:
    @patch("src.stage3_variant_tox.clinvar_client.Cache")
    @resp_mock.activate
    def test_pathogenic_count(self, MockCache) -> None:
        resp_mock.add(resp_mock.GET, ESEARCH_URL, json=_esearch_payload(["1", "2"]), status=200)
        resp_mock.add(
            resp_mock.GET,
            ESUMMARY_URL,
            json=_esummary_payload(
                {
                    "1": _variant_entry(uid="1", significance="Pathogenic"),
                    "2": _variant_entry(uid="2", significance="Likely pathogenic"),
                }
            ),
            status=200,
        )
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)
        config = OrcSonarConfig()

        results = check_clinvar([REGION_A], config)
        assert len(results) == 1
        r = results[0]
        assert isinstance(r, ClinvarResult)
        assert r.pathogenic_count == 1
        assert r.likely_pathogenic_count == 1
        assert len(r.variants) == 2

    @patch("src.stage3_variant_tox.clinvar_client.Cache")
    @resp_mock.activate
    def test_no_variants_region(self, MockCache) -> None:
        resp_mock.add(resp_mock.GET, ESEARCH_URL, json=_esearch_payload([]), status=200)
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)
        config = OrcSonarConfig()

        results = check_clinvar([REGION_EMPTY], config)
        assert results[0].pathogenic_count == 0
        assert results[0].likely_pathogenic_count == 0
        assert results[0].variants == []

    @patch("src.stage3_variant_tox.clinvar_client.Cache")
    @resp_mock.activate
    def test_preserves_input_order(self, MockCache) -> None:
        resp_mock.add(resp_mock.GET, ESEARCH_URL, json=_esearch_payload(["1"]), status=200)
        resp_mock.add(
            resp_mock.GET,
            ESUMMARY_URL,
            json=_esummary_payload({"1": _variant_entry(uid="1")}),
            status=200,
        )
        resp_mock.add(resp_mock.GET, ESEARCH_URL, json=_esearch_payload([]), status=200)
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)
        config = OrcSonarConfig()

        results = check_clinvar([REGION_A, REGION_EMPTY], config)
        assert len(results) == 2
        assert results[0].region == REGION_A
        assert results[1].region == REGION_EMPTY

    @patch("src.stage3_variant_tox.clinvar_client.Cache")
    def test_empty_input_returns_empty_list(self, MockCache) -> None:
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)
        config = OrcSonarConfig()
        results = check_clinvar([], config)
        assert results == []

    @patch("src.stage3_variant_tox.clinvar_client.Cache")
    @resp_mock.activate
    def test_returns_clinvar_result_instance(self, MockCache) -> None:
        resp_mock.add(resp_mock.GET, ESEARCH_URL, json=_esearch_payload([]), status=200)
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)
        config = OrcSonarConfig()
        results = check_clinvar([REGION_A], config)
        assert isinstance(results[0], ClinvarResult)
        assert results[0].region == REGION_A

    @patch("src.stage3_variant_tox.clinvar_client.Cache")
    @resp_mock.activate
    def test_api_failure_does_not_raise(self, MockCache) -> None:
        resp_mock.add(resp_mock.GET, ESEARCH_URL, status=503)
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)
        config = OrcSonarConfig()
        # Should not propagate the exception
        results = check_clinvar([REGION_A], config)
        assert results[0].pathogenic_count == 0
        assert results[0].variants == []
