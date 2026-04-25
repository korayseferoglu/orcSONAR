"""UCSC RepeatMasker-based repeat element scanner for Stage 2.

Queries the UCSC rmsk track via REST API to detect Alu, LINE-1, and other
repeat elements overlapping off-target genomic regions.

ADAR risk rationale:
  - Alu inverted repeats form dsRNA → ~90% of ADAR A-to-I editing occurs in Alu elements
  - LINE-1 elements carry transposition / insertional mutagenesis risk
"""

from __future__ import annotations

import requests
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.cache import Cache
from src.core.config import OrcSonarConfig
from src.core.models import GenomicRegion, RepeatEntry, RepeatResult

_ALU_FAMILIES: frozenset[str] = frozenset({"Alu"})
_LINE_CLASSES: frozenset[str] = frozenset({"LINE"})

_ADAR_SCORE_ALU = 0.8
_ADAR_SCORE_LINE = 0.3


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_repeats(
    regions: list[GenomicRegion],
    config: OrcSonarConfig,
) -> list[RepeatResult]:
    """Query UCSC rmsk track for repeat elements in each off-target region.

    Args:
        regions: Genomic intervals to scan (hg38, chr-prefixed).
        config: Pipeline config (ucsc_api_url, data_paths.cache_db).

    Returns:
        RepeatResult for every input region (same order as input).
    """
    results: list[RepeatResult] = []
    with Cache(config.data_paths.cache_db) as cache:
        for region in regions:
            entries = _query_ucsc_rmsk(region, config, cache)
            has_alu, has_line, score = _classify_risk(entries)
            results.append(
                RepeatResult(
                    region=region,
                    repeats=entries,
                    has_alu=has_alu,
                    has_line=has_line,
                    adar_risk_score=score,
                )
            )
            logger.info(
                f"repeat_scanner: {region} → {len(entries)} repeat(s), "
                f"alu={has_alu}, line={has_line}, adar_risk={score:.2f}"
            )
    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _query_ucsc_rmsk(
    region: GenomicRegion,
    config: OrcSonarConfig,
    cache: Cache,
) -> list[RepeatEntry]:
    """Fetch RepeatMasker annotations for one region, with cache + retry.

    On any unrecoverable API failure the function logs a warning and returns
    an empty list (graceful degradation per pipeline policy).

    Args:
        region: Genomic interval (chr-prefixed chrom expected).
        config: Pipeline config supplying ucsc_api_url.
        cache: Open SQLite cache instance.

    Returns:
        List of RepeatEntry objects (may be empty).
    """
    cache_key = f"rmsk:{region.chrom}:{region.start}:{region.end}"
    cached = cache.get(cache_key)
    if cached is not None:
        logger.debug(f"repeat_scanner cache HIT: {cache_key}")
        return [RepeatEntry(**e) for e in cached["entries"]]

    try:
        entries = _fetch_rmsk(region, config.ucsc_api_url)
    except Exception as exc:
        logger.warning(
            f"UCSC rmsk query failed for {region} — falling back to empty repeat list: {exc}"
        )
        entries = []

    cache.set(cache_key, {"entries": [e.model_dump() for e in entries]})
    return entries


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _fetch_rmsk(region: GenomicRegion, base_url: str) -> list[RepeatEntry]:
    """HTTP call to UCSC getData/track endpoint, retried up to 3 times.

    Args:
        region: Target interval.
        base_url: UCSC getData/track base URL (from config).

    Returns:
        Parsed list of RepeatEntry objects.

    Raises:
        requests.HTTPError: On non-2xx response (triggers tenacity retry).
        requests.RequestException: On network errors (triggers tenacity retry).
    """
    params = {
        "genome": "hg38",
        "track": "rmsk",
        "chrom": region.chrom,
        "start": region.start,
        "end": region.end,
    }
    resp = requests.get(base_url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    entries: list[RepeatEntry] = []
    for item in data.get("rmsk", []):
        entries.append(
            RepeatEntry(
                chrom=item["genoName"],
                start=item["genoStart"],
                end=item["genoEnd"],
                rep_name=item["repName"],
                rep_class=item["repClass"],
                rep_family=item["repFamily"],
            )
        )
    logger.debug(f"UCSC rmsk: {region} → {len(entries)} element(s)")
    return entries


def _classify_risk(entries: list[RepeatEntry]) -> tuple[bool, bool, float]:
    """Compute Alu/LINE presence flags and ADAR risk score.

    Score components:
      Alu (repFamily == "Alu")  → +0.8  (dominant ADAR editing substrate)
      LINE (repClass == "LINE") → +0.3  (transposition / dsRNA risk)
      Combined score is capped at 1.0.

    Args:
        entries: RepeatMasker entries for a genomic region.

    Returns:
        Tuple of (has_alu, has_line, adar_risk_score).
    """
    has_alu = any(e.rep_family in _ALU_FAMILIES for e in entries)
    has_line = any(e.rep_class in _LINE_CLASSES for e in entries)

    score = 0.0
    if has_alu:
        score += _ADAR_SCORE_ALU
    if has_line:
        score += _ADAR_SCORE_LINE
    score = min(score, 1.0)

    return has_alu, has_line, score


# ---------------------------------------------------------------------------
# Snakemake run() entry point
# ---------------------------------------------------------------------------


def run(
    seed_hits_path: str,
    ucsc_api_url: str,
    output_path: str,
    log_path: str,
) -> None:
    """Scan RepeatMasker for off-target regions and write stage2_repeats.json."""
    import json
    import sys
    from pathlib import Path as _Path
    from typing import Any

    _Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(log_path, level="DEBUG")
    logger.add(sys.stderr, level="INFO")

    seed_data: dict[str, Any] = {}
    try:
        seed_data = json.loads(_Path(seed_hits_path).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"repeat_scanner: cannot load seed hits: {exc}")

    sites: list[dict] = seed_data.get("sites", [])

    from src.core.config import OrcSonarConfig
    from src.core.models import GenomicRegion

    config = OrcSonarConfig(ucsc_api_url=ucsc_api_url)

    regions: list[GenomicRegion] = []
    site_ids: list[str] = []
    for s in sites:
        try:
            regions.append(GenomicRegion(**s["region"]))
            site_ids.append(f"{s['gene']}:{s['transcript_id']}")
        except Exception:
            pass

    repeat_results: dict[str, Any] = {}
    if regions:
        try:
            results = scan_repeats(regions, config)
            for site_id, res in zip(site_ids, results):
                repeat_results[site_id] = res.model_dump()
        except Exception as exc:
            logger.warning(f"repeat_scanner: scan_repeats failed: {exc}")

    payload: dict[str, Any] = {"repeat_results": repeat_results}
    out = _Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info(f"repeat_scanner: scanned {len(regions)} regions")
