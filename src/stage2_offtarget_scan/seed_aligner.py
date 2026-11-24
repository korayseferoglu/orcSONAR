"""Seed-based alignment engine for saRNA off-target detection (Stage 2).

Algorithm:
  1. Extract 7-nt seed (positions 2-8, 1-indexed = sarna[1:8]) from the saRNA.
  2. Build a seed index: find all occurrences of reverse_complement(seed) in
     each transcript mRNA using fast substring search (pre-filter).
  3. For each candidate position, score the full-length anti-parallel alignment.
  4. Apply filters: max 1 seed mismatch (G:U wobbles exempt), max 3 total mismatches.

Anti-parallel pairing convention:
    saRNA[i]  pairs with  mRNA_window[n-1-i]  (reading mRNA 3'→5').
    Perfect Watson-Crick: +1.0 | G:U wobble: +0.5 | Mismatch: 0.0
"""

from __future__ import annotations

from typing import Any, Literal

from loguru import logger

from src.core.config import OrcSonarConfig
from src.core.exceptions import DataSourceError
from src.core.models import AlignmentResult, GenomicRegion, OffTargetSite, TranscriptInfo

_COMPLEMENT: dict[str, str] = {"A": "U", "U": "A", "G": "C", "C": "G", "T": "A"}

# 0-indexed position in saRNA where seed begins (miRNA convention: nt 2-8, 1-indexed)
_SEED_START = 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def find_offtargets(
    sarna_seq: str,
    transcripts: list[TranscriptInfo],
    sequences: dict[str, str],
    config: OrcSonarConfig,
) -> list[OffTargetSite]:
    """Find all off-target binding sites for a saRNA across the transcriptome.

    Uses two-pass strategy: fast seed RC substring pre-filter, then full-length
    anti-parallel alignment scoring only on transcripts with seed hits.

    Args:
        sarna_seq: saRNA sequence (RNA uppercase, U not T).
        transcripts: Transcript metadata from Stage 1.
        sequences: Mapping transcript_id → mRNA sequence (T or U accepted).
        config: Pipeline config (seed_length, max_mismatches).

    Returns:
        List of OffTargetSite sorted by alignment_score descending.
    """
    seed = _extract_seed(sarna_seq, seed_start=_SEED_START, seed_length=config.seed_length)
    seed_index = _build_seed_index(sequences, seed)

    logger.info(
        f"Seed '{seed}' hit {len(seed_index)}/{len(sequences)} transcripts; "
        "running full alignment on candidates"
    )

    transcript_map: dict[str, TranscriptInfo] = {t.transcript_id: t for t in transcripts}
    sarna_len = len(sarna_seq)
    # Inclusive 0-indexed position of the last seed base in saRNA
    seed_end_in_sarna = _SEED_START + config.seed_length - 1

    offtargets: list[OffTargetSite] = []

    for transcript_id, positions in seed_index.items():
        t_seq = sequences[transcript_id]
        t_info = transcript_map.get(transcript_id)
        if t_info is None:
            continue

        for p in positions:
            # Window derivation:
            #   sarna[seed_end_in_sarna] pairs with mRNA[p]
            #   sarna[i] pairs with mRNA[p + seed_end_in_sarna - i]
            #   sarna[0] pairs with mRNA[p + seed_end_in_sarna]
            #   sarna[sarna_len-1] pairs with mRNA[p - (sarna_len - 1 - seed_end_in_sarna)]
            win_start = p - (sarna_len - 1 - seed_end_in_sarna)
            win_end = win_start + sarna_len

            if win_start < 0 or win_end > len(t_seq):
                continue

            mRNA_window = t_seq[win_start:win_end]
            result = _score_alignment(sarna_seq, mRNA_window, config.seed_length)

            # Safety net: exact pre-filter guarantees seed_mismatches == 0;
            # guard remains in case the pre-filter is relaxed in future.
            if result.seed_mismatches > 1:
                continue
            if result.mismatches > config.max_mismatches:
                continue

            if result.seed_mismatches == 0 and result.gu_wobbles == 0:
                seed_match_type: Literal["perfect", "G:U_wobble", "mismatch", "bulge"] = "perfect"
            elif result.seed_mismatches == 0:
                seed_match_type = "G:U_wobble"
            else:
                seed_match_type = "mismatch"

            # Approximate genomic coordinates (mRNA is spliced; coordinates are indicative)
            if t_info.strand == "+":
                g_start = t_info.start + win_start
                g_end = t_info.start + win_end
            else:
                g_start = max(0, t_info.end - win_end)
                g_end = t_info.end - win_start

            region = GenomicRegion(
                chrom=t_info.chrom,
                start=g_start,
                end=g_end,
                strand=t_info.strand,
            )

            offtargets.append(
                OffTargetSite(
                    gene=t_info.gene,
                    transcript_id=transcript_id,
                    region=region,
                    seed_match_type=seed_match_type,
                    mismatches=result.mismatches,
                    alignment_score=result.score,
                    tx_start=win_start,
                    tx_end=win_end,
                    # Already in hand; stage 5 needs it and cannot re-derive
                    # it without re-fetching the transcript (roadmap C3).
                    target_window=mRNA_window,
                )
            )

    offtargets.sort(key=lambda x: x.alignment_score, reverse=True)

    # site_id uniqueness is the premise every downstream stage relies on, and it
    # is not guaranteed: the minus-strand branch above clamps with max(0, ...),
    # so two windows past a short transcript's end both land on start=0 and
    # collapse to one key. Assert rather than assume — a collision here silently
    # reinstates Bulgu-2 with the fix nominally in place.
    site_ids = [s.site_id for s in offtargets]
    if len(set(site_ids)) != len(site_ids):
        dupes = sorted({sid for sid in site_ids if site_ids.count(sid) > 1})
        logger.error(
            f"seed_aligner: site_id COLLISION — {len(site_ids)} hits produced only "
            f"{len(set(site_ids))} unique ids. Downstream stages will overwrite each "
            f"other for: {dupes[:5]}{' ...' if len(dupes) > 5 else ''}"
        )

    logger.info(f"Found {len(offtargets)} off-target sites after filtering")
    return offtargets


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


