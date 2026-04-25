"""NCBI ClinVar pathogenic variant checker for Stage 3.

Uses NCBI E-utilities (esearch + esummary) to find clinically significant
variants overlapping off-target genomic regions.

Rate limit: 3 req/s without API key, 10 req/s with NCBI_API_KEY env var.
All results are cached in SQLite (30-day TTL) to stay well within limits.
"""

from __future__ import annotations

import requests
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.cache import Cache
from src.core.config import OrcSonarConfig
from src.core.models import ClinvarResult, ClinvarVariant, GenomicRegion

_RETMODE = "json"
_RETMAX = "100"
_CLINVAR_TTL_HOURS = 720  # 30 days — ClinVar data changes rarely


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_clinvar(
    regions: list[GenomicRegion],
    config: OrcSonarConfig,
) -> list[ClinvarResult]:
    """Query NCBI ClinVar for pathogenic variants in each off-target region.

    Args:
        regions: Genomic intervals to check (hg38, chr-prefixed).
        config: Pipeline config supplying ncbi_eutils_url and cache_db.

    Returns:
        ClinvarResult for every input region (same order as input).
    """
    results: list[ClinvarResult] = []
    with Cache(config.data_paths.cache_db) as cache:
        for region in regions:
            variants = _search_clinvar_region(region, config, cache)
            pathogenic = sum(
                1
                for v in variants
                if "pathogenic" in v.significance.lower()
                and "likely" not in v.significance.lower()
            )
            likely_path = sum(
                1 for v in variants if "likely pathogenic" in v.significance.lower()
            )
            results.append(
                ClinvarResult(
                    region=region,
                    pathogenic_count=pathogenic,
                    likely_pathogenic_count=likely_path,
                    variants=variants,
                )
            )
            logger.info(
                f"clinvar_client: {region} → {len(variants)} variant(s), "
                f"pathogenic={pathogenic}, likely_pathogenic={likely_path}"
            )
    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _search_clinvar_region(
    region: GenomicRegion,
    config: OrcSonarConfig,
    cache: Cache,
) -> list[ClinvarVariant]:
    """E-search then E-summary for pathogenic variants in one region.

    On any unrecoverable API error, logs a warning and returns [] (graceful
    degradation per pipeline policy).

    Args:
        region: Target genomic interval.
        config: Pipeline config.
        cache: Open SQLite cache instance.

    Returns:
        List of ClinvarVariant objects (may be empty).
    """
    cache_key = f"clinvar:{region.chrom}:{region.start}:{region.end}"
    cached = cache.get(cache_key)
    if cached is not None:
        logger.debug(f"clinvar cache HIT: {cache_key}")
        return [ClinvarVariant(**v) for v in cached["variants"]]

    try:
        uids = _esearch(region, config.ncbi_eutils_url)
        variants: list[ClinvarVariant] = _esummary(uids, config.ncbi_eutils_url) if uids else []
    except Exception as exc:
        logger.warning(f"clinvar_client: query failed for {region} — returning empty: {exc}")
        variants = []

    cache.set(cache_key, {"variants": [v.model_dump() for v in variants]}, ttl_hours=_CLINVAR_TTL_HOURS)
    return variants


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=20),
    reraise=True,
)
def _esearch(region: GenomicRegion, base_url: str) -> list[str]:
    """Call ClinVar esearch to find variant UIDs for a genomic region.

    Searches for pathogenic variants using chromosome + position range terms.

    Args:
        region: Genomic region (chr-prefixed chrom).
        base_url: NCBI E-utilities base URL (e.g. https://eutils.ncbi.nlm.nih.gov/entrez/eutils/).

    Returns:
        List of ClinVar UID strings (may be empty).

    Raises:
        requests.HTTPError: On non-2xx response (triggers tenacity retry).
        requests.RequestException: On network errors (triggers tenacity retry).
    """
    # ClinVar CHR field uses no "chr" prefix
    chrom = region.chrom[3:] if region.chrom.startswith("chr") else region.chrom
    term = (
        f"{chrom}[CHR]+AND+"
        f"{region.start}:{region.end}[CHRPOS]+AND+"
        "clinsig_pathogenic[prop]"
    )
    params = {
        "db": "clinvar",
        "term": term,
        "retmode": _RETMODE,
        "retmax": _RETMAX,
    }
    resp = requests.get(f"{base_url}esearch.fcgi", params=params, timeout=30)
    resp.raise_for_status()
    uids: list[str] = resp.json().get("esearchresult", {}).get("idlist", [])
    logger.debug(f"clinvar esearch: {region} → {len(uids)} UID(s)")
    return uids


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=20),
    reraise=True,
)
def _esummary(uids: list[str], base_url: str) -> list[ClinvarVariant]:
    """Fetch ClinVar document summaries for a list of UIDs.

    Args:
        uids: ClinVar variant UIDs from esearch.
        base_url: NCBI E-utilities base URL.

    Returns:
        List of parsed ClinvarVariant objects.

    Raises:
        requests.HTTPError: On non-2xx response (triggers tenacity retry).
        requests.RequestException: On network errors (triggers tenacity retry).
    """
    params = {
        "db": "clinvar",
        "id": ",".join(uids),
        "retmode": _RETMODE,
    }
    resp = requests.get(f"{base_url}esummary.fcgi", params=params, timeout=30)
    resp.raise_for_status()
    result_block = resp.json().get("result", {})
    uid_list: list[str] = result_block.get("uids", uids)

    variants: list[ClinvarVariant] = []
    for uid in uid_list:
        entry = result_block.get(uid, {})
        variant = _parse_esummary_entry(uid, entry)
        if variant is not None:
            variants.append(variant)
    return variants


