"""ADAR A-to-I editing risk calculator for Stage 5 (orcSONAR).

ADAR edits double-stranded RNA structures. Risk is estimated from two
independent signals:
  1. Alu repeat density — Alu elements form dsRNA hairpins that are the
     canonical ADAR substrate (proxy from Stage 2 RepeatMasker data).
  2. SHAPE-derived double-strandedness — positions with low SHAPE
     reactivity (< 0.3) are likely double-stranded.

Final risk is a weighted combination: 0.6 × alu_risk + 0.4 × shape_risk.
"""

from __future__ import annotations

from typing import Optional

from loguru import logger

from src.core.models import AdarRiskResult, GenomicRegion, RepeatResult, ShapeResult

# Weights for the two risk signals
_ALU_WEIGHT: float = 0.6
_SHAPE_WEIGHT: float = 0.4

# SHAPE threshold below which a position is considered double-stranded
_DS_THRESHOLD: float = 0.3


def _alu_risk(repeat_result: RepeatResult) -> float:
    """Derive Alu-based ADAR risk in [0, 1].

    One or more Alu elements → high base risk (0.8). Multiple Alu
    repeats compound linearly up to the cap. No Alu → 0.0.
    """
    if not repeat_result.has_alu:
        return 0.0

    alu_count = sum(
        1 for r in repeat_result.repeats if r.rep_family.upper() == "ALU"
    )
    # 0.8 for first Alu, +0.1 per additional, capped at 1.0
    risk = min(0.8 + 0.1 * max(alu_count - 1, 0), 1.0)
    return round(risk, 4)


def _shape_ds_risk(shape_result: Optional[ShapeResult]) -> float:
    """Derive double-strandedness risk from SHAPE data.

    Returns:
        0.5 (neutral) if no SHAPE data are available, otherwise the
        fraction of double-stranded positions (reactivity < 0.3).
    """
    if shape_result is None or not shape_result.data_available:
        return 0.5  # graceful degradation

    ds_frac = 1.0 - shape_result.single_stranded_fraction
    return round(ds_frac, 4)


def calculate_adar_risk(
    region: GenomicRegion,
    repeat_result: RepeatResult,
    shape_result: Optional[ShapeResult] = None,
) -> AdarRiskResult:
    """Calculate ADAR A-to-I editing risk for an off-target region.

    Combines Alu-based and SHAPE-based signals into a single risk score.

    Args:
        region:        Genomic region being assessed.
        repeat_result: Stage 2 RepeatMasker output for this region.
        shape_result:  Optional SHAPE accessibility for this region and
                       cell line. Pass None to rely on Alu signal alone.

    Returns:
        AdarRiskResult with alu_risk, shape_ds_risk, and combined adar_score.
    """
    alu = _alu_risk(repeat_result)
    shape_ds = _shape_ds_risk(shape_result)
    shape_available = shape_result is not None and shape_result.data_available

    # When SHAPE is unavailable, the combined score is 100% Alu-based
    if not shape_available:
        combined = alu
    else:
        combined = round(_ALU_WEIGHT * alu + _SHAPE_WEIGHT * shape_ds, 4)

    logger.debug(
        "ADAR risk for {}: alu={:.3f}, shape_ds={:.3f}, combined={:.3f}",
        region,
        alu,
        shape_ds,
        combined,
    )

    return AdarRiskResult(
        region=region,
        alu_risk=alu,
        shape_ds_risk=shape_ds,
        adar_score=combined,
        shape_used=shape_available,
    )
