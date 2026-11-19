"""Unit tests for src/stage4_epigenetic/transcription_run.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml as _yaml

from src.core.config import load_config
from src.core.models import GenomicRegion, GROseqResult
from src.stage4_epigenetic.encode_reader import UNKNOWN_SIGNAL
from src.stage4_epigenetic.transcription_run import GROseqReader

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REGION = GenomicRegion(chrom="chr6", start=43_768_652, end=43_769_652, strand="+")
REGION_2 = GenomicRegion(chrom="chr17", start=7_000_000, end=7_001_000, strand="-")

PLUS_URL = "https://www.encodeproject.org/files/ENCFF111AAA/@@download/ENCFF111AAA.bigWig"
MINUS_URL = "https://www.encodeproject.org/files/ENCFF222BBB/@@download/ENCFF222BBB.bigWig"

CELL_LINES_FULL = {
    "HeLa": {
        "gro_seq_plus_url": PLUS_URL,
        "gro_seq_minus_url": MINUS_URL,
    },
    "K562": {
        "gro_seq_plus_url": PLUS_URL,
        "gro_seq_minus_url": None,   # minus absent → neutral for minus
    },
    "A549": {
        # both absent → all neutral
    },
    "HepG2": {
        "gro_seq_plus_url": None,
        "gro_seq_minus_url": None,
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_reader(tmp_path: Path, cell_lines: dict | None = None) -> GROseqReader:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "target_gene: VEGFA\ncell_line: HeLa\nsarna_sequence: GCAACCATAGCCTCGGCCGC\n",
        encoding="utf-8",
    )
    config = load_config(cfg_file)
    config.data_paths.cache_db = str(tmp_path / "cache.db")

    yaml_path = tmp_path / "cell_lines.yaml"
    yaml_path.write_text(_yaml.dump(cell_lines or CELL_LINES_FULL), encoding="utf-8")
    return GROseqReader(config, cell_lines_yaml=yaml_path)


def _mock_cache_hit(signal: float) -> MagicMock:
    cache = MagicMock()
    cache.get.return_value = {"signal": signal}
    return cache


def _mock_cache_miss() -> MagicMock:
    cache = MagicMock()
    cache.get.return_value = None
    return cache


# ---------------------------------------------------------------------------
# get_transcription — single region
# ---------------------------------------------------------------------------


class TestGetTranscription:
    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_returns_both_strands(self, mock_open, MockCache, tmp_path: Path) -> None:
        bw = MagicMock()
        bw.stats.side_effect = [[4.5], [2.1]]
        mock_open.return_value = bw
        MockCache.return_value.__enter__ = lambda s: _mock_cache_miss()
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        result = reader.get_transcription(REGION, "HeLa")

        assert isinstance(result, GROseqResult)
        assert result.plus_signal == pytest.approx(4.5)
        assert result.minus_signal == pytest.approx(2.1)
        assert result.combined_signal == pytest.approx(6.6)
        assert result.region == REGION

    def test_both_urls_absent_returns_all_unknown(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        result = reader.get_transcription(REGION, "A549")
        assert result.plus_signal is UNKNOWN_SIGNAL
        assert result.minus_signal is UNKNOWN_SIGNAL
        # combined_signal is a TOTAL. With a strand unmeasured the total is
        # unknown, not smaller — a partial total understates transcription and
        # less transcription reads as lower risk (roadmap B2). The measured
        # strand is still recorded in plus_signal/minus_signal.
        assert result.combined_signal is UNKNOWN_SIGNAL

    def test_null_urls_returns_all_unknown(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        result = reader.get_transcription(REGION, "HepG2")
        assert result.plus_signal is UNKNOWN_SIGNAL
        assert result.minus_signal is UNKNOWN_SIGNAL

    def test_unknown_cell_line_returns_all_unknown(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        result = reader.get_transcription(REGION, "Jurkat")
        assert result.plus_signal is UNKNOWN_SIGNAL
        assert result.minus_signal is UNKNOWN_SIGNAL

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_minus_absent_still_reads_plus(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        bw = MagicMock()
        bw.stats.return_value = [3.0]
        mock_open.return_value = bw
        MockCache.return_value.__enter__ = lambda s: _mock_cache_miss()
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        result = reader.get_transcription(REGION, "K562")

        assert result.plus_signal == pytest.approx(3.0)
        assert result.minus_signal is UNKNOWN_SIGNAL
        # combined_signal is a TOTAL. With a strand unmeasured the total is
        # unknown, not smaller — a partial total understates transcription and
        # less transcription reads as lower risk (roadmap B2). The measured
        # strand is still recorded in plus_signal/minus_signal.
        assert result.combined_signal is UNKNOWN_SIGNAL

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_minus_strand_signal_is_absolute(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        """Minus-strand BigWigs often report negative values; reader takes abs."""
        bw = MagicMock()
        bw.stats.side_effect = [[5.0], [-3.0]]
        mock_open.return_value = bw
        MockCache.return_value.__enter__ = lambda s: _mock_cache_miss()
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        result = reader.get_transcription(REGION, "HeLa")

        assert result.minus_signal == pytest.approx(3.0)
        assert result.combined_signal == pytest.approx(8.0)

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_bigwig_failure_returns_unknown_strand(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        mock_open.side_effect = OSError("network error")
        MockCache.return_value.__enter__ = lambda s: _mock_cache_miss()
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        result = reader.get_transcription(REGION, "HeLa")

        assert result.plus_signal is UNKNOWN_SIGNAL
        assert result.minus_signal is UNKNOWN_SIGNAL
        # combined_signal is a TOTAL. With a strand unmeasured the total is
        # unknown, not smaller — a partial total understates transcription and
        # less transcription reads as lower risk (roadmap B2). The measured
        # strand is still recorded in plus_signal/minus_signal.
        assert result.combined_signal is UNKNOWN_SIGNAL

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    def test_cache_hit_returns_cached_signal(self, MockCache, tmp_path: Path) -> None:
        MockCache.return_value.__enter__ = lambda s: _mock_cache_hit(7.7)
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        result = reader.get_transcription(REGION, "HeLa")

        assert result.plus_signal == pytest.approx(7.7)
        assert result.minus_signal == pytest.approx(7.7)

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_opens_correct_urls(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        bw = MagicMock()
        bw.stats.return_value = [1.0]
        mock_open.return_value = bw
        MockCache.return_value.__enter__ = lambda s: _mock_cache_miss()
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        reader.get_transcription(REGION, "HeLa")

        opened_urls = [call[0][0] for call in mock_open.call_args_list]
        assert PLUS_URL in opened_urls
        assert MINUS_URL in opened_urls


# ---------------------------------------------------------------------------
# get_transcription_bulk
# ---------------------------------------------------------------------------


class TestGetTranscriptionBulk:
    def test_empty_regions_returns_empty(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        assert reader.get_transcription_bulk([], "HeLa") == []

    def test_all_absent_returns_all_unknown(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        results = reader.get_transcription_bulk([REGION, REGION_2], "A549")
        for r in results:
            assert r.plus_signal is UNKNOWN_SIGNAL
            assert r.minus_signal is UNKNOWN_SIGNAL
            assert r.combined_signal is UNKNOWN_SIGNAL

    def test_unknown_cell_line_returns_all_unknown(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        results = reader.get_transcription_bulk([REGION, REGION_2], "Ghost")
        assert all(r.combined_signal is UNKNOWN_SIGNAL for r in results)

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_opens_each_strand_bigwig_once(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        bw = MagicMock()
        bw.stats.side_effect = [[2.0], [3.0], [1.5], [0.5]]
        mock_open.return_value = bw
        MockCache.return_value.__enter__ = lambda s: _mock_cache_miss()
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        results = reader.get_transcription_bulk([REGION, REGION_2], "HeLa")

        # The returned values were discarded here until H15, so this checked
        # the plumbing and never the output — in a module whose output contract
        # B2 had just changed. stats yields 2.0, 3.0 for the plus track and
        # 1.5, 0.5 for the minus one, and the minus strand is taken absolute.
        assert [r.plus_signal for r in results] == [2.0, 3.0]
        assert [r.minus_signal for r in results] == [1.5, 0.5]
        assert [r.combined_signal for r in results] == [3.5, 3.5]

        # pyBigWig.open must be called once for plus and once for minus
        assert mock_open.call_count == 2
        opened_urls = {call[0][0] for call in mock_open.call_args_list}
        assert PLUS_URL in opened_urls
        assert MINUS_URL in opened_urls

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_preserves_order(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        bw = MagicMock()
        # plus for REGION, plus for REGION_2, minus for REGION, minus for REGION_2
        bw.stats.side_effect = [[10.0], [1.0], [5.0], [0.5]]
        mock_open.return_value = bw
        MockCache.return_value.__enter__ = lambda s: _mock_cache_miss()
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        results = reader.get_transcription_bulk([REGION, REGION_2], "HeLa")

        assert len(results) == 2
        assert results[0].region == REGION
        assert results[1].region == REGION_2

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_combined_equals_sum_of_strands(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        bw = MagicMock()
        bw.stats.side_effect = [[4.0], [6.0], [1.0], [2.0]]
        mock_open.return_value = bw
        MockCache.return_value.__enter__ = lambda s: _mock_cache_miss()
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        results = reader.get_transcription_bulk([REGION, REGION_2], "HeLa")

        assert results[0].combined_signal == pytest.approx(
            results[0].plus_signal + results[0].minus_signal
        )
        assert results[1].combined_signal == pytest.approx(
            results[1].plus_signal + results[1].minus_signal
        )

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_bigwig_failure_returns_unknown_bulk(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        mock_open.side_effect = OSError("timeout")
        MockCache.return_value.__enter__ = lambda s: _mock_cache_miss()
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        results = reader.get_transcription_bulk([REGION, REGION_2], "HeLa")

        assert all(r.combined_signal is UNKNOWN_SIGNAL for r in results)

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_minus_only_absent_makes_the_total_unknown(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        bw = MagicMock()
        bw.stats.side_effect = [[3.0], [7.0]]
        mock_open.return_value = bw
        MockCache.return_value.__enter__ = lambda s: _mock_cache_miss()
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        results = reader.get_transcription_bulk([REGION, REGION_2], "K562")

        # K562 has only plus_url set
        assert mock_open.call_count == 1
        opened_url = mock_open.call_args_list[0][0][0]
        assert opened_url == PLUS_URL
        assert results[0].minus_signal is UNKNOWN_SIGNAL
        # Was: combined == plus. That asserted a partial total as the total,
        # which biases every single-strand cell line toward 'safe' (B2).
        assert results[0].combined_signal is UNKNOWN_SIGNAL
