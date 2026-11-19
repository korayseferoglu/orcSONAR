"""Unit tests for Stage 2 seed-based alignment engine."""

from __future__ import annotations

import json
import random
import time
from pathlib import Path

import pytest

from src.core.config import OrcSonarConfig
from src.core.models import TranscriptInfo
from src.stage2_offtarget_scan.seed_aligner import (
    _build_seed_index,
    _extract_seed,
    _is_gu_wobble,
    _is_watson_crick,
    _reverse_complement,
    _score_alignment,
    find_offtargets,
)
from src.stage2_offtarget_scan.seed_aligner import (
    run as seed_aligner_run,
)

# ---------------------------------------------------------------------------
# Constants shared across tests
# ---------------------------------------------------------------------------

SARNA = "GCAACCAUAGCCUCGGCCGC"  # 20 nt, RNA
# Perfect complement mRNA window = reverse_complement(SARNA)
# sarna[i] pairs with target[19-i]; perfect target = rc(sarna) reversed? No:
# target[n-1-i] must equal complement(sarna[i])
# ⟹ target[j] = complement(sarna[n-1-j])  where n=20
# ⟹ target = [complement(sarna[19]), ..., complement(sarna[0])]
#           = reverse_complement(sarna)


def _make_perfect_window(sarna: str) -> str:
    """Return the 20-nt mRNA window that gives a perfect alignment score."""
    comp = {"A": "U", "U": "A", "G": "C", "C": "G"}
    return "".join(comp[b] for b in reversed(sarna))


def _make_transcript(tid: str, seq_len: int = 2000) -> TranscriptInfo:
    return TranscriptInfo(
        transcript_id=tid,
        gene=f"GENE_{tid}",
        chrom="chr1",
        start=0,
        end=seq_len,
        strand="+",
        source="Ensembl",
    )


def _default_config() -> OrcSonarConfig:
    return OrcSonarConfig()


# ---------------------------------------------------------------------------
# _reverse_complement
# ---------------------------------------------------------------------------


class TestReverseComplement:
    def test_simple_rna(self) -> None:
        assert _reverse_complement("AUGC") == "GCAU"

    def test_all_bases(self) -> None:
        assert _reverse_complement("AUCG") == "CGAU"

    def test_dna_t_treated_as_u(self) -> None:
        # T → A in complement, so rc("ATCG") == rc("AUCG")
        assert _reverse_complement("ATCG") == _reverse_complement("AUCG")

    def test_palindrome(self) -> None:
        # GCGC: comp = CGCG, reversed = GCGC — not a palindrome actually
        assert _reverse_complement("GCGC") == "GCGC"

    def test_unknown_base_becomes_n(self) -> None:
        assert _reverse_complement("ANX") == "NNU"

    def test_length_preserved(self) -> None:
        seq = "AUCGAUCGAUCG"
        assert len(_reverse_complement(seq)) == len(seq)

    def test_double_rc_returns_original(self) -> None:
        seq = "GCAACCAUAGCC"
        assert _reverse_complement(_reverse_complement(seq)) == seq


# ---------------------------------------------------------------------------
# _extract_seed
# ---------------------------------------------------------------------------


class TestExtractSeed:
    def test_default_positions(self) -> None:
        # positions 2-8 (1-indexed) = sarna[1:8] (0-indexed)
        seed = _extract_seed(SARNA)
        assert seed == SARNA[1:8]
        assert len(seed) == 7

    def test_custom_start_and_length(self) -> None:
        seed = _extract_seed(SARNA, seed_start=0, seed_length=5)
        assert seed == SARNA[0:5]

    def test_raises_when_out_of_bounds(self) -> None:
        with pytest.raises(ValueError, match="out of bounds"):
            _extract_seed("GCAAC", seed_start=1, seed_length=7)


# ---------------------------------------------------------------------------
# _is_watson_crick / _is_gu_wobble
# ---------------------------------------------------------------------------


class TestBasePairing:
    @pytest.mark.parametrize("b1,b2", [("A", "U"), ("U", "A"), ("G", "C"), ("C", "G")])
    def test_watson_crick_pairs(self, b1: str, b2: str) -> None:
        assert _is_watson_crick(b1, b2)

    @pytest.mark.parametrize("b1,b2", [("G", "U"), ("U", "G")])
    def test_gu_wobble_pairs(self, b1: str, b2: str) -> None:
        assert _is_gu_wobble(b1, b2)

    @pytest.mark.parametrize("b1,b2", [("A", "A"), ("C", "U"), ("G", "A")])
    def test_mismatches_not_wobble(self, b1: str, b2: str) -> None:
        assert not _is_gu_wobble(b1, b2)

    @pytest.mark.parametrize("b1,b2", [("G", "U"), ("U", "G")])
    def test_wobble_not_watson_crick(self, b1: str, b2: str) -> None:
        assert not _is_watson_crick(b1, b2)


