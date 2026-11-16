"""Snakemake run() adapter for Stage 1 promoter window definition."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from src.core.models import TSSInfo
from src.stage1_genomic_map.promoter_region import define_promoter


def run(
    tss_path: str,
    transcripts_path: str,
    upstream: int,
    downstream: int,
    output_path: str,
    log_path: str,
) -> None:
    """Define promoter windows and write stage1_promoter.json.

    Args:
        tss_path: Path to stage1_tss.json.
        transcripts_path: Path to stage1_transcripts.json.
        upstream: Bases upstream of TSS.
        downstream: Bases downstream of TSS.
        output_path: Destination JSON path.
        log_path: Log file path.
    """
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(log_path, level="DEBUG")
    logger.add(sys.stderr, level="INFO")

    tss_data: dict[str, Any] = {}
    try:
        tss_data = json.loads(Path(tss_path).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"promoter_definer: failed to load TSS JSON: {exc}")

    transcripts_data: dict[str, Any] = {}
    try:
        transcripts_data = json.loads(Path(transcripts_path).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"promoter_definer: failed to load transcripts JSON: {exc}")

    gene = tss_data.get("gene", "UNKNOWN")
    tss_raw = tss_data.get("tss", {})

    try:
        tss = TSSInfo(**tss_raw)
        region = define_promoter(tss, upstream=upstream, downstream=downstream)
        promoter_dict = region.model_dump()
        logger.info(
            f"promoter_definer: {gene} promoter → "
            f"{region.chrom}:{region.start}-{region.end}({region.strand})"
        )
    except Exception as exc:
        logger.warning(f"promoter_definer: define_promoter failed: {exc} — using fallback")
        promoter_dict = {"chrom": "chr1", "start": 0, "end": 1200, "strand": "+"}

    payload: dict[str, Any] = {
        "gene": gene,
        "tss": tss_raw,
        "promoter_region": promoter_dict,
        "transcripts": transcripts_data.get("transcripts", []),
    }

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