def _extract_seed(
    sarna_seq: str,
    seed_start: int = 1,
    seed_length: int = 7,
) -> str:
    """Extract the seed region from a saRNA sequence.

    Args:
        sarna_seq: Full saRNA sequence (RNA uppercase, U not T).
        seed_start: 0-indexed start of seed (default 1 = position 2 in 1-indexed).
        seed_length: Seed length in nucleotides (default 7).

    Returns:
        Seed subsequence string.

    Raises:
        ValueError: If seed window extends beyond the saRNA length.
    """
    seed_end = seed_start + seed_length
    if seed_end > len(sarna_seq):
        raise ValueError(
            f"Seed [{seed_start}:{seed_end}] out of bounds for saRNA length {len(sarna_seq)}"
        )
    return sarna_seq[seed_start:seed_end]


def _build_seed_index(
    sequences: dict[str, str],
    seed: str,
) -> dict[str, list[int]]:
    """Index positions where reverse_complement(seed) occurs in each transcript.

    Args:
        sequences: Mapping transcript_id → mRNA sequence (T or U).
        seed: saRNA seed (RNA, U not T); RC is computed internally.

    Returns:
        Mapping transcript_id → list of 0-indexed start positions of RC seed.
        Only transcripts with ≥ 1 hit are included.
    """
    rc_seed_u = _reverse_complement(seed)
    rc_seed_t = rc_seed_u.replace("U", "T")

    index: dict[str, list[int]] = {}
    for tid, seq in sequences.items():
        # Pick the needle matching the sequence alphabet (T or U based)
        needle = rc_seed_t if "T" in seq else rc_seed_u
        positions: list[int] = []
        start = 0
        while True:
            pos = seq.find(needle, start)
            if pos == -1:
                break
            positions.append(pos)
            start = pos + 1
        if positions:
            index[tid] = positions
    return index


