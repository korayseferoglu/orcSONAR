"""TLR7/TLR8 immune motif screen for Stage 6.

Short RNA sequences containing immunostimulatory motifs activate endosomal
Toll-like receptors (TLR7/TLR8), triggering innate immune responses.  High
motif density in a saRNA → elevated off-target toxicity risk.

Data source: ``data/5_Icra_Güvenlik/Immun_Motifler/immune_motifs.txt``
  — one motif per line, RNA format (U not T); ``#`` lines are comments.

Algorithm:
  1. Convert saRNA sequence to RNA (T → U, uppercase).
  2. Scan the sense strand (+) for all motif occurrences.
  3. Scan the antisense strand (−) — the reverse complement of the saRNA.
  4. Aggregate hits; compute risk score and level.

Risk classification:
  0 hits  → SAFE    (score 0.00)
  1 hit   → LOW     (score 0.25)
  ≥2 hits → HIGH    (score = min(1.0, 0.50 + hits × 0.10))
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from loguru import logger

from src.core.models import ImmuneResult, MotifHit

# Per the spec: ≥2 hits triggers high immunogenicity risk.
_HIGH_RISK_THRESHOLD: int = 2

_RNA_COMPLEMENT: dict[str, str] = {"A": "U", "U": "A", "G": "C", "C": "G"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _to_rna(sequence: str) -> str:
    """Normalise a nucleotide sequence to RNA format (uppercase, T → U).

    Args:
        sequence: DNA or RNA sequence string.

    Returns:
        Uppercase RNA sequence with all T replaced by U.
    """
    return sequence.upper().replace("T", "U")


def _reverse_complement_rna(sequence: str) -> str:
    """Return the reverse complement of an RNA sequence.

    Complement map: A↔U, G↔C.  Unknown bases are left unchanged.

    Args:
        sequence: Uppercase RNA sequence.

    Returns:
        Reverse complement RNA string.
    """
    comp = [_RNA_COMPLEMENT.get(b, b) for b in sequence]
    return "".join(reversed(comp))


def _load_motifs(filepath: str | Path) -> list[str] | None:
    """Load immune motifs from a plain-text file.

    Lines starting with ``#`` and blank lines are skipped.  Each motif is
    normalised to uppercase RNA format (T → U).

    ⚠️ ``None`` means **there is no motif list to screen against** — the file
    is missing, unreadable, or holds no motif. Roadmap `B11b`; all three used
    to return ``[]``, and the caller then reported ``"SAFE"`` for a sequence
    it had compared against nothing.

    ⚠️ And this is where `B11b` *differs* from `B11` on purpose. miRBase's
    empty-but-readable case is a measured absence — there is genuinely no
    human miRNA to overlap with — so it stays ``SAFE``. This list is **our own
    curation**, so an empty one does not mean no immunostimulatory motif
    exists; it means nothing was compared. The caller's decision is identical
    in all three cases, so the type carries that and the log carries the
    reason.

    Args:
        filepath: Path to the motif file.

    Returns:
        List of motif strings (RNA, uppercase), or ``None`` when no usable
        list could be read.
    """
    path = Path(filepath)
    if not path.exists():
        logger.warning(
            f"immune_screen: motif file not found at '{path}' — UNKNOWN, not SAFE"
        )
        return None
    motifs: list[str] = []
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            motifs.append(_to_rna(line))
    except OSError as exc:
        logger.error(
            f"immune_screen: cannot read motif file '{path}': {exc} — "
            "UNKNOWN, not SAFE"
        )
        return None
    if not motifs:
        logger.warning(
            f"immune_screen: '{path}' holds no motif — UNKNOWN, not SAFE "
            "(a hand-curated empty list means nothing was compared)"
        )
        return None
    logger.debug(f"immune_screen: loaded {len(motifs)} motifs from {path}")
    return motifs


def _scan_motifs(sequence: str, motifs: list[str]) -> list[MotifHit]:
    """Find all occurrences of each motif in *sequence* (all non-overlapping and overlapping).

    Searches for every motif at every position in the sequence.
    Overlapping matches are reported individually.

    Args:
        sequence: Uppercase RNA strand to search (sense or antisense).
        motifs: List of motif strings to search for.

    Returns:
        List of ``MotifHit`` objects with position and strand ``"+"``.
        Callers pass the antisense sequence to get minus-strand hits and
        then annotate those hits with ``strand="-"``.
    """
    hits: list[MotifHit] = []
    for motif in motifs:
        start = 0
        while True:
            pos = sequence.find(motif, start)
            if pos == -1:
                break
            hits.append(MotifHit(motif=motif, position=pos, strand="+"))
            start = pos + 1  # allow overlapping matches
    return hits


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def screen_immune_motifs(
    sarna_sequence: str,
    motif_file: str | Path,
) -> ImmuneResult:
    """Screen a saRNA sequence for TLR7/TLR8 immunostimulatory motifs.

    Searches both the sense strand and the antisense (reverse complement)
    strand of the saRNA.  Positions in the antisense result are reported
    relative to the antisense sequence.

    Args:
        sarna_sequence: saRNA nucleotide sequence (DNA or RNA, any case).
        motif_file: Path to the immune motifs file.

    Returns:
        ``ImmuneResult`` with all motif hits, total count, risk score,
        and risk level.
    """
    motifs = _load_motifs(motif_file)
    if motifs is None:
        # Not "SAFE": nothing was screened, so there is no verdict to give.
        # This function does not raise, which is why the adapter's `except`
        # never fired and this value overwrote its correct unknown
        # placeholder (roadmap B11b).
        logger.warning(
            "immune_screen: no motif list — returning UNKNOWN (not SAFE)"
        )
        return ImmuneResult()

    sense = _to_rna(sarna_sequence)
    antisense = _reverse_complement_rna(sense)

    sense_hits = _scan_motifs(sense, motifs)

    # Antisense hits get strand="-"
    antisense_raw = _scan_motifs(antisense, motifs)
    antisense_hits = [
        MotifHit(motif=h.motif, position=h.position, strand="-")
        for h in antisense_raw
    ]

    all_hits = sense_hits + antisense_hits
    total = len(all_hits)

    risk_score, risk_level = _classify_risk(total)

    logger.debug(
        f"immune_screen: seq={sense[:20]}... total_hits={total} "
        f"risk={risk_level} score={risk_score:.2f}"
    )

    return ImmuneResult(
        motifs_found=all_hits,
        total_hits=total,
        risk_score=risk_score,
        risk_level=risk_level,
        # Reported beside the verdict rather than redefining it: a threshold
        # on an empirical p would be another free parameter, and §10.1 of the
        # pre-registration already carries this column as `validated: false`.
        chance_hits=_chance_hits(motifs, len(sense)),
        u_count=sense.count("U"),
        u_fraction=sense.count("U") / len(sense) if sense else 0.0,
    )


def _chance_hits(motifs: list[str], length: int) -> float:
    """Expected motif hits for a uniform-composition sequence of `length`.

    Closed form, so no simulation and no seed: each motif of length L has
    ``length - L + 1`` positions per strand and both strands are scanned, and
    a specific L-mer occurs with probability ``4 ** -L``.

    ⚠️ Roadmap `B11c` measured why this is the null that belongs here and a
    **composition-matched** one does not. Shuffling the sequence preserves its
    uridine content, and the motifs are largely a U-richness detector, so the
    shuffled null tracks the observation almost exactly (U fraction 0.8:
    observed 8.08, shuffled null 7.99) — it cancels precisely the quantity
    Goodchild et al. 2009 (PMID 19630977) found to correlate with activity. A
    uniform-composition expectation instead answers the question a reader has:
    what would a random sequence of this length score?

    📌 This docstring used to avoid the word "shuffling" on purpose, because
    `run_manifest.stochastic_components()` decided whether the pipeline had
    randomness with a textual `git grep` and so read prose as a stochastic
    component — the record was being written to fit the detector's blindness.
    Roadmap `H24` moved that probe to an AST walk, where a docstring is not a
    call, so the plain wording is back. This function performs no sampling.

    Args:
        motifs: Motif list actually screened against.
        length: Sequence length in nucleotides.

    Returns:
        Expected hit count, both strands. ``0.0`` when no motif fits.
    """
    return sum(
        2 * (length - len(motif) + 1) * 0.25 ** len(motif)
        for motif in motifs
        if length >= len(motif)
    )


def _classify_risk(total_hits: int) -> tuple[float, Literal["SAFE", "LOW", "HIGH"]]:
    """Map hit count to (risk_score, risk_level).

    Per spec: ≥2 hits → HIGH immunogenicity risk.

    Args:
        total_hits: Total number of motif hits (sense + antisense).

    Returns:
        Tuple of (risk_score ∈ [0, 1], risk_level string).
    """
    if total_hits == 0:
        return 0.0, "SAFE"
    if total_hits == 1:
        return 0.25, "LOW"
    # ≥2 hits: score climbs from 0.50, capped at 1.0
    score = min(1.0, 0.50 + total_hits * 0.10)
    return score, "HIGH"
