"""Snakemake run() adapter for Stage 5 SHAPE-seq accessibility extraction."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from src.core.models import GenomicRegion
from src.stage5_biophysics.shape_profile import get_shape_accessibility


def run(
    offtargets_path: str,
    shape_dir: str,
    cell_line: str,
    output_path: str,
    log_path: str,
) -> None:
    """Read SHAPE-seq accessibility for off-target regions and write stage5_shape.json.

    Falls back to neutral (accessibility_score=0.5, data_available=False) when
    SHAPE data is not available for the requested cell line.

    Args:
        offtargets_path: Path to stage2_offtargets.json.
        shape_dir: Path to SHAPE_Seq root directory.
        cell_line: Target cell line name.
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
        logger.warning(f"shape_reader: cannot load offtargets: {exc}")

    sites: list[dict] = offtargets.get("offtarget_sites", [])
    shape_results: dict[str, Any] = {}
    for s in sites:
        site_id = s["site_id"]
        try:
            region = GenomicRegion(**s["region"])
            result = get_shape_accessibility(
                region,
                cell_line,
                shape_dir,
                transcript_id=s.get("transcript_id"),
                tx_start=s.get("tx_start"),
                tx_end=s.get("tx_end"),
            )
            new_payload = result.model_dump()
        except Exception as exc:
            logger.debug(f"shape_reader: failed for {site_id}: {exc}")
            new_payload = {
                "region": s.get("region", {}),
                # A dead source knows nothing; on these channels a
                # smaller number is a lower risk (audit Bulgu 2).
                "mean_reactivity": None,
                "accessibility_score": None,
                "single_stranded_fraction": None,
                "data_available": False,
            }
        # site_id includes the locus, so each window has its own key and no
        # window can overwrite another. This used to prefer the window with real
        # signal over a neutral fallback, which is why SHAPE reported a
        # different locus than every other stage (AUDIT.md Bulgu-2). Sites that
        # previously borrowed a sibling window's measured signal now correctly
        # report their own — including its absence.
        shape_results[site_id] = new_payload

    n_with_data = sum(1 for v in shape_results.values() if v.get("data_available"))
    n_with_signal = sum(1 for v in shape_results.values() if _has_signal(v))

    payload: dict[str, Any] = {"shape_results": shape_results}
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(
        f"shape_reader: {len(shape_results)} regions in {cell_line} "
        f"({n_with_data} consulted icSHAPE, {n_with_signal} with measured signal) "
        f"→ {output_path}"
    )


def _has_signal(payload: dict[str, Any]) -> bool:
    """A SHAPE payload carries real icSHAPE signal when icSHAPE was consulted
    AND the result is not the (0.5/0.5) NULL-window neutral fallback."""
    if not payload.get("data_available"):
        return False
    return not (
        payload.get("accessibility_score") == 0.5
        and payload.get("single_stranded_fraction") == 0.5
    )
