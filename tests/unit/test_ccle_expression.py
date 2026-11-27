"""Unit tests for src/stage4_epigenetic/ccle_expression.py.

Two test categories:
  - TestCCLERealData: integration-level tests that read the actual
    CCLE_Expression.csv (291 MB).  They are skipped automatically
    when the file is absent (CI without data).
  - TestCCLEMock: pure unit tests using a small in-memory CSV written
    to tmp_path — no dependency on the 291 MB file.
  - TestCCLEHelpers: tests for module-level helpers.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml as _yaml

from src.core.config import load_config
from src.core.models import CCLEResult
from src.stage4_epigenetic.ccle_expression import (
    CCLEReader,
)

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_REAL_CCLE = Path("data/3_Topoloji_Epigenetik/CCLE/CCLE_Expression.csv")

# Real DepMap IDs verified against the CSV
_HELA_ACH = "ACH-001113"
_K562_ACH = "ACH-000707"

# Minimal fake CSV used by mock tests
_MOCK_CSV = textwrap.dedent("""\
    ,SequencingID,ModelConditionID,ModelID,IsDefaultEntryForMC,IsDefaultEntryForModel,VEGFA (7422),MYC (4609),TP53 (7157)
    0,SEQ-001,MC-001,ACH-MOCK1,Yes,Yes,6.5,8.0,5.0
    1,SEQ-002,MC-002,ACH-MOCK2,Yes,Yes,0.3,9.1,4.2
    2,SEQ-003,MC-003,ACH-MOCK3,Yes,No,10.0,1.0,3.0
