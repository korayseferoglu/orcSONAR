"""Snakemake run() adapter for Stage 4 ATAC-seq signal extraction."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from src.stage4_epigenetic.chromatin_access import ATACSeqReader
from src.core.config import OrcSonarConfig
from src.core.models import GenomicRegion


def run(
    offtargets_path: str,
    cell_line: str,
    cell_lines_cfg: str,
    output_path: str,
    log_path: str,
) -> None:
    """Extract ATAC-seq signal for off-target regions and write stage4_atac.json."""
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(log_path, level="DEBUG")
    logger.add(sys.stderr, level="INFO")

    offtargets: dict[str, Any] = {}
    try:
        offtargets = json.loads(Path(offtargets_path).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"atac_fetcher: cannot load offtargets: {exc}")

    sites: list[dict] = offtargets.get("offtarget_sites", [])
    regions: list[GenomicRegion] = []
    site_ids: list[str] = []
    for s in sites:
        try:
            regions.append(GenomicRegion(**s["region"]))
            site_ids.append(f"{s['gene']}:{s['transcript_id']}")
        except Exception:
            pass

    atac_signals: dict[str, float] = {}
    if regions:
        try:
            config = OrcSonarConfig()
            reader = ATACSeqReader(config, cell_lines_yaml=cell_lines_cfg)
            signals = reader.get_accessibility_bulk(regions, cell_line)
            for site_id, sig in zip(site_ids, signals):
                atac_signals[site_id] = round(sig, 4)
        except Exception as exc:
            logger.warning(f"atac_fetcher: signal extraction failed: {exc} — using 0.0")
            atac_signals = {sid: 0.0 for sid in site_ids}

    payload: dict[str, Any] = {"atac_signals": atac_signals}
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"atac_fetcher: {len(regions)} regions for {cell_line} → {output_path}")
