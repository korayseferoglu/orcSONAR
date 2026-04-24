"""Unit tests for src/stage4_epigenetic/histone_marks.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml as _yaml

from src.core.config import load_config
from src.core.models import GenomicRegion
from src.stage4_epigenetic.histone_marks import HistoneMarkReader
from src.stage4_epigenetic.encode_reader import _NEUTRAL_SIGNAL

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REGION = GenomicRegion(chrom="chr6", start=43_768_652, end=43_769_652, strand="+")
REGION_2 = GenomicRegion(chrom="chr1", start=1_000, end=2_000, strand=".")

H3K4ME3_URL = "https://www.encodeproject.org/files/ENCFF553KON/@@download/ENCFF553KON.bigWig"
H3K27AC_URL = "https://www.encodeproject.org/files/ENCFF044JNJ/@@download/ENCFF044JNJ.bigWig"
H3K27ME3_URL = "https://www.encodeproject.org/files/ENCFF999TST/@@download/ENCFF999TST.bigWig"

CELL_LINES_FULL = {
    "HeLa": {
        "h3k4me3_chip": H3K4ME3_URL,
        "h3k27ac_chip": H3K27AC_URL,
        "h3k27me3_chip": H3K27ME3_URL,
    },
    "K562": {
        "h3k4me3_chip": H3K4ME3_URL,
        "h3k27ac_chip": H3K27AC_URL,
        "h3k27me3_chip": None,   # null — neutral expected
    },
    "A549": {
        "h3k4me3_chip": H3K4ME3_URL,
        # h3k27ac_chip absent — neutral expected
    },
}


def _make_reader(tmp_path: Path, cell_lines: dict | None = None) -> HistoneMarkReader:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "target_gene: VEGFA\ncell_line: HeLa\nsarna_sequence: GCAACCATAGCCTCGGCCGC\n",
        encoding="utf-8",
    )
    config = load_config(cfg_file)
    config.data_paths.cache_db = str(tmp_path / "cache.db")

    yaml_path = tmp_path / "cell_lines.yaml"
    yaml_path.write_text(_yaml.dump(cell_lines or CELL_LINES_FULL), encoding="utf-8")
    return HistoneMarkReader(config, cell_lines_yaml=yaml_path)


def _mock_cache_hit(signal: float) -> MagicMock:
    cache = MagicMock()
    cache.get.return_value = {"signal": signal}
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
# get_h3k4me3
# ---------------------------------------------------------------------------


class TestGetH3K4me3:
    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_returns_signal(self, mock_open, MockCache, tmp_path: Path) -> None:
        bw = MagicMock()
        bw.stats.return_value = [6.0]
        mock_open.return_value = bw
        MockCache.return_value.__enter__ = lambda s: _mock_cache_miss()
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        result = reader.get_h3k4me3(REGION, "HeLa")
        assert result == pytest.approx(6.0)
        mock_open.assert_called_once_with(H3K4ME3_URL)

    def test_missing_key_returns_neutral(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        # A549 has no h3k27ac but has h3k4me3; try a missing key for A549
        assert reader.get_h3k4me3(REGION, "Ghost") == pytest.approx(_NEUTRAL_SIGNAL)

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_bigwig_open_failure_returns_neutral(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        mock_open.side_effect = OSError("network error")
        MockCache.return_value.__enter__ = lambda s: _mock_cache_miss()
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        assert reader.get_h3k4me3(REGION, "HeLa") == pytest.approx(_NEUTRAL_SIGNAL)

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    def test_cache_hit_returns_cached(self, MockCache, tmp_path: Path) -> None:
        MockCache.return_value.__enter__ = lambda s: _mock_cache_hit(3.7)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        result = reader.get_h3k4me3(REGION, "HeLa")
        assert result == pytest.approx(3.7)


# ---------------------------------------------------------------------------
# get_h3k27ac
# ---------------------------------------------------------------------------


class TestGetH3K27ac:
    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_returns_signal(self, mock_open, MockCache, tmp_path: Path) -> None:
        bw = MagicMock()
        bw.stats.return_value = [8.3]
        mock_open.return_value = bw
        MockCache.return_value.__enter__ = lambda s: _mock_cache_miss()
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        result = reader.get_h3k27ac(REGION, "HeLa")
        assert result == pytest.approx(8.3)
        mock_open.assert_called_once_with(H3K27AC_URL)

    def test_missing_key_returns_neutral(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        # A549 has no h3k27ac_chip key
        assert reader.get_h3k27ac(REGION, "A549") == pytest.approx(_NEUTRAL_SIGNAL)

    def test_unknown_cell_line_returns_neutral(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        assert reader.get_h3k27ac(REGION, "UnknownLine") == pytest.approx(_NEUTRAL_SIGNAL)

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_bigwig_failure_returns_neutral(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        mock_open.side_effect = OSError("timeout")
        MockCache.return_value.__enter__ = lambda s: _mock_cache_miss()
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        assert reader.get_h3k27ac(REGION, "HeLa") == pytest.approx(_NEUTRAL_SIGNAL)


# ---------------------------------------------------------------------------
# get_h3k27me3 — repressive mark
# ---------------------------------------------------------------------------


class TestGetH3K27me3:
    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_returns_signal_when_configured(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        bw = MagicMock()
        bw.stats.return_value = [5.0]
        mock_open.return_value = bw
        MockCache.return_value.__enter__ = lambda s: _mock_cache_miss()
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        result = reader.get_h3k27me3(REGION, "HeLa")
        assert result == pytest.approx(5.0)
        mock_open.assert_called_once_with(H3K27ME3_URL)

    def test_null_url_returns_neutral(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        # K562 has h3k27me3_chip: null
        assert reader.get_h3k27me3(REGION, "K562") == pytest.approx(_NEUTRAL_SIGNAL)

    def test_missing_key_returns_neutral(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        # A549 has no h3k27me3_chip key
        assert reader.get_h3k27me3(REGION, "A549") == pytest.approx(_NEUTRAL_SIGNAL)

    def test_unknown_cell_line_returns_neutral(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        assert reader.get_h3k27me3(REGION, "Jurkat") == pytest.approx(_NEUTRAL_SIGNAL)

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_bigwig_failure_returns_neutral(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        mock_open.side_effect = OSError("refused")
        MockCache.return_value.__enter__ = lambda s: _mock_cache_miss()
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        assert reader.get_h3k27me3(REGION, "HeLa") == pytest.approx(_NEUTRAL_SIGNAL)


# ---------------------------------------------------------------------------
# Bulk methods
# ---------------------------------------------------------------------------


class TestBulkMethods:
    def test_get_h3k4me3_bulk_empty(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        assert reader.get_h3k4me3_bulk([], "HeLa") == []

    def test_get_h3k27ac_bulk_empty(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        assert reader.get_h3k27ac_bulk([], "HeLa") == []

    def test_get_h3k27me3_bulk_empty(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        assert reader.get_h3k27me3_bulk([], "HeLa") == []

    def test_null_url_bulk_all_neutral(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        results = reader.get_h3k27me3_bulk([REGION, REGION_2], "K562")
        assert results == [_NEUTRAL_SIGNAL, _NEUTRAL_SIGNAL]

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_h3k4me3_bulk_opens_bigwig_once(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        bw = MagicMock()
        bw.stats.side_effect = [[4.0], [2.0]]
        mock_open.return_value = bw
        MockCache.return_value.__enter__ = lambda s: _mock_cache_miss()
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        results = reader.get_h3k4me3_bulk([REGION, REGION_2], "HeLa")
        mock_open.assert_called_once_with(H3K4ME3_URL)
        assert results == pytest.approx([4.0, 2.0])

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_h3k27ac_bulk_opens_bigwig_once(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        bw = MagicMock()
        bw.stats.side_effect = [[7.0], [1.5]]
        mock_open.return_value = bw
        MockCache.return_value.__enter__ = lambda s: _mock_cache_miss()
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        results = reader.get_h3k27ac_bulk([REGION, REGION_2], "HeLa")
        mock_open.assert_called_once_with(H3K27AC_URL)
        assert results == pytest.approx([7.0, 1.5])

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_h3k27me3_bulk_opens_bigwig_once(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        bw = MagicMock()
        bw.stats.side_effect = [[3.0], [6.0]]
        mock_open.return_value = bw
        MockCache.return_value.__enter__ = lambda s: _mock_cache_miss()
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        results = reader.get_h3k27me3_bulk([REGION, REGION_2], "HeLa")
        mock_open.assert_called_once_with(H3K27ME3_URL)
        assert results == pytest.approx([3.0, 6.0])

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_all_marks_use_correct_url(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        """Each mark reader must open the correct BigWig URL."""
        bw = MagicMock()
        bw.stats.return_value = [1.0]
        mock_open.return_value = bw
        MockCache.return_value.__enter__ = lambda s: _mock_cache_miss()
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        reader.get_h3k4me3(REGION, "HeLa")
        assert mock_open.call_args_list[-1][0][0] == H3K4ME3_URL

        reader.get_h3k27ac(REGION, "HeLa")
        assert mock_open.call_args_list[-1][0][0] == H3K27AC_URL

        reader.get_h3k27me3(REGION, "HeLa")
        assert mock_open.call_args_list[-1][0][0] == H3K27ME3_URL
