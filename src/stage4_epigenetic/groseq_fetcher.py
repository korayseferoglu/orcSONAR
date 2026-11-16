"""Snakemake run() adapter for Stage 4 GRO-seq transcription signal."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from src.core.config import OrcSonarConfig
from src.core.site_keys import site_ids_and_regions
from src.stage4_epigenetic.transcription_run import GROseqReader


def run(
    offtargets_path: str,
    cell_line: str,
    cell_lines_cfg: str,
    output_path: str,
    log_path: str,
) -> None:
    """Extract GRO-seq signal for off-target regions and write stage4_groseq.json."""
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(log_path, level="DEBUG")
    logger.add(sys.stderr, level="INFO")

    offtargets: dict[str, Any] = {}
    try:
        offtargets = json.loads(Path(offtargets_path).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"groseq_fetcher: cannot load offtargets: {exc}")

    sites: list[dict] = offtargets.get("offtarget_sites", [])
    site_ids, regions = site_ids_and_regions(sites, caller="groseq_fetcher")

    groseq_signals: dict[str, float] = {}
    if regions:
        try:
            config = OrcSonarConfig()
            reader = GROseqReader(config, cell_lines_yaml=cell_lines_cfg)
            results = reader.get_transcription_bulk(regions, cell_line)
            for site_id, res in zip(site_ids, results, strict=True):
                groseq_signals[site_id] = round(res.combined_signal, 4)
        except Exception as exc:
            logger.warning(f"groseq_fetcher: extraction failed: {exc} — using 0.0")
            groseq_signals = {sid: 0.0 for sid in site_ids}

    payload: dict[str, Any] = {"groseq_signals": groseq_signals}
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"groseq_fetcher: {len(regions)} regions for {cell_line} → {output_path}")
