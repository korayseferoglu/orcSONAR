"""Unit tests for src/stage2_offtarget_scan/repeat_scanner.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import responses as resp_mock

from src.core.config import OrcSonarConfig
from src.core.models import GenomicRegion, RepeatEntry, RepeatResult
from src.stage2_offtarget_scan.repeat_scanner import (
    _classify_risk,
    _fetch_rmsk,
    _query_ucsc_rmsk,
    scan_repeats,
)

# ---------------------------------------------------------------------------
# Constants & helpers
# ---------------------------------------------------------------------------

UCSC_URL = "https://api.genome.ucsc.edu/getData/track"

REGION_ALU = GenomicRegion(chrom="chr1", start=100_000, end=101_000, strand="+")
REGION_LINE = GenomicRegion(chrom="chr2", start=200_000, end=201_000, strand="-")
REGION_EMPTY = GenomicRegion(chrom="chr3", start=300_000, end=301_000, strand=".")


def _rmsk_payload(items: list[dict]) -> dict:
    return {"rmsk": items}


def _alu_item(
    chrom: str = "chr1",
    start: int = 100_100,
    end: int = 100_400,
) -> dict:
    """UCSC API response format — use in HTTP mock payloads."""
    return {
        "genoName": chrom,
        "genoStart": start,
        "genoEnd": end,
        "repName": "AluSx",
        "repClass": "SINE",
        "repFamily": "Alu",
    }


def _line_item(
    chrom: str = "chr2",
    start: int = 200_100,
    end: int = 200_800,
) -> dict:
    """UCSC API response format — use in HTTP mock payloads."""
    return {
        "genoName": chrom,
        "genoStart": start,
        "genoEnd": end,
        "repName": "L1HS",
        "repClass": "LINE",
        "repFamily": "L1",
    }


def _alu_entry_kwargs(
    chrom: str = "chr1",
    start: int = 100_100,
    end: int = 100_400,
) -> dict:
    """RepeatEntry field names — use for direct model construction and cache payloads."""
    return {
        "chrom": chrom,
        "start": start,
        "end": end,
        "rep_name": "AluSx",
        "rep_class": "SINE",
        "rep_family": "Alu",
    }


def _line_entry_kwargs(
    chrom: str = "chr2",
    start: int = 200_100,
    end: int = 200_800,
) -> dict:
    """RepeatEntry field names — use for direct model construction and cache payloads."""
    return {
        "chrom": chrom,
        "start": start,
        "end": end,
        "rep_name": "L1HS",
        "rep_class": "LINE",
        "rep_family": "L1",
    }


def _mock_cache(hit: dict | None = None) -> MagicMock:
    """Cache mock: .get() returns *hit*, .set() is a no-op."""
    cache = MagicMock()
    cache.get.return_value = hit
    return cache


# ---------------------------------------------------------------------------
# _classify_risk
# ---------------------------------------------------------------------------


class TestClassifyRisk:
    def test_no_repeats(self) -> None:
        has_alu, has_line, score = _classify_risk([])
        assert has_alu is False
        assert has_line is False
        assert score == 0.0

    def test_alu_only(self) -> None:
        entry = RepeatEntry(**_alu_entry_kwargs())
        has_alu, has_line, score = _classify_risk([entry])
        assert has_alu is True
        assert has_line is False
        assert score == pytest.approx(0.8)

    def test_line_only(self) -> None:
        entry = RepeatEntry(**_line_entry_kwargs())
        has_alu, has_line, score = _classify_risk([entry])
        assert has_alu is False
        assert has_line is True
        assert score == pytest.approx(0.3)

    def test_alu_and_line_score_capped_at_one(self) -> None:
        entries = [RepeatEntry(**_alu_entry_kwargs()), RepeatEntry(**_line_entry_kwargs())]
        has_alu, has_line, score = _classify_risk(entries)
        assert has_alu is True
        assert has_line is True
        assert score == pytest.approx(1.0)

    def test_non_alu_sine_not_flagged_as_alu(self) -> None:
        # MIR is a SINE but not Alu family
        entry = RepeatEntry(
            chrom="chr1", start=1000, end=1200,
            rep_name="MIRb", rep_class="SINE", rep_family="MIR",
        )
        has_alu, has_line, score = _classify_risk([entry])
        assert has_alu is False

    def test_multiple_alu_elements_still_single_flag(self) -> None:
        entries = [RepeatEntry(**_alu_entry_kwargs(start=100_000, end=100_200)),
                   RepeatEntry(**_alu_entry_kwargs(start=100_300, end=100_500))]
        has_alu, has_line, score = _classify_risk(entries)
        assert has_alu is True
        assert score == pytest.approx(0.8)  # not doubled


# ---------------------------------------------------------------------------
# _fetch_rmsk  (HTTP layer, retries stubbed via responses + sleep patch)
# ---------------------------------------------------------------------------


class TestFetchRmsk:
    @resp_mock.activate
    def test_alu_detection(self) -> None:
        resp_mock.add(resp_mock.GET, UCSC_URL, json=_rmsk_payload([_alu_item()]), status=200)
        entries = _fetch_rmsk(REGION_ALU, UCSC_URL)
        assert len(entries) == 1
        assert entries[0].rep_family == "Alu"
        assert entries[0].rep_class == "SINE"
        assert entries[0].rep_name == "AluSx"

    @resp_mock.activate
    def test_line_detection(self) -> None:
        resp_mock.add(resp_mock.GET, UCSC_URL, json=_rmsk_payload([_line_item()]), status=200)
        entries = _fetch_rmsk(REGION_LINE, UCSC_URL)
        assert len(entries) == 1
        assert entries[0].rep_class == "LINE"
        assert entries[0].rep_name == "L1HS"

    @resp_mock.activate
    def test_no_repeats(self) -> None:
        resp_mock.add(resp_mock.GET, UCSC_URL, json=_rmsk_payload([]), status=200)
        entries = _fetch_rmsk(REGION_EMPTY, UCSC_URL)
        assert entries == []

    @patch("tenacity.nap.sleep")
    @resp_mock.activate
    def test_api_retry_on_failure(self, _mock_sleep) -> None:
        resp_mock.add(resp_mock.GET, UCSC_URL, status=500)
        resp_mock.add(resp_mock.GET, UCSC_URL, status=500)
        resp_mock.add(resp_mock.GET, UCSC_URL, json=_rmsk_payload([_alu_item()]), status=200)
        entries = _fetch_rmsk(REGION_ALU, UCSC_URL)
        assert len(entries) == 1
        assert entries[0].rep_family == "Alu"

    @patch("tenacity.nap.sleep")
    @resp_mock.activate
    def test_all_retries_exhausted_raises(self, _mock_sleep) -> None:
        for _ in range(3):
            resp_mock.add(resp_mock.GET, UCSC_URL, status=503)
        with pytest.raises(Exception):
            _fetch_rmsk(REGION_EMPTY, UCSC_URL)

    @resp_mock.activate
    def test_multiple_elements_all_parsed(self) -> None:
        resp_mock.add(
            resp_mock.GET,
            UCSC_URL,
            json=_rmsk_payload([_alu_item(), _line_item("chr1", 100_500, 100_700)]),
            status=200,
        )
        entries = _fetch_rmsk(REGION_ALU, UCSC_URL)
        assert len(entries) == 2

    @resp_mock.activate
    def test_correct_query_params_sent(self) -> None:
        resp_mock.add(resp_mock.GET, UCSC_URL, json=_rmsk_payload([]), status=200)
        _fetch_rmsk(REGION_ALU, UCSC_URL)
        req = resp_mock.calls[0].request
        assert "genome=hg38" in req.url
        assert "track=rmsk" in req.url
        assert "chrom=chr1" in req.url


# ---------------------------------------------------------------------------
# _query_ucsc_rmsk  (cache layer)
# ---------------------------------------------------------------------------


class TestQueryUcscRmsk:
    def test_cache_hit_returns_entries_without_http(self) -> None:
        cached_payload = {"entries": [_alu_entry_kwargs()]}
        mock_cache = _mock_cache(hit=cached_payload)
        config = OrcSonarConfig()
        entries = _query_ucsc_rmsk(REGION_ALU, config, mock_cache)
        assert len(entries) == 1
        assert entries[0].rep_family == "Alu"
        mock_cache.get.assert_called_once()
        mock_cache.set.assert_not_called()

    @resp_mock.activate
    def test_cache_miss_fetches_and_writes_cache(self) -> None:
        resp_mock.add(resp_mock.GET, UCSC_URL, json=_rmsk_payload([_line_item()]), status=200)
        mock_cache = _mock_cache(hit=None)
        config = OrcSonarConfig()
        entries = _query_ucsc_rmsk(REGION_LINE, config, mock_cache)
        assert len(entries) == 1
        assert entries[0].rep_class == "LINE"
        mock_cache.set.assert_called_once()

    @patch("tenacity.nap.sleep")
    @resp_mock.activate
    def test_api_failure_returns_empty_and_still_caches(self, _mock_sleep) -> None:
        for _ in range(3):
            resp_mock.add(resp_mock.GET, UCSC_URL, status=503)
        mock_cache = _mock_cache(hit=None)
        config = OrcSonarConfig()
        entries = _query_ucsc_rmsk(REGION_EMPTY, config, mock_cache)
        assert entries == []
        mock_cache.set.assert_called_once()
        stored = mock_cache.set.call_args[0][1]
        assert stored["entries"] == []

    def test_cache_key_includes_coordinates(self) -> None:
        """Cache must be keyed by chrom:start:end so different regions don't collide."""
        cached_payload = {"entries": [_alu_entry_kwargs()]}
        mock_cache = _mock_cache(hit=cached_payload)
        config = OrcSonarConfig()
        _query_ucsc_rmsk(REGION_ALU, config, mock_cache)
        key_used = mock_cache.get.call_args[0][0]
        assert "chr1" in key_used
        assert str(REGION_ALU.start) in key_used
        assert str(REGION_ALU.end) in key_used


