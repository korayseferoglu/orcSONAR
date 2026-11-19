"""Unit tests for src/stage3_variant_tox/gnomad_client.py."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import requests
import responses as resp_mock

from src.core.config import OrcSonarConfig
from src.core.models import GenomicRegion, GnomadResult, GnomadVariant
from src.stage3_variant_tox.gnomad_client import (
    _calculate_polymorphism_score,
    _fetch_variants,
    _graphql_query,
    _parse_variants,
    query_gnomad,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GNOMAD_API = "https://gnomad.broadinstitute.org/api"

REGION_A = GenomicRegion(chrom="chr1", start=100_000, end=101_000, strand="+")
REGION_B = GenomicRegion(chrom="chrX", start=50_000, end=51_000, strand=".")
REGION_EMPTY = GenomicRegion(chrom="chr22", start=10_000, end=11_000, strand=".")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Neutralise rate-limit sleeps so tests run fast and deterministically."""
    monkeypatch.setattr("src.stage3_variant_tox.gnomad_client.time.sleep", lambda _s: None)


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------


def _api_response(variants: list[dict]) -> dict:
    return {"data": {"region": {"variants": variants}}}


def _variant_item(
    variant_id: str = "1-100500-A-T",
    pos: int = 100_500,
    ref: str = "A",
    alt: str = "T",
    genome_af: float | None = 0.05,
    exome_af: float | None = None,
) -> dict:
    return {
        "variant_id": variant_id,
        "pos": pos,
        "ref": ref,
        "alt": alt,
        "genome": {"af": genome_af} if genome_af is not None else None,
        "exome": {"af": exome_af} if exome_af is not None else None,
    }


def _mock_cache(hit: dict | None = None) -> MagicMock:
    cache = MagicMock()
    cache.get.return_value = hit
    return cache


# ---------------------------------------------------------------------------
# _graphql_query
# ---------------------------------------------------------------------------


class TestGraphqlQuery:
    def test_contains_chrom_without_prefix(self) -> None:
        q = _graphql_query("1", 100_000, 101_000)
        assert '"1"' in q
        assert "chr1" not in q

    def test_contains_start_and_stop(self) -> None:
        q = _graphql_query("17", 7_668_400, 7_668_500)
        assert "7668400" in q
        assert "7668500" in q

    def test_contains_gnomad_r4_dataset(self) -> None:
        q = _graphql_query("1", 0, 1000)
        assert "gnomad_r4" in q

    def test_contains_required_fields(self) -> None:
        q = _graphql_query("1", 0, 1000)
        for field in ("variant_id", "pos", "ref", "alt", "genome", "exome", "af"):
            assert field in q

    def test_contains_reference_genome_grch38(self) -> None:
        # gnomAD v4 schema: region(...) requires reference_genome (enum, unquoted)
        q = _graphql_query("1", 0, 1000)
        assert "reference_genome: GRCh38" in q

    def test_dataset_argument_on_variants_field(self) -> None:
        # gnomAD v4 schema: dataset moved from region(...) to region.variants(...)
        q = _graphql_query("1", 0, 1000)
        assert "variants(dataset: gnomad_r4)" in q


# ---------------------------------------------------------------------------
# _parse_variants
# ---------------------------------------------------------------------------


