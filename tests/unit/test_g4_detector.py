"""Unit tests for src/stage5_biophysics/g4_detector.py."""

from __future__ import annotations

import pytest

from src.core.models import G4Motif, G4Result
from src.stage5_biophysics.g4_detector import (
    _find_g4_motifs,
    _reverse_complement,
    _score_g4_stability,
    detect_g4,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _motif(g_tracts: list[int], loops: list[int]) -> G4Motif:
    """Build a minimal G4Motif for stability testing."""
    return G4Motif(
        start=0,
        end=sum(g_tracts) + sum(loops),
        sequence="G" * sum(g_tracts),
        g_tract_lengths=g_tracts,
        loop_lengths=loops,
        stability_score=0.0,
    )


# ---------------------------------------------------------------------------
# _reverse_complement
# ---------------------------------------------------------------------------


class TestReverseComplement:
    def test_telomeric_rna_rc(self):
        # RC of telomeric G4 should be C-rich (no G4)
        assert _reverse_complement("GGGUUAGGGUUAGGGUUAGGG") == "CCCUAACCCUAACCCUAACCC"

    def test_c_rich_rc_gives_g4(self):
        # RC of C-rich region → G4 on antisense strand
        rc = _reverse_complement("CCCUUACCCUUACCCUUACCC")
        assert rc == "GGGUAAGGGUAAGGGUAAGGG"

    def test_t_treated_as_u(self):
        # T in input should be treated identically to U for complement
        rc_t = _reverse_complement("GGGTTAGGGTTAGGGTTAGGG")
        rc_u = _reverse_complement("GGGUUAGGGUUAGGGUUAGGG")
        # complement of T is A (same as complement of U)
        assert rc_t == rc_u

    def test_single_nucleotide(self):
        assert _reverse_complement("G") == "C"
        assert _reverse_complement("C") == "G"
        assert _reverse_complement("A") == "U"
        assert _reverse_complement("U") == "A"

    def test_empty_string(self):
        assert _reverse_complement("") == ""


# ---------------------------------------------------------------------------
# _score_g4_stability
# ---------------------------------------------------------------------------


class TestScoreG4Stability:
    def test_empty_fields_returns_zero(self):
        m = G4Motif(start=0, end=0, sequence="", g_tract_lengths=[], loop_lengths=[])
        assert _score_g4_stability(m) == pytest.approx(0.0)

    def test_telomeric_stability(self):
        # GGG × 4 with 3-nt loops: g_score=0.5, loop_score=0.667 → 0.583
        m = _motif([3, 3, 3, 3], [3, 3, 3])
        s = _score_g4_stability(m)
        assert s == pytest.approx(0.5833, abs=0.001)

    def test_longer_tracts_increase_stability(self):
        base = _score_g4_stability(_motif([3, 3, 3, 3], [3, 3, 3]))
        longer = _score_g4_stability(_motif([5, 5, 5, 5], [3, 3, 3]))
        assert longer > base

    def test_shorter_loops_increase_stability(self):
        long_loops = _score_g4_stability(_motif([3, 3, 3, 3], [6, 6, 6]))
        short_loops = _score_g4_stability(_motif([3, 3, 3, 3], [1, 1, 1]))
        assert short_loops > long_loops

    def test_min_loop_max_score(self):
        # 1-nt loops: loop_score=1.0; G-tract 6: g_score=1.0 → stability=1.0
        m = _motif([6, 6, 6, 6], [1, 1, 1])
        assert _score_g4_stability(m) == pytest.approx(1.0)

    def test_max_loop_zero_loop_score(self):
        # 7-nt loops: loop_score=0.0; G-tract 3: g_score=0.5 → stability=0.25
        m = _motif([3, 3, 3, 3], [7, 7, 7])
        assert _score_g4_stability(m) == pytest.approx(0.25, abs=0.001)

    def test_score_in_bounds(self):
        for g in ([3, 3, 3, 3], [6, 6, 6, 6], [3, 4, 5, 6]):
            for l in ([1, 1, 1], [7, 7, 7], [3, 5, 2]):
                s = _score_g4_stability(_motif(g, l))
                assert 0.0 <= s <= 1.0


# ---------------------------------------------------------------------------
# _find_g4_motifs
# ---------------------------------------------------------------------------


class TestFindG4Motifs:
    def test_telomeric_finds_one(self):
        seq = "GGGUUAGGGUUAGGGUUAGGG"
        motifs = _find_g4_motifs(seq)
        assert len(motifs) == 1
        m = motifs[0]
        assert m.g_tract_lengths == [3, 3, 3, 3]
        assert m.loop_lengths == [3, 3, 3]
        assert m.start == 0
        assert m.end == len(seq)

    def test_no_motif_in_non_g_sequence(self):
        assert _find_g4_motifs("ACUACUACUACUACUACUACU") == []

    def test_t_normalised_to_u(self):
        rna = _find_g4_motifs("GGGUUAGGGUUAGGGUUAGGG")
        dna = _find_g4_motifs("GGGTTAGGGTTAGGGTTAGGG")
        assert len(rna) == len(dna)
        assert rna[0].g_tract_lengths == dna[0].g_tract_lengths
        assert rna[0].loop_lengths == dna[0].loop_lengths

    def test_overlapping_five_tracts(self):
        # 5 G-tracts → 2 overlapping G4 motifs
        seq = "GGGAGGGAGGGAGGGAGGG"
        motifs = _find_g4_motifs(seq)
        assert len(motifs) == 2
        assert motifs[0].start == 0
        assert motifs[1].start == 4  # second G-tract starts at pos 4

    def test_strand_label(self):
        motifs = _find_g4_motifs("GGGAGGGAGGGAGGG", strand="-")
        assert all(m.strand == "-" for m in motifs)

    def test_stability_precomputed(self):
        motifs = _find_g4_motifs("GGGAGGGAGGGAGGG")
        assert motifs[0].stability_score > 0.0

    def test_longer_g_tracts_detected(self):
        seq = "GGGGTTAGGGGTTAGGGGTTAGGGGT"
        motifs = _find_g4_motifs(seq)
        assert len(motifs) >= 1
        assert max(motifs[0].g_tract_lengths) >= 4


# ---------------------------------------------------------------------------
# detect_g4 — main tests
# ---------------------------------------------------------------------------


class TestDetectG4:
    # ---- test_known_g4 ----

    def test_known_g4(self):
        """Telomeric RNA G4: GGGUUAGGGUUAGGGUUAGGG."""
        seq = "GGGUUAGGGUUAGGGUUAGGG"
        result = detect_g4(seq)

        assert isinstance(result, G4Result)
        assert result.g4_count >= 1
        assert result.risk_score > 0.0

        fwd = [m for m in result.motifs if m.strand == "+"]
        assert len(fwd) == 1
        m = fwd[0]
        assert m.g_tract_lengths == [3, 3, 3, 3]
        assert m.loop_lengths == [3, 3, 3]
        assert m.stability_score == pytest.approx(0.5833, abs=0.001)

    # ---- test_no_g4 ----

    def test_no_g4(self):
        """Non-G-rich sequence has zero motifs and zero risk."""
        result = detect_g4("ACUACUACUACUACUACUACU")
        assert result.g4_count == 0
        assert result.risk_score == pytest.approx(0.0)
        assert result.motifs == []
        assert result.g4_density == pytest.approx(0.0)

    # ---- test_both_strands ----

    def test_both_strands(self):
        """Forward G4 + C-rich region whose RC is a G4 → motifs on + and -."""
        # Forward G4 (strand "+")
        fwd_g4 = "GGGUUAGGGUUAGGGUUAGGG"
        # The RC of this C-rich region is GGGUAAGGGUAAGGGUAAGGG (also a G4)
        antisense_g4_src = "CCCUUACCCUUACCCUUACCC"
        seq = fwd_g4 + "AAAAAAAAA" + antisense_g4_src

        result = detect_g4(seq)
        strands = {m.strand for m in result.motifs}
        assert "+" in strands, "No forward-strand G4 detected"
        assert "-" in strands, "No antisense-strand G4 detected"

    # ---- additional coverage tests ----

    def test_empty_sequence(self):
        result = detect_g4("")
        assert result.g4_count == 0
        assert result.risk_score == pytest.approx(0.0)
        assert result.motifs == []

    def test_too_short_for_g4(self):
        result = detect_g4("GGGAGGG")  # only 2 G-tracts
        assert result.g4_count == 0

    def test_dna_input_with_t(self):
        """T in input should be handled identically to U."""
        rna = detect_g4("GGGUUAGGGUUAGGGUUAGGG")
        dna = detect_g4("GGGTTAGGGTTAGGGTTAGGG")
        assert rna.g4_count == dna.g4_count
        assert rna.motifs[0].loop_lengths == dna.motifs[0].loop_lengths

    def test_density_calculation(self):
        """Density = motifs / (seq_len / 1000)."""
        seq = "GGGAGGGAGGGAGGG"  # length 15, 1 fwd motif (+ possibly RC)
        result = detect_g4(seq)
        expected_density = result.g4_count / (len(seq) / 1000.0)
        assert result.g4_density == pytest.approx(expected_density, rel=0.01)

    def test_risk_score_capped_at_1(self):
        """10 G-tracts with 1-nt loops → 7 overlapping G4s → risk saturated."""
        # GGG + AGGG×9 = 10 G-tracts, loops all 1 nt → stability = 0.75 each
        # risk = 7 × 0.75 / 5 = 1.05 → capped to 1.0
        seq = "GGG" + "AGGG" * 9
        result = detect_g4(seq)
        assert result.risk_score == pytest.approx(1.0)
        assert result.g4_count >= 7

    def test_motif_coordinate_bounds(self):
        """All motif coordinates must be within the sequence."""
        seq = "GGGUUAGGGUUAGGGUUAGGG"
        result = detect_g4(seq)
        for m in result.motifs:
            assert m.start >= 0
            assert m.end <= len(seq)
            assert m.start < m.end

    def test_antisense_coordinates_in_original_frame(self):
        """Antisense motif coordinates must reference the forward sequence."""
        antisense_g4_src = "CCCUUACCCUUACCCUUACCC"
        seq = "AAAAAAAAA" + antisense_g4_src  # 9 A's + 21 C/U
        result = detect_g4(seq)
        rev = [m for m in result.motifs if m.strand == "-"]
        assert len(rev) >= 1
        for m in rev:
            assert m.start >= 0
            assert m.end <= len(seq)

    def test_risk_positive_for_single_motif(self):
        result = detect_g4("GGGAGGGAGGGAGGG")
        assert result.risk_score > 0.0

    def test_result_fields_present(self):
        result = detect_g4("GGGAGGGAGGGAGGG")
        assert hasattr(result, "motifs")
        assert hasattr(result, "g4_count")
        assert hasattr(result, "g4_density")
        assert hasattr(result, "risk_score")

    def test_g4_count_equals_len_motifs(self):
        seq = "GGGAGGGAGGGAGGG"
        result = detect_g4(seq)
        assert result.g4_count == len(result.motifs)