# ---------------------------------------------------------------------------
# _score_alignment
# ---------------------------------------------------------------------------


class TestScoreAlignment:
    def test_perfect_match(self) -> None:
        window = _make_perfect_window(SARNA)
        result = _score_alignment(SARNA, window)

        assert result.score == pytest.approx(len(SARNA))
        assert result.mismatches == 0
        assert result.gu_wobbles == 0
        assert result.seed_mismatches == 0
        assert result.positions == []

    def test_gu_wobble_detection(self) -> None:
        # Build a window that is perfect except position i=5 (non-seed edge case)
        # but introduce a G:U wobble at sarna position 0 (non-seed).
        # sarna[0]='G'; for wobble, target[n-1-0]=target[19] must be 'U'.
        window_list = list(_make_perfect_window(SARNA))
        # target[19] currently = complement(sarna[0])='C'; change to 'U' for G:U wobble
        window_list[19] = "U"
        window = "".join(window_list)

        result = _score_alignment(SARNA, window)
        assert result.gu_wobbles == 1
        assert result.mismatches == 0  # wobble is NOT a mismatch
        assert result.score == pytest.approx(len(SARNA) - 1 + 0.5)
        assert result.seed_mismatches == 0  # position 0 is outside seed

    def test_gu_wobble_in_seed_not_counted_as_seed_mismatch(self) -> None:
        # Introduce G:U wobble at sarna position 3 (within seed positions 1-7).
        # sarna[3]='A'; to create a wobble we need sarna[3]='G' or 'U'.
        # Let's use a custom saRNA with G at position 3.
        sarna = "GCAGCCAUAGCCUCGGCCGC"  # sarna[3]='G'
        window_list = list(_make_perfect_window(sarna))
        # target[n-1-3]=target[16] currently = complement(sarna[3])='C'; change to 'U'
        window_list[16] = "U"
        window = "".join(window_list)

        result = _score_alignment(sarna, window)
        assert result.gu_wobbles == 1
        assert result.seed_mismatches == 0  # G:U in seed is NOT a seed mismatch

    def test_mismatch_counted(self) -> None:
        window_list = list(_make_perfect_window(SARNA))
        # Introduce a mismatch at sarna position 10 (outside seed 1-7)
        # target[n-1-10]=target[9]; replace with a base that doesn't pair with sarna[10]
        # sarna[10]='C'; complement='G'; make it 'A' → mismatch
        window_list[9] = "A"
        window = "".join(window_list)

        result = _score_alignment(SARNA, window)
        assert result.mismatches == 1
        assert result.seed_mismatches == 0
        assert 10 in result.positions

    def test_seed_mismatch_counted(self) -> None:
        window_list = list(_make_perfect_window(SARNA))
        # Introduce mismatch at sarna position 2 (seed, 0-indexed 1..7)
        # target[n-1-2]=target[17] currently = complement(sarna[2])='U'; change to 'G'
        window_list[17] = "G"
        window = "".join(window_list)

        result = _score_alignment(SARNA, window)
        assert result.seed_mismatches == 1
        assert result.mismatches == 1
        assert 2 in result.positions

    def test_score_is_zero_for_all_mismatches(self) -> None:
        # All-C saRNA vs all-C window → mismatches everywhere (C:C = mismatch)
        sarna = "C" * 10
        target = "C" * 10
        result = _score_alignment(sarna, target)
        assert result.score == 0.0
        assert result.mismatches == 10

    def test_raises_on_length_mismatch(self) -> None:
        with pytest.raises(ValueError, match="Length mismatch"):
            _score_alignment("AUCG", "AUC")

    def test_t_in_target_normalised_to_u(self) -> None:
        # window using T instead of U should give same result as U version
        window_u = _make_perfect_window(SARNA)
        window_t = window_u.replace("U", "T")
        result_u = _score_alignment(SARNA, window_u)
        result_t = _score_alignment(SARNA, window_t)
        assert result_t.score == pytest.approx(result_u.score)
        assert result_t.mismatches == result_u.mismatches


# ---------------------------------------------------------------------------
# _build_seed_index
# ---------------------------------------------------------------------------


