#!/usr/bin/env python3
"""Empirical 7-mer null for the off-target seed (roadmap H13, used by E1).

The question this answers is the one the whole hit list rests on: **is this
saRNA's seed unusually promiscuous, or does it hit about as much as any 7-mer
would?** A list of 41 off-target sites looks alarming until you learn what an
arbitrary seed scores against the same background.

The null is exact, not sampled. There are 4^7 = 16384 possible 7-mers, so every
one of them is counted against the same background set the pipeline scans, and
the observed seed's rank in that distribution is read off directly. No
resampling, no distributional assumption.

Two units are reported because they answer slightly different questions and
mixing them up is easy:

* ``transcripts`` — how many background transcripts contain the seed's match
  site at all. This is the candidacy step: a transcript with no seed match can
  never become a site.
* ``occurrences`` — how many match positions exist in total, since one
  transcript can carry several.

What is deliberately **not** done here: no threshold, no verdict, no "safe" or
"risky" label. Choosing a cutoff after seeing the distribution is invariant 7's
violation, and the cutoff belongs in the pre-registration (`A12`). This script
measures and writes the numbers down.

Matching rule: the pipeline indexes ``reverse_complement(seed)`` and searches
the transcript in cDNA space (`.claude/rules/10-koordinatlar.md`), so the null
uses exactly that rule for every candidate 7-mer. Using a different rule for
the null than for the observation would compare two different experiments.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from itertools import product
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

SEED_LENGTH = 7
_COMPLEMENT = {"A": "U", "U": "A", "G": "C", "C": "G"}


def reverse_complement(seq: str) -> str:
    """Reverse complement an RNA sequence.

    Args:
        seq: Sequence over A/C/G/U.

    Returns:
        The reverse complement.
    """
    return "".join(_COMPLEMENT[base] for base in reversed(seq))


def kmer_counts(
    sequences: list[str], k: int = SEED_LENGTH
) -> tuple[Counter[str], Counter[str]]:
    """Count, for every k-mer, its transcript and occurrence frequencies.

    One pass over the background: for each sequence the distinct k-mers it
    contains raise the transcript count by one each, while every position
    raises the occurrence count. Doing it this way means the 16384-wide null
    costs the same as counting a single seed.

    Args:
        sequences: Background sequences, RNA alphabet, upper case.
        k: k-mer width.

    Returns:
        ``(transcript_counts, occurrence_counts)``.
    """
    per_transcript: Counter[str] = Counter()
    per_occurrence: Counter[str] = Counter()
    for seq in sequences:
        seen: set[str] = set()
        for i in range(len(seq) - k + 1):
            kmer = seq[i : i + k]
            per_occurrence[kmer] += 1
            seen.add(kmer)
        per_transcript.update(seen)
    return per_transcript, per_occurrence


def distribution(counts: Counter[str], k: int = SEED_LENGTH) -> list[int]:
    """The full null distribution over every possible k-mer.

    k-mers absent from the background count as zero rather than being dropped.
    Leaving them out would compare the observed seed only against seeds that
    happen to occur, which is the easier comparison and the wrong one.

    Args:
        counts: Observed k-mer counts.
        k: k-mer width.

    Returns:
        One count per possible k-mer, in lexicographic order.
    """
    return [
        counts.get("".join(combo), 0) for combo in product("ACGU", repeat=k)
    ]


def summarise(observed: int, null: list[int]) -> dict[str, Any]:
    """Locate ``observed`` inside ``null`` without choosing a threshold.

    Args:
        observed: The seed's own count.
        null: Counts for all possible k-mers.

    Returns:
        Rank statistics and a one-sided empirical p-value.
    """
    total = len(null)
    at_least = sum(1 for value in null if value >= observed)
    below = sum(1 for value in null if value < observed)
    mean = sum(null) / total
    ordered = sorted(null)
    mid = total // 2
    median = (
        ordered[mid] if total % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    )
    return {
        "observed": observed,
        "null_size": total,
        "null_mean": round(mean, 4),
        "null_median": median,
        "null_max": ordered[-1],
        "percentile_of_observed": round(100.0 * below / total, 4),
        # One-sided and inclusive of the observation itself: the fraction of
        # 7-mers that are at least as promiscuous as this one.
        "p_empirical_ge": round(at_least / total, 6),
        "interpretation_is_not_here": (
            "No threshold or verdict is computed. Picking a cutoff after seeing "
            "this distribution is what invariant 7 forbids; the cutoff belongs "
            "in docs/PRE_REGISTRATION.md (roadmap A12)."
        ),
    }


def load_background(cell_line: str) -> tuple[list[str], dict[str, Any]]:
    """Fetch the background transcript sequences the pipeline scans.

    Args:
        cell_line: Cell line passed through to the fetcher.

    Returns:
        ``(sequences, provenance)``.
    """
    from src.core.config import load_config
    from src.stage2_offtarget_scan.transcriptome_fetcher import (
        get_background_transcriptome,
    )

    config = load_config(REPO_ROOT / "config" / "config.yaml")
    target_gene = config.target_gene
    # Three values, not the two the annotation claims — see roadmap B16.
    transcripts, raw_sequences, coverage = get_background_transcriptome(
        config, exclude_gene=target_gene
    )
    sequences = [
        seq.upper().replace("T", "U") for seq in raw_sequences.values() if seq
    ]
    return sequences, {
        "transcripts_returned": len(transcripts),
        "sequences_returned": len(raw_sequences),
        "sequences_non_empty": len(sequences),
        "excluded_gene": target_gene,
        "cell_line": cell_line,
        "total_nucleotides": sum(len(s) for s in sequences),
        "resolution_coverage": coverage,
    }


def main() -> int:
    """Compute the null and write the report.

    Returns:
        ``0`` when the report was written, ``2`` when it could not be.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell-line", default="HeLa")
    parser.add_argument(
        "--output", default=str(REPO_ROOT / "reports" / "null_gate.json")
    )
    args = parser.parse_args()

    import yaml

    config = yaml.safe_load(
        (REPO_ROOT / "config" / "config.yaml").read_text(encoding="utf-8")
    )
    guide = config["sarna_sequence"].upper().replace("T", "U")
    seed_length = int(config["seed_length"])
    if seed_length != SEED_LENGTH:
        print(
            f"null_check: config seed_length={seed_length} but this null is "
            f"built over {SEED_LENGTH}-mers — refusing to compare two "
            "different experiments",
            file=sys.stderr,
        )
        return 2

    # The seed slice is rule 10's to state (`.claude/rules/10-koordinatlar.md`);
    # the offset below is taken from `seed_aligner._SEED_START`, not restated.
    from src.stage2_offtarget_scan.seed_aligner import _SEED_START

    seed = guide[_SEED_START : _SEED_START + seed_length]
    query = reverse_complement(seed)

    try:
        sequences, provenance = load_background(args.cell_line)
    except Exception as exc:  # noqa: BLE001 - reported, never silently zeroed
        print(f"null_check: background could not be loaded: {exc}", file=sys.stderr)
        return 2
    if not sequences:
        print("null_check: background carries no sequences", file=sys.stderr)
        return 2

    per_transcript, per_occurrence = kmer_counts(sequences, seed_length)

    report = {
        "schema_version": 1,
        "written_at": datetime.now(UTC).isoformat(),
        "guide": guide,
        "seed": seed,
        "seed_match_target": query,
        "seed_positions_1_based_inclusive": [2, 1 + seed_length],
        "background": provenance,
        "units": {
            "transcripts": summarise(
                per_transcript.get(query, 0), distribution(per_transcript, seed_length)
            ),
            "occurrences": summarise(
                per_occurrence.get(query, 0), distribution(per_occurrence, seed_length)
            ),
        },
    }

    # The `H4` status line reads a fixed set of top-level keys (`_status.
    # null_gate_text`): at, p_value, observed, expected, significant, verdict.
    # The first four are mirrored from the primary unit so the launch line says
    # something instead of "tanınan alan yok". `significant` and `verdict` are
    # deliberately NOT written: both are interpretations against a threshold,
    # and no threshold is pre-registered yet (`A12`). Emitting them would be
    # choosing a cutoff after seeing the distribution — invariant 7.
    primary = "occurrences"
    report["primary_unit"] = primary
    report["primary_unit_reason"] = (
        "occurrences is the count a hit list is compared against: one transcript "
        "can carry several match positions, and each is a candidate site"
    )
    report["at"] = report["written_at"]
    report["observed"] = report["units"][primary]["observed"]
    report["expected"] = report["units"][primary]["null_mean"]
    report["p_value"] = report["units"][primary]["p_empirical_ge"]

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    for unit, stats in report["units"].items():
        print(
            f"null_check: {unit:<12} observed={stats['observed']:<6} "
            f"null mean={stats['null_mean']:<10} "
            f"percentile={stats['percentile_of_observed']:.1f} "
            f"p(≥obs)={stats['p_empirical_ge']}"
        )
    print(f"null_check: → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
