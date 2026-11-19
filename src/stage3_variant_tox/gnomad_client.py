"""gnomAD population genetics client for Stage 3.

Queries the gnomAD v4 GraphQL API to detect common polymorphisms in
off-target genomic regions.  High allele-frequency variants indicate the
region is already variable in the human population, which REDUCES off-target
risk — the saRNA is less likely to disrupt conserved function.

gnomAD quirk: chromosome field uses no "chr" prefix (e.g. "1", not "chr1").
"""

from __future__ import annotations

import threading
import time
from typing import Any

import requests
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.cache import Cache
from src.core.config import OrcSonarConfig
from src.core.models import GenomicRegion, GnomadResult, GnomadVariant
from src.core.site_keys import site_ids_and_regions

# Allele-frequency threshold: variants above this are "common" → polymorphic region
_AF_COMMON_THRESHOLD: float = 0.01
# Cache TTL — gnomAD data is updated infrequently
_GNOMAD_TTL_HOURS: int = 720  # 30 days

# gnomAD enforces a strict rate limit. 1 req/s keeps us well below the cap.
_MIN_REQUEST_INTERVAL_SEC: float = 1.0
# When we hit 429, gnomAD asks us to back off — wait long enough for the bucket to reset.
_RATE_LIMIT_BACKOFF_SEC: float = 30.0

_last_request_time: float = 0.0
_rate_limit_lock = threading.Lock()

