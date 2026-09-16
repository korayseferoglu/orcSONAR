"""Snakemake run() adapter for Stage 5 ADAR A-to-I editing risk estimation."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from src.stage5_biophysics.adar_risk import calculate_adar_risk
from src.core.models import GenomicRegion, RepeatResult, ShapeResult


def run(
    offtargets_path: str,
    ucsc_api_url: str,
    output_path: str,
    log_path: str,
) -> None:
    """Estimate ADAR A-to-I editing risk for off-target regions and write stage5_adar.json.

    Uses repeat annotation already embedded in stage2_offtargets.json.
    SHAPE data is not available at this stage and is treated as absent
    (graceful degradation; Alu-only risk is used instead).

    Args:
        offtargets_path: Path to stage2_offtargets.json (contains repeat_results).
        ucsc_api_url: UCSC API URL (not used here; kept for Snakemake interface compatibility).
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
        logger.warning(f"adar_estimator: cannot load offtargets: {exc}")

    sites: list[dict] = offtargets.get("offtarget_sites", [])
    repeat_map: dict[str, Any] = offtargets.get("repeat_results", {})

    adar_results: dict[str, Any] = {}
    for s in sites:
        site_id = s["site_id"]
        try:
            region = GenomicRegion(**s["region"])
            repeat_raw = repeat_map.get(site_id, {})
            if repeat_raw:
                repeat_result = RepeatResult(**repeat_raw)
            else:
                repeat_result = RepeatResult(region=region, repeats=[], has_alu=False, has_line=False, adar_risk_score=0.0)

            result = calculate_adar_risk(region, repeat_result, shape_result=None)
            adar_results[site_id] = result.model_dump()
        except Exception as exc:
            logger.debug(f"adar_estimator: failed for {site_id}: {exc}")
            adar_results[site_id] = {
                "region": s.get("region", {}),
                "alu_risk": 0.0, "shape_ds_risk": 0.5,
                "adar_score": 0.0, "shape_used": False,
            }
        logger.debug(
            f"adar_estimator: {site_id} → "
            f"adar_score={adar_results[site_id].get('adar_score', 0.0):.3f}"
        )

    payload: dict[str, Any] = {"adar_results": adar_results}
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"adar_estimator: {len(adar_results)} sites → {output_path}")
