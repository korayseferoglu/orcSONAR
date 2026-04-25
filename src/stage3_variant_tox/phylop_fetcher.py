"""Snakemake run() adapter for Stage 3 phyloP conservation scoring."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from src.stage3_variant_tox.phylop_scorer import score_phylop
from src.core.models import GenomicRegion


def run(
    offtargets_path: str,
    bigwig_url: str,
    output_path: str,
    log_path: str,
) -> None:
    """Score phyloP conservation for off-target regions and write stage3_phylop.json.

    Args:
        offtargets_path: Path to stage2_offtargets.json.
        bigwig_url: URL to UCSC phyloP100way remote BigWig.
        output_path: Destination JSON path.
        log_path: Log file path.
    """
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(log_path, level="DEBUG")
    logger.add(sys.stderr, level="INFO")

    offtargets: dict[str, Any] = {}
    try:
        offtargets = json.loads(Path(offtargets_path).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"phylop_fetcher: cannot load offtargets: {exc}")

    sites: list[dict] = offtargets.get("offtarget_sites", [])
    regions: list[GenomicRegion] = []
    site_ids: list[str] = []
    for s in sites:
        try:
            regions.append(GenomicRegion(**s["region"]))
            site_ids.append(f"{s['gene']}:{s['transcript_id']}")
        except Exception:
            pass

    phylop_results: dict[str, Any] = {}
    if regions:
        try:
            results = score_phylop(regions, bigwig_url)
            for site_id, res in zip(site_ids, results):
                phylop_results[site_id] = res.model_dump()
        except Exception as exc:
            logger.warning(f"phylop_fetcher: scoring failed: {exc} — using neutral")
            for site_id, region in zip(site_ids, regions):
                phylop_results[site_id] = {
                    "region": region.model_dump(),
                    "mean_score": 0.0,
                    "conservation_score": 0.5,
                }

    payload: dict[str, Any] = {"phylop_results": phylop_results}
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"phylop_fetcher: scored {len(regions)} regions → {output_path}")
