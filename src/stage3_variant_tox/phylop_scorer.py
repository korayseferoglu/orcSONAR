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

from typing import Any

import pyBigWig
from loguru import logger

from src.core.cache import Cache
from src.core.models import GenomicRegion, PhylopResult

# phyloP score that saturates conservation_score to 1.0
_PHYLOP_SATURATION: float = 4.0
# ⚠️ Roadmap R14 removed `_NEUTRAL_MEAN_SCORE = 0.0`. It was returned both when
# the BigWig had no value for a window and when the read raised, and 0.0
# normalises to `conservation_score = 0.0` — the LOWEST risk this channel can
# report. So a window the file does not cover looked maximally unconserved,
# which is invariant 2's prohibition on the success path rather than the
# failure path (`R7` fixed this module's failure path and did not see this).
#
# What made the sentinel undetectable is specific to phyloP. UCSC's hg38
# cons100way track description states that "Both phastCons and phyloP treat
# alignment gaps and unaligned nucleotides as missing data", and that "the
# absolute values of the scores represent -log p-values under a null
# hypothesis of neutral evolution". A phyloP of 0 is therefore a *measurement*
# — p = 1, no detectable departure from neutrality — so writing 0.0 for
# "unmeasured" produced a value nobody could tell from a real result. That is
# worse than a score-space 0.5, which at least has no measured counterpart.
#
# ⚠️ The constant below is DEAD — declared here and read nowhere (`git grep`
# finds only this definition). `R7` made the open-failure path return
# `None`/`None` and left it behind. It is kept rather than deleted for the same
# reason invariant 2 keeps the equivalent dead sentinel in `epigenetic_merger`:
# the constant is that invariant's own evidence, and deleting the evidence
# would make the record thinner than the finding. See
# `.claude/rules/00-degismezler.md`, invariant 2, which is the authority on the
# fallback sentinel — this comment does not restate its value. The `R14` gate
# asserts the constant stays unread, so it cannot quietly come back into use.
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
                # ⚠️ These were `:.3f` and would raise TypeError the moment
                # either became None, which `R14` made possible.
                mean_text = (
                    "UNKNOWN" if result.mean_score is None
                    else f"{result.mean_score:.3f}"
                )
                norm_text = (
                    "UNKNOWN" if result.conservation_score is None
                    else f"{result.conservation_score:.3f}"
                )
                logger.info(
                    f"phylop_scorer: {region} → mean={mean_text}, "
                    f"conservation_score={norm_text}, "
                    f"covered={result.covered_fraction}"
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

    raw, covered = _get_conservation_score(
        bw, region.chrom, region.start, region.end
    )
    norm = _normalize_phylop(raw) if raw is not None else None

    # An unknown is not cached. Caching it would make one bad read outlive the
    # condition that caused it, for a week (invariant 2, as settled in `B2`).
    if raw is not None:
        cache.set(
            cache_key,
            {
                "mean_score": raw,
                "conservation_score": norm,
                "covered_fraction": covered,
            },
            ttl_hours=_PHYLOP_TTL_HOURS,
        )
    return PhylopResult(
        region=region,
        mean_score=raw,
        conservation_score=norm,
        covered_fraction=covered,
    )


def _get_conservation_score(
    bw: Any, chrom: str, start: int, end: int
) -> tuple[float | None, float | None]:
    """Read the mean phyloP score for a region, and how much of it was covered.

    Roadmap `R14`. Three outcomes, and keeping them apart is the whole point:

    * **a measurement** — a mean (which may be ``0.0`` or negative) together
      with the fraction of the window the alignment covers;
    * **outside the alignment** — ``(None, 0.0)``. The file omits unaligned
      positions, so conservation is not assessable here. It is *not* neutral,
      and reporting ``0.0`` would have claimed the strongest possible
      "unconserved" verdict from no data at all;
    * **a failed read** — ``(None, None)``. Measured against the live file:
      a chromosome name missing its ``chr`` prefix raises
      ``RuntimeError: Invalid interval bounds!``, and so does an interval past
      the end of a contig — which is where `Bulgu-8`'s splice-blind
      coordinates land. Neither knows anything, not even the coverage.

    Note that this differs from `encode_reader._bigwig_mean` on purpose. There,
    "contig present but no intervals here" is a real zero: the assay covered
    the locus and recorded nothing. A phyloP file has no such case — a position
    either has an alignment column and a score, or neither.

    Args:
        bw: Open pyBigWig handle.
        chrom: Chromosome with "chr" prefix (e.g. "chr1").
        start: 0-based start coordinate.
        end: 0-based end coordinate (exclusive).

    Returns:
        ``(mean_phylop, covered_fraction)``; see above for the three cases.
    """
    try:
        stats = bw.stats(chrom, start, end, type="mean")
        value = stats[0] if stats else None
        if value is None:
            logger.warning(
                f"phylop_scorer: {chrom}:{start}-{end} has no phyloP value — "
                f"the 100-way alignment does not cover it, so conservation is "
                f"UNKNOWN here, not neutral. Reporting 0.0 would be the "
                f"lowest risk this channel can express (roadmap R14)."
            )
            return None, 0.0
        covered = _covered_fraction(bw, chrom, start, end)
        return float(value), covered
    except Exception as exc:
        logger.warning(
            f"phylop_scorer: stats failed for {chrom}:{start}-{end}: {exc} — "
            f"UNKNOWN, not zero. A missing 'chr' prefix and a span running "
            f"past the end of a contig both arrive here (roadmap R14)."
        )
        return None, None


def _covered_fraction(
    bw: Any, chrom: str, start: int, end: int
) -> float | None:
    """What fraction of ``[start, end)`` the alignment covers, if readable.

    Args:
        bw: Open pyBigWig handle.
        chrom: Chromosome with "chr" prefix.
        start: 0-based start coordinate.
        end: 0-based end coordinate (exclusive).

    Returns:
        The fraction in ``[0, 1]``, or ``None`` if coverage is unreadable —
        in which case the mean itself is still a measurement, only its extent
        is unknown.
    """
    try:
        stats = bw.stats(chrom, start, end, type="coverage")
    except Exception as exc:  # noqa: BLE001 - coverage is secondary to the mean
        logger.debug(f"phylop_scorer: coverage unreadable for {chrom}:{start}-{end}: {exc}")
        return None
    value = stats[0] if stats else None
    if value is None:
        # A readable mean with no coverage figure should not happen; if it
        # does, the extent is unknown rather than assumed complete.
        return None
    return float(value)


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
