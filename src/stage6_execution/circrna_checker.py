"""Snakemake run() adapter for Stage 6 circRNA sponge overlap check."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from src.core.site_keys import site_ids_and_regions
from src.stage6_execution.circrna_sponge import check_circrna_overlap


def run(
    offtargets_path: str,
    circrna_dir: str,
    output_path: str,
    log_path: str,
) -> None:
    """Check circRNA sponge overlap for off-target regions and write stage6_circrna.json.

    Falls back to data_available=False if no circRNA BED file is found in *circrna_dir*.

    Args:
        offtargets_path: Path to stage2_offtargets.json.
        circrna_dir: Directory containing hg38_circRNAs.bed (circAtlas).
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
        logger.warning(f"circrna_checker: cannot load offtargets: {exc}")

    sites: list[dict] = offtargets.get("offtarget_sites", [])
    site_ids, regions = site_ids_and_regions(sites, caller="circrna_checker")

    # Look for a BED file in the circAtlas directory
    circrna_bed: str | None = None
    circrna_path = Path(circrna_dir)
    if circrna_path.exists():
        beds = list(circrna_path.glob("*.bed"))
        if beds:
            circrna_bed = str(beds[0])
            logger.info(f"circrna_checker: using BED file {circrna_bed}")
        else:
            logger.warning(f"circrna_checker: no BED files in {circrna_dir}")
    else:
        logger.warning(f"circrna_checker: directory not found: {circrna_dir}")

    circrna_results: dict[str, Any] = {}
    if regions:
        try:
            results = check_circrna_overlap(regions, circrna_bed)
            for site_id, res in zip(site_ids, results, strict=True):
                circrna_results[site_id] = res.model_dump()
        except Exception as exc:
            logger.warning(f"circrna_checker: check failed: {exc} — using neutral")
            for site_id, region in zip(site_ids, regions, strict=True):
                circrna_results[site_id] = {
                    "region": region.model_dump(),
                    "overlapping_circrnas": [],
                    # A dead source knows nothing. Writing 0.0/False here
                    # asserts "no signal"/"not loaded", which is the safe
                    # direction on a risk channel — and for Ago2 it is the
                    # 0.40-weight channel execution_merger's own docstring
                    # warns about (audit 2026-11-19, Bulgu 3).
                    "overlap_count": None, "sponge_risk": None, "data_available": False,
                }

    payload: dict[str, Any] = {"circrna_results": circrna_results}
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"circrna_checker: {len(regions)} regions → {output_path}")
