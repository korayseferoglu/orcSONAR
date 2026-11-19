"""Unit tests for src/stage4_epigenetic/hic_contacts.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml as _yaml

from src.core.config import load_config
from src.core.models import GenomicRegion, HiCResult
from src.stage4_epigenetic.hic_contacts import (
    _NEUTRAL_CONTACT,
    HiCContactReader,
    _contact_cache_key,
    _round_bin,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RESOLUTION = 25_000

# chr6:43_768_652 → bin 43_750_000  (43768652 // 25000 * 25000)
TARGET = GenomicRegion(chrom="chr6", start=43_768_652, end=43_769_652, strand="+")
# chr17:7_000_000 → bin 7_000_000
OFFTARGET = GenomicRegion(chrom="chr17", start=7_000_000, end=7_001_000, strand="-")
OFFTARGET_2 = GenomicRegion(chrom="chr1", start=1_000, end=2_000, strand=".")

HIC_URL = "https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/wfoutput/abc123/4DNFI.hic"

CELL_LINES = {
    "HeLa": {"hic_url": HIC_URL},
    "K562": {"hic_url": None},    # null — neutral expected
    "A549": {},                    # missing key — neutral expected
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_reader(tmp_path: Path, cell_lines: dict | None = None) -> HiCContactReader:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "target_gene: VEGFA\ncell_line: HeLa\nsarna_sequence: GCAACCATAGCCTCGGCCGC\n",
        encoding="utf-8",
    )
    config = load_config(cfg_file)
    config.data_paths.cache_db = str(tmp_path / "cache.db")

    yaml_path = tmp_path / "cell_lines.yaml"
    yaml_path.write_text(_yaml.dump(cell_lines or CELL_LINES), encoding="utf-8")
    return HiCContactReader(config, cell_lines_yaml=yaml_path)


def _make_record(bin_x: int, bin_y: int, counts: float) -> MagicMock:
    rec = MagicMock()
    rec.binX = bin_x
    rec.binY = bin_y
    rec.counts = counts
    return rec


def _mock_cache_hit(contact: float) -> MagicMock:
    cache = MagicMock()
    cache.get.return_value = {"contact": contact}
    return cache


def _mock_cache_miss() -> MagicMock:
    cache = MagicMock()
    cache.get.return_value = None
    return cache


def _ctx(mock_cache: MagicMock) -> MagicMock:
    MockCache = MagicMock()
    MockCache.return_value.__enter__ = lambda s: mock_cache
    MockCache.return_value.__exit__ = MagicMock(return_value=False)
    return MockCache


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_round_bin_exact(self) -> None:
        assert _round_bin(25_000, 25_000) == 25_000

    def test_round_bin_rounds_down(self) -> None:
        assert _round_bin(43_768_652, 25_000) == 43_750_000

    def test_round_bin_zero(self) -> None:
        assert _round_bin(1_000, 25_000) == 0

    def test_contact_cache_key_structure(self) -> None:
        key = _contact_cache_key(HIC_URL, TARGET, OFFTARGET, RESOLUTION)
        assert key.startswith("hic_contact:")
        assert "4DNFI" in key
        assert "6" in key   # TARGET chrom stripped of "chr"
        assert "17" in key  # OFFTARGET chrom stripped
        assert str(RESOLUTION) in key


# ---------------------------------------------------------------------------
# get_contact — single pair
# ---------------------------------------------------------------------------


class TestGetContact:
    @patch("src.stage4_epigenetic.hic_contacts.Cache")
    @patch.object(HiCContactReader, "_call_straw")
    def test_returns_contact_frequency(
        self, mock_call_straw, MockCache, tmp_path: Path
    ) -> None:
        bin_x = _round_bin(TARGET.start, RESOLUTION)      # 43_750_000
        bin_y = _round_bin(OFFTARGET.start, RESOLUTION)   # 7_000_000
        rec = _make_record(bin_x, bin_y, 12.5)
        mock_call_straw.return_value = [rec]
        MockCache.return_value.__enter__ = lambda s: _mock_cache_miss()
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        result = reader.get_contact(TARGET, OFFTARGET, "HeLa", RESOLUTION)

        assert isinstance(result, HiCResult)
        assert result.contact_frequency == pytest.approx(12.5)
        assert result.target_region == TARGET
        assert result.offtarget_region == OFFTARGET

    def test_null_hic_url_returns_neutral(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        result = reader.get_contact(TARGET, OFFTARGET, "K562", RESOLUTION)
        assert result.contact_frequency == pytest.approx(_NEUTRAL_CONTACT)

    def test_missing_hic_url_returns_neutral(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        result = reader.get_contact(TARGET, OFFTARGET, "A549", RESOLUTION)
        assert result.contact_frequency == pytest.approx(_NEUTRAL_CONTACT)

    def test_unknown_cell_line_returns_neutral(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        result = reader.get_contact(TARGET, OFFTARGET, "Jurkat", RESOLUTION)
        assert result.contact_frequency == pytest.approx(_NEUTRAL_CONTACT)

    @patch("src.stage4_epigenetic.hic_contacts.Cache")
    def test_cache_hit_returns_cached(self, MockCache, tmp_path: Path) -> None:
        MockCache.return_value.__enter__ = lambda s: _mock_cache_hit(7.3)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        result = reader.get_contact(TARGET, OFFTARGET, "HeLa", RESOLUTION)
        assert result.contact_frequency == pytest.approx(7.3)

    @patch("src.stage4_epigenetic.hic_contacts.Cache")
    @patch.object(HiCContactReader, "_call_straw")
    def test_cache_hit_skips_straw(
        self, mock_call_straw, MockCache, tmp_path: Path
    ) -> None:
        MockCache.return_value.__enter__ = lambda s: _mock_cache_hit(5.0)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        reader.get_contact(TARGET, OFFTARGET, "HeLa", RESOLUTION)
        mock_call_straw.assert_not_called()

    @patch("src.stage4_epigenetic.hic_contacts.Cache")
    @patch.object(HiCContactReader, "_call_straw")
    def test_straw_failure_returns_neutral(
        self, mock_call_straw, MockCache, tmp_path: Path
    ) -> None:
        mock_call_straw.side_effect = RuntimeError("network timeout")
        MockCache.return_value.__enter__ = lambda s: _mock_cache_miss()
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        result = reader.get_contact(TARGET, OFFTARGET, "HeLa", RESOLUTION)
        assert result.contact_frequency == pytest.approx(_NEUTRAL_CONTACT)

    @patch("src.stage4_epigenetic.hic_contacts.Cache")
    @patch.object(HiCContactReader, "_call_straw")
    def test_kr_fails_falls_back_to_none(
        self, mock_call_straw, MockCache, tmp_path: Path
    ) -> None:
        bin_x = _round_bin(TARGET.start, RESOLUTION)
        bin_y = _round_bin(OFFTARGET.start, RESOLUTION)
        rec = _make_record(bin_x, bin_y, 3.0)

        def _straw_side_effect(url, norm, r1, r2, res):
            if norm == "KR":
                raise ValueError("KR normalization not available")
            return [rec]

        mock_call_straw.side_effect = _straw_side_effect
        MockCache.return_value.__enter__ = lambda s: _mock_cache_miss()
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        result = reader.get_contact(TARGET, OFFTARGET, "HeLa", RESOLUTION)
        assert result.contact_frequency == pytest.approx(3.0)

    @patch("src.stage4_epigenetic.hic_contacts.Cache")
    @patch.object(HiCContactReader, "_call_straw")
    def test_no_exact_bin_match_returns_max(
        self, mock_call_straw, MockCache, tmp_path: Path
    ) -> None:
        # Records with wrong bin coordinates → fallback to max
        rec1 = _make_record(0, 0, 2.0)
        rec2 = _make_record(0, 0, 9.0)
        mock_call_straw.return_value = [rec1, rec2]
        MockCache.return_value.__enter__ = lambda s: _mock_cache_miss()
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        result = reader.get_contact(TARGET, OFFTARGET, "HeLa", RESOLUTION)
        assert result.contact_frequency == pytest.approx(9.0)

    @patch("src.stage4_epigenetic.hic_contacts.Cache")
    @patch.object(HiCContactReader, "_call_straw")
    def test_empty_straw_result_returns_neutral(
        self, mock_call_straw, MockCache, tmp_path: Path
    ) -> None:
        mock_call_straw.return_value = []
        MockCache.return_value.__enter__ = lambda s: _mock_cache_miss()
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        result = reader.get_contact(TARGET, OFFTARGET, "HeLa", RESOLUTION)
        assert result.contact_frequency == pytest.approx(_NEUTRAL_CONTACT)


# ---------------------------------------------------------------------------
# get_contacts_bulk
# ---------------------------------------------------------------------------


class TestGetContactsBulk:
    def test_empty_offtargets_returns_empty(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        results = reader.get_contacts_bulk(TARGET, [], "HeLa", RESOLUTION)
        assert results == []

    def test_null_url_all_neutral(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        results = reader.get_contacts_bulk(TARGET, [OFFTARGET, OFFTARGET_2], "K562", RESOLUTION)
        assert all(r.contact_frequency == pytest.approx(_NEUTRAL_CONTACT) for r in results)

    @patch("src.stage4_epigenetic.hic_contacts.Cache")
    @patch.object(HiCContactReader, "_call_straw")
    def test_bulk_returns_correct_order(
        self, mock_call_straw, MockCache, tmp_path: Path
    ) -> None:
        bin_t = _round_bin(TARGET.start, RESOLUTION)
        bin_o1 = _round_bin(OFFTARGET.start, RESOLUTION)
        bin_o2 = _round_bin(OFFTARGET_2.start, RESOLUTION)

        call_count = [0]

        def _straw_side_effect(url, norm, r1, r2, res):
            call_count[0] += 1
            if "17" in r2:
                return [_make_record(bin_t, bin_o1, 5.0)]
            return [_make_record(bin_t, bin_o2, 2.0)]

        mock_call_straw.side_effect = _straw_side_effect
        MockCache.return_value.__enter__ = lambda s: _mock_cache_miss()
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        results = reader.get_contacts_bulk(
            TARGET, [OFFTARGET, OFFTARGET_2], "HeLa", RESOLUTION
        )
        assert len(results) == 2
        assert results[0].contact_frequency == pytest.approx(5.0)
        assert results[1].contact_frequency == pytest.approx(2.0)

    def test_bulk_preserves_region_references(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        results = reader.get_contacts_bulk(
            TARGET, [OFFTARGET, OFFTARGET_2], "A549", RESOLUTION
        )
        assert results[0].offtarget_region == OFFTARGET
        assert results[1].offtarget_region == OFFTARGET_2


# ---------------------------------------------------------------------------
# _call_straw — import guard
# ---------------------------------------------------------------------------


class TestCallStraw:
    def test_raises_runtimeerror_when_hicstraw_missing(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        with (
            patch.dict("sys.modules", {"hicstraw": None}),
            pytest.raises((RuntimeError, ImportError)),
        ):
                reader._call_straw(HIC_URL, "KR", "6:0:25000", "17:0:25000", RESOLUTION)
