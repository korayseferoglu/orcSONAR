"""G-Quadruplex (G4) structure detector for Stage 5 (orcSONAR).

Scans both strands of a nucleotide sequence for the consensus G4 motif:
    G{3,}[ACGTU]{1,7}G{3,}[ACGTU]{1,7}G{3,}[ACGTU]{1,7}G{3,}

Positive (risk-increasing) outcomes:
  - G4 in the off-target region → saRNA access blocked (reduced off-target effect)
  - G4 disruption by saRNA binding → genome-instability risk

The module reports motif coordinates, per-motif stability estimates, and a
combined risk score.
"""

from __future__ import annotations

import re

from loguru import logger

from src.core.models import G4Motif, G4Result

# G4 consensus: 4+ G-tracts (≥3 Gs each) separated by short loops (1–7 nt).
# Non-greedy loops prefer the shortest valid loop, giving the most
# biologically canonical interpretation.
_G4_RE = re.compile(
    r"(G{3,})([ACGTU]{1,7}?)(G{3,})([ACGTU]{1,7}?)(G{3,})([ACGTU]{1,7}?)(G{3,})",
    re.IGNORECASE,
)

# RNA complement table (uppercase; T treated as deoxythymidine → A complement)
_COMP_TABLE = str.maketrans("ACGTU", "UGCAA")


def _reverse_complement(seq: str) -> str:
    """Return the RNA reverse complement of *seq*.

    Treats T identically to U (both complement to A). Input is
    normalised to uppercase before translation.
    """
    return seq.upper().translate(_COMP_TABLE)[::-1]


def _score_g4_stability(motif: G4Motif) -> float:
    """Estimate G4 thermodynamic stability as a score in [0, 1].

    Combines two empirically motivated terms:

    * **g_score** = min(avg_g_tract_length / 6, 1.0):
      3 Gs → 0.50, 6+ Gs → 1.0 (longer tracts stack more stably).
    * **loop_score** = max(1 − (avg_loop_length − 1) / 6, 0.0):
      1 nt loop → 1.0, 7 nt loop → 0.0 (shorter loops constrain topology).

    Combined: (g_score + loop_score) / 2.

    Args:
        motif: Populated G4Motif (g_tract_lengths and loop_lengths must be set).

    Returns:
        Stability estimate in [0, 1].
    """
    if not motif.g_tract_lengths or not motif.loop_lengths:
        return 0.0

    avg_g = sum(motif.g_tract_lengths) / len(motif.g_tract_lengths)
    avg_loop = sum(motif.loop_lengths) / len(motif.loop_lengths)

    g_score = min(avg_g / 6.0, 1.0)
    loop_score = max(1.0 - (avg_loop - 1.0) / 6.0, 0.0)

    return round((g_score + loop_score) / 2.0, 4)


def _find_g4_motifs(seq: str, strand: str = "+") -> list[G4Motif]:
    """Find all G4 motifs in *seq* with an overlapping positional scan.

    Advances the search position by 1 after each match so that nested or
    tandem G4s (common in G-rich promoters) are all captured.

    Args:
        seq:    Nucleotide sequence (A/C/G/U or T). Case-insensitive.
        strand: Strand label for the returned motifs ("+" or "-").

    Returns:
        List of G4Motif objects (stability pre-computed).
    """
    seq_norm = seq.upper().replace("T", "U")
    motifs: list[G4Motif] = []
    pos = 0
    seq_len = len(seq_norm)

    while pos < seq_len:
        m = _G4_RE.search(seq_norm, pos)
        if m is None:
            break

        g_tract_lengths = [len(m.group(i)) for i in (1, 3, 5, 7)]
        loop_lengths = [len(m.group(i)) for i in (2, 4, 6)]

        # Create a temporary motif to feed into the stability scorer
        _tmp = G4Motif(
            start=m.start(),
            end=m.end(),
            sequence=m.group(0),
            strand=strand,
            g_tract_lengths=g_tract_lengths,
            loop_lengths=loop_lengths,
            stability_score=0.0,
        )
        stability = _score_g4_stability(_tmp)
        motifs.append(_tmp.model_copy(update={"stability_score": stability}))

        pos = m.start() + 1  # advance by 1 for overlapping detection

    return motifs


def detect_g4(sequence: str) -> G4Result:
    """Detect G-Quadruplex structures on both strands of *sequence*.

    Scans:
      1. Forward strand  ("+" motifs, coordinates relative to *sequence*)
      2. RNA reverse complement  ("-" motifs, coordinates mapped back to
         the original forward-strand frame)

    Args:
        sequence: Nucleotide sequence (A/C/G/U or T). An empty string
                  is accepted and returns a zero-risk G4Result.

    Returns:
        G4Result with motif list, density (motifs/kb), and risk score.
        Risk = min(n_motifs × avg_stability / 5, 1.0) — five fully-
        stable motifs saturate the score.
    """
    if not sequence:
        return G4Result()

    seq_len = len(sequence)

    fwd_motifs = _find_g4_motifs(sequence, strand="+")

    rc = _reverse_complement(sequence)
    rev_raw = _find_g4_motifs(rc, strand="-")

    # Re-map RC coordinates to the original (forward-strand) frame.
    rev_motifs: list[G4Motif] = []
    for rm in rev_raw:
        orig_start = seq_len - rm.end
        orig_end = seq_len - rm.start
        rev_motifs.append(rm.model_copy(update={"start": orig_start, "end": orig_end}))

    all_motifs = fwd_motifs + rev_motifs
    g4_count = len(all_motifs)
    density = g4_count / (seq_len / 1000.0) if seq_len > 0 else 0.0

    if all_motifs:
        avg_stability = sum(m.stability_score for m in all_motifs) / len(all_motifs)
        risk = min(g4_count * avg_stability / 5.0, 1.0)
    else:
        risk = 0.0

    logger.debug(
        "G4: {} motifs ({} fwd / {} rev), density={:.2f}/kb, risk={:.3f}",
        g4_count,
        len(fwd_motifs),
        len(rev_motifs),
        density,
        round(risk, 4),
    )

    return G4Result(
        motifs=all_motifs,
        g4_count=g4_count,
        g4_density=round(density, 4),
        risk_score=round(risk, 4),
    )
