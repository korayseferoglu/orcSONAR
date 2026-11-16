"""Snakemake run() wrapper for Stage 7 risk classification.

Reads stage7_scores.json, applies the cell-specific modifier via ScoreIntegrator,
classifies each site, selects the overall worst-case score, and writes
stage7_classification.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from src.core.config import RiskThresholds
from src.core.models import DomainScores
from src.scoring.classifier import RiskClass, classify, get_recommendation
from src.scoring.integrator import ScoreIntegrator

_RISK_ORDER = [RiskClass.SAFE, RiskClass.WARNING, RiskClass.HIGH_RISK, RiskClass.DANGEROUS]


def _thresholds_from_dict(thresholds: dict[str, float]) -> RiskThresholds:
    return RiskThresholds(
        safe=thresholds.get("safe", 0.3),
        warning=thresholds.get("warning", 0.6),
        high_risk=thresholds.get("high_risk", 0.8),
    )


def run(
    scores_path: str,
    thresholds: dict[str, float],
    output_path: str,
    log_path: str,
) -> None:
    """Classify off-target sites and compute overall pipeline risk.

    Args:
        scores_path: Path to stage7_scores.json.
        thresholds: Risk threshold mapping (safe, warning, high_risk).
        output_path: Destination for stage7_classification.json.
        log_path: Log file path.
    """
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(log_path, level="DEBUG")
    logger.add(sys.stderr, level="INFO")

    logger.info("risk_classifier: loading scores")
    p = Path(scores_path)
    if not p.exists():
        logger.error(f"risk_classifier: {scores_path} not found")
        raise FileNotFoundError(scores_path)

    data: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    domain_scores_raw: dict[str, dict[str, float]] = data.get("domain_scores", {})
    base_scores: dict[str, float] = data.get("base_scores", {})
    cell_context: dict[str, float] = data.get("cell_context", {})
    weights: dict[str, float] = data.get("weights", {})

    rt = _thresholds_from_dict(thresholds)
    integrator = ScoreIntegrator(risk_thresholds=rt)

    site_classifications: dict[str, dict[str, Any]] = {}
    worst_score: float = 0.0
    worst_class: RiskClass = RiskClass.SAFE

    for site_id, raw in domain_scores_raw.items():
        ds = DomainScores(**raw)
        base = base_scores.get(site_id, integrator.integrate(ds, weights) if weights else 0.5)
        final = integrator.apply_cell_modifier(base, cell_context)
        risk = classify(final, rt)

        site_classifications[site_id] = {
            "base_score": round(base, 6),
            "final_score": round(final, 6),
            "risk_class": risk.value,
        }

        if _RISK_ORDER.index(risk) > _RISK_ORDER.index(worst_class):
            worst_class = risk
            worst_score = final
        elif _RISK_ORDER.index(risk) == _RISK_ORDER.index(worst_class) and final > worst_score:
            worst_score = final

        logger.debug(f"site {site_id}: base={base:.4f} final={final:.4f} → {risk.value}")

    n_sites = len(site_classifications)
    active = sum(
        1 for v in site_classifications.values()
        if v["risk_class"] not in ("SAFE",)
    )

    cell_line_context = (
        f"Active chromatin detected at {active} of {n_sites} off-target sites. "
        f"Overall risk: {worst_class.value}. {get_recommendation(worst_class)}"
    ) if n_sites else "No off-target sites detected."

    payload: dict[str, Any] = {
        "site_classifications": site_classifications,
        "overall_risk_score": round(worst_score, 6),
        "overall_risk_class": worst_class.value,
        "cell_line_context": cell_line_context,
    }

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(
        f"risk_classifier: {n_sites} sites classified — "
        f"overall={worst_class.value} ({worst_score:.4f}) → {output_path}"
    )
