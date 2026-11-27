"""Unit tests for src/stage2_offtarget_scan/mirbase_checker.py."""

from __future__ import annotations

import json
import tempfile
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

# saRNA whose seed (rule 10's slice) is "AGCUUAU". The slice itself is
# not restated here: the version of this comment removed in H9c said
# "pos 1-8", which was already wrong.
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

    def test_missing_file_returns_unknown_not_empty(self):
        """The second test that defended the conflation (roadmap B11).

        It asserted the same `[]` an *empty but readable* FASTA returns
        (the test just above), which is exactly what made a missing file
        indistinguishable from a measured absence of human miRNAs.
        """
        assert _parse_mirbase("/nonexistent/path/mature.fa") is None
        # And the readable-but-empty case still returns a list, so the two
        # really are different values rather than both being falsy-by-luck.
        assert _parse_mirbase.__annotations__["return"] is not None

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

    def test_missing_file_returns_unknown_not_safe(self):
        """Roadmap B11, and this test used to assert the bug.

        It read `risk_level == "SAFE"` for a file that does not exist — the
        third of invariant 2's measured fallbacks and the one `B2` left open.
        A miRBase check that cannot run must say *unknown*, because "SAFE" is
        a risk decision made from the absence of data.
        """
        result = check_mirbase_overlap("UAGCUUAUCAGACUGAUGUUGA", "/no/such/file.fa")
        assert result.risk_level is None, "missing file claimed a risk level"
        assert result.max_overlap_score is None, "missing file claimed a score"

    def test_present_but_nonhuman_file_really_is_safe(self):
        """The control, and without it the fix would make everything unknown.

        A file that reads fine and contains no human miRNA is a *measured*
        absence: nothing to overlap with, so SAFE and 0.0 are the right
        answers. The distinction between this and the test above is the whole
        point of `B11` — the same distinction `_bigwig_mean` already draws
        between "contig absent" and "signal measured 0" (invariant 2).
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mature.fa"
            path.write_text(textwrap.dedent("""\
                >cel-let-7-5p MIMAT0000001 Caenorhabditis elegans let-7-5p
                UGAGGUAGUAGGUUGUAUAGUU
            """), encoding="utf-8")
            result = check_mirbase_overlap("UAGCUUAUCAGACUGAUGUUGA", str(path))
        assert result.risk_level == "SAFE"
        assert result.max_overlap_score == pytest.approx(0.0)

    def test_the_parser_separates_unreadable_from_empty(self):
        """`_parse_mirbase` must not return the same thing for both."""
        assert _parse_mirbase("/no/such/file.fa") is None, (
            "an unreadable FASTA returns the same empty list as a readable "
            "one with no human entries, so the caller cannot tell them apart"
        )

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
        # hsa-miR-21-5p = UAGCUUAUCAGACUGAUGUUGA → its seed is AGCUUAU
        assert mir21.seed == "AGCUUAU"

    def test_perfect_match_against_real_data(self):
        result = check_mirbase_overlap(SARNA_PERFECT_MATCH, MIRBASE_PATH)
        assert result.max_overlap_score == pytest.approx(1.0)
        assert result.risk_level == "HIGH"


# ---------------------------------------------------------------------------
# B11 — the exception path, the seed slice, and the next hop
# ---------------------------------------------------------------------------


class TestTheFailurePathEmitsNoRiskDecision:
    """Roadmap B11. Three hops turned missing data into "SAFE"; all three go.

    The measured scope, before the fix: `_parse_mirbase` returned `[]` for a
    missing file, indistinguishable from a readable file with no human
    entries, so `check_mirbase_overlap` computed `max_score = 0.0` and
    `risk = SAFE`. `run()`'s `except` wrote the same verdict directly. And
    `offtarget_merger` re-introduced it one hop later as its default when
    `stage2_mirbase.json` could not be parsed. Fixing only the first would
    have left the chain's output unchanged.

    ⚠️ Measured and worth stating plainly: this channel's risk level feeds
    **nothing** in production scoring today — the only reader of
    `max_overlap_score` is `src/scoring/domain_scores.py`, which has zero
    production callers (roadmap B8). So this fix is about the invariant and
    the honesty of the written output, not about moving a score.
    """

    def test_run_writes_unknown_not_safe_when_the_check_fails(self, tmp_path):
        from src.stage2_offtarget_scan import mirbase_checker

        out = tmp_path / "stage2_mirbase.json"
        mirbase_checker.run(
            sarna_sequence="UAGCUUAUCAGACUGAUGUUGA",
            mirbase_fa="/no/such/file.fa",
            output_path=str(out),
            log_path=str(tmp_path / "log.txt"),
        )
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["risk_level"] is None, "the failure path claimed SAFE"
        assert payload["max_overlap_score"] is None

    def test_run_reports_the_rule_10_seed_slice_on_the_exception_path(self, tmp_path):
        """The second bug on the same line: `[:7]` is positions 1-7, not 2-8.

        ⚠️ Measured while writing this test: a *missing* file does not reach
        that line. `_parse_mirbase` returns for a missing path without
        raising, so `run()`'s `except` never fires and the correct slice is
        used. The wrong slice is only reachable when the check genuinely
        raises — a directory handed in as the FASTA does it, because the path
        exists and `open()` then raises. Without that trigger this test would
        have passed against the bug.

        Rule 10 is the authority for the slice and it is not restated here;
        the expectation is built from the module's own constants so the test
        cannot drift from them.
        """
        from src.stage2_offtarget_scan import mirbase_checker

        sequence = "UAGCUUAUCAGACUGAUGUUGA"
        expected = sequence[
            mirbase_checker._SEED_START :
            mirbase_checker._SEED_START + mirbase_checker._SEED_LENGTH
        ]
        assert expected != sequence[:7], "fixture cannot distinguish the slices"
        a_directory = tmp_path / "not-a-fasta"
        a_directory.mkdir()
        out = tmp_path / "stage2_mirbase.json"
        mirbase_checker.run(
            sarna_sequence=sequence,
            mirbase_fa=str(a_directory),
            output_path=str(out),
            log_path=str(tmp_path / "log.txt"),
        )
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["sarna_seed"] == expected
        assert payload["sarna_seed"] != sequence[:7], (
            "the exception path still reports positions 1-7"
        )

    def test_the_exception_path_also_emits_no_risk_decision(self, tmp_path):
        from src.stage2_offtarget_scan import mirbase_checker

        a_directory = tmp_path / "not-a-fasta"
        a_directory.mkdir()
        out = tmp_path / "stage2_mirbase.json"
        mirbase_checker.run(
            sarna_sequence="UAGCUUAUCAGACUGAUGUUGA",
            mirbase_fa=str(a_directory),
            output_path=str(out),
            log_path=str(tmp_path / "log.txt"),
        )
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["risk_level"] is None
        assert payload["max_overlap_score"] is None

    def test_the_merger_does_not_reintroduce_safe(self, tmp_path):
        """The next hop. Fixing the checker alone leaves the chain unchanged."""
        from src.stage2_offtarget_scan import offtarget_merger

        seed_hits = tmp_path / "stage2_seed_hits.json"
        seed_hits.write_text(json.dumps({"sites": [], "sequence_scores": {}}),
                             encoding="utf-8")
        repeats = tmp_path / "stage2_repeats.json"
        repeats.write_text(json.dumps({"repeat_results": {}}), encoding="utf-8")
        out = tmp_path / "stage2_offtargets.json"
        offtarget_merger.run(
            seed_hits_path=str(seed_hits),
            mirbase_path="/no/such/file.json",
            repeats_path=str(repeats),
            output_path=str(out),
            log_path=str(tmp_path / "log.txt"),
        )
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["mirbase_result"]["risk_level"] is None
        assert payload["mirbase_result"]["max_overlap_score"] is None

    def test_the_model_default_is_unknown(self):
        """A default of "SAFE" means every half-built result claims safety."""
        bare = MirbaseResult(sarna_seed="AGCUUAU")
        assert bare.risk_level is None
        assert bare.max_overlap_score is None
