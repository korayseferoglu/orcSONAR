"""Snakemake run() adapter for Stage 4 Hi-C contact frequency extraction."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from src.core.config import OrcSonarConfig
from src.core.site_keys import site_ids_and_regions
from src.stage4_epigenetic.hic_contacts import HiCContactReader


def run(
    offtargets_path: str,
    cell_line: str,
    cell_lines_cfg: str,
    output_path: str,
    log_path: str,
) -> None:
    """Extract Hi-C contact frequencies for off-target regions and write stage4_hic.json."""
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(log_path, level="DEBUG")
    logger.add(sys.stderr, level="INFO")

    offtargets: dict[str, Any] = {}
    try:
        offtargets = json.loads(Path(offtargets_path).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"hic_fetcher: cannot load offtargets: {exc}")

    sites: list[dict] = offtargets.get("offtarget_sites", [])
    site_ids, regions = site_ids_and_regions(sites, caller="hic_fetcher")

    hic_contacts: dict[str, float] = {}
    if regions:
        try:
            config = OrcSonarConfig()
            reader = HiCContactReader(config, cell_lines_yaml=cell_lines_cfg)
            # Use the first region as the "target" and all others as off-targets
            # (Hi-C measures contact between the saRNA target locus and off-target loci)
            target_region = regions[0]
            results = reader.get_contacts_bulk(target_region, regions, cell_line)
            for site_id, res in zip(site_ids, results, strict=True):
                hic_contacts[site_id] = round(res.contact_frequency, 6)
        except Exception as exc:
            logger.warning(f"hic_fetcher: extraction failed: {exc} — using 0.0")
            hic_contacts = {sid: 0.0 for sid in site_ids}

    payload: dict[str, Any] = {"hic_contacts": hic_contacts}
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"hic_fetcher: {len(regions)} regions for {cell_line} → {output_path}")
