"""Unit tests for src/stage5_biophysics/shape_profile.py."""

from __future__ import annotations

import gzip
import os
import tempfile

import pytest

from src.core.models import GenomicRegion
from src.stage5_biophysics.shape_profile import (
    _load_icshape_data,
    _load_shape_data,
    _strip_ensembl_version,
    get_shape_accessibility,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REGION = GenomicRegion(chrom="chr1", start=0, end=10)


def _write_shape_file(directory: str, filename: str, lines: list[str]) -> str:
    path = os.path.join(directory, filename)
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


# ---------------------------------------------------------------------------
# _load_shape_data
# ---------------------------------------------------------------------------


class TestLoadShapeData:
    def test_returns_none_when_directory_missing(self, tmp_path):
        result = _load_shape_data("NonExistent", str(tmp_path))
        assert result is None

    def test_returns_none_when_no_shape_files(self, tmp_path):
        cell_dir = tmp_path / "HeLa"
        cell_dir.mkdir()
        result = _load_shape_data("HeLa", str(tmp_path))
        assert result is None

    def test_loads_shape_file(self, tmp_path):
        cell_dir = tmp_path / "HeLa"
        cell_dir.mkdir()
        _write_shape_file(
            str(cell_dir),
            "test.shape",
            ["1\t0.1", "2\t0.8", "3\t1.2", "4\t-999"],
        )
        data = _load_shape_data("HeLa", str(tmp_path))
        assert data is not None
        assert data[1] == pytest.approx(0.1)
        assert data[2] == pytest.approx(0.8)
        assert data[3] == pytest.approx(1.2)
        assert 4 not in data  # -999 sentinel excluded

    def test_loads_map_file(self, tmp_path):
        cell_dir = tmp_path / "K562"
        cell_dir.mkdir()
        _write_shape_file(
            str(cell_dir),
            "data.map",
            ["# comment", "1\t0.5", "2\tnan", "3\t0.3"],
        )
        data = _load_shape_data("K562", str(tmp_path))
        assert data is not None
        assert 2 not in data  # nan excluded
        assert data[3] == pytest.approx(0.3)

    def test_case_insensitive_cell_line(self, tmp_path):
        cell_dir = tmp_path / "hela"
        cell_dir.mkdir()
        _write_shape_file(str(cell_dir), "r.shape", ["1\t0.9"])
        data = _load_shape_data("HeLa", str(tmp_path))
        assert data is not None

    def test_ignores_malformed_lines(self, tmp_path):
        cell_dir = tmp_path / "HeLa"
        cell_dir.mkdir()
        _write_shape_file(
            str(cell_dir), "r.shape", ["garbage", "1\t0.5", "", "  "]
        )
        data = _load_shape_data("HeLa", str(tmp_path))
        assert data is not None
        assert len(data) == 1


# ---------------------------------------------------------------------------
# get_shape_accessibility
# ---------------------------------------------------------------------------


class TestGetShapeAccessibility:
    def test_no_data_returns_neutral(self, tmp_path):
        region = GenomicRegion(chrom="chr1", start=0, end=100)
        result = get_shape_accessibility(region, "HeLa", str(tmp_path))
        assert result.data_available is False
        assert result.accessibility_score == pytest.approx(0.5)
        assert result.single_stranded_fraction == pytest.approx(0.5)

    def test_accessible_region(self, tmp_path):
        """All positions highly reactive → near-maximum accessibility."""
        cell_dir = tmp_path / "HeLa"
        cell_dir.mkdir()
        # positions 1–5 all have reactivity 1.6 → single-stranded
        _write_shape_file(
            str(cell_dir),
            "r.shape",
            [f"{i}\t1.6" for i in range(1, 6)],
        )
        region = GenomicRegion(chrom="chr1", start=0, end=5)
        result = get_shape_accessibility(region, "HeLa", str(tmp_path))
        assert result.data_available is True
        assert result.accessibility_score == pytest.approx(0.8, abs=0.01)
        assert result.single_stranded_fraction == pytest.approx(1.0)

    def test_inaccessible_region(self, tmp_path):
        """All positions with low reactivity → near-zero accessibility."""
        cell_dir = tmp_path / "HeLa"
        cell_dir.mkdir()
        _write_shape_file(
            str(cell_dir),
            "r.shape",
            [f"{i}\t0.1" for i in range(1, 6)],
        )
        region = GenomicRegion(chrom="chr1", start=0, end=5)
        result = get_shape_accessibility(region, "HeLa", str(tmp_path))
        assert result.data_available is True
        assert result.accessibility_score == pytest.approx(0.05, abs=0.01)
        assert result.single_stranded_fraction == pytest.approx(0.0)

    def test_no_overlap_returns_neutral(self, tmp_path):
        """SHAPE data present but no positions overlap the region."""
        cell_dir = tmp_path / "HeLa"
        cell_dir.mkdir()
        _write_shape_file(str(cell_dir), "r.shape", ["1000\t1.0"])
        region = GenomicRegion(chrom="chr1", start=0, end=5)
        result = get_shape_accessibility(region, "HeLa", str(tmp_path))
        assert result.data_available is True
        assert result.accessibility_score == pytest.approx(0.5)

    def test_mixed_reactivity(self, tmp_path):
        """Half single-stranded, half double-stranded."""
        cell_dir = tmp_path / "HeLa"
        cell_dir.mkdir()
        lines = ["1\t1.0", "2\t1.0", "3\t0.1", "4\t0.1"]
        _write_shape_file(str(cell_dir), "r.shape", lines)
        region = GenomicRegion(chrom="chr1", start=0, end=4)
        result = get_shape_accessibility(region, "HeLa", str(tmp_path))
        assert result.single_stranded_fraction == pytest.approx(0.5)
        assert result.mean_reactivity == pytest.approx(0.55, abs=0.01)

    def test_reactivity_clamped_at_1(self, tmp_path):
        """Reactivity above 2.0 is clamped to accessibility=1.0."""
        cell_dir = tmp_path / "HeLa"
        cell_dir.mkdir()
        _write_shape_file(str(cell_dir), "r.shape", ["1\t5.0"])
        region = GenomicRegion(chrom="chr1", start=0, end=1)
        result = get_shape_accessibility(region, "HeLa", str(tmp_path))
        assert result.accessibility_score == pytest.approx(1.0)

    def test_result_region_preserved(self, tmp_path):
        region = GenomicRegion(chrom="chr7", start=100, end=200)
        result = get_shape_accessibility(region, "HeLa", str(tmp_path))
        assert result.region == region


# ---------------------------------------------------------------------------
# icSHAPE per-transcript loader + lookup
# ---------------------------------------------------------------------------


def _write_icshape_file(
    cell_dir, filename: str, rows: list[tuple[str, list[str]]]
) -> str:
    """Write a gzipped icSHAPE table.

    Each row: (transcript_id_with_version, [reactivity strings of length N]).
    The output columns are: tid, length, "*", r_1, ..., r_length.
    """
    path = os.path.join(str(cell_dir), filename)
    with gzip.open(path, mode="wt", encoding="utf-8") as fh:
        for tid, vals in rows:
            cols = [tid, str(len(vals)), "*"] + list(vals)
            fh.write("\t".join(cols) + "\n")
    return path


@pytest.fixture(autouse=True)
def _reset_icshape_cache():
    """Clear the lru_cache on _load_icshape_data between tests."""
    _load_icshape_data.cache_clear()
    yield
    _load_icshape_data.cache_clear()


class TestStripEnsemblVersion:
    def test_with_version(self):
        assert _strip_ensembl_version("ENST00000606214.5") == "ENST00000606214"

    def test_without_version(self):
        assert _strip_ensembl_version("ENST00000606214") == "ENST00000606214"


class TestLoadIcshapeData:
    def test_returns_none_when_no_icshape_file(self, tmp_path):
        (tmp_path / "HeLa").mkdir()
        assert _load_icshape_data("HeLa", str(tmp_path)) is None

    def test_returns_none_when_cell_dir_missing(self, tmp_path):
        assert _load_icshape_data("HeLa", str(tmp_path)) is None

    def test_loads_basic_table(self, tmp_path):
        cell_dir = tmp_path / "HeLa"
        cell_dir.mkdir()
        _write_icshape_file(
            cell_dir,
            "GSM_HeLa_icSHAPE.txt.gz",
            [
                ("ENST00000000001.4", ["0.10", "NULL", "0.80", "1.20"]),
                ("ENST00000000002.1", ["NULL", "0.50"]),
            ],
        )
        table = _load_icshape_data("HeLa", str(tmp_path))
        assert table is not None
        # Versionless keys
        assert "ENST00000000001" in table
        assert "ENST00000000002" in table
        assert table["ENST00000000001"][0] == pytest.approx(0.10)
        assert table["ENST00000000001"][2] == pytest.approx(0.80)
        # NULL → NaN
        import math
        assert math.isnan(table["ENST00000000001"][1])
        assert math.isnan(table["ENST00000000002"][0])

    def test_case_insensitive_cell_line(self, tmp_path):
        cell_dir = tmp_path / "hela"
        cell_dir.mkdir()
        _write_icshape_file(
            cell_dir, "x_icSHAPE.txt.gz", [("ENST00000999.1", ["0.5"])]
        )
        assert _load_icshape_data("HeLa", str(tmp_path)) is not None

    def test_skips_truncated_rows(self, tmp_path):
        cell_dir = tmp_path / "HeLa"
        cell_dir.mkdir()
        path = os.path.join(str(cell_dir), "icSHAPE.txt.gz")
        with gzip.open(path, mode="wt", encoding="utf-8") as fh:
            # length=4 but only 2 reactivity columns supplied → must be skipped
            fh.write("ENST00000111.1\t4\t*\t0.1\t0.2\n")
            fh.write("ENST00000222.1\t2\t*\t0.3\t0.4\n")
        table = _load_icshape_data("HeLa", str(tmp_path))
        assert "ENST00000111" not in table
        assert "ENST00000222" in table


class TestGetShapeAccessibilityIcshape:
    def test_uses_icshape_when_transcript_present(self, tmp_path):
        cell_dir = tmp_path / "HeLa"
        cell_dir.mkdir()
        # Reactivities at tx positions 0..4 = [1.0, 1.0, 1.0, 0.1, 0.1]
        _write_icshape_file(
            cell_dir,
            "icSHAPE.txt.gz",
            [("ENST00000123.2", ["1.0", "1.0", "1.0", "0.1", "0.1"])],
        )
        region = GenomicRegion(chrom="chr1", start=0, end=20)
        result = get_shape_accessibility(
            region,
            "HeLa",
            str(tmp_path),
            transcript_id="ENST00000123",
            tx_start=0,
            tx_end=3,
        )
        assert result.data_available is True
        assert result.single_stranded_fraction == pytest.approx(1.0)
        assert result.mean_reactivity == pytest.approx(1.0, abs=0.01)

    def test_versioned_id_matches_versionless(self, tmp_path):
        cell_dir = tmp_path / "HeLa"
        cell_dir.mkdir()
        _write_icshape_file(
            cell_dir, "icSHAPE.txt.gz", [("ENST00000999.7", ["0.9", "0.9"])]
        )
        region = GenomicRegion(chrom="chr1", start=0, end=2)
        result = get_shape_accessibility(
            region,
            "HeLa",
            str(tmp_path),
            transcript_id="ENST00000999.7",  # passing with version too works
            tx_start=0,
            tx_end=2,
        )
        assert result.data_available is True
        assert result.single_stranded_fraction == pytest.approx(1.0)

    def test_null_window_returns_neutral_with_data_available(self, tmp_path):
        cell_dir = tmp_path / "HeLa"
        cell_dir.mkdir()
        _write_icshape_file(
            cell_dir, "icSHAPE.txt.gz", [("ENST00000333.1", ["NULL", "NULL", "NULL"])]
        )
        region = GenomicRegion(chrom="chr1", start=0, end=3)
        result = get_shape_accessibility(
            region,
            "HeLa",
            str(tmp_path),
            transcript_id="ENST00000333",
            tx_start=0,
            tx_end=3,
        )
        # Transcript present, but every measured slot was NULL → neutral, but
        # data_available stays True so consumers know icSHAPE was consulted.
        assert result.data_available is True
        assert result.accessibility_score == pytest.approx(0.5)
        assert result.single_stranded_fraction == pytest.approx(0.5)

    def test_unknown_transcript_falls_back_to_legacy(self, tmp_path):
        cell_dir = tmp_path / "HeLa"
        cell_dir.mkdir()
        _write_icshape_file(
            cell_dir, "icSHAPE.txt.gz", [("ENST_KNOWN.1", ["0.5"])]
        )
        # Legacy single-coord file should be picked up because the icSHAPE
        # table doesn't contain the requested transcript.
        with open(cell_dir / "legacy.shape", "w") as fh:
            fh.write("1\t1.0\n2\t1.0\n3\t1.0\n")
        region = GenomicRegion(chrom="chr1", start=0, end=3)
        result = get_shape_accessibility(
            region,
            "HeLa",
            str(tmp_path),
            transcript_id="ENST_UNKNOWN",
            tx_start=0,
            tx_end=3,
        )
        assert result.data_available is True
        assert result.single_stranded_fraction == pytest.approx(1.0)

    def test_missing_tx_args_uses_legacy(self, tmp_path):
        """Without tx_start/tx_end, icSHAPE is bypassed even if file exists."""
        cell_dir = tmp_path / "HeLa"
        cell_dir.mkdir()
        _write_icshape_file(
            cell_dir, "icSHAPE.txt.gz", [("ENST00000123.1", ["1.0", "1.0", "1.0"])]
        )
        with open(cell_dir / "legacy.shape", "w") as fh:
            fh.write("1\t0.1\n2\t0.1\n")
        region = GenomicRegion(chrom="chr1", start=0, end=2)
        # No transcript info → legacy path → low accessibility
        result = get_shape_accessibility(region, "HeLa", str(tmp_path))
        assert result.data_available is True
        assert result.accessibility_score == pytest.approx(0.05, abs=0.01)

    def test_window_clamped_to_transcript_bounds(self, tmp_path):
        cell_dir = tmp_path / "HeLa"
        cell_dir.mkdir()
        _write_icshape_file(
            cell_dir, "icSHAPE.txt.gz", [("ENST_X.1", ["1.0", "1.0"])]
        )
        region = GenomicRegion(chrom="chr1", start=0, end=10)
        # Ask for tx 0..10 although the transcript is only 2 nt long.
        result = get_shape_accessibility(
            region,
            "HeLa",
            str(tmp_path),
            transcript_id="ENST_X",
            tx_start=0,
            tx_end=10,
        )
        # Should average just the two available positions
        assert result.data_available is True
        assert result.single_stranded_fraction == pytest.approx(1.0)