class TestBuildSeedIndex:
    def test_finds_rc_seed_in_sequence(self) -> None:
        seed = _extract_seed(SARNA)
        rc = _reverse_complement(seed).replace("U", "T")  # sequences use T
        seq = "AAAA" + rc + "CCCC"
        index = _build_seed_index({"T1": seq}, seed)
        assert "T1" in index
        assert 4 in index["T1"]

    def test_finds_multiple_occurrences(self) -> None:
        seed = _extract_seed(SARNA)
        rc = _reverse_complement(seed).replace("U", "T")
        seq = rc + "AAAA" + rc
        index = _build_seed_index({"T1": seq}, seed)
        assert len(index["T1"]) == 2

    def test_no_hit_excluded_from_index(self) -> None:
        seed = _extract_seed(SARNA)
        # Sequence of all-A won't contain rc_seed
        seq = "A" * 100
        index = _build_seed_index({"T1": seq}, seed)
        assert "T1" not in index

    def test_rna_u_in_sequence(self) -> None:
        seed = _extract_seed(SARNA)
        rc_u = _reverse_complement(seed)  # U version
        seq = "AAAA" + rc_u + "CCCC"
        index = _build_seed_index({"T1": seq}, seed)
        assert "T1" in index


# ---------------------------------------------------------------------------
# find_offtargets — integration-style unit tests
# ---------------------------------------------------------------------------


def _embed_offtarget(
    sarna: str,
    seq_len: int = 200,
    seed_start: int = 1,
    seed_length: int = 7,
    extra_mismatches: int = 0,
) -> tuple[str, int]:
    """Build an mRNA sequence containing a perfect off-target window for sarna.

    Returns (mRNA_sequence, p) where p is the start of rc_seed within the sequence.
    """
    # Perfect window: reverse_complement(sarna) (using T for DNA-like seqs)
    comp = {"A": "T", "U": "A", "G": "C", "C": "G"}
    perfect_window = "".join(comp[b] for b in reversed(sarna))

    # rc_seed position within perfect_window:
    # seed_end_in_sarna = seed_start + seed_length - 1 = 7
    # In the window, sarna[seed_end_in_sarna] pairs with target[n-1-seed_end] = target[12]
    # rc_seed occupies target[seed_length-1 .. seed_length-1+seed_length-1] ... easier to compute:
    # sarna[seed_start..seed_end] pairs with target[n-1-seed_end .. n-1-seed_start]
    n = len(sarna)
    seed_end = seed_start + seed_length - 1
    # target positions for seed: from n-1-seed_end to n-1-seed_start (inclusive)
    t_seed_start = n - 1 - seed_end  # lower index in target
    t_seed_end = n - 1 - seed_start   # upper index in target (inclusive)
    # rc_seed in target runs from t_seed_start .. t_seed_end (7 positions).
    #
    # This helper plants a seed into a synthetic mRNA using its own index
    # arithmetic. If that drifts from what production slices, every alignment
    # test built on it would plant the wrong subsequence and still pass. So
    # the two are tied together here. (`t_seed_end - t_seed_start + 1 ==
    # seed_length` was asserted first and removed: it follows algebraically
    # from the two lines above, so it could never fail.)
    seed = _extract_seed(sarna, seed_start, seed_length)
    assert sarna[seed_start : seed_end + 1] == seed
    # And the span the two indices describe really does hold the planted
    # reverse complement, which is what `p` below points callers at.
    assert perfect_window[t_seed_start : t_seed_end + 1] == _reverse_complement(seed).replace(
        "U", "T"
    )

    padding = 50
    insert_pos = padding  # where the window starts in the mRNA
    p = insert_pos + t_seed_start  # position of rc_seed in the full mRNA

    if extra_mismatches > 0:
        window_list = list(perfect_window)
        # Introduce mismatches outside the seed (positions n-1-0 and n-1-8 in target
        # correspond to sarna[0] and sarna[8] — both outside the seed)
        mismatch_target_positions = [n - 1, n - 2][:extra_mismatches]
        for tp in mismatch_target_positions:
            # Change to a base that won't Watson-Crick pair with the saRNA
            window_list[tp] = "A" if window_list[tp] != "A" else "C"
        perfect_window = "".join(window_list)

    mRNA = "A" * padding + perfect_window + "A" * (seq_len - padding - n)
    return mRNA, p


