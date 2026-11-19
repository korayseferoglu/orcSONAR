"""Snakemake run() adapter for Stage 6 Ago2 eCLIP loading assessment."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from src.core.config import config_from_mapping
from src.core.site_keys import site_ids_and_regions
from src.stage6_execution.ago2_loading import assess_ago2_loading


def run(
    offtargets_path: str,
    cell_line: str,
    cell_lines_cfg: str,
    output_path: str,
    log_path: str,
    config_raw: dict[str, Any] | None = None,
) -> None:
    """Extract Ago2 eCLIP signal for off-target regions and write stage6_ago2.json."""
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(log_path, level="DEBUG")
    logger.add(sys.stderr, level="INFO")

    offtargets: dict[str, Any] = {}
    try:
        offtargets = json.loads(Path(offtargets_path).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"ago2_fetcher: cannot load offtargets: {exc}")

    sites: list[dict] = offtargets.get("offtarget_sites", [])
    site_ids, regions = site_ids_and_regions(sites, caller="ago2_fetcher")

    ago2_results: dict[str, Any] = {}
    if regions:
        try:
            config = config_from_mapping(config_raw, cell_line=cell_line)
            results = assess_ago2_loading(regions, cell_line, config, cell_lines_cfg)
            for site_id, res in zip(site_ids, results, strict=True):
                ago2_results[site_id] = res.model_dump()
        except Exception as exc:
            logger.warning(f"ago2_fetcher: assessment failed: {exc} — using neutral")
            for site_id, region in zip(site_ids, regions, strict=True):
                ago2_results[site_id] = {
                    "region": region.model_dump(), "cell_line": cell_line,
                    # A dead source knows nothing. Writing 0.0/False here
                    # asserts "no signal"/"not loaded", which is the safe
                    # direction on a risk channel — and for Ago2 it is the
                    # 0.40-weight channel execution_merger's own docstring
                    # warns about (audit 2026-11-19, Bulgu 3).
                    "raw_signal": None, "loading_score": None, "is_loaded": None,
                }

    payload: dict[str, Any] = {"ago2_results": ago2_results}
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"ago2_fetcher: {len(regions)} regions for {cell_line} → {output_path}")