""")

_MOCK_DEPMAP = {
    "MockHeLa": "ACH-MOCK1",
    "MockK562": "ACH-MOCK2",
    "MockNoDefault": "ACH-MOCK3",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(tmp_path: Path) -> object:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "target_gene: VEGFA\ncell_line: HeLa\nsarna_sequence: GCAACCATAGCCTCGGCCGC\n",
        encoding="utf-8",
    )
    config = load_config(cfg_file)
    config.data_paths.cache_db = str(tmp_path / "cache.db")
    return config


def _make_mock_reader(tmp_path: Path, cell_lines: dict | None = None) -> CCLEReader:
    """Build a CCLEReader backed by the small mock CSV."""
    config = _make_config(tmp_path)
    csv_path = tmp_path / "CCLE_Expression.csv"
    csv_path.write_text(_MOCK_CSV, encoding="utf-8")

    depmap_yaml = tmp_path / "ccle_depmap_ids.yaml"
    depmap_yaml.write_text(
        _yaml.dump(cell_lines or _MOCK_DEPMAP), encoding="utf-8"
    )
    return CCLEReader(config, csv_path=csv_path, depmap_ids_yaml=depmap_yaml)


def _make_real_reader(tmp_path: Path) -> CCLEReader:
    """Build a CCLEReader backed by the real 291 MB CCLE CSV."""
    config = _make_config(tmp_path)
    depmap_yaml = Path("config/ccle_depmap_ids.yaml")
    return CCLEReader(config, csv_path=_REAL_CCLE, depmap_ids_yaml=depmap_yaml)


# ---------------------------------------------------------------------------
# TestCCLERealData — skipped when CCLE CSV absent
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _REAL_CCLE.exists(),
    reason="CCLE_Expression.csv not present (data not downloaded)",
)
class TestCCLERealData:
    def test_hela_vegfa_expression_value(self, tmp_path: Path) -> None:
        reader = _make_real_reader(tmp_path)
        result = reader.get_expression("VEGFA", "HeLa")

        assert result.gene == "VEGFA"
        assert result.cell_line == "HeLa"
        assert result.expression_value == pytest.approx(6.231, abs=0.01)

    def test_hela_vegfa_is_expressed(self, tmp_path: Path) -> None:
        reader = _make_real_reader(tmp_path)
        result = reader.get_expression("VEGFA", "HeLa")
        assert result.is_expressed is True

    def test_hela_vegfa_percentile_range(self, tmp_path: Path) -> None:
        reader = _make_real_reader(tmp_path)
        result = reader.get_expression("VEGFA", "HeLa")
        # HeLa VEGFA is ~63rd percentile across CCLE
        assert 0.55 < result.expression_percentile < 0.75

    def test_k562_myc_high_expression(self, tmp_path: Path) -> None:
        reader = _make_real_reader(tmp_path)
        result = reader.get_expression("MYC", "K562")
        # K562 is a leukemia line with very high MYC
        assert result.expression_value == pytest.approx(9.295, abs=0.01)
        assert result.is_expressed is True
        assert result.expression_percentile > 0.95

    def test_a549_vegfa_expressed(self, tmp_path: Path) -> None:
        reader = _make_real_reader(tmp_path)
        result = reader.get_expression("VEGFA", "A549")
        assert result.expression_value == pytest.approx(4.254, abs=0.01)
        assert result.is_expressed is True

    def test_mcf7_vegfa_expressed(self, tmp_path: Path) -> None:
        reader = _make_real_reader(tmp_path)
        result = reader.get_expression("VEGFA", "MCF7")
        assert result.is_expressed is True

    def test_gene_not_found_is_unknown_not_zero(self, tmp_path: Path) -> None:
        """Roadmap B19. An expression of 0.0 means *not expressed*, which means
        *cannot be silenced*, which reads as **lower risk** — for a gene nobody
        measured. These three tests asserted that 0.0 until B19; they were
        pinning the invariant-2 violation in place.
        """
        reader = _make_real_reader(tmp_path)
        result = reader.get_expression("NOTAREALGENEXYZ123", "HeLa")
        assert result.expression_value is None
        assert result.is_expressed is None
        assert result.expression_percentile is None

    def test_cell_line_not_found_is_unknown_not_zero(self, tmp_path: Path) -> None:
        reader = _make_real_reader(tmp_path)
        result = reader.get_expression("VEGFA", "NotARealCellLine")
        assert result.expression_value is None
        assert result.is_expressed is None

    def test_hek293t_absent_is_unknown_not_zero(self, tmp_path: Path) -> None:
        # HEK293T is null in ccle_depmap_ids.yaml: there is no DepMap model for
        # it, so there is nothing to look up — and nothing to look up is not a
        # measured zero.
        reader = _make_real_reader(tmp_path)
        result = reader.get_expression("VEGFA", "HEK293T")
        assert result.expression_value is None

    def test_percentile_within_unit_interval(self, tmp_path: Path) -> None:
        reader = _make_real_reader(tmp_path)
        result = reader.get_expression("MYC", "MCF7")
        assert 0.0 <= result.expression_percentile <= 1.0

    def test_returns_ccle_result_type(self, tmp_path: Path) -> None:
        reader = _make_real_reader(tmp_path)
        result = reader.get_expression("VEGFA", "HeLa")
        assert isinstance(result, CCLEResult)

    def test_cache_hit_skips_csv(self, tmp_path: Path) -> None:
        reader = _make_real_reader(tmp_path)
        # Warm the cache
        result1 = reader.get_expression("MYC", "K562")
        # Second call should hit cache — patch read_csv to verify not called
        with patch("src.stage4_epigenetic.ccle_expression.pd.read_csv") as mock_read:
            result2 = reader.get_expression("MYC", "K562")
            mock_read.assert_not_called()
        assert result1.expression_value == pytest.approx(result2.expression_value)


# ---------------------------------------------------------------------------
# TestCCLEMock — fast, no 291 MB dependency
# ---------------------------------------------------------------------------


class TestCCLEMock:
    def test_returns_correct_value(self, tmp_path: Path) -> None:
        reader = _make_mock_reader(tmp_path)
        result = reader.get_expression("VEGFA", "MockHeLa")
        assert result.expression_value == pytest.approx(6.5)
        assert result.is_expressed is True  # 6.5 > threshold 1.0

    def test_returns_ccle_result_type(self, tmp_path: Path) -> None:
        reader = _make_mock_reader(tmp_path)
        assert isinstance(reader.get_expression("VEGFA", "MockHeLa"), CCLEResult)

    def test_low_expression_is_not_expressed(self, tmp_path: Path) -> None:
        reader = _make_mock_reader(tmp_path)
        # MockK562 has VEGFA = 0.3 (below threshold)
        result = reader.get_expression("VEGFA", "MockK562")
        assert result.expression_value == pytest.approx(0.3)
        assert result.is_expressed is False

    def test_gene_not_found_is_unknown(self, tmp_path: Path) -> None:
        """Roadmap B19: a gene absent from the header was never measured."""
        reader = _make_mock_reader(tmp_path)
        result = reader.get_expression("FAKEGENE", "MockHeLa")
        assert result.expression_value is None
        assert result.is_expressed is None
        assert result.expression_percentile is None

    def test_cell_line_not_in_depmap_is_unknown(self, tmp_path: Path) -> None:
        reader = _make_mock_reader(tmp_path)
        result = reader.get_expression("VEGFA", "UnknownLine")
        assert result.expression_value is None
        assert result.is_expressed is None

    def test_ach_id_not_in_csv_is_unknown(self, tmp_path: Path) -> None:
        # MockNoDefault has IsDefaultEntryForModel=No → excluded. An excluded
        # row is a row nobody read, not a row that read zero.
        reader = _make_mock_reader(tmp_path)
        result = reader.get_expression("VEGFA", "MockNoDefault")
        assert result.expression_value is None

    def test_percentile_less_than_one(self, tmp_path: Path) -> None:
        reader = _make_mock_reader(tmp_path)
        result = reader.get_expression("MYC", "MockHeLa")
        # MockHeLa MYC=8.0; MockK562 MYC=9.1 → pct < 1.0
        assert 0.0 <= result.expression_percentile < 1.0

    def test_highest_value_has_max_percentile(self, tmp_path: Path) -> None:
        reader = _make_mock_reader(tmp_path)
        # MockK562 MYC=9.1 is the highest among default entries
        result = reader.get_expression("MYC", "MockK562")
        assert result.expression_percentile == pytest.approx(0.5)  # 1/2 values < 9.1

    def test_gene_and_cell_line_stored_in_result(self, tmp_path: Path) -> None:
        reader = _make_mock_reader(tmp_path)
        result = reader.get_expression("TP53", "MockHeLa")
        assert result.gene == "TP53"
        assert result.cell_line == "MockHeLa"

    def test_csv_not_found_is_unknown(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        depmap_yaml = tmp_path / "ccle_depmap_ids.yaml"
        depmap_yaml.write_text(_yaml.dump(_MOCK_DEPMAP), encoding="utf-8")
        reader = CCLEReader(
            config,
            csv_path=tmp_path / "nonexistent.csv",
            depmap_ids_yaml=depmap_yaml,
        )
        result = reader.get_expression("VEGFA", "MockHeLa")
        # A missing CSV is the loudest possible "not measured".
        assert result.expression_value is None

    def test_cache_hit_skips_read_csv(self, tmp_path: Path) -> None:
        reader = _make_mock_reader(tmp_path)
        # Warm the cache
        reader.get_expression("VEGFA", "MockHeLa")
        # Second call must be served from cache
        with patch("src.stage4_epigenetic.ccle_expression.pd.read_csv") as mock_read:
            result = reader.get_expression("VEGFA", "MockHeLa")
            mock_read.assert_not_called()
        assert result.expression_value == pytest.approx(6.5)

    def test_header_loaded_once(self, tmp_path: Path) -> None:
        """_ensure_header is called at most once regardless of query count."""
        reader = _make_mock_reader(tmp_path)
        with patch.object(reader, "_ensure_header", wraps=reader._ensure_header) as mock_hdr:
            reader.get_expression("VEGFA", "MockHeLa")
            reader.get_expression("MYC", "MockHeLa")
            # _ensure_header may be called multiple times internally but
            # after the first real call it is a no-op (guard flag is set)
            assert reader._header_loaded is True
            _ = mock_hdr  # suppress unused warning


# ---------------------------------------------------------------------------
# TestFindGeneColumn
# ---------------------------------------------------------------------------


class TestFindGeneColumn:
    def test_finds_vegfa(self, tmp_path: Path) -> None:
        reader = _make_mock_reader(tmp_path)
        col = reader._find_gene_column("VEGFA")
        assert col == "VEGFA (7422)"

    def test_finds_myc(self, tmp_path: Path) -> None:
        reader = _make_mock_reader(tmp_path)
        col = reader._find_gene_column("MYC")
        assert col == "MYC (4609)"

    def test_returns_none_for_unknown_gene(self, tmp_path: Path) -> None:
        reader = _make_mock_reader(tmp_path)
        assert reader._find_gene_column("NOTEXIST") is None

    def test_header_not_reloaded_on_second_call(self, tmp_path: Path) -> None:
        reader = _make_mock_reader(tmp_path)
        reader._find_gene_column("VEGFA")
        assert reader._header_loaded is True
        with patch("src.stage4_epigenetic.ccle_expression.pd.read_csv") as mock_read:
            reader._find_gene_column("MYC")
            mock_read.assert_not_called()


# ---------------------------------------------------------------------------
# TestLoadDepMapIds
# ---------------------------------------------------------------------------


class TestLoadDepMapIds:
    def test_loads_mapping(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "ids.yaml"
        yaml_path.write_text("HeLa: ACH-001113\nK562: ACH-000707\n", encoding="utf-8")
        mapping = CCLEReader._load_depmap_ids(yaml_path)
        assert mapping["HeLa"] == "ACH-001113"
        assert mapping["K562"] == "ACH-000707"

    def test_null_values_excluded(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "ids.yaml"
        yaml_path.write_text("HeLa: ACH-001113\nHEK293T: null\n", encoding="utf-8")
        mapping = CCLEReader._load_depmap_ids(yaml_path)
        assert "HEK293T" not in mapping

    def test_missing_yaml_returns_empty(self, tmp_path: Path) -> None:
        mapping = CCLEReader._load_depmap_ids(tmp_path / "nonexistent.yaml")
        assert mapping == {}


# ---------------------------------------------------------------------------
# B19 — the unknown must survive all the way to the merger
# ---------------------------------------------------------------------------


class TestUnknownReachesTheMerger:
    """A `None` at the source is only useful if nothing downstream fills it in.

    The merger was already built for this by `B2`: `ScoreComponents.
    ccle_expression` is `float | None` and `epigenetic_merger` excludes an
    unknown channel and renormalises the remaining weights. What was missing
    was the signal ever *being* unknown — so these tests pin the seam, which
    is where this project keeps losing things (`H4`'s porcelain bug).
    """

    def test_model_default_is_unknown(self) -> None:
        from src.core.models import CCLEResult

        result = CCLEResult(gene="X", cell_line="HeLa")
        assert result.expression_value is None
        assert result.is_expressed is None
        assert result.expression_percentile is None

    def test_adapter_failure_path_writes_null_not_zero(self, tmp_path: Path) -> None:
        """`ccle_reader`'s except branch hand-wrote three zeros."""
        import inspect

        from src.stage4_epigenetic import ccle_reader

        source = inspect.getsource(ccle_reader)
        assert '"expression_value": 0.0' not in source
        assert '"expression_percentile": 0.0' not in source

    def test_merger_excludes_an_unknown_expression(self) -> None:
        from src.stage4_epigenetic.epigenetic_merger import _as_optional

        assert _as_optional(None) is None
        assert _as_optional(0.0) == 0.0  # a measured zero stays a zero
