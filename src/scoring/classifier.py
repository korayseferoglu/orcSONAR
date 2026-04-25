"""Risk classifier for Stage 7 — final saRNA off-target risk classification."""

from __future__ import annotations

from enum import Enum

from loguru import logger

from src.core.config import RiskThresholds


class RiskClass(str, Enum):
    """Enumeration of saRNA off-target risk levels."""

    SAFE = "SAFE"
    WARNING = "WARNING"
    HIGH_RISK = "HIGH_RISK"
    DANGEROUS = "DANGEROUS"


_RECOMMENDATIONS: dict[RiskClass, str] = {
    RiskClass.SAFE: (
        "Off-target risk is acceptably low. Proceed with in vitro validation "
        "in the target cell line."
    ),
    RiskClass.WARNING: (
        "Moderate off-target risk detected. Perform dose-response experiments "
        "and transcriptome-wide RNA-seq to confirm specificity."
    ),
    RiskClass.HIGH_RISK: (
        "High off-target activity predicted. Redesign the saRNA seed sequence "
        "or apply 2'-OMe / phosphorothioate modifications to restrict RISC loading."
    ),
    RiskClass.DANGEROUS: (
        "Unacceptable off-target profile. Do not advance to cellular experiments. "
        "Re-target to an alternative promoter window or select a new saRNA candidate."
    ),
}


def classify(
    score: float,
    thresholds: RiskThresholds | None = None,
) -> RiskClass:
    """Classify a final risk score into a ``RiskClass`` category.

    Boundaries (configurable via ``thresholds``):
    - [0.0, safe)      → SAFE
    - [safe, warning)  → WARNING
    - [warning, high)  → HIGH_RISK
    - [high, 1.0]      → DANGEROUS

    Args:
        score: Final normalised risk score in [0, 1].
        thresholds: Risk threshold configuration.  Uses project defaults when
            ``None`` (safe=0.3, warning=0.6, high_risk=0.8).

    Returns:
        ``RiskClass`` for the given score.
    """
    t = thresholds or RiskThresholds()
    score = max(0.0, min(1.0, score))

    if score < t.safe:
        risk = RiskClass.SAFE
    elif score < t.warning:
        risk = RiskClass.WARNING
    elif score < t.high_risk:
        risk = RiskClass.HIGH_RISK
    else:
        risk = RiskClass.DANGEROUS

    logger.debug(f"classifier: score={score:.4f} → {risk.value}")
    return risk


def get_recommendation(risk_class: RiskClass) -> str:
    """Return a human-readable recommendation for a given risk class.

    Args:
        risk_class: Classified risk level.

    Returns:
        Actionable recommendation string.
    """
    return _RECOMMENDATIONS[risk_class]