class TestFindOfftargets:
    def test_perfect_offtarget_found(self) -> None:
        config = _default_config()
        mRNA, _ = _embed_offtarget(SARNA)
        sequences = {"ENST00000000001": mRNA}
        transcripts = [_make_transcript("ENST00000000001", len(mRNA))]

        hits = find_offtargets(SARNA, transcripts, sequences, config)

        assert len(hits) == 1
        hit = hits[0]
        assert hit.transcript_id == "ENST00000000001"
        assert hit.seed_match_type == "perfect"
        assert hit.mismatches == 0
        assert hit.alignment_score == pytest.approx(len(SARNA))

    def test_seed_mismatch_filter(self) -> None:
        """Verify seed_mismatches counting at alignment level, and that near-seed
        variants (1 mismatch in rc_seed) are not found by the exact pre-filter.

        Note: because the pre-filter requires the exact rc_seed substring, the
        alignment positions 12-18 (seed region) are always perfect matches when
        a candidate is indexed.  The seed_mismatches > 1 guard in find_offtargets
        acts as a safety net; we verify the counting logic via _score_alignment.
        """
        config = _default_config()

        # _score_alignment level: verify seed mismatch counting
        perfect = _make_perfect_window(SARNA)
        win_1mm = list(perfect)
        # sarna[2] (seed) → target[17]; introduce mismatch
        win_1mm[17] = "A" if win_1mm[17] != "A" else "C"
        result_1 = _score_alignment(SARNA, "".join(win_1mm))
        assert result_1.seed_mismatches == 1

        win_2mm = list(perfect)
        win_2mm[17] = "A" if win_2mm[17] != "A" else "C"  # sarna pos 2
        win_2mm[16] = "A" if win_2mm[16] != "A" else "C"  # sarna pos 3
        result_2 = _score_alignment(SARNA, "".join(win_2mm))
        assert result_2.seed_mismatches == 2

        # find_offtargets level: near-seed variant (1 mismatch in rc_seed) is not indexed
        seed = _extract_seed(SARNA)
        rc_seed_t = _reverse_complement(seed).replace("U", "T")
        near = list(rc_seed_t)
        near[2] = "A" if near[2] != "A" else "C"
        mRNA = "A" * 50 + "".join(near) + "A" * 100

        hits = find_offtargets(
            SARNA,
            [_make_transcript("T1", len(mRNA))],
            {"T1": mRNA},
            config,
        )
        assert len(hits) == 0, "Near-seed variant should not pass the exact pre-filter"

    def test_max_mismatch_filter(self) -> None:
        """4 total mismatches → filtered out; 3 → kept."""
        config = _default_config()
        assert config.max_mismatches == 3

        # Build window with 3 non-seed mismatches
        comp = {"A": "T", "U": "A", "G": "C", "C": "G"}
        window_ok = list("".join(comp[b] for b in reversed(SARNA)))
        # Introduce 3 mismatches at non-seed positions (sarna 0, 8, 9 → target 19, 11, 10)
        for tp in [19, 11, 10]:
            window_ok[tp] = "A" if window_ok[tp] != "A" else "C"
        mRNA_ok = "A" * 50 + "".join(window_ok) + "A" * 50

        # Build window with 4 non-seed mismatches (add one more at sarna 15 → target 4)
        window_bad = window_ok[:]
        window_bad[4] = "A" if window_bad[4] != "A" else "C"
        mRNA_bad = "A" * 50 + "".join(window_bad) + "A" * 50

        seed = _extract_seed(SARNA)
        rc_seed_t = _reverse_complement(seed).replace("U", "T")
        assert rc_seed_t in mRNA_ok
        assert rc_seed_t in mRNA_bad

        sequences = {"T_ok": mRNA_ok, "T_bad": mRNA_bad}
        transcripts = [
            _make_transcript("T_ok", len(mRNA_ok)),
            _make_transcript("T_bad", len(mRNA_bad)),
        ]

        hits = find_offtargets(SARNA, transcripts, sequences, config)
        hit_ids = {h.transcript_id for h in hits}
        assert "T_ok" in hit_ids, "3 mismatches should pass"
        assert "T_bad" not in hit_ids, "4 mismatches should be filtered"

    def test_no_transcripts_no_hits(self) -> None:
        config = _default_config()
        hits = find_offtargets(SARNA, [], {}, config)
        assert hits == []

    def test_sorted_by_score_descending(self) -> None:
        """Multiple off-targets are returned highest-score first."""
        config = _default_config()
        comp = {"A": "T", "U": "A", "G": "C", "C": "G"}

        # Perfect window for T1
        win_perfect = "".join(comp[b] for b in reversed(SARNA))
        # 3-mismatch window for T2 (non-seed)
        win_3mm = list(win_perfect)
        for tp in [19, 11, 10]:
            win_3mm[tp] = "A" if win_3mm[tp] != "A" else "C"
        win_3mm = "".join(win_3mm)

        sequences = {
            "T1": "A" * 50 + win_perfect + "A" * 50,
            "T2": "A" * 50 + win_3mm + "A" * 50,
        }
        transcripts = [
            _make_transcript("T1", 120),
            _make_transcript("T2", 120),
        ]

        hits = find_offtargets(SARNA, transcripts, sequences, config)
        assert len(hits) == 2
        assert hits[0].alignment_score >= hits[1].alignment_score
        assert hits[0].transcript_id == "T1"

    def test_window_boundary_not_included(self) -> None:
        """Off-target windows that reach beyond transcript boundaries are skipped."""
        config = _default_config()
        # A window placed at offset 12 would give win_start = 12 - 12 = 0, which
        # is still valid. The edge case below puts rc_seed at position 0 so that
        # win_start would be -12. (A half-written `mRNA` variable for the first
        # case sat here unused until H15.)
        seed = _extract_seed(SARNA)
        rc_seed_t = _reverse_complement(seed).replace("U", "T")
        mRNA_edge = rc_seed_t + "A" * 100  # rc_seed at position 0 → win_start = -12

        sequences = {"T1": mRNA_edge}
        transcripts = [_make_transcript("T1", len(mRNA_edge))]
        hits = find_offtargets(SARNA, transcripts, sequences, config)
        assert len(hits) == 0