class TestParseVariants:
    def test_genome_af_only(self) -> None:
        raw = [_variant_item(genome_af=0.05, exome_af=None)]
        variants = _parse_variants(raw)
        assert len(variants) == 1
        assert variants[0].allele_frequency == pytest.approx(0.05)

    def test_exome_af_only(self) -> None:
        raw = [_variant_item(genome_af=None, exome_af=0.03)]
        variants = _parse_variants(raw)
        assert variants[0].allele_frequency == pytest.approx(0.03)

    def test_takes_max_of_genome_and_exome(self) -> None:
        raw = [_variant_item(genome_af=0.02, exome_af=0.08)]
        variants = _parse_variants(raw)
        assert variants[0].allele_frequency == pytest.approx(0.08)

    def test_null_genome_and_exome_gives_zero_af(self) -> None:
        raw = [_variant_item(genome_af=None, exome_af=None)]
        variants = _parse_variants(raw)
        assert variants[0].allele_frequency == pytest.approx(0.0)

    def test_fields_parsed_correctly(self) -> None:
        raw = [_variant_item(variant_id="1-100500-A-T", pos=100_500, ref="A", alt="T", genome_af=0.01)]
        v = _parse_variants(raw)[0]
        assert v.variant_id == "1-100500-A-T"
        assert v.position == 100_500
        assert v.ref == "A"
        assert v.alt == "T"

    def test_empty_list(self) -> None:
        assert _parse_variants([]) == []

    def test_malformed_entry_skipped(self) -> None:
        raw = [{"bad_key": "no variant_id"}]
        variants = _parse_variants(raw)
        assert variants == []

    def test_af_clamped_to_one(self) -> None:
        raw = [_variant_item(genome_af=1.5)]  # API quirk — clamp to 1.0
        variants = _parse_variants(raw)
        assert variants[0].allele_frequency == pytest.approx(1.0)

    def test_negative_af_clamped_to_zero(self) -> None:
        raw = [_variant_item(genome_af=-0.001)]
        variants = _parse_variants(raw)
        assert variants[0].allele_frequency == pytest.approx(0.0)

    def test_returns_gnomad_variant_instances(self) -> None:
        raw = [_variant_item()]
        variants = _parse_variants(raw)
        assert all(isinstance(v, GnomadVariant) for v in variants)


# ---------------------------------------------------------------------------
# _calculate_polymorphism_score
# ---------------------------------------------------------------------------


class TestCalculatePolymorphismScore:
    def _make_variants(self, afs: list[float]) -> list[GnomadVariant]:
        return [
            GnomadVariant(variant_id=f"1-{i}-A-T", position=i, ref="A", alt="T", allele_frequency=af)
            for i, af in enumerate(afs)
        ]

    def test_no_variants_returns_one(self) -> None:
        assert _calculate_polymorphism_score([]) == pytest.approx(1.0)

    def test_common_snp_saturates_to_zero(self) -> None:
        # max_af = 0.05 >= 0.01 → score = 0.0
        variants = self._make_variants([0.05])
        assert _calculate_polymorphism_score(variants) == pytest.approx(0.0)

    def test_exactly_threshold_gives_zero(self) -> None:
        # max_af = 0.01 → 1 - 0.01/0.01 = 0.0
        variants = self._make_variants([0.01])
        assert _calculate_polymorphism_score(variants) == pytest.approx(0.0)

    def test_half_threshold_gives_half(self) -> None:
        # max_af = 0.005 → 1 - 0.005/0.01 = 0.5
        variants = self._make_variants([0.005])
        assert _calculate_polymorphism_score(variants) == pytest.approx(0.5)

    def test_very_rare_variant_near_one(self) -> None:
        # max_af = 0.0001 → 1 - 0.0001/0.01 = 0.99
        variants = self._make_variants([0.0001])
        assert _calculate_polymorphism_score(variants) == pytest.approx(0.99)

    def test_takes_max_across_multiple_variants(self) -> None:
        # highest AF drives the score
        variants = self._make_variants([0.0001, 0.005, 0.008])
        score = _calculate_polymorphism_score(variants)
        # max_af = 0.008 → 1 - 0.008/0.01 = 0.2
        assert score == pytest.approx(0.2)

    def test_zero_af_gives_one(self) -> None:
        # AF of zero → completely conserved at population level → max risk
        variants = self._make_variants([0.0])
        assert _calculate_polymorphism_score(variants) == pytest.approx(1.0)

    def test_score_bounded_above_one(self) -> None:
        # Should never exceed 1.0 regardless of AF
        variants = self._make_variants([0.0])
        assert _calculate_polymorphism_score(variants) <= 1.0

    def test_score_bounded_below_zero(self) -> None:
        # Should never go below 0.0
        variants = self._make_variants([0.5])
        assert _calculate_polymorphism_score(variants) >= 0.0


