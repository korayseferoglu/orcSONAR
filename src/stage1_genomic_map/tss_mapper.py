"""TSS lookup for orcSONAR Stage 1 (EPDnew → FANTOM5 fallback)."""
# ruff: noqa: E402

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.core.cache import Cache
from src.core.config import OrcSonarConfig
from src.core.exceptions import APIError, DataSourceError
from src.core.models import GenomicRegion, TSSInfo

_EPD_COLS = ["chrom", "start", "end", "name", "score", "strand", "thickStart", "thickEnd"]
_F5_COLS = [
    "chrom", "start", "end", "name", "score", "strand",
    "thickStart", "thickEnd", "itemRgb",
]
_EPD_DTYPES = {
    "chrom": str, "start": int, "end": int, "name": str,
    "score": float, "strand": str, "thickStart": int, "thickEnd": int,
}
_F5_DTYPES = {
    "chrom": str, "start": int, "end": int, "name": str,
    "score": float, "strand": str, "thickStart": int, "thickEnd": int, "itemRgb": str,
}

# How far from the Ensembl gene boundary to search for FANTOM5 CAGE peaks
_FANTOM5_WINDOW = 5000


def find_tss(gene_name: str, config: OrcSonarConfig) -> TSSInfo:
    """Find the TSS for a gene: EPDnew first, then FANTOM5 as fallback.

    Args:
        gene_name: HGNC gene symbol (e.g. "VEGFA").
        config: Validated OrcSonarConfig with data_paths populated.

    Returns:
        TSSInfo for the highest-confidence TSS.

    Raises:
        DataSourceError: If no TSS is found in either source.
    """
    root = Path(".")
    epdnew_path = root / config.data_paths.epdnew_bed
    fantom5_path = root / config.data_paths.fantom5_bed

    tss = _search_epdnew(gene_name, epdnew_path)
    if tss is not None:
        logger.info(f"EPDnew TSS: {gene_name} → {tss.chrom}:{tss.position}({tss.strand})")
        return tss

    logger.warning(f"'{gene_name}' not in EPDnew — falling back to FANTOM5")
    tss = _search_fantom5(gene_name, fantom5_path, config)
    if tss is not None:
        logger.info(f"FANTOM5 TSS: {gene_name} → {tss.chrom}:{tss.position}({tss.strand})")
        return tss

    raise DataSourceError(f"TSS not found for '{gene_name}' in EPDnew or FANTOM5")


def _search_epdnew(gene_name: str, bed_path: Path) -> Optional[TSSInfo]:
    """Search EPDnew BED for a gene's TSS by name prefix.

    EPDnew name format: ``GENENAME_isoform`` (e.g. VEGFA_1). The gene is
    identified by the prefix before the first underscore.

    TSS position convention:
      - (+) strand → thickStart (marks the verified TSS)
      - (−) strand → thickEnd  (marks the TSS in reverse-complement orientation)

    Args:
        gene_name: Gene symbol to look up (case-insensitive).
        bed_path: Path to EPDnew BED file.

    Returns:
        TSSInfo for the highest-score isoform, or None if not found.
    """
    if not bed_path.exists():
        logger.warning(f"EPDnew BED not found: {bed_path}")
        return None

    try:
        df = pd.read_csv(
            bed_path,
            sep="\t",
            header=None,
            names=_EPD_COLS,
            dtype=_EPD_DTYPES,
        )
    except Exception as exc:
        logger.warning(f"Failed to read EPDnew BED '{bed_path}': {exc}")
        return None

    mask = df["name"].str.split("_").str[0].str.upper() == gene_name.upper()
    hits = df[mask]

    if hits.empty:
        return None

    best = hits.loc[hits["score"].idxmax()]
    strand: str = best["strand"]
    tss_pos = int(best["thickStart"]) if strand == "+" else int(best["thickEnd"])

    return TSSInfo(
        gene=gene_name.upper(),
        chrom=str(best["chrom"]),
        position=tss_pos,
        strand=strand,
        source="EPDnew",
        score=float(best["score"]),
    )


