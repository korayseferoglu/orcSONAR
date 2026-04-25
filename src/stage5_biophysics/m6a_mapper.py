"""m6A site mapper for Stage 5 (orcSONAR) — queries tabix-indexed RMBase BED."""

from __future__ import annotations

from typing import Optional

import pysam
from loguru import logger

from src.core.models import GenomicRegion, M6AResult, M6ASite

# Column indices in the m6A BED file (0-based)
_COL_CHROM = 0
_COL_START = 1
_COL_END = 2
_COL_NAME = 3
_COL_STRAND = 5
_COL_MOD_TYPE = 6
_COL_CELL_LINE = 11
_COL_GENE = 15


def _query_tabix(
    bed_path: str,
    chrom: str,
    start: int,
    end: int,
    cell_line: Optional[str] = None,
) -> list[M6ASite]:
    """Fetch m6A sites from a tabix-indexed BED file for one region.

    Args:
        bed_path:  Path to the gzipped, tabix-indexed BED file.
        chrom:     Chromosome string (must include "chr" prefix for this file).
        start:     0-based start coordinate.
        end:       0-based end coordinate (exclusive).
        cell_line: If given, only return sites whose cell-line column contains
                   this string (case-insensitive partial match).

    Returns:
        List of M6ASite records (may be empty).
    """
    sites: list[M6ASite] = []
    cell_filter = cell_line.lower() if cell_line else None  # empty string → no filter

    try:
        tb = pysam.TabixFile(bed_path)
    except (OSError, ValueError) as exc:
        logger.error("Cannot open tabix file {}: {}", bed_path, exc)
        return sites

    try:
        for row in tb.fetch(chrom, start, end):
            parts = row.split("\t")
            if len(parts) <= _COL_CELL_LINE:
                continue

            if cell_filter:
                row_cell = parts[_COL_CELL_LINE].lower()
                if cell_filter not in row_cell:
                    continue

            try:
                site_start = int(parts[_COL_START])
                site_end = int(parts[_COL_END])
            except ValueError:
                continue

            strand = parts[_COL_STRAND] if len(parts) > _COL_STRAND else "."
            gene = parts[_COL_GENE] if len(parts) > _COL_GENE else ""
            mod_type = parts[_COL_MOD_TYPE] if len(parts) > _COL_MOD_TYPE else "m6A"

            sites.append(
                M6ASite(
                    chrom=parts[_COL_CHROM],
                    start=site_start,
                    end=site_end,
                    strand=strand if strand in ("+", "-") else ".",
                    mod_type=mod_type,
                    cell_line=parts[_COL_CELL_LINE],
                    gene=gene,
                )
            )
    except ValueError as exc:
        # pysam raises ValueError for regions not in the index
        logger.debug("Tabix fetch failed for {}:{}-{}: {}", chrom, start, end, exc)
    finally:
        tb.close()

    return sites


def scan_m6a_sites(
    regions: list[GenomicRegion],
    cell_line: str,
    bed_path: str,
) -> list[M6AResult]:
    """Scan m6A modification sites overlapping a list of genomic regions.

    Args:
        regions:   Genomic intervals to query (hg38, 0-based half-open).
        cell_line: Cell line to filter by (e.g. "HeLa").
        bed_path:  Path to the tabix-indexed m6A BED.gz file.

    Returns:
        One M6AResult per region (in the same order as *regions*).
    """
    results: list[M6AResult] = []

    for region in regions:
        sites = _query_tabix(
            bed_path=bed_path,
            chrom=region.chrom,
            start=region.start,
            end=region.end,
            cell_line=cell_line,
        )

        site_count = len(sites)
        # Density: sites per kb
        region_kb = region.length / 1000.0 if region.length > 0 else 1.0
        density = site_count / region_kb

        # Normalise density to [0, 1] with a soft cap at 10 sites/kb
        m6a_score = min(density / 10.0, 1.0)

        logger.debug(
            "m6A scan {} ({}): {} sites, density={:.2f}/kb",
            region,
            cell_line,
            site_count,
            density,
        )

        results.append(
            M6AResult(
                region=region,
                cell_line=cell_line,
                sites=sites,
                site_count=site_count,
                m6a_score=round(m6a_score, 4),
            )
        )

    return results
