"""Unit tests for src/stage6_execution/rbp_competition.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml as _yaml

from src.core.config import load_config
from src.core.models import GenomicRegion, RBPResult
from src.stage4_epigenetic.encode_reader import _NEUTRAL_SIGNAL
from src.stage6_execution.rbp_competition import (
    RBPCompetitionReader,
    _COMPETITION_THRESHOLD,
    _RBP_SATURATION,
    _competition_score,
    assess_rbp_competition,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REGION = GenomicRegion(chrom="chr7", start=55_019_017, end=55_020_017, strand="+")
REGION_2 = GenomicRegion(chrom="chr17", start=7_669_609, end=7_670_609, strand="-")

HNRNPA1_URL = "https://www.encodeproject.org/files/ENCFF810JXO/@@download/ENCFF810JXO.bigWig"

CELL_LINES = {
    "HeLa": {"hnrnpa1_eclip": HNRNPA1_URL},
    "K562": {"hnrnpa1_eclip": None},   # null URL → neutral
    "HepG2": {},                        # missing key → neutral
}


def _make_reader(tmp_path: Path) -> RBPCompetitionReader:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "target_gene: EGFR\ncell_line: HeLa\nsarna_sequence: GCAACCATAGCCTCGGCCGC\n",
        encoding="utf-8",
    )
    config = load_config(cfg_file)
    config.data_paths.cache_db = str(tmp_path / "cache.db")

    yaml_path = tmp_path / "cell_lines.yaml"
    yaml_path.write_text(_yaml.dump(CELL_LINES), encoding="utf-8")
    return RBPCompetitionReader(config, cell_lines_yaml=yaml_path)


def _mock_cache(signal: float | None = None) -> MagicMock:
    cache = MagicMock()
    cache.get.return_value = {"signal": signal} if signal is not None else None
    return cache


# ---------------------------------------------------------------------------
# _competition_score — unit tests
# ---------------------------------------------------------------------------


class TestCompetitionScore:
    def test_zero_signal_returns_zero(self) -> None:
        assert _competition_score(0.0) == pytest.approx(0.0)

    def test_negative_signal_returns_zero(self) -> None:
        assert _competition_score(-3.0) == pytest.approx(0.0)

    def test_half_saturation(self) -> None:
        assert _competition_score(_RBP_SATURATION / 2) == pytest.approx(0.5)

    def test_at_saturation_returns_one(self) -> None:
        assert _competition_score(_RBP_SATURATION) == pytest.approx(1.0)

    def test_above_saturation_clamped(self) -> None:
        assert _competition_score(_RBP_SATURATION * 5) == pytest.approx(1.0)

    def test_below_threshold_not_competing(self) -> None:
        score = _competition_score(_COMPETITION_THRESHOLD * _RBP_SATURATION * 0.9)
        assert score <= _COMPETITION_THRESHOLD

    def test_above_threshold_competing(self) -> None:
        score = _competition_score(_COMPETITION_THRESHOLD * _RBP_SATURATION * 1.1)
        assert score > _COMPETITION_THRESHOLD


# ---------------------------------------------------------------------------
# RBPCompetitionReader.get_rbp_signal — single region
# ---------------------------------------------------------------------------


class TestGetRBPSignal:
    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_returns_signal_for_configured_cell_line(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        bw = MagicMock()
        bw.stats.return_value = [5.5]
        mock_open.return_value = bw

        mock_cache = _mock_cache(None)
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        assert reader.get_rbp_signal(REGION, "HeLa") == pytest.approx(5.5)

    def test_null_url_returns_neutral(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        assert reader.get_rbp_signal(REGION, "K562") == pytest.approx(_NEUTRAL_SIGNAL)

    def test_missing_key_returns_neutral(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        assert reader.get_rbp_signal(REGION, "HepG2") == pytest.approx(_NEUTRAL_SIGNAL)

    def test_unknown_cell_line_returns_neutral(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        assert reader.get_rbp_signal(REGION, "Jurkat") == pytest.approx(_NEUTRAL_SIGNAL)

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_cache_hit_skips_bigwig(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        mock_cache = _mock_cache(signal=9.0)
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        assert reader.get_rbp_signal(REGION, "HeLa") == pytest.approx(9.0)
        mock_open.assert_not_called()

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_bigwig_failure_returns_neutral(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        mock_open.side_effect = OSError("network error")
        mock_cache = _mock_cache(None)
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        assert reader.get_rbp_signal(REGION, "HeLa") == pytest.approx(_NEUTRAL_SIGNAL)


# ---------------------------------------------------------------------------
# RBPCompetitionReader.get_rbp_signal_bulk
# ---------------------------------------------------------------------------


class TestGetRBPSignalBulk:
    def test_empty_regions_returns_empty(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        assert reader.get_rbp_signal_bulk([], "HeLa") == []

    def test_null_url_returns_all_neutral(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        results = reader.get_rbp_signal_bulk([REGION, REGION_2], "K562")
        assert results == [_NEUTRAL_SIGNAL, _NEUTRAL_SIGNAL]

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_opens_bigwig_once_for_batch(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        bw = MagicMock()
        bw.stats.side_effect = [[4.0], [11.0]]
        mock_open.return_value = bw

        mock_cache = _mock_cache(None)
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        results = reader.get_rbp_signal_bulk([REGION, REGION_2], "HeLa")
        mock_open.assert_called_once_with(HNRNPA1_URL)
        assert results == pytest.approx([4.0, 11.0])

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_preserves_order(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        bw = MagicMock()
        bw.stats.side_effect = [[18.0], [1.0]]
        mock_open.return_value = bw
        mock_cache = _mock_cache(None)
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        results = reader.get_rbp_signal_bulk([REGION, REGION_2], "HeLa")
        assert results[0] == pytest.approx(18.0)
        assert results[1] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# assess_rbp_competition
# ---------------------------------------------------------------------------


class TestAssessRBPCompetition:
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

        results = assess_rbp_competition([], "HeLa", config, yaml_path)
        assert results == []

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_competing_region(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        """Signal above threshold → is_competing=True, risk decreases."""
        raw = 12.0  # score = 12/20 = 0.6 > 0.3
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

        results = assess_rbp_competition([REGION], "HeLa", config, yaml_path)
        assert len(results) == 1
        r = results[0]
        assert isinstance(r, RBPResult)
        assert r.cell_line == "HeLa"
        assert r.rbp_name == "hnRNPA1"
        assert r.raw_signal == pytest.approx(raw)
        assert r.competition_score == pytest.approx(0.6)
        assert r.is_competing is True

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_non_competing_region(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        """Signal below threshold → is_competing=False."""
        raw = 1.0  # score = 1/20 = 0.05 < 0.3
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

        results = assess_rbp_competition([REGION], "HeLa", config, yaml_path)
        assert results[0].is_competing is False
        assert results[0].competition_score == pytest.approx(0.05)

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_custom_rbp_name_propagated(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        bw = MagicMock()
        bw.stats.return_value = [5.0]
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

        results = assess_rbp_competition(
            [REGION], "HeLa", config, yaml_path, rbp_name="ELAVL1"
        )
        assert results[0].rbp_name == "ELAVL1"

    def test_null_url_returns_neutral_results(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            "target_gene: X\ncell_line: K562\nsarna_sequence: GCAACCATAGCCTCGGCCGC\n",
            encoding="utf-8",
        )
        config = load_config(cfg_file)
        config.data_paths.cache_db = str(tmp_path / "cache.db")
        yaml_path = tmp_path / "cell_lines.yaml"
        yaml_path.write_text(_yaml.dump(CELL_LINES), encoding="utf-8")

        results = assess_rbp_competition([REGION, REGION_2], "K562", config, yaml_path)
        assert len(results) == 2
        for r in results:
            assert r.competition_score == pytest.approx(0.0)
            assert r.is_competing is False

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

        results = assess_rbp_competition([REGION, REGION_2], "HeLa", config, yaml_path)
        assert results[0].region == REGION
        assert results[0].is_competing is True
        assert results[1].region == REGION_2
        assert results[1].is_competing is False
