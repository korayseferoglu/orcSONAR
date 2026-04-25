"""Machine-readable JSON report generation for orcSONAR (Stage 7).

Serialises the complete ``FinalReport`` to a structured JSON file that
includes all intermediate domain scores, per-site breakdowns, and pipeline
metadata (version, timestamp, data source registry).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from src.core.models import FinalReport

_ORCSONAR_VERSION: str = "0.1.0"

_DATA_SOURCES: list[str] = [
    "EPDnew hg38 (TSS database)",
    "FANTOM5 CAGE peaks hg38",
    "GENCODE v44 via Ensembl REST",
    "NCBI RefSeq via E-utilities",
    "miRBase v22 (mature.fa)",
    "RepeatMasker via UCSC rmsk API",
    "COSMIC v103 GRCh38",
    "gnomAD v4 via GraphQL API",
    "NCBI ClinVar via E-utilities",
    "UCSC phyloP 100-way BigWig",
    "ENCODE ATAC-seq BigWig",
    "ENCODE ChIP-seq (H3K4me3/H3K27ac/H3K27me3)",
    "GRO-seq / PRO-seq BigWig",
    "Hi-C / 4DN portal",
    "CCLE / DepMap expression matrix",
    "Turner nearest-neighbour thermodynamics",
    "SHAPE-Seq accessibility profiles",
    "m6A-Atlas / RMBase hg38 (Tabix)",
    "ADAR A→I risk via Alu proxy (RepeatMasker)",
    "G4 RNA quadruplex (regex scan)",
    "Ago2 eCLIP BigWig (ENCODE)",
    "POSTAR3 RBP eCLIP (ENCODE)",
    "circAtlas 3.0 circRNA FASTA/BED",
    "TLR7/TLR8 immune danger motifs",
]


def _build_payload(report: FinalReport) -> dict[str, Any]:
    """Enrich the Pydantic-serialised report with pipeline metadata.

    Args:
        report: Completed orcSONAR analysis result.

    Returns:
        Dict ready for JSON serialisation.
    """
    data = report.model_dump(mode="json")
    data["_metadata"] = {
        "orcsonar_version": _ORCSONAR_VERSION,
        "generated_at": datetime.now().isoformat(),
        "genome_assembly": "hg38 / GRCh38",
        "data_sources": _DATA_SOURCES,
        "risk_thresholds": {
            "SAFE":      {"min": 0.0, "max": 0.3},
            "WARNING":   {"min": 0.3, "max": 0.6},
            "HIGH_RISK": {"min": 0.6, "max": 0.8},
            "DANGEROUS": {"min": 0.8, "max": 1.0},
        },
        "domain_weights": {
            "sequence_specificity": 0.20,
            "variant_toxicity":     0.15,
            "epigenetic_context":   0.20,
            "biophysics_structure": 0.25,
            "execution_safety":     0.20,
        },
    }
    return data


def save_json_report(report: FinalReport, output_path: str) -> None:
    """Serialise a ``FinalReport`` to a machine-readable JSON file.

    The output includes all domain scores, per-site breakdowns, pipeline
    metadata (version, timestamp, data-source registry) and the final
    risk classification.  Parent directories are created as needed.

    Args:
        report: Completed orcSONAR analysis result.
        output_path: Destination path for the ``.json`` file.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = _build_payload(report)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"json_report: saved → {path} ({path.stat().st_size} bytes)")