def _score_alignment(sarna: str, target: str, seed_length: int = 7) -> AlignmentResult:
    """Score saRNA vs mRNA window using anti-parallel miRNA-like pairing.

    saRNA[i] pairs with target[n-1-i] (reading target 3'→5').

    Scoring: Watson-Crick +1.0, G:U wobble +0.5, mismatch 0.0.
    Seed = sarna[_SEED_START : _SEED_START + seed_length].

    Args:
        sarna: saRNA sequence (RNA uppercase, U not T), length n.
        target: mRNA window, length n (T or U accepted).
        seed_length: Number of seed nucleotides (default 7).

    Returns:
        AlignmentResult with scores, counts, and mismatch positions.

    Raises:
        ValueError: If sarna and target have different lengths.
    """
    if len(sarna) != len(target):
        raise ValueError(
            f"Length mismatch: sarna={len(sarna)}, target={len(target)}"
        )

    n = len(sarna)
    score = 0.0
    mismatches = 0
    gu_wobbles = 0
    seed_mismatches = 0
    mismatch_positions: list[int] = []

    seed_region_end = _SEED_START + seed_length  # exclusive

    for i in range(n):
        s_base = sarna[i]
        t_base = target[n - 1 - i].replace("T", "U")

        if _is_watson_crick(s_base, t_base):
            score += 1.0
        elif _is_gu_wobble(s_base, t_base):
            score += 0.5
            gu_wobbles += 1
        else:
            mismatches += 1
            mismatch_positions.append(i)
            if _SEED_START <= i < seed_region_end:
                seed_mismatches += 1

    return AlignmentResult(
        score=score,
        mismatches=mismatches,
        gu_wobbles=gu_wobbles,
        seed_mismatches=seed_mismatches,
        aligned_target=target,
        positions=mismatch_positions,
    )


def _is_watson_crick(base1: str, base2: str) -> bool:
    """Return True for canonical Watson-Crick RNA base pairs (A:U, G:C)."""
    return _COMPLEMENT.get(base1) == base2


def _is_gu_wobble(base1: str, base2: str) -> bool:
    """Return True if base1:base2 forms a G:U wobble pair.

    Args:
        base1: saRNA base.
        base2: mRNA anti-parallel base (already normalised to U).

    Returns:
        True if (G,U) or (U,G).
    """
    return (base1 == "G" and base2 == "U") or (base1 == "U" and base2 == "G")


def _reverse_complement(seq: str) -> str:
    """Return the RNA reverse complement of seq.

    Args:
        seq: RNA or cDNA sequence (uppercase, T or U accepted).

    Returns:
        Reverse complement using A↔U, G↔C. Unknown bases become 'N'.
    """
    comp: dict[str, str] = {"A": "U", "U": "A", "G": "C", "C": "G", "T": "A", "N": "N"}
    return "".join(comp.get(b, "N") for b in reversed(seq))


# ---------------------------------------------------------------------------
# Snakemake run() entry point
# ---------------------------------------------------------------------------


