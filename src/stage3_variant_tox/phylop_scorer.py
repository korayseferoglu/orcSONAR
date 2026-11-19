"""phyloP evolutionary conservation scorer for Stage 3.

Streams per-base phyloP 100-vertebrate conservation scores from the UCSC
remote BigWig file and summarises them as a mean score per off-target region.

Scoring rationale:
  phyloP > 2.0  → strong positive selection / high conservation → dangerous
  phyloP ≈ 0    → neutral evolution
  phyloP < 0    → fast evolving / relaxed constraint → lower off-target risk

phyloP BigWig quirk: chromosome names require "chr" prefix (chr1, chrX …).
gnomAD uses no prefix; this module uses the prefix-inclusive names from the
GenomicRegion model directly.
"""

from __future__ import annotations

import pyBigWig
from loguru import logger

from src.core.cache import Cache
from src.core.models import GenomicRegion, PhylopResult

# phyloP score that saturates conservation_score to 1.0
_PHYLOP_SATURATION: float = 4.0
# Neutral score returned when the BigWig has no coverage for a region
_NEUTRAL_MEAN_SCORE: float = 0.0
# Fallback conservation_score when the BigWig URL cannot be opened
_NEUTRAL_CONSERVATION_SCORE: float = 0.5
_PHYLOP_TTL_HOURS: int = 168  # 1 week


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def score_phylop(
    regions: list[GenomicRegion],
    bigwig_url: str,
    # No default: a hardcoded path here meant phylop_fetcher opened the
    # live cache while the rest of the run used the configured one
    # (audit 2026-11-19 — found by watching which file a run touched,
    # not by reading the code).
    cache_db: str,
) -> list[PhylopResult]:
    """Score phyloP conservation for each off-target region via remote BigWig.

    Opens the remote BigWig once and reuses the handle for all regions.
    All scores are cached in SQLite to avoid repeated remote reads.

    Args:
        regions: Genomic intervals to score (hg38, chr-prefixed).
        bigwig_url: URL or local path to phyloP 100-way BigWig file.
        cache_db: Path to the SQLite cache database.

    Returns:
        PhylopResult for every input region (same order as input).
        On BigWig open failure returns neutral results (conservation_score=0.5).
    """
    if not regions:
        return []

    try:
        bw = pyBigWig.open(bigwig_url)
    except Exception as exc:
        logger.error(f"phylop_scorer: cannot open BigWig '{bigwig_url}': {exc}")
        return [
            # A source that could not be read knows nothing. Writing a
            # number here makes an outage indistinguishable from a
            # measurement, and for these channels it is the safe
            # direction (audit 2026-11-19, Bulgu 2/5).
            PhylopResult(region=r, mean_score=None, conservation_score=None)
            for r in regions
        ]

    results: list[PhylopResult] = []
    try:
        with Cache(cache_db) as cache:
            for region in regions:
                result = _score_region(bw, region, cache)
                results.append(result)
                logger.info(
                    f"phylop_scorer: {region} → mean={result.mean_score:.3f}, "
                    f"conservation_score={result.conservation_score:.3f}"
                )
    finally:
        bw.close()

    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _score_region(
    bw: object,
    region: GenomicRegion,
    cache: Cache,
) -> PhylopResult:
    """Retrieve or compute the phyloP result for one region.

    Args:
        bw: Open pyBigWig handle.
        region: Target genomic interval.
        cache: Open SQLite cache instance.

    Returns:
        PhylopResult with raw mean score and normalised conservation_score.
    """
    cache_key = f"phylop:{region.chrom}:{region.start}:{region.end}"
    cached = cache.get(cache_key)
    if cached is not None:
        logger.debug(f"phylop cache HIT: {cache_key}")
        return PhylopResult(
            region=region,
            mean_score=cached["mean_score"],
            conservation_score=cached["conservation_score"],
        )

    raw = _get_conservation_score(bw, region.chrom, region.start, region.end)
    norm = _normalize_phylop(raw)

    cache.set(cache_key, {"mean_score": raw, "conservation_score": norm}, ttl_hours=_PHYLOP_TTL_HOURS)
    return PhylopResult(region=region, mean_score=raw, conservation_score=norm)


def _get_conservation_score(bw: object, chrom: str, start: int, end: int) -> float:
    """Read mean phyloP score for a region from an open BigWig handle.

    Returns _NEUTRAL_MEAN_SCORE (0.0) when the region has no coverage or on
    any runtime error, so downstream normalisation produces a neutral score.

    Args:
        bw: Open pyBigWig handle.
        chrom: Chromosome with "chr" prefix (e.g. "chr1").
        start: 0-based start coordinate.
        end: 0-based end coordinate (exclusive).

    Returns:
        Mean phyloP score as a float (may be negative).
    """
    try:
        stats = bw.stats(chrom, start, end, type="mean")
        value = stats[0] if stats else None
        if value is None:
            logger.debug(f"phylop_scorer: no coverage for {chrom}:{start}-{end}")
            return _NEUTRAL_MEAN_SCORE
        return float(value)
    except Exception as exc:
        logger.warning(f"phylop_scorer: stats failed for {chrom}:{start}-{end}: {exc}")
        return _NEUTRAL_MEAN_SCORE


def _normalize_phylop(raw_score: float) -> float:
    """Normalise a raw phyloP score to [0, 1].

    Piece-wise linear:
      raw < 0              → 0.0  (fast evolving, low risk)
      0 ≤ raw < saturation → raw / saturation
      raw ≥ saturation     → 1.0  (extremely conserved, high risk)

    Saturation point (_PHYLOP_SATURATION) is 4.0, so:
      phyloP = 2 → 0.50  (high conservation per user threshold)
      phyloP = 4 → 1.00

    Args:
        raw_score: Raw mean phyloP value from the BigWig.

    Returns:
        Normalised conservation score in [0.0, 1.0].
    """
    if raw_score < 0.0:
        return 0.0
    return min(raw_score / _PHYLOP_SATURATION, 1.0)