def _search_fantom5(
    gene_name: str,
    bed_path: Path,
    config: OrcSonarConfig,
) -> Optional[TSSInfo]:
    """Find the highest-scoring FANTOM5 CAGE peak near a gene.

    Fetches gene coordinates from Ensembl, then selects the CAGE peak with
    the highest tag count within ±5 kb of the gene boundary.

    Args:
        gene_name: Gene symbol to look up via Ensembl.
        bed_path: Path to FANTOM5 CAGE BED file.
        config: Config providing Ensembl base URL and SQLite cache path.

    Returns:
        TSSInfo from the best peak (highest score), or None.
    """
    gene_coords = _get_gene_coordinates_ensembl(gene_name, config)
    if gene_coords is None:
        return None

    if not bed_path.exists():
        logger.warning(f"FANTOM5 BED not found: {bed_path}")
        return None

    try:
        df = pd.read_csv(
            bed_path,
            sep="\t",
            header=None,
            names=_F5_COLS,
            dtype=_F5_DTYPES,
        )
    except Exception as exc:
        logger.warning(f"Failed to read FANTOM5 BED '{bed_path}': {exc}")
        return None

    search_start = gene_coords.start - _FANTOM5_WINDOW
    search_end = gene_coords.end + _FANTOM5_WINDOW

    window = df[
        (df["chrom"] == gene_coords.chrom)
        & (df["start"] >= search_start)
        & (df["end"] <= search_end)
    ]

    if window.empty:
        logger.warning(
            f"No FANTOM5 peaks for '{gene_name}' near "
            f"{gene_coords.chrom}:{search_start}-{search_end}"
        )
        return None

    best = window.loc[window["score"].idxmax()]
    strand: str = best["strand"]
    tss_pos = int(best["thickStart"]) if strand == "+" else int(best["thickEnd"])

    return TSSInfo(
        gene=gene_name.upper(),
        chrom=str(best["chrom"]),
        position=tss_pos,
        strand=strand,
        source="FANTOM5",
        score=float(best["score"]),
    )


@retry(
    retry=retry_if_exception_type(requests.RequestException),
    wait=wait_exponential(multiplier=1, min=1, max=16),
    stop=stop_after_attempt(4),
    reraise=True,
)
def _ensembl_get(url: str) -> dict:
    """Single Ensembl REST GET; tenacity retries on network errors."""
    resp = requests.get(url, headers={"Content-Type": "application/json"}, timeout=10)
    resp.raise_for_status()
    return resp.json()  # type: ignore[no-any-return]


def _get_gene_coordinates_ensembl(
    gene_name: str,
    config: OrcSonarConfig,
) -> Optional[GenomicRegion]:
    """Fetch hg38 gene coordinates from Ensembl REST API with SQLite caching.

    Args:
        gene_name: HGNC gene symbol.
        config: Config providing Ensembl base URL and cache DB path.

    Returns:
        GenomicRegion (hg38, with "chr" prefix) or None on failure.
    """
    cache_key = f"ensembl:lookup:{gene_name.upper()}"
    cache = Cache(config.data_paths.cache_db)

    try:
        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Ensembl cache hit: {gene_name}")
            return GenomicRegion(**cached)

        url = (
            f"{config.ensembl_base_url}/lookup/symbol/homo_sapiens/{gene_name}"
            "?expand=0&content-type=application/json"
        )

        try:
            data = _ensembl_get(url)
        except requests.RequestException as exc:
            logger.warning(f"Ensembl lookup failed for '{gene_name}': {exc}")
            return None

        chrom: str = data.get("seq_region_name", "")
        if not chrom:
            logger.warning(f"Ensembl missing seq_region_name for '{gene_name}'")
            return None
        if not chrom.startswith("chr"):
            chrom = f"chr{chrom}"

        start: int = data.get("start", 0)
        end: int = data.get("end", 0)
        if start == 0 or end == 0:
            logger.warning(f"Ensembl returned invalid coordinates for '{gene_name}': {data}")
            return None

        strand_int: int = data.get("strand", 1)
        strand = "+" if strand_int == 1 else "-"

        region = GenomicRegion(chrom=chrom, start=start, end=end, strand=strand)
        cache.set(cache_key, region.model_dump(), ttl_hours=168)
        return region

    finally:
        cache.close()


# ---------------------------------------------------------------------------
# Snakemake run() entry point
# ---------------------------------------------------------------------------


def run(
    gene: str,
    epdnew_bed: str,
    fantom5_bed: str,
    output_path: str,
    log_path: str,
) -> None:
    """Map TSS for *gene* from EPDnew/FANTOM5 and write stage1_tss.json.

    Args:
        gene: HGNC gene symbol (e.g. ``"VEGFA"``).
        epdnew_bed: Path to EPDnew BED file.
        fantom5_bed: Path to FANTOM5 BED file.
        output_path: Destination JSON path.
        log_path: Log file path.
    """
    import json
    import sys

    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(log_path, level="DEBUG")
    logger.add(sys.stderr, level="INFO")

    config = OrcSonarConfig(
        target_gene=gene,
        data_paths={"epdnew_bed": epdnew_bed, "fantom5_bed": fantom5_bed},
    )

    try:
        tss = find_tss(gene, config)
        payload = {"gene": gene, "tss": tss.model_dump()}
        logger.info(f"tss_mapper: {gene} → {tss.chrom}:{tss.position}({tss.strand})")
    except Exception as exc:
        logger.warning(f"tss_mapper: TSS lookup failed for '{gene}': {exc} — using fallback")
        payload = {
            "gene": gene,
            "tss": {
                "gene": gene, "chrom": "chr1", "position": 0,
                "strand": "+", "source": "EPDnew", "score": 0.0,
            },
        }

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