# ---------------------------------------------------------------------------
# _fetch_variants
# ---------------------------------------------------------------------------


class TestFetchVariants:
    @resp_mock.activate
    def test_parses_variants_from_response(self) -> None:
        resp_mock.add(
            resp_mock.POST,
            GNOMAD_API,
            json=_api_response([_variant_item(genome_af=0.02)]),
            status=200,
        )
        variants = _fetch_variants(REGION_A, GNOMAD_API)
        assert len(variants) == 1
        assert variants[0].allele_frequency == pytest.approx(0.02)

    @resp_mock.activate
    def test_empty_region_returns_empty_list(self) -> None:
        resp_mock.add(resp_mock.POST, GNOMAD_API, json=_api_response([]), status=200)
        variants = _fetch_variants(REGION_EMPTY, GNOMAD_API)
        assert variants == []

    @resp_mock.activate
    def test_chr_prefix_stripped_in_query(self) -> None:
        resp_mock.add(resp_mock.POST, GNOMAD_API, json=_api_response([]), status=200)
        _fetch_variants(REGION_A, GNOMAD_API)  # REGION_A has "chr1"
        body = json.loads(resp_mock.calls[0].request.body)
        assert '"1"' in body["query"]
        assert "chr1" not in body["query"]

    @resp_mock.activate
    def test_http_error_raises(self) -> None:
        resp_mock.add(resp_mock.POST, GNOMAD_API, status=500)
        with pytest.raises(requests.HTTPError, match="500"):
            _fetch_variants(REGION_A, GNOMAD_API)

    @resp_mock.activate
    def test_null_region_in_response(self) -> None:
        # gnomAD returns null for region when chromosome/coordinates are invalid
        resp_mock.add(
            resp_mock.POST, GNOMAD_API, json={"data": {"region": None}}, status=200
        )
        variants = _fetch_variants(REGION_A, GNOMAD_API)
        assert variants == []

    @resp_mock.activate
    def test_429_triggers_backoff_then_succeeds(self) -> None:
        # First response is 429 → tenacity retries → second response succeeds.
        resp_mock.add(resp_mock.POST, GNOMAD_API, status=429)
        resp_mock.add(
            resp_mock.POST,
            GNOMAD_API,
            json=_api_response([_variant_item(genome_af=0.02)]),
            status=200,
        )
        variants = _fetch_variants(REGION_A, GNOMAD_API)
        assert len(variants) == 1
        assert variants[0].allele_frequency == pytest.approx(0.02)

    @resp_mock.activate
    def test_graphql_errors_array_raises(self) -> None:
        # gnomAD reports schema errors as 200 + {"errors": [...]} — must not be silently dropped.
        resp_mock.add(
            resp_mock.POST,
            GNOMAD_API,
            json={"errors": [{"message": "bad argument"}]},
            status=200,
        )
        # A GraphQL error arrives with HTTP 200, so this is NOT an HTTPError.
        # Today the client raises a bare RuntimeError rather than the project's
        # APIError; the test records what it does, and the inconsistency is
        # noted in H15's row rather than changed here (invariant 8).
        with pytest.raises(RuntimeError, match="GraphQL"):
            _fetch_variants(REGION_A, GNOMAD_API)


# ---------------------------------------------------------------------------
# query_gnomad — top-level
# ---------------------------------------------------------------------------


