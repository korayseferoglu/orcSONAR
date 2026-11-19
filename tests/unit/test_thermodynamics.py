"""Unit tests for src/stage5_biophysics/thermodynamics.py."""

from __future__ import annotations

import os

import pytest

from src.core.models import ThermoResult
from src.stage5_biophysics.thermodynamics import (
    TurnerCalculator,
    _parse_4x4_tables,
    _parse_init_energy,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

TURNER_DIR = os.path.join("data", "4_Biyofizik_Yapısal", "Turner_Rules")
STACK_DG = os.path.join(TURNER_DIR, "rna.stack.dg")
HELIX_ENDS_DG = os.path.join(TURNER_DIR, "rna.helix_ends.dg")
MISC_DG = os.path.join(TURNER_DIR, "rna.miscloop.dg")

TURNER_FILES_PRESENT = os.path.isfile(STACK_DG)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def calc() -> TurnerCalculator:
    """A TurnerCalculator loaded from the real data files."""
    return TurnerCalculator(TURNER_DIR)


# ---------------------------------------------------------------------------
# _parse_4x4_tables
# ---------------------------------------------------------------------------


class TestParse4x4Tables:
    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_stack_has_six_starting_pairs(self) -> None:
        tables = _parse_4x4_tables(STACK_DG)
        # AU, CG, GC, GU, UA, UG
        assert len(tables) == 6

    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_au_table_contains_aa_uu_stack(self) -> None:
        # 5'-AA/3'-UU = -0.9 kcal/mol (Turner 2004)
        tables = _parse_4x4_tables(STACK_DG)
        au_table = tables[("A", "U")]
        assert au_table[("A", "U")] == pytest.approx(-0.9)

    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_gc_table_contains_gc_cg_stack(self) -> None:
        # 5'-GC/3'-CG = -3.4 kcal/mol
        tables = _parse_4x4_tables(STACK_DG)
        gc_table = tables[("G", "C")]
        assert gc_table[("C", "G")] == pytest.approx(-3.4)

    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_dots_not_in_table(self) -> None:
        # "." entries (infinity) must not appear as float values
        tables = _parse_4x4_tables(STACK_DG)
        for table in tables.values():
            for val in table.values():
                assert val != float("inf")
                assert isinstance(val, float)

    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_gu_wobble_table_present(self) -> None:
        tables = _parse_4x4_tables(STACK_DG)
        assert ("G", "U") in tables
        assert ("U", "G") in tables

    def test_missing_file_raises_os_error(self, tmp_path) -> None:
        with pytest.raises(OSError):
            _parse_4x4_tables(str(tmp_path / "nonexistent.dg"))


# ---------------------------------------------------------------------------
# _parse_init_energy
# ---------------------------------------------------------------------------


class TestParseInitEnergy:
    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_reads_4_1_from_miscloop(self) -> None:
        energy = _parse_init_energy(MISC_DG)
        assert energy == pytest.approx(4.1)

    def test_returns_fallback_on_missing_file(self, tmp_path) -> None:
        energy = _parse_init_energy(str(tmp_path / "missing.dg"))
        assert energy == pytest.approx(4.1)

    def test_returns_fallback_on_empty_file(self, tmp_path) -> None:
        empty = tmp_path / "empty.dg"
        empty.write_text("")
        energy = _parse_init_energy(str(empty))
        assert energy == pytest.approx(4.1)


# ---------------------------------------------------------------------------
# TurnerCalculator — constructor
# ---------------------------------------------------------------------------


class TestTurnerCalculatorInit:
    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_loads_without_error(self) -> None:
        c = TurnerCalculator(TURNER_DIR)
        assert len(c._stacks) == 6

    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_init_dg_is_4_1(self, calc) -> None:
        assert calc._init_dg == pytest.approx(4.1)

    def test_bad_dir_does_not_raise_constructor(self, tmp_path) -> None:
        # Graceful degradation: stacks empty, init falls back to 4.1
        c = TurnerCalculator(str(tmp_path / "nonexistent"))
        assert c._stacks == {}
        assert c._init_dg == pytest.approx(4.1)


# ---------------------------------------------------------------------------
# TurnerCalculator.calculate_duplex_dg — input validation
# ---------------------------------------------------------------------------


class TestCalculateDuplexDgValidation:
    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_empty_sarna_raises(self, calc) -> None:
        with pytest.raises(ValueError, match="empty"):
            calc.calculate_duplex_dg("", "")

    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_length_mismatch_raises(self, calc) -> None:
        with pytest.raises(ValueError, match="length"):
            calc.calculate_duplex_dg("GCA", "CGUA")

    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_t_converted_to_u(self, calc) -> None:
        # "GCATG" should be treated as "GCAUG"
        r_t = calc.calculate_duplex_dg("GCATG", "CGUAC")
        r_u = calc.calculate_duplex_dg("GCAUG", "CGUAC")
        assert r_t.delta_g == pytest.approx(r_u.delta_g)

    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_returns_thermo_result_instance(self, calc) -> None:
        result = calc.calculate_duplex_dg("GCAUG", "CGUAC")
        assert isinstance(result, ThermoResult)


# ---------------------------------------------------------------------------
# test_known_duplex_dg
# Referans: 5'-GCAUG-3' / 3'-CGUAC-5'
# Turner 2004 nearest-neighbor gives ΔG ≈ -4.6 kcal/mol
# (init=4.1, stacks: GC/CG=-3.4, CG/AU=-2.1, AU/UA=-1.1, UA/GC=-2.1 = -8.7)
# ---------------------------------------------------------------------------


class TestKnownDuplexDg:
    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_gcaug_cguac_delta_g(self, calc) -> None:
        """ΔG for 5'-GCAUG-3' / 3'-CGUAC-5' computed from Turner tables."""
        # Expected: init(4.1) + stacks(-8.7) + terminal(GC,GC=0.0) = -4.6
        result = calc.calculate_duplex_dg("GCAUG", "CGUAC")
        assert result.delta_g == pytest.approx(-4.6, abs=0.15)

    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_gcaug_has_no_mismatches(self, calc) -> None:
        result = calc.calculate_duplex_dg("GCAUG", "CGUAC")
        assert result.has_mismatches is False
        assert result.mismatch_penalties == []

    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_gcaug_has_four_stack_entries(self, calc) -> None:
        result = calc.calculate_duplex_dg("GCAUG", "CGUAC")
        assert len(result.stack_energies) == 4

    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_gcaug_individual_stacks(self, calc) -> None:
        result = calc.calculate_duplex_dg("GCAUG", "CGUAC")
        stacks = result.stack_energies
        assert stacks[0] == pytest.approx(-3.4)  # GC/CG
        assert stacks[1] == pytest.approx(-2.1)  # CG/AU (CA/GU)
        assert stacks[2] == pytest.approx(-1.1)  # AU/UA
        assert stacks[3] == pytest.approx(-2.1)  # UA/GC (UG/AC)


# ---------------------------------------------------------------------------
# test_perfect_complement
# AAAA / UUUU — all AU pairs
# ---------------------------------------------------------------------------


class TestPerfectComplement:
    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_aaaa_uuuu_is_positive(self, calc) -> None:
        # AU-only duplex is weak (AU stacks low, + 2× terminal penalty 0.5)
        # Expected: init(4.1) + 2*terminal(0.5) + 3*stack(-0.9) = 5.1 - 2.7 = +2.4
        result = calc.calculate_duplex_dg("AAAA", "UUUU")
        assert result.delta_g == pytest.approx(2.4, abs=0.15)

    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_aaaa_uuuu_no_mismatches(self, calc) -> None:
        result = calc.calculate_duplex_dg("AAAA", "UUUU")
        assert result.has_mismatches is False

    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_aaaa_uuuu_three_stacks(self, calc) -> None:
        result = calc.calculate_duplex_dg("AAAA", "UUUU")
        assert len(result.stack_energies) == 3

    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_gc_rich_duplex_more_stable_than_au(self, calc) -> None:
        au_result = calc.calculate_duplex_dg("AAAA", "UUUU")
        gc_result = calc.calculate_duplex_dg("GCGC", "CGCG")
        assert gc_result.delta_g < au_result.delta_g


# ---------------------------------------------------------------------------
# test_gu_wobble_penalty
# sarna=GUAG / target=UAUC → terminal GU wobble pair
# ---------------------------------------------------------------------------


class TestGUWobble:
    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_gu_wobble_not_counted_as_mismatch(self, calc) -> None:
        result = calc.calculate_duplex_dg("GUAG", "UAUC")
        assert result.has_mismatches is False
        assert result.mismatch_penalties == []

    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_gu_wobble_delta_g_near_zero(self, calc) -> None:
        # Expected: init(4.1) + terminal(GU=0.5, GC=0.0) + stacks(-4.8) = -0.2
        result = calc.calculate_duplex_dg("GUAG", "UAUC")
        assert result.delta_g == pytest.approx(-0.2, abs=0.15)

    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_gu_wobble_more_stable_than_same_position_mismatch(self, calc) -> None:
        # GU wobble vs AA mismatch at same terminal position
        gu_result = calc.calculate_duplex_dg("GUAG", "UAUC")  # G-U wobble
        # `AUAG` was tried first and discarded: A-U is Watson-Crick, so it is
        # not the mismatch this test needs. Its result sat unused here (H15).
        mm_result = calc.calculate_duplex_dg("CUAG", "UAUC")  # C-U mismatch at pos 0
        assert gu_result.delta_g < mm_result.delta_g

    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_ug_wobble_also_valid(self, calc) -> None:
        # U-G wobble (sarna has U, target has G)
        result = calc.calculate_duplex_dg("UCAG", "GAUC")
        # U-G (wobble), C-A... wait, let's verify: sarna=UCAG, target=GAUC
        # U pairs G (wobble ✓), C pairs A (mismatch ✗)...
        # Use a clean UG wobble: sarna=UGCA, target=ACGU
        result = calc.calculate_duplex_dg("UGCA", "ACGU")
        # U-A? No: sarna[0]=U, target[0]=A → U-A WC
        # G-C WC, C-G WC, A-U WC → all WC, no wobble
        # For explicit UG wobble: sarna[0]=U, target[0]=G
        result = calc.calculate_duplex_dg("UAUG", "GAUC")
        # U-G (wobble ✓), A-A (mismatch ✗)
        # Let me use: sarna=UGCA, target=GCGU
        # U-G (wobble ✓), G-C WC, C-G WC, A-U WC
        result = calc.calculate_duplex_dg("UGCA", "GCGU")
        # U-G wobble ✓, G-C ✓, C-G ✓, A-U ✓
        assert result.has_mismatches is False


# ---------------------------------------------------------------------------
# test_mismatch_penalty
# sarna=GCAAG / target=CGUAC → A-A mismatch at position 3
# ---------------------------------------------------------------------------


class TestMismatchPenalty:
    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_mismatch_detected(self, calc) -> None:
        result = calc.calculate_duplex_dg("GCAAG", "CGUAC")
        assert result.has_mismatches is True

    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_mismatch_count(self, calc) -> None:
        result = calc.calculate_duplex_dg("GCAAG", "CGUAC")
        assert len(result.mismatch_penalties) == 1

    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_mismatch_less_stable_than_perfect(self, calc) -> None:
        perfect = calc.calculate_duplex_dg("GCAUG", "CGUAC")
        mismatch = calc.calculate_duplex_dg("GCAAG", "CGUAC")
        assert mismatch.delta_g > perfect.delta_g

    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_mismatch_delta_g(self, calc) -> None:
        # init(4.1) + stacks(GC/CG=-3.4, CG/AU=-2.1, skip, skip) + mismatch(+1.5) = 0.1
        result = calc.calculate_duplex_dg("GCAAG", "CGUAC")
        assert result.delta_g == pytest.approx(0.1, abs=0.15)

    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_two_mismatches_higher_delta_g(self, calc) -> None:
        one_mm = calc.calculate_duplex_dg("GCAAG", "CGUAC")  # 1 mismatch
        two_mm = calc.calculate_duplex_dg("GCAAA", "CGUAC")  # 2 mismatches
        assert two_mm.delta_g > one_mm.delta_g

    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_mismatch_stacks_at_boundary_are_zero(self, calc) -> None:
        result = calc.calculate_duplex_dg("GCAAG", "CGUAC")
        # stack[2] and stack[3] involve the mismatch position → both 0.0
        assert result.stack_energies[2] == pytest.approx(0.0)
        assert result.stack_energies[3] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_single_base_pair(self, calc) -> None:
        result = calc.calculate_duplex_dg("G", "C")
        # Only initiation + terminal penalties; no stacks
        assert isinstance(result, ThermoResult)
        assert result.stack_energies == []

    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_two_base_pair_duplex(self, calc) -> None:
        result = calc.calculate_duplex_dg("GC", "CG")
        assert len(result.stack_energies) == 1
        # GC terminal (0.0) + GC terminal (0.0) + init(4.1) + GC/CG stack(-3.4) = 0.7
        assert result.delta_g == pytest.approx(0.7, abs=0.15)

    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_lowercase_input_accepted(self, calc) -> None:
        r_lower = calc.calculate_duplex_dg("gcaug", "cguac")
        r_upper = calc.calculate_duplex_dg("GCAUG", "CGUAC")
        assert r_lower.delta_g == pytest.approx(r_upper.delta_g)

    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_longer_duplex_negative_dg(self, calc) -> None:
        # 20-mer perfect complement should give strongly negative ΔG
        sarna = "GCGCGCGCGCGCGCGCGCGC"
        target = "CGCGCGCGCGCGCGCGCGCG"
        result = calc.calculate_duplex_dg(sarna, target)
        assert result.delta_g < -10.0

    @pytest.mark.skipif(not TURNER_FILES_PRESENT, reason="Turner data files absent")
    def test_all_mismatches_large_positive_dg(self, calc) -> None:
        # All A-C mismatches → large positive ΔG
        result = calc.calculate_duplex_dg("AAAAA", "CCCCC")
        assert result.delta_g > 5.0
        assert len(result.mismatch_penalties) == 5
