"""Aligned extraction of site ids and regions from a stage-2 off-target list.

Thirteen stage adapters share one shape: walk ``offtarget_sites``, collect a
``GenomicRegion`` per site and its id, hand the regions to a bulk reader, then
``zip`` the ids back onto the results. That shape has a trap — if the two lists
are appended independently and one append fails, they desync by one and every
measurement is paired with the *next* site's id. Nothing raises; every score
stays in range; all sites are mislabelled.

Collecting both here, atomically, removes thirteen chances to reintroduce it.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from src.core.models import GenomicRegion


def site_ids_and_regions(
    sites: list[dict[str, Any]],
    *,
    caller: str,
) -> tuple[list[str], list[GenomicRegion]]:
    """Extract ``(site_ids, regions)`` from stage-2 sites, index-aligned.

    A site is taken only when both its id and its region parse; otherwise it is
    skipped whole, so the two lists always describe the same sites in the same
    order and ``zip(site_ids, results, strict=True)`` cannot mispair.

    Args:
        sites: ``offtarget_sites`` as loaded from a stage-2 JSON file.
        caller: module name, used in the warning when a site is skipped.

    Returns:
        Two lists of equal length: canonical site ids, and their regions.
    """
    site_ids: list[str] = []
    regions: list[GenomicRegion] = []
    skipped = 0

    for site in sites:
        try:
            # Mint the key BEFORE the region: appending only after both succeed
            # is what keeps the lists aligned.
            key = site["site_id"]
            region = GenomicRegion(**site["region"])
        except Exception:
            skipped += 1
            continue
        site_ids.append(key)
        regions.append(region)

    if skipped:
        logger.warning(
            f"{caller}: skipped {skipped} of {len(sites)} site(s) with an unusable "
            f"site_id or region"
        )

    return site_ids, regions