# Schema notes (verified against live API on 2026-05-08):
#   - region(...) now requires reference_genome (no longer accepts dataset).
#   - dataset moved to the inner Region.variants(dataset: …) field.
# reference_genome and dataset are GraphQL enums → no quotes around them.
_GRAPHQL_QUERY_TEMPLATE = """
{{
  region(chrom: "{chrom}", start: {start}, stop: {stop}, reference_genome: GRCh38) {{
    variants(dataset: gnomad_r4) {{
      variant_id
      pos
      ref
      alt
      genome {{ af }}
      exome {{ af }}
    }}
  }}
}}
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def query_gnomad(
    regions: list[GenomicRegion],
    config: OrcSonarConfig,
) -> list[GnomadResult]:
    """Query gnomAD v4 for population variants in each off-target region.

    Regions with high-AF common variants receive a low polymorphism_score
    (the region is variable → off-target risk is reduced).  Regions with
    no common variants receive polymorphism_score = 1.0 (conserved → risky).

    Args:
        regions: Genomic intervals to query (hg38, chr-prefixed).
        config: Pipeline config supplying gnomad_api_url and cache_db.

    Returns:
        GnomadResult for every input region (same order as input).
    """
    results: list[GnomadResult] = []
    with Cache(config.data_paths.cache_db) as cache:
        for region in regions:
            result = _query_gnomad_region(region, config, cache)
            results.append(result)
            # A failed query now yields unknowns, and formatting one with
            # `:.4f` raises (audit 2026-11-19, Bulgu 6's shape).
            def _shown(value: float | None, digits: int) -> str:
                return "ÖLÇÜLMEDİ" if value is None else f"{value:.{digits}f}"

            logger.info(
                f"gnomad_client: {region} → {result.variant_count} variant(s), "
                f"max_af={_shown(result.max_af, 4)}, "
                f"polymorphism_score={_shown(result.polymorphism_score, 3)}"
            )
    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _query_gnomad_region(
    region: GenomicRegion,
    config: OrcSonarConfig,
    cache: Cache,
) -> GnomadResult:
    """Fetch gnomAD variants for one region, with cache + retry + graceful fallback.

    Args:
        region: Target genomic interval.
        config: Pipeline config.
        cache: Open SQLite cache instance.

    Returns:
        GnomadResult — neutral (polymorphism_score=0.5) on unrecoverable error.
    """
    cache_key = f"gnomad:{region.chrom}:{region.start}:{region.end}"
    cached = cache.get(cache_key)
    if cached is not None:
        logger.debug(f"gnomad cache HIT: {cache_key}")
        variants = [GnomadVariant(**v) for v in cached["variants"]]
        return _build_result(region, variants)

    try:
        variants = _fetch_variants(region, config.gnomad_api_url)
    except Exception as exc:
        logger.warning(f"gnomad_client: query failed for {region} — returning neutral: {exc}")
        # Neutral score (0.5) on API failure — unknown polymorphism state
        # A source that could not be read knows nothing. Writing a
        # number here makes an outage indistinguishable from a
        # measurement, and for these channels it is the safe
        # direction (audit 2026-11-19, Bulgu 2/5).
        return GnomadResult(
            region=region,
            variants=[],
            variant_count=None,
            max_af=None,
            polymorphism_score=None,
        )

    cache.set(cache_key, {"variants": [v.model_dump() for v in variants]}, ttl_hours=_GNOMAD_TTL_HOURS)
    return _build_result(region, variants)


def _build_result(region: GenomicRegion, variants: list[GnomadVariant]) -> GnomadResult:
    """Construct a GnomadResult from a list of parsed variants.

    Args:
        region: Source genomic region.
        variants: Parsed GnomadVariant list (may be empty).

    Returns:
        GnomadResult with computed max_af and polymorphism_score.
    """
    max_af = max((v.allele_frequency for v in variants), default=0.0)
    score = _calculate_polymorphism_score(variants)
    return GnomadResult(
        region=region,
        variants=variants,
        variant_count=len(variants),
        max_af=max_af,
        polymorphism_score=score,
    )


def _rate_limit_sleep() -> None:
    """Block until at least ``_MIN_REQUEST_INTERVAL_SEC`` has passed since the last call.

    gnomAD aggressively rate-limits the public GraphQL endpoint; pacing requests
    to ~1 Hz keeps us under the threshold and avoids 429 cascades.
    """
    global _last_request_time
    with _rate_limit_lock:
        elapsed = time.monotonic() - _last_request_time
        wait = _MIN_REQUEST_INTERVAL_SEC - elapsed
        if wait > 0:
            time.sleep(wait)
        _last_request_time = time.monotonic()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)
def _fetch_variants(region: GenomicRegion, api_url: str) -> list[GnomadVariant]:
    """POST gnomAD GraphQL query and parse the variant list.

    Args:
        region: Target interval (chr-prefixed; "chr" is stripped for the query).
        api_url: gnomAD GraphQL endpoint URL.

    Returns:
        List of GnomadVariant objects (empty if region has no variants).

    Raises:
        requests.HTTPError: On non-2xx response (triggers tenacity retry).
        requests.RequestException: On network errors (triggers tenacity retry).
        KeyError / ValueError: On unexpected response schema.
    """
    chrom = region.chrom[3:] if region.chrom.startswith("chr") else region.chrom
    query = _graphql_query(chrom, region.start, region.end)
    _rate_limit_sleep()
    resp = requests.post(api_url, json={"query": query}, timeout=60)
    if resp.status_code == 429:
        logger.warning(
            f"gnomad_client: HTTP 429 rate limited at {region}; "
            f"sleeping {_RATE_LIMIT_BACKOFF_SEC:.0f}s before retry"
        )
        time.sleep(_RATE_LIMIT_BACKOFF_SEC)
    resp.raise_for_status()
    data = resp.json()
    if data.get("errors"):
        # GraphQL schema/argument errors come back as 200 with an "errors" array.
        raise RuntimeError(f"gnomAD GraphQL error: {data['errors']}")
    raw_variants = (data.get("data", {}).get("region") or {}).get("variants") or []
    return _parse_variants(raw_variants)


def _graphql_query(chrom: str, start: int, end: int) -> str:
    """Build the gnomAD region GraphQL query string.

    Args:
        chrom: Chromosome without "chr" prefix (e.g. "1", "X").
        start: 0-based start position.
        end: 0-based end position (used as GraphQL ``stop``).

    Returns:
        Formatted GraphQL query string.
    """
    return _GRAPHQL_QUERY_TEMPLATE.format(chrom=chrom, start=start, stop=end)


def _parse_variants(raw: list[dict]) -> list[GnomadVariant]:
    """Parse the gnomAD API variants array into GnomadVariant objects.

    Handles null genome/exome blocks (when a variant was only observed in one
    cohort). Takes the maximum AF across genome and exome cohorts.

    Args:
        raw: List of variant dicts from the gnomAD API response.

    Returns:
        List of GnomadVariant objects (malformed entries are skipped).
    """
    variants: list[GnomadVariant] = []
    for item in raw:
        try:
            genome_block = item.get("genome") or {}
            exome_block = item.get("exome") or {}
            genome_af = float(genome_block.get("af") or 0.0)
            exome_af = float(exome_block.get("af") or 0.0)
            af = max(genome_af, exome_af)
            # Clamp to valid AF range (API occasionally returns tiny negatives)
            af = max(0.0, min(af, 1.0))
            variants.append(
                GnomadVariant(
                    variant_id=item["variant_id"],
                    position=int(item["pos"]),
                    ref=item["ref"],
                    alt=item["alt"],
                    allele_frequency=af,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.debug(f"gnomad_client: skipping malformed variant entry: {exc}")
    return variants


def _calculate_polymorphism_score(variants: list[GnomadVariant]) -> float:
    """Compute normalised polymorphism risk score in [0, 1].

    High AF common variants → the region is already polymorphic → off-target
    risk is LOWER → score approaches 0.  No variants (or all rare) → the region
    is conserved → score = 1.0.

    Score = max(0.0, 1.0 - max_af / AF_COMMON_THRESHOLD)
    Saturates at 0.0 when max_af >= 0.01 (1% population frequency).

    Args:
        variants: GnomadVariant list for the region.

    Returns:
        Polymorphism score in [0.0, 1.0].
    """
    if not variants:
        return 1.0  # no data → assume conserved → high risk
    max_af = max(v.allele_frequency for v in variants)
    return max(0.0, 1.0 - max_af / _AF_COMMON_THRESHOLD)


# ---------------------------------------------------------------------------
# Snakemake run() entry point
# ---------------------------------------------------------------------------


def run(
    offtargets_path: str,
    api_url: str,
    output_path: str,
    log_path: str,
    config_raw: dict[str, Any] | None = None,
) -> None:
    """Query gnomAD for each off-target region and write stage3_gnomad.json."""
    import json
    import sys
    from pathlib import Path as _Path

    _Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(log_path, level="DEBUG")
    logger.add(sys.stderr, level="INFO")

    from src.core.config import config_from_mapping

    offtargets: dict[str, Any] = {}
    try:
        offtargets = json.loads(_Path(offtargets_path).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"gnomad_client.run: cannot load offtargets: {exc}")

    sites: list[dict] = offtargets.get("offtarget_sites", [])
    site_ids, regions = site_ids_and_regions(sites, caller="gnomad_client")

    config = config_from_mapping(config_raw, gnomad_api_url=api_url)
    gnomad_results: dict[str, Any] = {}
    if regions:
        try:
            results = query_gnomad(regions, config)
            for site_id, res in zip(site_ids, results, strict=True):
                gnomad_results[site_id] = res.model_dump()
        except Exception as exc:
            logger.warning(f"gnomad_client.run: query failed: {exc}")

    payload: dict[str, Any] = {"gnomad_results": gnomad_results}
    out = _Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"gnomad_client: scanned {len(regions)} regions → {output_path}")
