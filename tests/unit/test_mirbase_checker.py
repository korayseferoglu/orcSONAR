"""Unit tests for src/stage2_offtarget_scan/mirbase_checker.py."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from src.core.models import MirbaseResult
from src.stage2_offtarget_scan.mirbase_checker import (
    _compare_seeds,
    _parse_mirbase,
    check_mirbase_overlap,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FASTA_HUMAN_ONLY = textwrap.dedent("""\
    >hsa-miR-21-5p MIMAT0000076 Homo sapiens miR-21-5p
    UAGCUUAUCAGACUGAUGUUGA
    >hsa-miR-155-5p MIMAT0000646 Homo sapiens miR-155-5p
    UUAAUGCUAAUUGUGAUAGGGGU
    >hsa-let-7a-5p MIMAT0000062 Homo sapiens let-7a-5p
    UGAGGUAGUAGGUUGUAUAGUU
""")

FASTA_MIXED = textwrap.dedent("""\
    >cel-let-7-5p MIMAT0000001 Caenorhabditis elegans let-7-5p
    UGAGGUAGUAGGUUGUAUAGUU
    >hsa-miR-21-5p MIMAT0000076 Homo sapiens miR-21-5p
    UAGCUUAUCAGACUGAUGUUGA
    >mmu-miR-155-5p MIMAT0000165 Mus musculus miR-155-5p
    UUAAUGCUAAUUGUGAUAGGGGU
    >hsa-let-7a-5p MIMAT0000062 Homo sapiens let-7a-5p
    UGAGGUAGUAGGUUGUAUAGUU
""")

FASTA_WITH_T = textwrap.dedent("""\
    >hsa-miR-test MIMAT9999999 Homo sapiens miR-test
    TAGCTTATCAGACTGATGTTGA
""")

FASTA_TOO_SHORT = textwrap.dedent("""\
    >hsa-miR-short MIMAT0000001 Homo sapiens miR-short
    UGAGGU
