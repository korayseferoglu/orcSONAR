"""Snakemake run() adapter — merges Stage 5 biophysics & structural outputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger

_NEUTRAL_DG = -15.0  # kcal/mol fallback
_DG_REFERENCE = -10.0  # weak binding baseline
_DG_STRONG = -30.0  # saturation point


def _load(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        logger.warning(f"biophysics_merger: {path} not found — using empty dict")
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"biophysics_merger: failed to parse {path}: {exc}")
        return {}


def _delta_g_risk(dg: float) -> float:
    """Normalise ΔG to [0, 1]. More negative = stronger binding = higher risk."""
    if dg <= _DG_STRONG:
        return 1.0
    if dg >= _DG_REFERENCE:
        return 0.0
    return round((dg - _DG_REFERENCE) / (_DG_STRONG - _DG_REFERENCE), 4)


def _normalize(
    delta_g: float,
    shape_acc: float,
    m6a_score: float,
    adar_score: float,
    g4_risk: float,
) -> float:
    """Compute normalised biophysics risk score in [0, 1]."""
    dg_risk = _delta_g_risk(delta_g)
    return min(1.0, round(
        0.35 * dg_risk
        + 0.25 * shape_acc
        + 0.15 * m6a_score
        + 0.15 * adar_score
        + 0.10 * g4_risk,
        4,
    ))


def run(
    deltag_path: str,
    shape_path: str,
    m6a_path: str,
    adar_path: str,
    g4_path: str,
    output_path: str,
    log_path: str,
) -> None:
    """Merge ΔG, SHAPE, m6A, ADAR, G4 into stage5_biophysics.json.

    Args:
        deltag_path: Path to stage5_deltag.json.
        shape_path: Path to stage5_shape.json.
        m6a_path: Path to stage5_m6a.json.
        adar_path: Path to stage5_adar.json.
        g4_path: Path to stage5_g4.json.
        output_path: Destination for stage5_biophysics.json.
        log_path: Log file path.
    """
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(log_path, level="DEBUG")
    logger.add(sys.stderr, level="INFO")

    deltag_data = _load(deltag_path)
    shape_data = _load(shape_path)
    m6a_data = _load(m6a_path)
    adar_data = _load(adar_path)
    g4_data = _load(g4_path)

    deltag_results: dict[str, Any] = deltag_data.get("deltag_results", {})
    shape_results: dict[str, Any] = shape_data.get("shape_results", {})
    m6a_results: dict[str, Any] = m6a_data.get("m6a_results", {})
    adar_results: dict[str, Any] = adar_data.get("adar_results", {})
    g4_results: dict[str, Any] = g4_data.get("g4_results", {})

    all_site_ids: set[str] = (
        set(deltag_results)
        | set(shape_results)
        | set(m6a_results)
        | set(adar_results)
        | set(g4_results)
    )

    biophysics_scores: dict[str, Any] = {}
    for site_id in sorted(all_site_ids):
        dg = float(deltag_results.get(site_id, {}).get("delta_g", _NEUTRAL_DG))
        shape_acc = float(shape_results.get(site_id, {}).get("accessibility_score", 0.5))
        m6a_score = float(m6a_results.get(site_id, {}).get("m6a_score", 0.0))
        m6a_count = int(m6a_results.get(site_id, {}).get("site_count", 0))
        adar_score = float(adar_results.get(site_id, {}).get("adar_score", 0.0))
        g4_risk = float(g4_results.get(site_id, {}).get("risk_score", 0.0))

        normalized = _normalize(dg, shape_acc, m6a_score, adar_score, g4_risk)
        biophysics_scores[site_id] = {
            "delta_g": dg,
            "shape_accessibility": shape_acc,
            "m6a_sites": m6a_count,
            "adar_risk": adar_score,
            "g4_risk": g4_risk,
            "normalized_score": normalized,
        }
        logger.debug(
            f"biophysics_merger: {site_id} → "
            f"ΔG={dg:.2f} shape={shape_acc:.2f} normalized={normalized:.4f}"
        )

    payload: dict[str, Any] = {"biophysics_scores": biophysics_scores}
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"biophysics_merger: {len(biophysics_scores)} sites → {output_path}")
