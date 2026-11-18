"""Unit tests for src/stage4_epigenetic/encode_reader.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import responses as responses_lib

from src.core.config import OrcSonarConfig
from src.core.models import GenomicRegion
from src.stage4_epigenetic.encode_reader import (
    EncodeSignalReader,
    _bigwig_mean,
    _read_one_region,
    _signal_cache_key,
    UNKNOWN_SIGNAL,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

REGION_CHR6 = GenomicRegion(chrom="chr6", start=43_768_652, end=43_769_652, strand="+")
REGION_CHR1 = GenomicRegion(chrom="chr1", start=1_000, end=2_000, strand=".")
REGION_CHR17 = GenomicRegion(chrom="chr17", start=7_000_000, end=7_001_000, strand="-")

ENCODE_URL = "https://www.encodeproject.org/files/ENCFF492CEJ/@@download/ENCFF492CEJ.bigWig"
ACCESSION = "ENCFF492CEJ"
ENCODE_PORTAL = "https://www.encodeproject.org"

MINIMAL_CELL_LINES = {
    "HeLa": {
        "atac_seq": ENCODE_URL,
        "h3k4me3_chip": "https://www.encodeproject.org/files/ENCFF553KON/@@download/ENCFF553KON.bigWig",
    }
}


def _make_config(tmp_path: Path) -> OrcSonarConfig:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "target_gene: VEGFA\ncell_line: HeLa\nsarna_sequence: GCAACCATAGCCTCGGCCGC\n",
        encoding="utf-8",
    )
    from src.core.config import load_config
    return load_config(cfg_file)


def _make_reader(tmp_path: Path, cell_lines: dict | None = None) -> EncodeSignalReader:
    """Build an EncodeSignalReader with an in-memory YAML override."""
    import yaml as _yaml

    config = _make_config(tmp_path)
    # Override cache path to tmp
    config.data_paths.cache_db = str(tmp_path / "test_cache.db")

    yaml_path = tmp_path / "cell_lines.yaml"
    yaml_path.write_text(
        _yaml.dump(cell_lines or MINIMAL_CELL_LINES), encoding="utf-8"
    )
    return EncodeSignalReader(config, cell_lines_yaml=yaml_path)


def _make_bw(signal: float | None) -> MagicMock:
    bw = MagicMock()
    bw.stats.return_value = [signal]
    return bw


# ---------------------------------------------------------------------------
# _signal_cache_key
# ---------------------------------------------------------------------------


class TestSignalCacheKey:
    def test_contains_accession(self) -> None:
        key = _signal_cache_key(ENCODE_URL, REGION_CHR6)
        assert "ENCFF492CEJ" in key

    def test_contains_chrom_and_coords(self) -> None:
        key = _signal_cache_key(ENCODE_URL, REGION_CHR6)
        assert "chr6" in key
        assert str(REGION_CHR6.start) in key
        assert str(REGION_CHR6.end) in key

    def test_starts_with_prefix(self) -> None:
        key = _signal_cache_key(ENCODE_URL, REGION_CHR6)
        assert key.startswith("encode_signal:")

    def test_different_regions_different_keys(self) -> None:
        k1 = _signal_cache_key(ENCODE_URL, REGION_CHR1)
        k2 = _signal_cache_key(ENCODE_URL, REGION_CHR17)
        assert k1 != k2

    def test_different_urls_different_keys(self) -> None:
        url2 = "https://www.encodeproject.org/files/ENCFF553KON/@@download/ENCFF553KON.bigWig"
        k1 = _signal_cache_key(ENCODE_URL, REGION_CHR6)
        k2 = _signal_cache_key(url2, REGION_CHR6)
        assert k1 != k2


# ---------------------------------------------------------------------------
# _bigwig_mean
# ---------------------------------------------------------------------------


class TestBigwigMean:
    def test_positive_value(self) -> None:
        bw = _make_bw(5.2)
        assert _bigwig_mean(bw, "chr6", 1000, 2000) == pytest.approx(5.2)
        bw.stats.assert_called_once_with("chr6", 1000, 2000, type="mean")

    def test_no_intervals_on_a_contig_the_file_has_is_a_measured_zero(self) -> None:
        """The assay covered this contig and recorded nothing here.

        That is evidence, not a gap, and it has to keep counting — treating it
        as unknown would throw away real information (roadmap B2).
        """
        bw = _make_bw(None)
        bw.chroms.return_value = {"chr6": 170_805_979}
        assert _bigwig_mean(bw, "chr6", 1000, 2000) == pytest.approx(0.0)

    def test_empty_stats_on_a_known_contig_is_also_a_measured_zero(self) -> None:
        bw = MagicMock()
        bw.stats.return_value = []
        bw.chroms.return_value = {"chr6": 170_805_979}
        assert _bigwig_mean(bw, "chr6", 1000, 2000) == pytest.approx(0.0)

    def test_a_contig_the_file_does_not_have_is_unknown(self) -> None:
        """Nothing was measured, and this is where a "chr" prefix bug lands.

        A file keyed `6` queried as `chr6` returns no intervals for every
        region. Reported as 0.0 that reads as a genome-wide silent locus, which
        lowers risk everywhere and looks entirely plausible (Bulgu-10).
        """
        bw = _make_bw(None)
        bw.chroms.return_value = {"6": 170_805_979, "7": 159_345_973}
        assert _bigwig_mean(bw, "chr6", 1000, 2000) is UNKNOWN_SIGNAL

    def test_exception_returns_unknown(self) -> None:
        bw = MagicMock()
        bw.stats.side_effect = RuntimeError("bad region")
        assert _bigwig_mean(bw, "chr6", 1000, 2000) is UNKNOWN_SIGNAL

    def test_an_unreadable_contig_list_is_unknown_not_zero(self) -> None:
        """If even the header cannot be read, nothing about this locus is known."""
        bw = _make_bw(None)
        bw.chroms.side_effect = RuntimeError("header unreadable")
        assert _bigwig_mean(bw, "chr6", 1000, 2000) is UNKNOWN_SIGNAL

    def test_negative_value_returned_as_is(self) -> None:
        bw = _make_bw(-1.5)
        assert _bigwig_mean(bw, "chr1", 0, 100) == pytest.approx(-1.5)


# ---------------------------------------------------------------------------
# _read_one_region
# ---------------------------------------------------------------------------


class TestReadOneRegion:
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_opens_closes_reads(self, mock_open) -> None:
        bw = _make_bw(3.0)
        mock_open.return_value = bw
        result = _read_one_region(ENCODE_URL, REGION_CHR6)
        assert result == pytest.approx(3.0)
        bw.close.assert_called_once()

    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_open_failure_returns_unknown(self, mock_open) -> None:
        mock_open.side_effect = OSError("network error")
        result = _read_one_region(ENCODE_URL, REGION_CHR6)
        assert result is UNKNOWN_SIGNAL

    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_closed_even_if_stats_raises(self, mock_open) -> None:
        bw = MagicMock()
        bw.stats.side_effect = RuntimeError("read failed")
        mock_open.return_value = bw
        _read_one_region(ENCODE_URL, REGION_CHR6)
        bw.close.assert_called_once()


# ---------------------------------------------------------------------------
# EncodeSignalReader._load_cell_lines
# ---------------------------------------------------------------------------


class TestLoadCellLines:
    def test_missing_yaml_returns_empty(self, tmp_path: Path) -> None:
        data = EncodeSignalReader._load_cell_lines(tmp_path / "nonexistent.yaml")
        assert data == {}

    def test_loads_yaml_correctly(self, tmp_path: Path) -> None:
        import yaml as _yaml

        yaml_path = tmp_path / "cl.yaml"
        yaml_path.write_text(_yaml.dump(MINIMAL_CELL_LINES), encoding="utf-8")
        data = EncodeSignalReader._load_cell_lines(yaml_path)
        assert "HeLa" in data
        assert data["HeLa"]["atac_seq"] == ENCODE_URL


# ---------------------------------------------------------------------------
# EncodeSignalReader._get_url_for_cell_line
# ---------------------------------------------------------------------------


class TestGetUrlForCellLine:
    def test_known_cell_line_and_key(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        url = reader._get_url_for_cell_line("HeLa", "atac_seq")
        assert url == ENCODE_URL

    def test_unknown_cell_line_returns_none(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        assert reader._get_url_for_cell_line("K562", "atac_seq") is None

    def test_missing_key_returns_none(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        assert reader._get_url_for_cell_line("HeLa", "h3k27me3_chip") is None

    def test_null_value_returns_none(self, tmp_path: Path) -> None:
        reader = _make_reader(
            tmp_path,
            cell_lines={"HeLa": {"atac_seq": None}},
        )
        assert reader._get_url_for_cell_line("HeLa", "atac_seq") is None


# ---------------------------------------------------------------------------
# EncodeSignalReader.read_signal — single region
# ---------------------------------------------------------------------------


class TestReadSignal:
    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_reads_and_returns_signal(self, mock_open, MockCache, tmp_path: Path) -> None:
        bw = _make_bw(7.5)
        mock_open.return_value = bw

        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        result = reader.read_signal(ENCODE_URL, REGION_CHR6)
        assert result == pytest.approx(7.5)

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_cache_hit_skips_bigwig(self, mock_open, MockCache, tmp_path: Path) -> None:
        mock_cache = MagicMock()
        mock_cache.get.return_value = {"signal": 3.3}
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        result = reader.read_signal(ENCODE_URL, REGION_CHR6)
        assert result == pytest.approx(3.3)
        mock_open.assert_not_called()

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_cache_set_on_miss(self, mock_open, MockCache, tmp_path: Path) -> None:
        bw = _make_bw(2.0)
        mock_open.return_value = bw
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        reader.read_signal(ENCODE_URL, REGION_CHR6)
        mock_cache.set.assert_called_once()
        key = mock_cache.set.call_args[0][0]
        assert "encode_signal" in key


# ---------------------------------------------------------------------------
# EncodeSignalReader.read_signal_bulk
# ---------------------------------------------------------------------------


class TestReadSignalBulk:
    def test_empty_input_returns_empty(self, tmp_path: Path) -> None:
        reader = _make_reader(tmp_path)
        assert reader.read_signal_bulk(ENCODE_URL, []) == []

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_opens_bigwig_once_for_multiple_regions(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        bw = MagicMock()
        bw.stats.side_effect = [[1.0], [2.0], [3.0]]
        mock_open.return_value = bw

        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        results = reader.read_signal_bulk(
            ENCODE_URL, [REGION_CHR6, REGION_CHR1, REGION_CHR17]
        )
        mock_open.assert_called_once()
        bw.close.assert_called_once()
        assert results == pytest.approx([1.0, 2.0, 3.0])

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_all_cache_hits_skips_bigwig(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        mock_cache = MagicMock()
        mock_cache.get.side_effect = [{"signal": 4.0}, {"signal": 5.0}]
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        results = reader.read_signal_bulk(ENCODE_URL, [REGION_CHR6, REGION_CHR1])
        mock_open.assert_not_called()
        assert results == pytest.approx([4.0, 5.0])

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_bigwig_open_failure_returns_unknown(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        mock_open.side_effect = OSError("connection refused")
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        results = reader.read_signal_bulk(ENCODE_URL, [REGION_CHR6, REGION_CHR1])
        assert results == [UNKNOWN_SIGNAL, UNKNOWN_SIGNAL]

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_preserves_input_order(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        bw = MagicMock()
        bw.stats.side_effect = [[10.0], [20.0]]
        mock_open.return_value = bw
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        results = reader.read_signal_bulk(ENCODE_URL, [REGION_CHR1, REGION_CHR17])
        assert results[0] == pytest.approx(10.0)
        assert results[1] == pytest.approx(20.0)

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @patch("src.stage4_epigenetic.encode_reader.pyBigWig.open")
    def test_bigwig_closed_after_reads(
        self, mock_open, MockCache, tmp_path: Path
    ) -> None:
        bw = _make_bw(1.0)
        mock_open.return_value = bw
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        reader.read_signal_bulk(ENCODE_URL, [REGION_CHR6])
        bw.close.assert_called_once()


# ---------------------------------------------------------------------------
# EncodeSignalReader.resolve_file_url — ENCODE API
# ---------------------------------------------------------------------------


class TestResolveFileUrl:
    @responses_lib.activate
    def test_resolves_via_s3_url(self, tmp_path: Path) -> None:
        s3_url = "https://s3.amazonaws.com/encode-public/ENCFF492CEJ.bigWig"
        responses_lib.add(
            responses_lib.GET,
            f"{ENCODE_PORTAL}/files/{ACCESSION}/?format=json",
            json={"cloud_metadata": {"url": s3_url}, "href": "/files/ENCFF492CEJ/@@download/ENCFF492CEJ.bigWig"},
            status=200,
        )

        reader = _make_reader(tmp_path)
        url = reader.resolve_file_url(ACCESSION)
        assert url == s3_url

    @responses_lib.activate
    def test_falls_back_to_href(self, tmp_path: Path) -> None:
        href = "/files/ENCFF492CEJ/@@download/ENCFF492CEJ.bigWig"
        responses_lib.add(
            responses_lib.GET,
            f"{ENCODE_PORTAL}/files/{ACCESSION}/?format=json",
            json={"href": href},
            status=200,
        )

        reader = _make_reader(tmp_path)
        url = reader.resolve_file_url(ACCESSION)
        assert url == f"{ENCODE_PORTAL}{href}"

    @responses_lib.activate
    def test_raises_if_no_url_in_response(self, tmp_path: Path) -> None:
        responses_lib.add(
            responses_lib.GET,
            f"{ENCODE_PORTAL}/files/{ACCESSION}/?format=json",
            json={"status": "in progress"},
            status=200,
        )

        reader = _make_reader(tmp_path)
        with pytest.raises(ValueError, match="no URL"):
            reader.resolve_file_url(ACCESSION)

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    def test_cache_hit_skips_api(self, MockCache, tmp_path: Path) -> None:
        cached_url = "https://cached.example.com/file.bigWig"
        mock_cache = MagicMock()
        mock_cache.get.return_value = {"url": cached_url}
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        url = reader.resolve_file_url(ACCESSION)
        assert url == cached_url

    @patch("src.stage4_epigenetic.encode_reader.Cache")
    @responses_lib.activate
    def test_cache_set_on_api_hit(self, MockCache, tmp_path: Path) -> None:
        s3_url = "https://s3.amazonaws.com/encode-public/ENCFF492CEJ.bigWig"
        responses_lib.add(
            responses_lib.GET,
            f"{ENCODE_PORTAL}/files/{ACCESSION}/?format=json",
            json={"cloud_metadata": {"url": s3_url}},
            status=200,
        )
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        MockCache.return_value.__enter__ = lambda s: mock_cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)

        reader = _make_reader(tmp_path)
        reader.resolve_file_url(ACCESSION)
        mock_cache.set.assert_called_once()
        key = mock_cache.set.call_args[0][0]
        assert f"encode_url:{ACCESSION}" == key