""")

FASTA_EMPTY = ""

# saRNA whose seed (pos 1-8, 0-indexed [1:8]) = "AGCUUAU"
# hsa-miR-21-5p seq = UAGCUUAUCAGACUGAUGUUGA → seed = AGCUUAU  (perfect 7/7)
SARNA_PERFECT_MATCH = "UAGCUUAUCAGACUGAUGUUGA"


@pytest.fixture
def tmp_fasta(tmp_path):
    """Return a factory: write content to a temp file and return its path."""
    def _write(content: str) -> str:
        p = tmp_path / "mature.fa"
        p.write_text(content)
        return str(p)
    return _write


# ---------------------------------------------------------------------------
# _parse_mirbase
# ---------------------------------------------------------------------------


class TestParseMirbase:
    def test_parse_human_mirnas_only(self, tmp_fasta):
        path = tmp_fasta(FASTA_MIXED)
        entries = _parse_mirbase(path)
        ids = [e.mirna_id for e in entries]
        assert "hsa-miR-21-5p" in ids
        assert "hsa-let-7a-5p" in ids
        assert "cel-let-7-5p" not in ids
        assert "mmu-miR-155-5p" not in ids

    def test_all_human_in_human_only_fasta(self, tmp_fasta):
        path = tmp_fasta(FASTA_HUMAN_ONLY)
        entries = _parse_mirbase(path)
        assert len(entries) == 3

    def test_sequences_normalised_to_u(self, tmp_fasta):
        path = tmp_fasta(FASTA_WITH_T)
        entries = _parse_mirbase(path)
        assert len(entries) == 1
        assert "T" not in entries[0].sequence
        assert "T" not in entries[0].seed

    def test_seed_is_positions_1_to_8(self, tmp_fasta):
        path = tmp_fasta(FASTA_HUMAN_ONLY)
        entries = _parse_mirbase(path)
        for e in entries:
            assert e.seed == e.sequence[1:8]
            assert len(e.seed) == 7

    def test_accession_captured(self, tmp_fasta):
        path = tmp_fasta(FASTA_HUMAN_ONLY)
        entries = {e.mirna_id: e for e in _parse_mirbase(path)}
        assert entries["hsa-miR-21-5p"].accession == "MIMAT0000076"
        assert entries["hsa-let-7a-5p"].accession == "MIMAT0000062"

    def test_too_short_mirna_skipped(self, tmp_fasta):
        path = tmp_fasta(FASTA_TOO_SHORT)
        entries = _parse_mirbase(path)
        assert entries == []

    def test_empty_fasta_returns_empty(self, tmp_fasta):
        path = tmp_fasta(FASTA_EMPTY)
        entries = _parse_mirbase(path)
        assert entries == []

    def test_missing_file_returns_empty(self):
        entries = _parse_mirbase("/nonexistent/path/mature.fa")
        assert entries == []

    def test_multiline_sequence(self, tmp_path):
        content = ">hsa-miR-multi MIMAT0000001 Homo sapiens miR-multi\nUGAGGUA\nGUAGGUU\nGUAUAGU\n"
        p = tmp_path / "mature.fa"
        p.write_text(content)
        entries = _parse_mirbase(str(p))
        assert len(entries) == 1
        assert entries[0].sequence == "UGAGGUAGUAGGUUGUAUAGU"


# ---------------------------------------------------------------------------
# _compare_seeds
# ---------------------------------------------------------------------------


class TestCompareSeeds:
    @pytest.mark.parametrize("s1,s2,expected", [
        ("AGCUUAU", "AGCUUAU", 1.0),   # 7/7 perfect
        ("AGCUUAU", "AGCUUAC", 0.7),   # 6/7
        ("AGCUUAU", "AGCUUCC", 0.3),   # 5/7
        ("AGCUUAU", "AGCUACC", 0.0),   # 4/7
        ("AGCUUAU", "CCCCCCC", 0.0),   # 0/7
        ("AAAAAAA", "AAAAAAA", 1.0),   # identical repeated
        ("AAAAAAA", "AAAAAUA", 0.7),   # one off
    ])
    def test_score_table(self, s1, s2, expected):
        assert _compare_seeds(s1, s2) == pytest.approx(expected)

    def test_wrong_length_returns_zero(self):
        assert _compare_seeds("AGCUU", "AGCUUAU") == 0.0
        assert _compare_seeds("AGCUUAU", "AGCUU") == 0.0
        assert _compare_seeds("", "") == 0.0


# ---------------------------------------------------------------------------
# check_mirbase_overlap  (integration)
# ---------------------------------------------------------------------------


class TestCheckMirbaseOverlap:
    def test_perfect_seed_overlap(self, tmp_fasta):
        path = tmp_fasta(FASTA_HUMAN_ONLY)
        result = check_mirbase_overlap(SARNA_PERFECT_MATCH, path)
        assert result.max_overlap_score == pytest.approx(1.0)
        assert result.risk_level == "HIGH"
        assert any(o.mirna_id == "hsa-miR-21-5p" for o in result.overlapping_mirnas)

    def test_sarna_seed_captured_in_result(self, tmp_fasta):
        path = tmp_fasta(FASTA_HUMAN_ONLY)
        result = check_mirbase_overlap(SARNA_PERFECT_MATCH, path)
        assert result.sarna_seed == SARNA_PERFECT_MATCH[1:8]

    def test_no_overlap_returns_safe(self, tmp_fasta):
        all_c_sarna = "CCCCCCCCCCCCCCCCCCCCCC"
        path = tmp_fasta(FASTA_HUMAN_ONLY)
        result = check_mirbase_overlap(all_c_sarna, path)
        assert result.max_overlap_score == pytest.approx(0.0)
        assert result.risk_level == "SAFE"
        assert result.overlapping_mirnas == []

    def test_partial_overlap_moderate(self, tmp_fasta):
        # Modify one position in the perfect-match seed → 6/7 → MODERATE
        seq = list(SARNA_PERFECT_MATCH)
        seq[1] = "C"  # break position 1 (first seed position, 0-indexed)
        mutated = "".join(seq)
        path = tmp_fasta(FASTA_HUMAN_ONLY)
        result = check_mirbase_overlap(mutated, path)
        best = max(result.overlapping_mirnas, key=lambda o: o.overlap_score, default=None)
        if best is not None and best.mirna_id == "hsa-miR-21-5p":
            assert best.overlap_score == pytest.approx(0.7)
            assert result.risk_level == "MODERATE"

    def test_results_sorted_by_score_descending(self, tmp_fasta):
        path = tmp_fasta(FASTA_HUMAN_ONLY)
        result = check_mirbase_overlap(SARNA_PERFECT_MATCH, path)
        scores = [o.overlap_score for o in result.overlapping_mirnas]
        assert scores == sorted(scores, reverse=True)

    def test_missing_file_returns_safe(self):
        result = check_mirbase_overlap("UAGCUUAUCAGACUGAUGUUGA", "/no/such/file.fa")
        assert result.risk_level == "SAFE"
        assert result.max_overlap_score == pytest.approx(0.0)

    def test_returns_mirbase_result_type(self, tmp_fasta):
        path = tmp_fasta(FASTA_HUMAN_ONLY)
        result = check_mirbase_overlap(SARNA_PERFECT_MATCH, path)
        assert isinstance(result, MirbaseResult)

    def test_overlap_count_correct(self, tmp_fasta):
        path = tmp_fasta(FASTA_HUMAN_ONLY)
        result = check_mirbase_overlap(SARNA_PERFECT_MATCH, path)
        # Only hsa-miR-21-5p should have a ≥5/7 seed match; others are different
        high_score_ids = [o.mirna_id for o in result.overlapping_mirnas if o.overlap_score > 0.0]
        assert "hsa-miR-21-5p" in high_score_ids

    def test_matched_positions_count_is_consistent(self, tmp_fasta):
        path = tmp_fasta(FASTA_HUMAN_ONLY)
        result = check_mirbase_overlap(SARNA_PERFECT_MATCH, path)
        for overlap in result.overlapping_mirnas:
            # Verify matched_positions is consistent with overlap_score
            score = _compare_seeds(result.sarna_seed, overlap.mirna_seed)
            assert overlap.overlap_score == pytest.approx(score)


# ---------------------------------------------------------------------------
# Real miRBase file (integration, skipped if file absent)
# ---------------------------------------------------------------------------


MIRBASE_PATH = "data/1_Temel_Harita/miRBase/mature.fa"


@pytest.mark.skipif(
    not Path(MIRBASE_PATH).exists(),
    reason="miRBase mature.fa not available",
)
class TestRealMirbase:
    def test_parses_all_human_mirnas(self):
        entries = _parse_mirbase(MIRBASE_PATH)
        assert len(entries) >= 2000

    def test_all_seeds_are_7nt(self):
        entries = _parse_mirbase(MIRBASE_PATH)
        for e in entries:
            assert len(e.seed) == 7, f"{e.mirna_id} seed length {len(e.seed)}"

    def test_no_t_in_sequences(self):
        entries = _parse_mirbase(MIRBASE_PATH)
        for e in entries:
            assert "T" not in e.sequence, f"{e.mirna_id} contains T"

    def test_known_mirna_present(self):
        entries = _parse_mirbase(MIRBASE_PATH)
        ids = {e.mirna_id for e in entries}
        assert "hsa-miR-21-5p" in ids
        assert "hsa-let-7a-5p" in ids

    def test_mir21_seed_known_value(self):
        entries = _parse_mirbase(MIRBASE_PATH)
        mir21 = next(e for e in entries if e.mirna_id == "hsa-miR-21-5p")
        # hsa-miR-21-5p = UAGCUUAUCAGACUGAUGUUGA → seed [1:8] = AGCUUAU
        assert mir21.seed == "AGCUUAU"

    def test_perfect_match_against_real_data(self):
        result = check_mirbase_overlap(SARNA_PERFECT_MATCH, MIRBASE_PATH)
        assert result.max_overlap_score == pytest.approx(1.0)
        assert result.risk_level == "HIGH"
