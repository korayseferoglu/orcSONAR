"""Snakemake run() adapter — merges Stage 2 off-target scan outputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger


def run(
    seed_hits_path: str,
    mirbase_path: str,
    repeats_path: str,
    output_path: str,
    log_path: str,
) -> None:
    """Merge seed hits, miRBase, and repeat scan into stage2_offtargets.json.

    Args:
        seed_hits_path: Path to stage2_seed_hits.json.
        mirbase_path: Path to stage2_mirbase.json.
        repeats_path: Path to stage2_repeats.json.
        output_path: Destination for stage2_offtargets.json.
        log_path: Log file path.
    """
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(log_path, level="DEBUG")
    logger.add(sys.stderr, level="INFO")

    def _load(path: str) -> dict[str, Any]:
        p = Path(path)
        if not p.exists():
            logger.warning(f"offtarget_merger: {path} not found — using empty dict")
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"offtarget_merger: failed to parse {path}: {exc}")
            return {}

    seed_data = _load(seed_hits_path)
    mirbase_data = _load(mirbase_path)
    repeats_data = _load(repeats_path)

    sites: list[dict[str, Any]] = seed_data.get("sites", [])
    sequence_scores: dict[str, float] = seed_data.get("sequence_scores", {})
    repeat_results: dict[str, Any] = repeats_data.get("repeat_results", {})

    # Default miRBase result if missing
    mirbase_result: dict[str, Any] = mirbase_data if mirbase_data else {
        "sarna_seed": "",
        "overlapping_mirnas": [],
        "max_overlap_score": 0.0,
        "risk_level": "SAFE",
    }

    payload: dict[str, Any] = {
        "offtarget_sites": sites,
        "mirbase_result": mirbase_result,
        "repeat_results": repeat_results,
        "sequence_scores": sequence_scores,
    }

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(
        f"offtarget_merger: {len(sites)} off-target sites, "
        f"{len(sequence_scores)} scored sites → {output_path}"
    )