def _parse_esummary_entry(uid: str, entry: dict) -> ClinvarVariant | None:
    """Extract ClinvarVariant fields from one esummary result entry.

    Args:
        uid: ClinVar variant UID.
        entry: Dict from the esummary result block for this uid.

    Returns:
        ClinvarVariant, or None if entry is empty or malformed.
    """
    if not entry:
        return None

    # Clinical significance — try germline_classification first (newer API), then legacy field
    germline = entry.get("germline_classification", {})
    significance = germline.get("description") or entry.get("clinical_significance", {}).get(
        "description", "unknown"
    )

    # Gene symbol — first gene in the list
    genes = entry.get("genes", [])
    gene = genes[0].get("symbol", "") if genes else ""

    # Condition name — first trait in first trait_set; fall back to title
    trait_set = entry.get("trait_set", [])
    condition = ""
    if trait_set:
        traits = trait_set[0].get("trait", [])
        condition = traits[0].get("trait_name", "") if traits else ""
    if not condition:
        condition = entry.get("title", "")

    # Genomic position — first GRCh38 location in variation_set
    position: int | None = None
    variation_set = entry.get("variation_set", [])
    if variation_set:
        for loc in variation_set[0].get("variation_loc", []):
            if loc.get("assembly_name", "") == "GRCh38":
                try:
                    position = int(loc.get("start", 0))
                except (ValueError, TypeError):
                    pass
                break

    return ClinvarVariant(
        uid=uid,
        position=position,
        significance=significance,
        condition=condition,
        gene=gene,
    )


# ---------------------------------------------------------------------------
# Snakemake run() entry point
# ---------------------------------------------------------------------------


def run(
    offtargets_path: str,
    ncbi_url: str,
    output_path: str,
    log_path: str,
) -> None:
    """Check ClinVar for each off-target region and write stage3_clinvar.json."""
    import json
    import sys
    from pathlib import Path as _Path
    from typing import Any

    _Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(log_path, level="DEBUG")
    logger.add(sys.stderr, level="INFO")

    from src.core.config import OrcSonarConfig
    from src.core.models import GenomicRegion

    offtargets: dict[str, Any] = {}
    try:
        offtargets = json.loads(_Path(offtargets_path).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"clinvar_client.run: cannot load offtargets: {exc}")

    sites: list[dict] = offtargets.get("offtarget_sites", [])
    regions: list[GenomicRegion] = []
    site_ids: list[str] = []
    for s in sites:
        try:
            regions.append(GenomicRegion(**s["region"]))
            site_ids.append(f"{s['gene']}:{s['transcript_id']}")
        except Exception:
            pass

    config = OrcSonarConfig(ncbi_eutils_url=ncbi_url)
    clinvar_results: dict[str, Any] = {}
    if regions:
        try:
            results = check_clinvar(regions, config)
            for site_id, res in zip(site_ids, results):
                clinvar_results[site_id] = res.model_dump()
        except Exception as exc:
            logger.warning(f"clinvar_client.run: query failed: {exc}")

    payload: dict[str, Any] = {"clinvar_results": clinvar_results}
    out = _Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"clinvar_client: scanned {len(regions)} regions → {output_path}")
