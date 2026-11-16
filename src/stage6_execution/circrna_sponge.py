"""circRNA sponge overlap detection for Stage 6.

A circular RNA (circRNA) that overlaps an off-target region may act as a
"sponge": it sequesters the saRNA via complementary base pairing, reducing
effective saRNA concentration and diminishing on-target activity.

Data source: circAtlas 3.0 — ``hg38_circRNAs.bed`` (standard BED4/BED6).
Graceful degradation: if the file is absent the module returns neutral results
(``sponge_risk=False``, ``data_available=False``) and logs a warning.

Overlap condition (0-based, half-open intervals):
  region.start < circ.end  AND  circ.start < region.end  AND  same chromosome
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from loguru import logger

from src.core.models import CircRNAEntry, CircRNAResult, GenomicRegion

# Expected filename inside the circAtlas data directory.
_CIRCRNA_BED_FILENAME: str = "hg38_circRNAs.bed"


# ---------------------------------------------------------------------------
# BED loader
# ---------------------------------------------------------------------------


def _load_circrna_bed(bed_path: Path) -> dict[str, list[CircRNAEntry]]:
    """Parse a circRNA BED file into a chromosome-keyed dict.

    Accepts BED4 through BED6+ formats.  Skips blank lines and ``#``
    comment lines.  Unknown strands default to ``"."``.

    Args:
        bed_path: Absolute path to the BED file.

    Returns:
        ``{chrom: [CircRNAEntry, ...], ...}`` — empty dict on parse failure.
    """
    entries: dict[str, list[CircRNAEntry]] = defaultdict(list)
    try:
        with bed_path.open(encoding="utf-8") as fh:
            for lineno, raw in enumerate(fh, 1):
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                cols = line.split("\t")
                if len(cols) < 4:
                    logger.warning(
                        f"circrna_sponge: skipping short line {lineno} in {bed_path}"
                    )
                    continue
                chrom, start_s, end_s, circ_id = cols[:4]
                strand = cols[5] if len(cols) >= 6 else "."
                try:
                    entry = CircRNAEntry(
                        chrom=chrom,
                        start=int(start_s),
                        end=int(end_s),
                        circ_id=circ_id,
                        strand=strand,  # type: ignore[arg-type]
                    )
                except (ValueError, Exception) as exc:
                    logger.warning(
                        f"circrna_sponge: bad record line {lineno}: {exc}"
                    )
                    continue
                entries[chrom].append(entry)
    except OSError as exc:
        logger.error(f"circrna_sponge: cannot read {bed_path}: {exc}")
        return {}
    total = sum(len(v) for v in entries.values())
    logger.info(f"circrna_sponge: loaded {total} circRNA entries from {bed_path}")
    return dict(entries)


# ---------------------------------------------------------------------------
# Overlap logic
# ---------------------------------------------------------------------------


def _overlaps(region: GenomicRegion, entry: CircRNAEntry) -> bool:
    """Return True when a query region overlaps a circRNA entry (same chrom).

    Uses standard 0-based half-open interval arithmetic.

    Args:
        region: Query genomic interval.
        entry: circRNA interval from BED file.

    Returns:
        True if they share at least one base on the same chromosome.
    """
    return (
        region.chrom == entry.chrom
        and region.start < entry.end
        and entry.start < region.end
    )


def _find_overlaps(
    region: GenomicRegion,
    index: dict[str, list[CircRNAEntry]],
) -> list[CircRNAEntry]:
    """Return all circRNA entries overlapping *region* from the chromosome index.

    Args:
        region: Query genomic interval (chr-prefixed, hg38).
        index: Chromosome-bucketed circRNA entries.

    Returns:
        List of overlapping ``CircRNAEntry`` objects (may be empty).
    """
    candidates = index.get(region.chrom, [])
    return [e for e in candidates if _overlaps(region, e)]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_circrna_overlap(
    regions: list[GenomicRegion],
    circrna_path: str | Path | None = None,
) -> list[CircRNAResult]:
    """Check whether off-target regions overlap circRNA loci.

    If *circrna_path* is ``None`` or the file does not exist, all results are
    returned with ``data_available=False`` and ``sponge_risk=False`` — the
    module degrades gracefully rather than raising.

    A region is flagged ``sponge_risk=True`` whenever at least one circRNA
    overlaps it; the scoring engine may use ``overlap_count`` for graded risk.

    Args:
        regions: Off-target genomic intervals (chr-prefixed, hg38).
        circrna_path: Path to ``hg38_circRNAs.bed``, or ``None`` if data is
            not yet available.

    Returns:
        One ``CircRNAResult`` per input region, in the same order.
    """
    if not regions:
        return []

    # Resolve BED path
    bed_path: Path | None = None
    if circrna_path is not None:
        bed_path = Path(circrna_path)
        if not bed_path.exists():
            logger.warning(
                f"circrna_sponge: BED file not found at '{bed_path}' — "
                "returning neutral results (data_available=False)"
            )
            bed_path = None

    if bed_path is None:
        return [
            CircRNAResult(
                region=r,
                overlapping_circrnas=[],
                overlap_count=0,
                sponge_risk=False,
                data_available=False,
            )
            for r in regions
        ]

    index = _load_circrna_bed(bed_path)
    data_available = bool(index)

    results: list[CircRNAResult] = []
    for region in regions:
        hits = _find_overlaps(region, index)
        results.append(
            CircRNAResult(
                region=region,
                overlapping_circrnas=hits,
                overlap_count=len(hits),
                sponge_risk=len(hits) > 0,
                data_available=data_available,
            )
        )
        logger.debug(
            f"circrna_sponge: {region} overlaps={len(hits)} sponge_risk={len(hits) > 0}"
        )

    return results
