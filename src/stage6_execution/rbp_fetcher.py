"""Snakemake run() adapter for Stage 6 RBP competition assessment."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from src.core.config import config_from_mapping
from src.core.site_keys import site_ids_and_regions
from src.stage6_execution.rbp_competition import assess_rbp_competition


def run(
    offtargets_path: str,
    cell_line: str,
    cell_lines_cfg: str,
    output_path: str,
    log_path: str,
    config_raw: dict[str, Any] | None = None,
) -> None:
    """Extract hnRNPA1 eCLIP signal for off-target regions and write stage6_rbp.json."""
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(log_path, level="DEBUG")
    logger.add(sys.stderr, level="INFO")

    offtargets: dict[str, Any] = {}
    try:
        offtargets = json.loads(Path(offtargets_path).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"rbp_fetcher: cannot load offtargets: {exc}")

    sites: list[dict] = offtargets.get("offtarget_sites", [])
    site_ids, regions = site_ids_and_regions(sites, caller="rbp_fetcher")

    rbp_results: dict[str, Any] = {}
    if regions:
        try:
            config = config_from_mapping(config_raw, cell_line=cell_line)
            results = assess_rbp_competition(regions, cell_line, config, cell_lines_cfg)
            for site_id, res in zip(site_ids, results, strict=True):
                rbp_results[site_id] = res.model_dump()
        except Exception as exc:
            logger.warning(f"rbp_fetcher: assessment failed: {exc} — using neutral")
            for site_id, region in zip(site_ids, regions, strict=True):
                rbp_results[site_id] = {
                    "region": region.model_dump(), "cell_line": cell_line,
                    "rbp_name": "hnRNPA1", "raw_signal": 0.0,
                    "competition_score": 0.0, "is_competing": False,
                }

    payload: dict[str, Any] = {"rbp_results": rbp_results}
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"rbp_fetcher: {len(regions)} regions for {cell_line} → {output_path}")
