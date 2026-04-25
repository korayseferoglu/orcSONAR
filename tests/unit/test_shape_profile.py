"""Unit tests for src/stage5_biophysics/shape_profile.py."""

from __future__ import annotations

import os
import tempfile

import pytest

from src.core.models import GenomicRegion
from src.stage5_biophysics.shape_profile import (
    _load_shape_data,
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
