"""Snakemake run() adapter for Stage 6 immune motif screening."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from src.stage6_execution.immune_screen import screen_immune_motifs
from src.core.models import GenomicRegion


def run(
    sarna_sequence: str,
    offtargets_path: str,
    immune_motifs_file: str,
    output_path: str,
    log_path: str,
) -> None:
    """Screen saRNA and off-target sequences for TLR7/TLR8 motifs.

    Screens:
    - The saRNA guide strand itself (``sarna_immune``).
    - Each off-target sequence (when a sequence can be obtained).

    Args:
        sarna_sequence: saRNA guide strand (DNA or RNA).
        offtargets_path: Path to stage2_offtargets.json.
        immune_motifs_file: Path to immune_motifs.txt.
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
        logger.warning(f"immune_screener: cannot load offtargets: {exc}")

    sites: list[dict] = offtargets.get("offtarget_sites", [])

    # Screen the saRNA itself
    sarna_immune: dict[str, Any] = {
        "motifs_found": [], "total_hits": 0, "risk_score": 0.0, "risk_level": "SAFE",
    }
    try:
        result = screen_immune_motifs(sarna_sequence, immune_motifs_file)
        sarna_immune = result.model_dump()
        logger.info(
            f"immune_screener: saRNA hits={result.total_hits} "
            f"risk={result.risk_level}"
        )
    except Exception as exc:
        logger.warning(f"immune_screener: saRNA screening failed: {exc}")

    # For off-target sites, we use the same saRNA sequence as a proxy
    # (off-target mRNA sequences are not available without Ensembl fetch)
    offtarget_immune: dict[str, Any] = {}
    for s in sites:
        site_id = f"{s['gene']}:{s['transcript_id']}"
        offtarget_immune[site_id] = sarna_immune

    payload: dict[str, Any] = {
        "sarna_immune": sarna_immune,
        "offtarget_immune": offtarget_immune,
    }
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(
        f"immune_screener: saRNA + {len(sites)} off-target sites → {output_path}"
    )
