"""Snakemake run() adapter for Stage 4 CCLE gene expression lookup."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from src.stage4_epigenetic.ccle_expression import CCLEReader
from src.core.config import OrcSonarConfig


def run(
    ccle_csv: str,
    offtargets_path: str,
    cell_line: str,
    output_path: str,
    log_path: str,
) -> None:
    """Look up CCLE expression for off-target genes and write stage4_ccle.json.

    Args:
        ccle_csv: Path to CCLE_Expression.csv.
        offtargets_path: Path to stage2_offtargets.json.
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
        logger.warning(f"ccle_reader: cannot load offtargets: {exc}")

    sites: list[dict] = offtargets.get("offtarget_sites", [])
    genes: set[str] = {s["gene"] for s in sites if "gene" in s}

    config = OrcSonarConfig(
        cell_line=cell_line,
        data_paths={"ccle_csv": ccle_csv},
    )

    ccle_results: dict[str, Any] = {}
    if genes:
        try:
            reader = CCLEReader(config)
            for gene in sorted(genes):
                try:
                    result = reader.get_expression(gene, cell_line)
                    ccle_results[gene] = result.model_dump()
                except Exception as exc:
                    logger.debug(f"ccle_reader: expression lookup failed for {gene}: {exc}")
                    ccle_results[gene] = {
                        "gene": gene, "cell_line": cell_line,
                        "expression_value": 0.0, "is_expressed": False,
                        "expression_percentile": 0.0,
                    }
        except Exception as exc:
            logger.warning(f"ccle_reader: reader init failed: {exc}")

    payload: dict[str, Any] = {"ccle_results": ccle_results, "cell_line": cell_line}
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(
        f"ccle_reader: {len(ccle_results)} genes in {cell_line} → {output_path}"
    )