# ---------------------------------------------------------------------------
# scan_repeats  (top-level, patches Cache class)
# ---------------------------------------------------------------------------


class TestScanRepeats:
    @patch("src.stage2_offtarget_scan.repeat_scanner.Cache")
    @resp_mock.activate
    def test_scan_alu_region(self, MockCache) -> None:
        resp_mock.add(resp_mock.GET, UCSC_URL, json=_rmsk_payload([_alu_item()]), status=200)
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)
        config = OrcSonarConfig()
        results = scan_repeats([REGION_ALU], config)
        assert len(results) == 1
        assert results[0].has_alu is True
        assert results[0].adar_risk_score == pytest.approx(0.8)

    @patch("src.stage2_offtarget_scan.repeat_scanner.Cache")
    @resp_mock.activate
    def test_scan_line_region(self, MockCache) -> None:
        resp_mock.add(resp_mock.GET, UCSC_URL, json=_rmsk_payload([_line_item()]), status=200)
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)
        config = OrcSonarConfig()
        results = scan_repeats([REGION_LINE], config)
        assert results[0].has_line is True
        assert results[0].adar_risk_score == pytest.approx(0.3)

    @patch("src.stage2_offtarget_scan.repeat_scanner.Cache")
    @resp_mock.activate
    def test_scan_empty_region(self, MockCache) -> None:
        resp_mock.add(resp_mock.GET, UCSC_URL, json=_rmsk_payload([]), status=200)
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)
        config = OrcSonarConfig()
        results = scan_repeats([REGION_EMPTY], config)
        assert results[0].has_alu is False
        assert results[0].has_line is False
        assert results[0].adar_risk_score == 0.0

    @patch("src.stage2_offtarget_scan.repeat_scanner.Cache")
    @resp_mock.activate
    def test_scan_preserves_input_order(self, MockCache) -> None:
        resp_mock.add(resp_mock.GET, UCSC_URL, json=_rmsk_payload([_alu_item()]), status=200)
        resp_mock.add(resp_mock.GET, UCSC_URL, json=_rmsk_payload([]), status=200)
        resp_mock.add(resp_mock.GET, UCSC_URL, json=_rmsk_payload([_line_item()]), status=200)
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)
        config = OrcSonarConfig()
        results = scan_repeats([REGION_ALU, REGION_EMPTY, REGION_LINE], config)
        assert len(results) == 3
        assert results[0].has_alu is True
        assert results[1].has_alu is False
        assert results[2].has_line is True

    @patch("src.stage2_offtarget_scan.repeat_scanner.Cache")
    @resp_mock.activate
    def test_scan_returns_repeat_result_instances(self, MockCache) -> None:
        resp_mock.add(resp_mock.GET, UCSC_URL, json=_rmsk_payload([_alu_item()]), status=200)
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)
        config = OrcSonarConfig()
        results = scan_repeats([REGION_ALU], config)
        assert isinstance(results[0], RepeatResult)
        assert results[0].region == REGION_ALU

    @patch("src.stage2_offtarget_scan.repeat_scanner.Cache")
    @resp_mock.activate
    def test_scan_empty_input_returns_empty_list(self, MockCache) -> None:
        MockCache.return_value.__enter__ = lambda s: _mock_cache(hit=None)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)
        config = OrcSonarConfig()
        results = scan_repeats([], config)
        assert results == []
