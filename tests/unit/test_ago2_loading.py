"""Unit tests for src/stage6_execution/ago2_loading.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml as _yaml

from src.core.config import load_config
from src.core.models import Ago2Result, GenomicRegion
from src.stage4_epigenetic.encode_reader import UNKNOWN_SIGNAL
from src.stage6_execution.ago2_loading import (
    _AGO2_SATURATION,
    _LOADING_THRESHOLD,
    Ago2Reader,
    _loading_score,
    assess_ago2_loading,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REGION = GenomicRegion(chrom="chr7", start=55_019_017, end=55_020_017, strand="+")
REGION_2 = GenomicRegion(chrom="chr17", start=7_669_609, end=7_670_609, strand="-")

AGO2_URL = "https://www.encodeproject.org/files/ENCFF765PFM/@@download/ENCFF765PFM.bigWig"

CELL_LINES = {
    "HeLa": {"ago2_eclip": AGO2_URL},
    "K562": {"ago2_eclip": None},   # null URL → neutral
    "HepG2": {},                    # missing key → neutral
}


def _make_reader(tmp_path: Path) -> Ago2Reader:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "target_gene: EGFR\ncell_line: HeLa\nsarna_sequence: GCAACCATAGCCTCGGCCGC\n",
        encoding="utf-8",
    )
    config = load_config(cfg_file)
    config.data_paths.cache_db = str(tmp_path / "cache.db")

    yaml_path = tmp_path / "cell_lines.yaml"
    yaml_path.write_text(_yaml.dump(CELL_LINES), encoding="utf-8")
    return Ago2Reader(config, cell_lines_yaml=yaml_path)


def _mock_cache(signal: float | None = None) -> MagicMock:
    cache = MagicMock()
    cache.get.return_value = {"signal": signal} if signal is not None else None
    return cache


# ---------------------------------------------------------------------------
# _loading_score — unit tests
# ---------------------------------------------------------------------------


class TestLoadingScore:
    def test_zero_signal_returns_zero(self) -> None:
        assert _loading_score(0.0) == pytest.approx(0.0)

    def test_negative_signal_returns_zero(self) -> None:
        assert _loading_score(-5.0) == pytest.approx(0.0)

    def test_half_saturation(self) -> None:
        assert _loading_score(_AGO2_SATURATION / 2) == pytest.approx(0.5)

    def test_at_saturation_returns_one(self) -> None:
        assert _loading_score(_AGO2_SATURATION) == pytest.approx(1.0)

    def test_above_saturation_clamped(self) -> None:
        assert _loading_score(_AGO2_SATURATION * 10) == pytest.approx(1.0)

    def test_below_threshold_not_loaded(self) -> None:
        score = _loading_score(_LOADING_THRESHOLD * _AGO2_SATURATION * 0.9)
        assert score <= _LOADING_THRESHOLD

    def test_above_threshold_loaded(self) -> None:
        score = _loading_score(_LOADING_THRESHOLD * _AGO2_SATURATION * 1.1)
        assert score > _LOADING_THRESHOLD


# ---------------------------------------------------------------------------
# Ago2Reader.get_ago2_signal — single region
# ---------------------------------------------------------------------------


class TestGetAgo2Signal:
    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_returns_signal_for_configured_cell_line(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        bw = MagicMock()
        bw.stats.return_value = [7.5]
        mock_open.return_value = bw

        mock_cache = _mock_cache(None)
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        assert reader.get_ago2_signal(REGION, "HeLa") == pytest.approx(7.5)

    def test_null_url_returns_unknown(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        assert reader.get_ago2_signal(REGION, "K562") is UNKNOWN_SIGNAL

    def test_missing_key_returns_unknown(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        assert reader.get_ago2_signal(REGION, "HepG2") is UNKNOWN_SIGNAL

    def test_unknown_cell_line_returns_unknown(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        assert reader.get_ago2_signal(REGION, "Jurkat") is UNKNOWN_SIGNAL

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_cache_hit_skips_bigwig(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        mock_cache = _mock_cache(signal=12.0)
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        assert reader.get_ago2_signal(REGION, "HeLa") == pytest.approx(12.0)
        mock_open.assert_not_called()

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_bigwig_failure_returns_unknown(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        mock_open.side_effect = OSError("network error")
        mock_cache = _mock_cache(None)
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        assert reader.get_ago2_signal(REGION, "HeLa") is UNKNOWN_SIGNAL


# ---------------------------------------------------------------------------
# Ago2Reader.get_ago2_signal_bulk
# ---------------------------------------------------------------------------


class TestGetAgo2SignalBulk:
    def test_empty_regions_returns_empty(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        assert reader.get_ago2_signal_bulk([], "HeLa") == []

    def test_null_url_returns_all_neutral(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        results = reader.get_ago2_signal_bulk([REGION, REGION_2], "K562")
        assert results == [UNKNOWN_SIGNAL, UNKNOWN_SIGNAL]

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_opens_bigwig_once_for_batch(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        bw = MagicMock()
        bw.stats.side_effect = [[3.0], [8.0]]
        mock_open.return_value = bw

        mock_cache = _mock_cache(None)
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        results = reader.get_ago2_signal_bulk([REGION, REGION_2], "HeLa")
        mock_open.assert_called_once_with(AGO2_URL)
        assert results == pytest.approx([3.0, 8.0])

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_preserves_order(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        bw = MagicMock()
        bw.stats.side_effect = [[15.0], [2.0]]
        mock_open.return_value = bw
        mock_cache = _mock_cache(None)
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        results = reader.get_ago2_signal_bulk([REGION, REGION_2], "HeLa")
        assert results[0] == pytest.approx(15.0)
        assert results[1] == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# assess_ago2_loading
# ---------------------------------------------------------------------------


class TestAssessAgo2Loading:
    def test_empty_regions_returns_empty(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            "target_gene: X\ncell_line: HeLa\nsarna_sequence: GCAACCATAGCCTCGGCCGC\n",
            encoding="utf-8",
        )
        config = load_config(cfg_file)
        config.data_paths.cache_db = str(tmp_path / "cache.db")
        yaml_path = tmp_path / "cell_lines.yaml"
        yaml_path.write_text(_yaml.dump(CELL_LINES), encoding="utf-8")

        results = assess_ago2_loading([], "HeLa", config, yaml_path)
        assert results == []

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_loaded_region(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        """Signal above threshold → is_loaded=True."""
        raw = 10.0  # score = 10/20 = 0.5 > 0.3
        bw = MagicMock()
        bw.stats.return_value = [raw]
        mock_open.return_value = bw
        mock_cache = _mock_cache(None)
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            "target_gene: X\ncell_line: HeLa\nsarna_sequence: GCAACCATAGCCTCGGCCGC\n",
            encoding="utf-8",
        )
        config = load_config(cfg_file)
        config.data_paths.cache_db = str(tmp_path / "cache.db")
        yaml_path = tmp_path / "cell_lines.yaml"
        yaml_path.write_text(_yaml.dump(CELL_LINES), encoding="utf-8")

        results = assess_ago2_loading([REGION], "HeLa", config, yaml_path)
        assert len(results) == 1
        r = results[0]
        assert isinstance(r, Ago2Result)
        assert r.cell_line == "HeLa"
        assert r.raw_signal == pytest.approx(raw)
        assert r.loading_score == pytest.approx(0.5)
        assert r.is_loaded is True

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_not_loaded_region(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        """Signal below threshold → is_loaded=False."""
        raw = 2.0  # score = 2/20 = 0.1 < 0.3
        bw = MagicMock()
        bw.stats.return_value = [raw]
        mock_open.return_value = bw
        mock_cache = _mock_cache(None)
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            "target_gene: X\ncell_line: HeLa\nsarna_sequence: GCAACCATAGCCTCGGCCGC\n",
            encoding="utf-8",
        )
        config = load_config(cfg_file)
        config.data_paths.cache_db = str(tmp_path / "cache.db")
        yaml_path = tmp_path / "cell_lines.yaml"
        yaml_path.write_text(_yaml.dump(CELL_LINES), encoding="utf-8")

        results = assess_ago2_loading([REGION], "HeLa", config, yaml_path)
        assert results[0].is_loaded is False
        assert results[0].loading_score == pytest.approx(0.1)

    def test_null_url_returns_unknown_results(self, tmp_path: Path) -> None:
        """Unconfigured cell line → all results have loading_score=0 and is_loaded=False."""
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            "target_gene: X\ncell_line: K562\nsarna_sequence: GCAACCATAGCCTCGGCCGC\n",
            encoding="utf-8",
        )
        config = load_config(cfg_file)
        config.data_paths.cache_db = str(tmp_path / "cache.db")
        yaml_path = tmp_path / "cell_lines.yaml"
        yaml_path.write_text(_yaml.dump(CELL_LINES), encoding="utf-8")

        results = assess_ago2_loading([REGION, REGION_2], "K562", config, yaml_path)
        assert len(results) == 2
        # No ago2_eclip accession for this cell line, so nothing was measured.
        # The old contract said 0.0 / not-loaded, which asserted an absence of
        # Ago2 loading on the strength of a missing config entry (roadmap B2).
        for r in results:
            assert r.loading_score is UNKNOWN_SIGNAL
            assert r.is_loaded is None

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_preserves_region_order(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        bw = MagicMock()
        bw.stats.side_effect = [[20.0], [0.0]]
        mock_open.return_value = bw
        mock_cache = _mock_cache(None)
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            "target_gene: X\ncell_line: HeLa\nsarna_sequence: GCAACCATAGCCTCGGCCGC\n",
            encoding="utf-8",
        )
        config = load_config(cfg_file)
        config.data_paths.cache_db = str(tmp_path / "cache.db")
        yaml_path = tmp_path / "cell_lines.yaml"
        yaml_path.write_text(_yaml.dump(CELL_LINES), encoding="utf-8")

        results = assess_ago2_loading([REGION, REGION_2], "HeLa", config, yaml_path)
        assert results[0].region == REGION
        assert results[0].is_loaded is True
        assert results[1].region == REGION_2
        assert results[1].is_loaded is False