def run(
    sarna_sequence: str,
    promoter_path: str,
    seed_length: int,
    max_mismatches: int,
    gc_range: list[float],
    threads: int,
    output_path: str,
    log_path: str,
    cell_line: str = "HeLa",
    config_raw: dict[str, Any] | None = None,
) -> None:
    """Run seed alignment against the whole transcriptome and write stage2_seed_hits.json.

    Loads target-gene transcript metadata from stage1_promoter.json, merges with
    a background set of ~250 canonical human transcripts fetched from Ensembl, then
    scans all combined sequences for off-target seed matches.
    Falls back to neutral (empty) results when sequence data is unavailable.
    """
    import json
    import sys
    from pathlib import Path as _Path

    _Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(log_path, level="DEBUG")
    logger.add(sys.stderr, level="INFO")

    # Load promoter JSON to get gene info and transcript metadata
    promoter_data: dict[str, Any] = {}
    try:
        promoter_data = json.loads(_Path(promoter_path).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"seed_aligner: cannot load promoter JSON: {exc}")

    gene = promoter_data.get("gene", "UNKNOWN")
    raw_transcripts: list[dict] = promoter_data.get("transcripts", [])

    from src.core.config import config_from_mapping
    from src.core.models import TranscriptInfo
    from src.stage1_genomic_map.transcript_resolver import get_transcript_sequence
    from src.stage2_offtarget_scan.transcriptome_fetcher import get_background_transcriptome

    config = config_from_mapping(config_raw, 
        target_gene=gene,
        seed_length=seed_length,
        max_mismatches=max_mismatches,
        gc_range=gc_range,
    )

    # --- Target gene transcripts (from Stage 1) ---
    transcripts: list[TranscriptInfo] = []
    for raw in raw_transcripts:
        try:
            transcripts.append(TranscriptInfo(**raw))
        except Exception as exc:
            # Never swallow this silently: a dropped transcript is one fewer
            # place an off-target can be found, so the failure biases the run
            # toward SAFE. Say which record was lost and why.
            logger.warning(
                f"seed_aligner: skipping unusable transcript record "
                f"{raw.get('transcript_id', raw)!r}: {exc}"
            )

    sequences: dict[str, str] = {}
    for t in transcripts:
        try:
            seq = get_transcript_sequence(t.transcript_id, config)
            if seq:
                sequences[t.transcript_id] = seq.upper().replace("T", "U")
        except Exception as exc:
            logger.debug(f"seed_aligner: sequence fetch failed for {t.transcript_id}: {exc}")

    # --- Background transcriptome (whole-transcriptome scan) ---
    # Unknown until the fetch reports it. The generic `except` below keeps the
    # run going, and in that case the coverage is genuinely not known — which
    # must not read as full coverage (roadmap R12a).
    bg_coverage: dict[str, Any] | None = None
    try:
        bg_transcripts, bg_sequences, bg_coverage = get_background_transcriptome(
            config, exclude_gene=gene
        )
        # Normalise to RNA alphabet
        for tid, seq in bg_sequences.items():
            bg_sequences[tid] = seq.upper().replace("T", "U")
        transcripts = transcripts + bg_transcripts
        sequences.update(bg_sequences)
        logger.info(
            f"seed_aligner: {gene} — scanning {len(sequences)} transcripts total "
            f"({len(bg_transcripts)} background + target gene)"
        )
    except DataSourceError:
        # Deliberately NOT swallowed. Losing the whole background transcriptome
        # shrinks the search space to the target gene, which yields zero
        # off-target sites and a SAFE verdict — the audit of 2026-11-19 watched
        # exactly that happen (Bulgu 12: Ensembl 504 → 0 sites → risk=SAFE,
        # exit 0). A warning here is indistinguishable from "nothing to find".
        raise
    except Exception as exc:
        logger.warning(f"seed_aligner: background transcriptome fetch failed: {exc}")

    if not sequences:
        # Same reasoning: no sequences at all is an outage, and writing an
        # empty hit file lets every downstream stage read it as a measurement.
        raise DataSourceError(
            f"seed_aligner: no transcript sequences available for {gene} — "
            f"the scan would have nothing to search, and an empty hit file "
            f"reads downstream as 'scanned, nothing found'."
        )

    sarna_rna = sarna_sequence.upper().replace("T", "U")
    try:
        sites = find_offtargets(sarna_rna, transcripts, sequences, config)
    except Exception as exc:
        logger.warning(f"seed_aligner: find_offtargets failed: {exc}")
        sites = []

    seq_scores = {s.site_id: round(s.alignment_score, 4) for s in sites}

    payload = {
        "sites": [s.model_dump() for s in sites],
        "sequence_scores": seq_scores,
        # How much of the declared 183-gene background was actually searched.
        # A run that does not carry this cannot be compared with another one
        # (roadmap R12a); the 2026-11-19 run searched 12% and said nothing.
        "background_coverage": bg_coverage,
    }

    out = _Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info(f"seed_aligner: {gene} → {len(sites)} off-target site(s)")
