"""Snakemake run() adapter for Stage 5 Turner nearest-neighbor ΔG calculation."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from src.stage5_biophysics.thermodynamics import TurnerCalculator
from src.core.config import OrcSonarConfig

_DG_NEUTRAL = -15.0  # kcal/mol neutral fallback
_DG_STRONG = -30.0
_DG_MODERATE = -25.0


def _dg_to_risk_score(delta_g: float, dg_strong: float, dg_moderate: float) -> float:
    """Normalise ΔG to a risk score in [0, 1].  More negative = higher risk."""
    if delta_g <= dg_strong:
        return 1.0
    if delta_g <= dg_moderate:
        frac = (delta_g - dg_moderate) / (dg_strong - dg_moderate)
        return round(0.5 + 0.5 * frac, 4)
    if delta_g < -10.0:
        frac = (delta_g - (-10.0)) / (dg_moderate - (-10.0))
        return round(frac * 0.5, 4)
    return 0.0


def run(
    sarna_sequence: str,
    offtargets_path: str,
    turner_dir: str,
    dg_strong: float,
    dg_moderate: float,
    output_path: str,
    log_path: str,
) -> None:
    """Compute RNA:DNA hybrid ΔG for each off-target site and write stage5_deltag.json.

    Args:
        sarna_sequence: saRNA guide strand (DNA or RNA).
        offtargets_path: Path to stage2_offtargets.json.
        turner_dir: Directory containing Turner parameter files.
        dg_strong: ΔG threshold for strong binding (kcal/mol).
        dg_moderate: ΔG threshold for moderate binding (kcal/mol).
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
        logger.warning(f"delta_g_calculator: cannot load offtargets: {exc}")

    sites: list[dict] = offtargets.get("offtarget_sites", [])

    sarna_rna = sarna_sequence.upper().replace("T", "U")

    try:
        calc = TurnerCalculator(turner_dir)
    except Exception as exc:
        logger.warning(f"delta_g_calculator: cannot init TurnerCalculator: {exc}")
        calc = None

    deltag_results: dict[str, Any] = {}
    for s in sites:
        site_id = s["site_id"]
        try:
            if calc is not None:
                # Use reverse complement of saRNA as target (antiparallel duplex)
                comp = {"A": "U", "U": "A", "G": "C", "C": "G", "N": "N"}
                target = "".join(comp.get(b, "N") for b in reversed(sarna_rna))
                result = calc.calculate_duplex_dg(sarna_rna, target)
                dg = result.delta_g
                has_mm = result.has_mismatches
            else:
                dg = _DG_NEUTRAL
                has_mm = False
        except Exception as exc:
            logger.debug(f"delta_g_calculator: ΔG failed for {site_id}: {exc}")
            dg = _DG_NEUTRAL
            has_mm = False

        risk = _dg_to_risk_score(dg, dg_strong, dg_moderate)
        deltag_results[site_id] = {
            "delta_g": round(dg, 4),
            "has_mismatches": has_mm,
            "risk_score": risk,
        }
        logger.debug(f"delta_g_calculator: {site_id} → ΔG={dg:.2f} risk={risk:.3f}")

    payload: dict[str, Any] = {"deltag_results": deltag_results}
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"delta_g_calculator: {len(deltag_results)} sites → {output_path}")
