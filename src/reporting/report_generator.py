"""Snakemake run() wrapper for Stage 7 final report generation.

Assembles the FinalReport from all stage JSON outputs and writes both
final_report.json and final_report.html.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from src.core.models import (
    DomainScores,
    FinalReport,
    GenomicRegion,
    OffTargetSite,
    SarnaInput,
)
from src.reporting.html_report import generate_html_report
from src.reporting.json_report import save_json_report


def _load(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        logger.warning(f"report_generator: {path} not found — using empty dict")
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"report_generator: failed to parse {path}: {exc}")
        return {}


def _parse_offtarget_sites(raw: list[dict[str, Any]]) -> list[OffTargetSite]:
    sites: list[OffTargetSite] = []
    for item in raw:
        try:
            region_data = item.get("region", {})
            region = GenomicRegion(
                chrom=region_data.get("chrom", "chrUn"),
                start=region_data.get("start", 0),
                end=region_data.get("end", 1),
                strand=region_data.get("strand", "."),
            )
            sites.append(
                OffTargetSite(
                    gene=item["gene"],
                    transcript_id=item["transcript_id"],
                    region=region,
                    seed_match_type=item.get("seed_match_type", "mismatch"),
                    mismatches=item.get("mismatches", 0),
                    alignment_score=item.get("alignment_score", 0.0),
                )
            )
        except Exception as exc:
            logger.warning(f"report_generator: skipping malformed site: {exc}")
    return sites


def run(
    classification_path: str,
    scores_path: str,
    offtargets_path: str,
    variants_path: str,
    epigenetic_path: str,
    biophysics_path: str,
    execution_path: str,
    gene: str,
    cell_line: str,
    sarna_sequence: str,
    json_output: str,
    html_output: str,
    log_path: str,
) -> None:
    """Assemble FinalReport from all stage outputs and write JSON + HTML reports.

    Args:
        classification_path: Path to stage7_classification.json.
        scores_path: Path to stage7_scores.json.
        offtargets_path: Path to stage2_offtargets.json.
        variants_path: Path to stage3_variants.json.
        epigenetic_path: Path to stage4_epigenetic.json.
        biophysics_path: Path to stage5_biophysics.json.
        execution_path: Path to stage6_execution.json.
        gene: Target gene symbol.
        cell_line: Analysis cell line.
        sarna_sequence: saRNA nucleotide sequence.
        json_output: Destination for final_report.json.
        html_output: Destination for final_report.html.
        log_path: Log file path.
    """
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(log_path, level="DEBUG")
    logger.add(sys.stderr, level="INFO")

    logger.info("report_generator: assembling FinalReport")
    classification = _load(classification_path)
    scores = _load(scores_path)
    stage2 = _load(offtargets_path)

    offtarget_sites = _parse_offtarget_sites(stage2.get("offtarget_sites", []))

    domain_scores_raw: dict[str, dict[str, float]] = scores.get("domain_scores", {})
    domain_scores_per_site: dict[str, DomainScores] = {}
    for site_id, raw in domain_scores_raw.items():
        try:
            domain_scores_per_site[site_id] = DomainScores(**raw)
        except Exception as exc:
            logger.warning(f"report_generator: skipping domain scores for {site_id}: {exc}")

    overall_risk_score: float = classification.get("overall_risk_score", 0.5)
    overall_risk_class: str = classification.get("overall_risk_class", "WARNING")
    cell_line_context: str = classification.get("cell_line_context", f"Analysis performed in {cell_line}.")

    sarna_input = SarnaInput(
        sequence=sarna_sequence,
        target_gene=gene,
        cell_line=cell_line,
    )

    report = FinalReport(
        sarna_input=sarna_input,
        offtarget_sites=offtarget_sites,
        domain_scores_per_site=domain_scores_per_site,
        final_risk_score=overall_risk_score,
        risk_class=overall_risk_class,  # type: ignore[arg-type]
        cell_line_context=cell_line_context,
    )

    save_json_report(report, json_output)
    generate_html_report(report, html_output)

    logger.info(
        f"report_generator: {len(offtarget_sites)} sites, "
        f"risk={overall_risk_class} ({overall_risk_score:.4f}) "
        f"→ {html_output}"
    )
