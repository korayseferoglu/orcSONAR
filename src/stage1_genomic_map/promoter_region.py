"""Promoter window definition for orcSONAR Stage 1."""

from __future__ import annotations

from src.core.models import GenomicRegion, TSSInfo


def define_promoter(
    tss: TSSInfo,
    upstream: int = 1000,
    downstream: int = 200,
) -> GenomicRegion:
    """Define the promoter window around a TSS.

    The window is strand-aware:
      - (+) strand: [TSS − upstream, TSS + downstream]
      - (−) strand: [TSS − downstream, TSS + upstream]

    The returned start coordinate is clamped to 0 to avoid negative positions.

    Args:
        tss: TSS anchor point (from EPDnew or FANTOM5).
        upstream: Bases upstream of the TSS to include (default 1000).
        downstream: Bases downstream of the TSS to include (default 200).

    Returns:
        GenomicRegion representing the promoter window (start < end).
    """
    pos = tss.position

    if tss.strand == "+":
        start = max(0, pos - upstream)
        end = pos + downstream
    else:
        start = max(0, pos - downstream)
        end = pos + upstream

    return GenomicRegion(
        chrom=tss.chrom,
        start=start,
        end=end,
        strand=tss.strand,
    )
