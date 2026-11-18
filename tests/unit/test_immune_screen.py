"""Unit tests for src/stage6_execution/immune_screen.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.models import ImmuneResult
from src.stage6_execution.immune_screen import (
    _classify_risk,
    _load_motifs,
    _reverse_complement_rna,
    _scan_motifs,
    _to_rna,
    screen_immune_motifs,
)

# ---------------------------------------------------------------------------
# Motif file content
# ---------------------------------------------------------------------------

MOTIF_FILE_CONTENT = """\
# TLR7/TLR8 immune motifs
UGUGU
GUUGUGU
UUGU
UUAU
AUAU
UUUU
"""


def _write_motif_file(tmp_path: Path, content: str = MOTIF_FILE_CONTENT) -> Path:
    f = tmp_path / "immune_motifs.txt"
    f.write_text(content, encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# _to_rna
# ---------------------------------------------------------------------------


class TestToRna:
    def test_converts_t_to_u(self) -> None:
        assert _to_rna("ACGT") == "ACGU"

    def test_already_rna_unchanged(self) -> None:
        assert _to_rna("ACGU") == "ACGU"

    def test_lowercaset_uppercased(self) -> None:
        assert _to_rna("acgt") == "ACGU"

    def test_mixed_case(self) -> None:
        assert _to_rna("AcGt") == "ACGU"

    def test_empty_string(self) -> None:
        assert _to_rna("") == ""


# ---------------------------------------------------------------------------
# _reverse_complement_rna
# ---------------------------------------------------------------------------


class TestReverseComplementRna:
    def test_simple_complement(self) -> None:
        # AUGC → complement UACG → reverse GCAU
        assert _reverse_complement_rna("AUGC") == "GCAU"

    def test_palindrome(self) -> None:
        # GCGC → complement CGCG → reverse GCGC
        assert _reverse_complement_rna("GCGC") == "GCGC"

    def test_all_u_gives_all_a(self) -> None:
        assert _reverse_complement_rna("UUUU") == "AAAA"

    def test_all_a_gives_all_u(self) -> None:
        assert _reverse_complement_rna("AAAA") == "UUUU"

    def test_empty_returns_empty(self) -> None:
        assert _reverse_complement_rna("") == ""

    def test_unknown_base_preserved(self) -> None:
        # N is not in complement map — kept as-is
        result = _reverse_complement_rna("NAUG")
        assert result == "CAUN"


# ---------------------------------------------------------------------------
# _load_motifs
# ---------------------------------------------------------------------------


class TestLoadMotifs:
    def test_loads_all_motifs(self, tmp_path: Path) -> None:
        f = _write_motif_file(tmp_path)
        motifs = _load_motifs(f)
        assert len(motifs) == 6

    def test_skips_comment_lines(self, tmp_path: Path) -> None:
        f = _write_motif_file(tmp_path)
        motifs = _load_motifs(f)
        assert not any(m.startswith("#") for m in motifs)

    def test_converts_to_rna(self, tmp_path: Path) -> None:
        f = tmp_path / "motifs.txt"
        f.write_text("TTTTT\nACGT\n", encoding="utf-8")
        motifs = _load_motifs(f)
        assert "UUUUU" in motifs
        assert "ACGU" in motifs

    def test_skips_blank_lines(self, tmp_path: Path) -> None:
        f = tmp_path / "motifs.txt"
        f.write_text("\nUGUGU\n\nUUUU\n", encoding="utf-8")
        motifs = _load_motifs(f)
        assert len(motifs) == 2

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        motifs = _load_motifs(tmp_path / "nonexistent.txt")
        assert motifs == []

    def test_exact_motifs_from_spec(self, tmp_path: Path) -> None:
        f = _write_motif_file(tmp_path)
        motifs = _load_motifs(f)
        assert set(motifs) == {"UGUGU", "GUUGUGU", "UUGU", "UUAU", "AUAU", "UUUU"}


# ---------------------------------------------------------------------------
# _scan_motifs
# ---------------------------------------------------------------------------


class TestScanMotifs:
    def test_single_hit(self) -> None:
        hits = _scan_motifs("AAUGUUGU", ["UUGU"])
        assert len(hits) == 1
        assert hits[0].motif == "UUGU"
        assert hits[0].position == 4
        assert hits[0].strand == "+"

    def test_no_hit(self) -> None:
        hits = _scan_motifs("GCGCGCGC", ["UUUU"])
        assert hits == []

    def test_multiple_motifs_found(self) -> None:
        seq = "UGUUGUGUGUUUU"
        hits = _scan_motifs(seq, ["UGUGU", "UUUU"])
        motifs_hit = {h.motif for h in hits}
        assert "UGUGU" in motifs_hit
        assert "UUUU" in motifs_hit

    def test_overlapping_hits_both_reported(self) -> None:
        # UGUGUGU contains UGUGU at pos 0 and pos 2 (overlapping)
        hits = _scan_motifs("UGUGUGU", ["UGUGU"])
        positions = {h.position for h in hits}
        assert 0 in positions
        assert 2 in positions

    def test_empty_sequence(self) -> None:
        assert _scan_motifs("", ["UGUGU"]) == []

    def test_empty_motif_list(self) -> None:
        assert _scan_motifs("UGUGU", []) == []

    def test_all_hits_have_plus_strand(self) -> None:
        hits = _scan_motifs("UUUUAUAU", ["UUUU", "AUAU"])
        assert all(h.strand == "+" for h in hits)


# ---------------------------------------------------------------------------
# _classify_risk
# ---------------------------------------------------------------------------


class TestClassifyRisk:
    def test_zero_hits_safe(self) -> None:
        score, level = _classify_risk(0)
        assert score == pytest.approx(0.0)
        assert level == "SAFE"

    def test_one_hit_low(self) -> None:
        score, level = _classify_risk(1)
        assert score == pytest.approx(0.25)
        assert level == "LOW"

    def test_two_hits_high(self) -> None:
        score, level = _classify_risk(2)
        assert level == "HIGH"
        assert score >= 0.5

    def test_three_hits_high(self) -> None:
        _, level = _classify_risk(3)
        assert level == "HIGH"

    def test_many_hits_capped_at_one(self) -> None:
        score, level = _classify_risk(100)
        assert score == pytest.approx(1.0)
        assert level == "HIGH"

    def test_score_increases_with_hits(self) -> None:
        scores = [_classify_risk(n)[0] for n in range(6)]
        for i in range(len(scores) - 1):
            assert scores[i] <= scores[i + 1]


# ---------------------------------------------------------------------------
# screen_immune_motifs — integration
# ---------------------------------------------------------------------------


class TestScreenImmuneMotifs:
    def test_clean_sequence_returns_safe(self, tmp_path: Path) -> None:
        f = _write_motif_file(tmp_path)
        # No motifs in GCGCGCGCGCGCGCGCGCGC
        result = screen_immune_motifs("GCGCGCGCGCGCGCGCGCGC", f)
        assert isinstance(result, ImmuneResult)
        assert result.risk_level == "SAFE"
        assert result.total_hits == 0
        assert result.risk_score == pytest.approx(0.0)

    def test_sequence_with_uuuu_motif(self, tmp_path: Path) -> None:
        f = _write_motif_file(tmp_path)
        # GCUUUUGC contains UUUU once on sense strand
        result = screen_immune_motifs("GCUUUUGC", f)
        assert result.total_hits >= 1
        sense_hits = [h for h in result.motifs_found if h.strand == "+"]
        assert any(h.motif == "UUUU" for h in sense_hits)

    def test_dna_sequence_normalized(self, tmp_path: Path) -> None:
        f = _write_motif_file(tmp_path)
        # T → U: GCTTTTGC → GCUUUUGC
        result_dna = screen_immune_motifs("GCTTTTGC", f)
        result_rna = screen_immune_motifs("GCUUUUGC", f)
        assert result_dna.total_hits == result_rna.total_hits

    def test_antisense_hits_have_minus_strand(self, tmp_path: Path) -> None:
        f = _write_motif_file(tmp_path)
        # Build a sequence whose RC contains UUUU:
        # RC of AAAA = UUUU, so sense = UUUU...; antisense of TTTTAAAA = UUUUAAAA → sense
        # Let's use sense = AAAAGCGC → antisense = GCGCUUUU (has UUUU)
        result = screen_immune_motifs("AAAAGCGC", f)
        minus_hits = [h for h in result.motifs_found if h.strand == "-"]
        assert any(h.motif == "UUUU" for h in minus_hits)

    def test_high_risk_with_multiple_motifs(self, tmp_path: Path) -> None:
        f = _write_motif_file(tmp_path)
        # UUUUUGUAUGUGU contains UUUU, UGUGU, AUAU (in sense or antisense)
        result = screen_immune_motifs("UUUUUGUAUGUGU", f)
        assert result.risk_level == "HIGH"
        assert result.total_hits >= 2

    def test_missing_motif_file_returns_safe(self, tmp_path: Path) -> None:
        result = screen_immune_motifs("GCUUUUGC", tmp_path / "missing.txt")
        assert result.risk_level == "SAFE"
        assert result.total_hits == 0

    def test_total_hits_equals_len_motifs_found(self, tmp_path: Path) -> None:
        f = _write_motif_file(tmp_path)
        result = screen_immune_motifs("UUUUAUAUGUGUGUUGUGUGUUAU", f)
        assert result.total_hits == len(result.motifs_found)

    def test_risk_score_in_range(self, tmp_path: Path) -> None:
        f = _write_motif_file(tmp_path)
        result = screen_immune_motifs("UUUUAUAUGUGUGUUGUGUGUUAU", f)
        assert 0.0 <= result.risk_score <= 1.0

    def test_real_motif_file_path(self) -> None:
        """Integration test using the actual project motif file (if present)."""
        real_path = Path("data/5_Icra_Güvenlik/Immun_Motifler/immune_motifs.txt")
        if not real_path.exists():
            pytest.skip("real motif file not available")
        result = screen_immune_motifs("UGUUGUGUGUUUU", real_path)
        assert result.total_hits >= 1
        assert result.risk_level in ("LOW", "HIGH")
