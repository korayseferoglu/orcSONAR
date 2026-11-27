"""miRBase mature miRNA seed-overlap checker for Stage 2.

Detects whether a saRNA seed region (nt 2-8, 1-indexed) matches the seed of
any known human miRNA.  A seed match implies the saRNA may suppress the same
targets as that miRNA — a significant off-target risk.

Scoring (fraction of 7 seed positions that match exactly, case-insensitive):
    7/7 → 1.0   (HIGH)
    6/7 → 0.7   (MODERATE)
    5/7 → 0.3   (LOW)
    <5  → 0.0   (SAFE)
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from loguru import logger

from src.core.models import MirbaseOverlap, MirbaseResult, MirnaEntry

# Seed region semantics are rule 10's (`.claude/rules/10-koordinatlar.md`);
# the slice is not restated here. ⚠️ `_SEED_LENGTH` is a second, live copy of
# `config.seed_length` — change the config and this module keeps the old
# width, so miRBase overlap would be computed against a different seed than
# the scan used. Roadmap `B14`.
_SEED_START = 1
_SEED_LENGTH = 7

_SCORE_TABLE: dict[int, float] = {7: 1.0, 6: 0.7, 5: 0.3}


def _seed_of(sequence: str) -> str:
    """Return the seed slice rule 10 defines, for every path in this module.

    One copy. The failure path used to slice ``[:7]`` — positions 1-7 instead
    of 2-8 — so the seed reported next to a failed check was the wrong one
    (roadmap `B11`; rule 10 is the authority for the slice).

    Args:
        sequence: saRNA sequence, 5'→3'.

    Returns:
        The seed substring, or the whole sequence when it is shorter than the
        slice.
    """
    if len(sequence) < _SEED_START + _SEED_LENGTH:
        return sequence
    return sequence[_SEED_START : _SEED_START + _SEED_LENGTH]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_mirbase_overlap(sarna_seq: str, mirbase_path: str) -> MirbaseResult:
    """Check if the saRNA seed overlaps with any known human miRNA seed.

    Args:
        sarna_seq: saRNA sequence (RNA uppercase, U not T).
        mirbase_path: Path to miRBase mature.fa FASTA file.

    Returns:
        MirbaseResult with all overlapping miRNAs and aggregate risk level.
    """
    sarna_seed = _seed_of(sarna_seq)
    mirnas = _parse_mirbase(mirbase_path)
    if mirnas is None:
        # The FASTA could not be read. "No overlap found" would be a risk
        # decision taken from the absence of data (invariant 2, roadmap B11).
        logger.warning(
            f"miRBase check NOT PERFORMED (unreadable: {mirbase_path}) — "
            "returning unknown, not SAFE"
        )
        return MirbaseResult(sarna_seed=sarna_seed)

    overlaps: list[MirbaseOverlap] = []
    for mirna in mirnas:
        score = _compare_seeds(sarna_seed, mirna.seed)
        if score > 0.0:
            # strict=True asserts what _compare_seeds already guarantees: a
            # score above 0.0 is only returned when both seeds are exactly
            # _SEED_LENGTH. A silent zip truncation here would score a short
            # seed as a full match.
            matched = sum(a == b for a, b in zip(sarna_seed, mirna.seed, strict=True))
            overlaps.append(
                MirbaseOverlap(
                    mirna_id=mirna.mirna_id,
                    mirna_seed=mirna.seed,
                    overlap_score=score,
                    matched_positions=matched,
                )
            )

    overlaps.sort(key=lambda x: x.overlap_score, reverse=True)
    max_score = overlaps[0].overlap_score if overlaps else 0.0
    risk = _score_to_risk(max_score)

    logger.info(
        f"miRBase check: seed='{sarna_seed}', "
        f"{len(overlaps)} overlaps found, max_score={max_score:.1f}, risk={risk}"
    )
    return MirbaseResult(
        sarna_seed=sarna_seed,
        overlapping_mirnas=overlaps,
        max_overlap_score=max_score,
        risk_level=risk,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_mirbase(fasta_path: str) -> list[MirnaEntry] | None:
    """Parse human miRNA entries from miRBase mature FASTA.

    Only records with an ``hsa-`` prefix (Homo sapiens) are returned.

    ⚠️ The return type carries the distinction roadmap `B11` is about:
    ``None`` means the FASTA could not be read, while ``[]`` means it was read
    and holds no human entry. Both used to be ``[]``, so the caller computed
    ``max_score = 0.0`` and ``risk = SAFE`` from a missing file — a risk
    decision taken from the absence of data (invariant 2).

    Args:
        fasta_path: Absolute or relative path to mature.fa.

    Returns:
        List of MirnaEntry objects (sequence and seed normalised to U), or
        ``None`` when the file could not be read at all.
    """
    path = Path(fasta_path)
    if not path.exists():
        logger.error(f"miRBase FASTA not found: {fasta_path}")
        return None

    entries: list[MirnaEntry] = []
    current_id: str | None = None
    current_acc: str | None = None
    seq_parts: list[str] = []

    with path.open() as fh:
        for raw_line in fh:
            line = raw_line.rstrip()
            if line.startswith(">"):
                if current_id is not None and seq_parts:
                    _append_entry(entries, current_id, current_acc or "", seq_parts)
                parts = line[1:].split(None, 2)
                mirna_id = parts[0]
                if not mirna_id.startswith("hsa-"):
                    current_id = None
                    current_acc = None
                    seq_parts = []
                    continue
                current_id = mirna_id
                current_acc = parts[1] if len(parts) > 1 else ""
                seq_parts = []
            elif current_id is not None:
                seq_parts.append(line.upper().replace("T", "U"))

    if current_id is not None and seq_parts:
        _append_entry(entries, current_id, current_acc or "", seq_parts)

    logger.debug(f"Parsed {len(entries)} human miRNA entries from {fasta_path}")
    return entries


def _append_entry(
    entries: list[MirnaEntry],
    mirna_id: str,
    accession: str,
    seq_parts: list[str],
) -> None:
    seq = "".join(seq_parts)
    if len(seq) < _SEED_START + _SEED_LENGTH:
        logger.warning(f"miRNA '{mirna_id}' too short for seed extraction, skipping")
        return
    seed = seq[_SEED_START : _SEED_START + _SEED_LENGTH]
    entries.append(MirnaEntry(mirna_id=mirna_id, accession=accession, sequence=seq, seed=seed))


def _compare_seeds(sarna_seed: str, mirna_seed: str) -> float:
    """Score exact-position overlap between two 7-nt seed sequences.

    Args:
        sarna_seed: 7-nt saRNA seed (RNA uppercase, U not T).
        mirna_seed: 7-nt miRNA seed (RNA uppercase, U not T).

    Returns:
        Overlap score: 1.0, 0.7, 0.3, or 0.0.
    """
    if len(sarna_seed) != _SEED_LENGTH or len(mirna_seed) != _SEED_LENGTH:
        return 0.0
    matched = sum(a == b for a, b in zip(sarna_seed, mirna_seed, strict=True))
    return _SCORE_TABLE.get(matched, 0.0)


def _score_to_risk(score: float) -> Literal["SAFE", "LOW", "MODERATE", "HIGH"]:
    """Map an overlap score to the risk level `MirbaseResult` accepts.

    The return type is the model's own `Literal` rather than `str` so the two
    cannot drift: before `B11` the field accepted any string and this returned
    `str`, so a typo here would have been a silently invalid risk level.

    Args:
        score: Overlap score in [0, 1].

    Returns:
        The risk level. Never ``None`` — a measured score always has one; the
        unknown case never reaches this function.
    """
    if score >= 1.0:
        return "HIGH"
    if score >= 0.7:
        return "MODERATE"
    if score >= 0.3:
        return "LOW"
    return "SAFE"


# ---------------------------------------------------------------------------
# Snakemake run() entry point
# ---------------------------------------------------------------------------


def run(
    sarna_sequence: str,
    mirbase_fa: str,
    output_path: str,
    log_path: str,
) -> None:
    """Check saRNA against miRBase and write stage2_mirbase.json."""
    import json
    import sys
    from pathlib import Path as _Path

    _Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(log_path, level="DEBUG")
    logger.add(sys.stderr, level="INFO")

    try:
        result = check_mirbase_overlap(sarna_sequence, mirbase_fa)
        payload = result.model_dump()
        logger.info(
            f"mirbase_checker: seed={result.sarna_seed} "
            f"overlaps={len(result.overlapping_mirnas)} risk={result.risk_level}"
        )
    except Exception as exc:
        # Not "SAFE": a check that crashed measured nothing (invariant 2,
        # roadmap B11). The seed goes through `_seed_of` so this path reports
        # rule 10's slice like every other one.
        logger.warning(
            f"mirbase_checker: failed: {exc} — returning UNKNOWN (not SAFE)"
        )
        payload = MirbaseResult(sarna_seed=_seed_of(sarna_sequence)).model_dump()

    out = _Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
