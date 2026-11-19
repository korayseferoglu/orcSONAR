"""Snakemake run() adapter for Stage 4 histone ChIP-seq signal extraction."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from src.core.config import OrcSonarConfig
from src.core.site_keys import site_ids_and_regions
from src.stage4_epigenetic.histone_marks import HistoneMarkReader


def run(
    offtargets_path: str,
    cell_line: str,
    cell_lines_cfg: str,
    output_path: str,
    log_path: str,
) -> None:
    """Extract H3K4me3 and H3K27ac signals for off-target regions and write stage4_histones.json."""
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(log_path, level="DEBUG")
    logger.add(sys.stderr, level="INFO")

    offtargets: dict[str, Any] = {}
    try:
        offtargets = json.loads(Path(offtargets_path).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"histone_fetcher: cannot load offtargets: {exc}")

    sites: list[dict] = offtargets.get("offtarget_sites", [])
    site_ids, regions = site_ids_and_regions(sites, caller="histone_fetcher")

    h3k4me3_signals: dict[str, float | None] = {}
    h3k27ac_signals: dict[str, float | None] = {}
    if regions:
        try:
            config = OrcSonarConfig()
            reader = HistoneMarkReader(config, cell_lines_yaml=cell_lines_cfg)
            k4me3 = reader.get_h3k4me3_bulk(regions, cell_line)
            k27ac = reader.get_h3k27ac_bulk(regions, cell_line)
            for site_id, k4, k27 in zip(site_ids, k4me3, k27ac, strict=True):
                h3k4me3_signals[site_id] = (None if k4 is None else round(k4, 4))
                h3k27ac_signals[site_id] = (None if k27 is None else round(k27, 4))
        except Exception as exc:
            logger.warning(f"histone_fetcher: extraction failed: {exc} — writing UNKNOWN")
            h3k4me3_signals = dict.fromkeys(site_ids)
            h3k27ac_signals = dict.fromkeys(site_ids)

    payload: dict[str, Any] = {
        "h3k4me3_signals": h3k4me3_signals,
        "h3k27ac_signals": h3k27ac_signals,
    }
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"histone_fetcher: {len(regions)} regions for {cell_line} → {output_path}")