class TestQueryGnomad:
    @patch("src.stage3_variant_tox.gnomad_client.Cache")
    @resp_mock.activate
    def test_common_variant_low_polymorphism_score(self, MockCache) -> None:
        resp_mock.add(
            resp_mock.POST,
            GNOMAD_API,
            json=_api_response([_variant_item(genome_af=0.05)]),
            status=200,
        )
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)
        config = OrcSonarConfig()
        results = query_gnomad([REGION_A], config)
        assert len(results) == 1
        r = results[0]
        assert isinstance(r, GnomadResult)
        assert r.polymorphism_score == pytest.approx(0.0)  # af=0.05 >= 0.01
        assert r.max_af == pytest.approx(0.05)
        assert r.variant_count == 1

    @patch("src.stage3_variant_tox.gnomad_client.Cache")
    @resp_mock.activate
    def test_no_variants_high_polymorphism_score(self, MockCache) -> None:
        resp_mock.add(resp_mock.POST, GNOMAD_API, json=_api_response([]), status=200)
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)
        config = OrcSonarConfig()
        results = query_gnomad([REGION_EMPTY], config)
        r = results[0]
        assert r.polymorphism_score == pytest.approx(1.0)
        assert r.variant_count == 0
        assert r.max_af == pytest.approx(0.0)

    @patch("src.stage3_variant_tox.gnomad_client.Cache")
    @resp_mock.activate
    def test_api_failure_is_unknown_not_a_mid_scale_score(self, MockCache) -> None:
        resp_mock.add(resp_mock.POST, GNOMAD_API, status=503)
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)
        config = OrcSonarConfig()
        results = query_gnomad([REGION_A], config)
        # Inverted 2026-11-19 (audit Bulgu 2/5). This asserted the
        # fallback *numbers*, pinning "a dead source reads as a measurement"
        # as the contract. The name said "returns neutral"; there is no
        # neutral value on a risk channel, only an unknown one.
        assert results[0].polymorphism_score is None
        assert results[0].variant_count is None

    @patch("src.stage3_variant_tox.gnomad_client.Cache")
    def test_cache_hit_skips_http(self, MockCache) -> None:
        cached_data = {
            "variants": [
                {
                    "variant_id": "1-100500-A-T",
                    "position": 100_500,
                    "ref": "A",
                    "alt": "T",
                    "allele_frequency": 0.03,
                }
            ]
        }
        mock_cache = _mock_cache(hit=cached_data)
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)
        config = OrcSonarConfig()
        results = query_gnomad([REGION_A], config)
        assert results[0].variant_count == 1
        assert results[0].max_af == pytest.approx(0.03)
        mock_cache.get.assert_called_once()

    @patch("src.stage3_variant_tox.gnomad_client.Cache")
    @resp_mock.activate
    def test_preserves_input_order(self, MockCache) -> None:
        resp_mock.add(resp_mock.POST, GNOMAD_API, json=_api_response([_variant_item()]), status=200)
        resp_mock.add(resp_mock.POST, GNOMAD_API, json=_api_response([]), status=200)
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)
        config = OrcSonarConfig()
        results = query_gnomad([REGION_A, REGION_EMPTY], config)
        assert len(results) == 2
        assert results[0].region == REGION_A
        assert results[1].region == REGION_EMPTY

    @patch("src.stage3_variant_tox.gnomad_client.Cache")
    def test_empty_input_returns_empty_list(self, MockCache) -> None:
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)
        config = OrcSonarConfig()
        results = query_gnomad([], config)
        assert results == []

    @patch("src.stage3_variant_tox.gnomad_client.Cache")
    @resp_mock.activate
    def test_cache_set_called_on_miss(self, MockCache) -> None:
        resp_mock.add(resp_mock.POST, GNOMAD_API, json=_api_response([_variant_item()]), status=200)
        mock_cache = _mock_cache(hit=None)
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)
        config = OrcSonarConfig()
        query_gnomad([REGION_A], config)
        mock_cache.set.assert_called_once()
        key = mock_cache.set.call_args[0][0]
        assert "gnomad" in key
        assert "chr1" in key

    @patch("src.stage3_variant_tox.gnomad_client.Cache")
    @resp_mock.activate
    def test_rare_variant_high_score(self, MockCache) -> None:
        resp_mock.add(
            resp_mock.POST,
            GNOMAD_API,
            json=_api_response([_variant_item(genome_af=0.0001)]),
            status=200,
        )
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)
        config = OrcSonarConfig()
        results = query_gnomad([REGION_A], config)
        # max_af = 0.0001 → score = 1 - 0.0001/0.01 = 0.99
        assert results[0].polymorphism_score == pytest.approx(0.99)
