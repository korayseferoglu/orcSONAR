"""COSMIC cancer mutation scanner for Stage 3.

Queries the local tabix-indexed COSMIC VCF (GRCh38, v103) to detect cancer
mutations overlapping off-target genomic regions identified by Stage 2.

COSMIC VCF quirk: chromosome column has NO "chr" prefix (e.g. "1", not "chr1").
"""

from __future__ import annotations

from typing import Optional

import pysam
from loguru import logger

from src.core.models import CosmicMutation, CosmicResult, GenomicRegion

# mutations/kb that maps to density_score == 1.0
_DENSITY_SATURATION_PER_KB: float = 10.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_cosmic(
    regions: list[GenomicRegion],
    vcf_path: str,
) -> list[CosmicResult]:
    """Scan COSMIC VCF for cancer mutations overlapping each off-target region.

    Args:
        regions: Genomic intervals to scan (hg38, chr-prefixed).
        vcf_path: Path to tabix-indexed COSMIC VCF.gz file.

    Returns:
        CosmicResult for every input region (same order as input).
        On VCF open failure, returns neutral results (0 mutations) for all regions.
    """
    try:
        tbx = pysam.TabixFile(vcf_path)
    except Exception as exc:
        logger.error(f"cosmic_scanner: failed to open VCF '{vcf_path}': {exc}")
        return [
            CosmicResult(region=r, mutations=[], mutation_count=0, has_tier1_gene=False, density_score=0.0)
            for r in regions
        ]

    results: list[CosmicResult] = []
    try:
        for region in regions:
            mutations = _fetch_mutations(tbx, region)
            has_tier1 = any(m.tier == 1 for m in mutations)
            density = _calculate_mutation_density(mutations, region.length)
            results.append(
                CosmicResult(
                    region=region,
                    mutations=mutations,
                    mutation_count=len(mutations),
                    has_tier1_gene=has_tier1,
                    density_score=density,
                )
            )
            logger.info(
                f"cosmic_scanner: {region} → {len(mutations)} mutation(s), "
                f"tier1={has_tier1}, density={density:.3f}"
            )
    finally:
        tbx.close()

    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fetch_mutations(tbx: pysam.TabixFile, region: GenomicRegion) -> list[CosmicMutation]:
    """Fetch and parse COSMIC mutations for one genomic region.

    Args:
        tbx: Open pysam.TabixFile handle.
        region: Target genomic interval (chr-prefixed chrom).

    Returns:
        List of CosmicMutation objects (empty on index miss or parse error).
    """
    # COSMIC VCF has no "chr" prefix — strip it before tabix lookup
    chrom = region.chrom[3:] if region.chrom.startswith("chr") else region.chrom
    mutations: list[CosmicMutation] = []
    try:
        for record in tbx.fetch(chrom, region.start, region.end):
            mut = _parse_vcf_record(record)
            if mut is not None:
                mutations.append(mut)
    except ValueError as exc:
        # pysam raises ValueError when the contig is absent from the tabix index
        logger.warning(f"cosmic_scanner: contig not found for {region}: {exc}")
    return mutations


def _parse_vcf_record(record: str) -> Optional[CosmicMutation]:
    """Parse one VCF tab-delimited line into a CosmicMutation.

    VCF columns: chrom, pos, id, ref, alt, qual, filter, info

    Args:
        record: Raw VCF record string (tab-separated, no newline).

    Returns:
        CosmicMutation, or None if the record is malformed.
    """
    cols = record.split("\t")
    if len(cols) < 8:
        logger.debug(f"cosmic_scanner: malformed record (< 8 cols): {record[:100]}")
        return None

    try:
        position = int(cols[1])
    except ValueError:
        logger.debug(f"cosmic_scanner: non-integer POS: {cols[1]!r}")
        return None

    ref = cols[3]
    alt = cols[4]
    info = _parse_info(cols[7])

    gene = info.get("GENE", "")
    so_term = info.get("SO_TERM", "")

    tier: Optional[int] = None
    tier_str = info.get("TIER", "")
    if tier_str in ("1", "2"):
        tier = int(tier_str)

    try:
        sample_count = int(info.get("GENOME_SCREEN_SAMPLE_COUNT", "0"))
    except ValueError:
        sample_count = 0

    return CosmicMutation(
        position=position,
        ref=ref,
        alt=alt,
        gene=gene,
        so_term=so_term,
        sample_count=sample_count,
        tier=tier,
    )


def _parse_info(info_str: str) -> dict[str, str]:
    """Parse a VCF INFO field string into a key→value dict.

    Args:
        info_str: Semicolon-separated ``key=value`` pairs.

    Returns:
        Dict mapping INFO keys to their string values.
    """
    result: dict[str, str] = {}
    for field in info_str.split(";"):
        if "=" in field:
            key, _, value = field.partition("=")
            result[key] = value
    return result


def _calculate_mutation_density(mutations: list[CosmicMutation], region_length: int) -> float:
    """Compute normalised mutation density in [0, 1].

    Density = mutations per kb, saturating to 1.0 at _DENSITY_SATURATION_PER_KB.

    Args:
        mutations: Mutations found in the region.
        region_length: Region length in base pairs.

    Returns:
        Normalised density score in [0.0, 1.0].
    """
    if region_length <= 0 or not mutations:
        return 0.0
    density_per_kb = len(mutations) / (region_length / 1000.0)
    return min(density_per_kb / _DENSITY_SATURATION_PER_KB, 1.0)


# ---------------------------------------------------------------------------
# Snakemake run() entry point
# ---------------------------------------------------------------------------


def run(
    offtargets_path: str,
    cosmic_vcf: str,
    output_path: str,
    log_path: str,
) -> None:
    """Scan COSMIC VCF for each off-target region and write stage3_cosmic.json."""
    import json
    import sys
    from pathlib import Path as _Path
    from typing import Any

    _Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(log_path, level="DEBUG")
    logger.add(sys.stderr, level="INFO")

    from src.core.models import GenomicRegion

    offtargets: dict[str, Any] = {}
    try:
        offtargets = json.loads(_Path(offtargets_path).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"cosmic_scanner.run: cannot load offtargets: {exc}")

    sites: list[dict] = offtargets.get("offtarget_sites", [])
    regions: list[GenomicRegion] = []
    site_ids: list[str] = []
    for s in sites:
        try:
            regions.append(GenomicRegion(**s["region"]))
            site_ids.append(f"{s['gene']}:{s['transcript_id']}")
        except Exception:
            pass

    cosmic_results: dict[str, Any] = {}
    if regions:
        try:
            results = scan_cosmic(regions, cosmic_vcf)
            for site_id, res in zip(site_ids, results):
                cosmic_results[site_id] = res.model_dump()
        except Exception as exc:
            logger.warning(f"cosmic_scanner.run: scan failed: {exc}")

    payload: dict[str, Any] = {"cosmic_results": cosmic_results}
    out = _Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"cosmic_scanner: scanned {len(regions)} regions → {output_path}")