# ---------------------------------------------------------------------------
# Performance test
# ---------------------------------------------------------------------------


def test_performance() -> None:
    """10 000 random transcripts (2 kb each) must complete in < 5 seconds."""
    config = _default_config()
    rng = random.Random(42)
    bases = list("ACGT")
    n_seqs = 10_000
    seq_len = 2_000

    sequences: dict[str, str] = {}
    transcripts: list[TranscriptInfo] = []

    for i in range(n_seqs):
        tid = f"ENST{i:011d}"
        seq = "".join(rng.choices(bases, k=seq_len))
        sequences[tid] = seq
        transcripts.append(
            TranscriptInfo(
                transcript_id=tid,
                gene=f"GENE{i}",
                chrom="chr1",
                start=i * (seq_len + 1000),
                end=i * (seq_len + 1000) + seq_len,
                strand="+",
                source="Ensembl",
            )
        )

    t0 = time.perf_counter()
    find_offtargets(SARNA, transcripts, sequences, config)
    elapsed = time.perf_counter() - t0

    assert elapsed < 5.0, f"Performance budget exceeded: {elapsed:.2f}s > 5.0s"


class TestRunDoesNotSwallowAnOutage:
    """A lost background transcriptome must stop the run, not shrink it.

    Audit 2026-11-19, Bulgu 12. ``get_background_transcriptome`` now raises
    when nothing resolves, but that fix is worthless on its own: ``run()``
    wrapped the call in ``except Exception`` and only logged a warning, so the
    scan continued against the target gene alone, found zero off-target sites,
    and the pipeline reported ``risk=SAFE (0.0000)`` with exit 0.

    The same "the fix is swallowed one layer up" shape appears three more
    times in that audit (B1's APIError, B2's sentinel, B4's default), which is
    why this is pinned by a test rather than trusted to the call site.
    """

    def test_background_outage_propagates_out_of_run(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        from src.core.exceptions import DataSourceError

        promoter = tmp_path / "stage1_promoter.json"
        promoter.write_text(
            json.dumps(
                {
                    "transcripts": [
                        {
                            "transcript_id": "ENST00000000001",
                            "gene": "VEGFA",
                            "chrom": "chr6",
                            "start": 43770209,
                            "end": 43786487,
                            "strand": "+",
                            "source": "Ensembl",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        out = tmp_path / "stage2_seed_hits.json"

        # Both are imported *inside* run(), so they must be patched at their
        # source modules, not on seed_aligner.
        with patch(
            "src.stage1_genomic_map.transcript_resolver.get_transcript_sequence",
            return_value="ACGU" * 50,
        ), patch(
            "src.stage2_offtarget_scan.transcriptome_fetcher.get_background_transcriptome",
            side_effect=DataSourceError("no canonical transcripts resolved"),
        ), pytest.raises(DataSourceError, match="no canonical transcripts"):
            seed_aligner_run(
                sarna_sequence="GCAACCAUAGCCUCGGCCGC",
                promoter_path=str(promoter),
                seed_length=7,
                max_mismatches=12,
                gc_range=[35.0, 65.0],
                threads=1,
                output_path=str(out),
                log_path=str(tmp_path / "seed.log"),
            )

        assert not out.exists(), (
            "run() wrote an output file despite the outage — a downstream stage "
            "would read it as 'scanned, nothing found'"
        )
