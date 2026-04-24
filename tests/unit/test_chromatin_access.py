"""Unit tests for src/stage4_epigenetic/chromatin_access.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml as _yaml

from src.core.config import load_config
from src.core.models import GenomicRegion
from src.stage4_epigenetic.chromatin_access import ATACSeqReader
from src.stage4_epigenetic.encode_reader import _NEUTRAL_SIGNAL

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REGION = GenomicRegion(chrom="chr6", start=43_768_652, end=43_769_652, strand="+")
REGION_2 = GenomicRegion(chrom="chr17", start=7_000_000, end=7_001_000, strand="-")

ATAC_URL = "https://www.encodeproject.org/files/ENCFF492CEJ/@@download/ENCFF492CEJ.bigWig"

CELL_LINES = {
    "HeLa": {"atac_seq": ATAC_URL},
    "K562": {"atac_seq": None},          # null URL — should return neutral
    "HepG2": {},                          # missing key — should return neutral
}


def _make_reader(tmp_path: Path) -> ATACSeqReader:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "target_gene: VEGFA\ncell_line: HeLa\nsarna_sequence: GCAACCATAGCCTCGGCCGC\n",
        encoding="utf-8",
    )
    config = load_config(cfg_file)
    config.data_paths.cache_db = str(tmp_path / "cache.db")

    yaml_path = tmp_path / "cell_lines.yaml"
    yaml_path.write_text(_yaml.dump(CELL_LINES), encoding="utf-8")
    return ATACSeqReader(config, cell_lines_yaml=yaml_path)


def _mock_cache(signal: float | None = None) -> MagicMock:
    cache = MagicMock()
    cache.get.return_value = {"signal": signal} if signal is not None else None
    return cache


# ---------------------------------------------------------------------------
# ATACSeqReader.get_accessibility — single region
# ---------------------------------------------------------------------------


class TestGetAccessibility:
    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_returns_signal_for_configured_cell_line(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        bw = MagicMock()
        bw.stats.return_value = [4.2]
        mock_open.return_value = bw

        mock_cache = _mock_cache(None)
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        result = reader.get_accessibility(REGION, "HeLa")
        assert result == pytest.approx(4.2)

    def test_null_url_returns_neutral(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        assert reader.get_accessibility(REGION, "K562") == pytest.approx(_NEUTRAL_SIGNAL)

    def test_missing_key_returns_neutral(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        assert reader.get_accessibility(REGION, "HepG2") == pytest.approx(_NEUTRAL_SIGNAL)

    def test_unknown_cell_line_returns_neutral(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        assert reader.get_accessibility(REGION, "Jurkat") == pytest.approx(_NEUTRAL_SIGNAL)

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_cache_hit_skips_bigwig(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        mock_cache = _mock_cache(signal=9.9)
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        result = reader.get_accessibility(REGION, "HeLa")
        assert result == pytest.approx(9.9)
        mock_open.assert_not_called()

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_bigwig_failure_returns_neutral(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        mock_open.side_effect = OSError("cannot reach host")
        mock_cache = _mock_cache(None)
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        result = reader.get_accessibility(REGION, "HeLa")
        assert result == pytest.approx(_NEUTRAL_SIGNAL)


# ---------------------------------------------------------------------------
# ATACSeqReader.get_accessibility_bulk
# ---------------------------------------------------------------------------


class TestGetAccessibilityBulk:
    def test_empty_regions_returns_empty(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        assert reader.get_accessibility_bulk([], "HeLa") == []

    def test_null_url_returns_all_neutral(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        results = reader.get_accessibility_bulk([REGION, REGION_2], "K562")
        assert results == [_NEUTRAL_SIGNAL, _NEUTRAL_SIGNAL]

    def test_unknown_cell_line_returns_all_neutral(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        results = reader.get_accessibility_bulk([REGION, REGION_2], "Ghost")
        assert results == [_NEUTRAL_SIGNAL, _NEUTRAL_SIGNAL]

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_opens_bigwig_once_for_batch(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        bw = MagicMock()
        bw.stats.side_effect = [[2.0], [3.5]]
        mock_open.return_value = bw

        mock_cache = _mock_cache(None)
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        results = reader.get_accessibility_bulk([REGION, REGION_2], "HeLa")
        mock_open.assert_called_once_with(ATAC_URL)
        assert results == pytest.approx([2.0, 3.5])

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_preserves_order(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        bw = MagicMock()
        bw.stats.side_effect = [[10.0], [5.0]]
        mock_open.return_value = bw
        mock_cache = _mock_cache(None)
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        results = reader.get_accessibility_bulk([REGION, REGION_2], "HeLa")
        assert results[0] == pytest.approx(10.0)
        assert results[1] == pytest.approx(5.0)

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_bigwig_failure_returns_neutral_list(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        mock_open.side_effect = OSError("timeout")
        mock_cache = _mock_cache(None)
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        results = reader.get_accessibility_bulk([REGION, REGION_2], "HeLa")
        assert results == pytest.approx([_NEUTRAL_SIGNAL, _NEUTRAL_SIGNAL])
