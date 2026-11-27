"""Snakemake run() adapter — merges Stage 5 biophysics & structural outputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger

_NEUTRAL_DG = -15.0  # kcal/mol fallback
# The ΔG → risk thresholds that used to live here are gone (roadmap C3d),
# and this module's pair was a *second, independent* copy: -30/-10 against
# the calculator's -30/-25, neither from config, and the merger recomputed
# its own number while ignoring the one the calculator had just written.
# Three copies of an unjustifiable decision, with different constants.
# The successor is a per-site criterion with an accessibility term
# (RIsearch2, PMID 28108657; PITA's ddG, PMID 17893677) — roadmap `C3e`.
# Until it is pre-registered, ΔG abstains: it contributes `None`, which
# `_normalize` excludes before renormalising (B2).


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


def _normalize(
    delta_g: float | None,
    shape_acc: float | None,
    m6a_score: float | None,
    adar_score: float | None,
    g4_risk: float | None,
) -> float | None:
    """Weighted biophysics score over the channels that were measured.

    An unknown channel is **excluded** and the remaining weights renormalised,
    matching the epigenetic, execution and variant mergers. Before this, every
    missing channel became a number: ΔG fell back to ``_NEUTRAL_DG`` (risk
    0.25), SHAPE to 0.5, and m6A/ADAR/G4 to 0.0 — three quarters of this
    domain's weight failing toward "safe" (audit 2026-11-19, Bulgu 2).

    See ``variant_merger._normalize`` for why renormalisation is used here
    despite roadmap ``B3`` still owning the question.

    Returns:
        Score in [0, 1], or ``None`` if no channel was measured.
    """
    contributions: dict[str, tuple[float, float | None]] = {
        # ΔG abstains until `C3e` lands and `A10` pre-registers the mapping.
        # The weight stays declared so the abstention is visible rather
        # than silently redistributed in the source as well as at runtime.
        "delta_g": (0.35, None),
        "shape": (0.25, shape_acc),
        "m6a": (0.15, m6a_score),
        "adar": (0.15, adar_score),
        "g4": (0.10, g4_risk),
    }
    total = 0.0
    weight_used = 0.0
    for weight, value in contributions.values():
        if value is None:
            continue
        total += weight * value
        weight_used += weight
    if weight_used == 0.0:
        return None
    return min(1.0, round(total / weight_used, 4))


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
        def _opt(results: dict[str, Any], key: str, sid: str = site_id) -> float | None:
            """Read a channel, keeping an unmeasured one unmeasured.

            A site absent from a stage's output was never measured there, and
            `.get(key, default)` also does not fire when the key is present
            with value null — so both routes must be checked.
            """
            value = results.get(sid, {}).get(key)
            return None if value is None else float(value)

        dg = _opt(deltag_results, "delta_g")
        shape_acc = _opt(shape_results, "accessibility_score")
        m6a_score = _opt(m6a_results, "m6a_score")
        raw_count = m6a_results.get(site_id, {}).get("site_count")
        m6a_count = None if raw_count is None else int(raw_count)
        adar_score = _opt(adar_results, "adar_score")
        g4_risk = _opt(g4_results, "risk_score")

        normalized = _normalize(dg, shape_acc, m6a_score, adar_score, g4_risk)
        biophysics_scores[site_id] = {
            "delta_g": dg,
            "shape_accessibility": shape_acc,
            "m6a_sites": m6a_count,
            "adar_risk": adar_score,
            "g4_risk": g4_risk,
            "normalized_score": normalized,
        }
        def _shown(value: float | None, digits: int) -> str:
            return "ÖLÇÜLMEDİ" if value is None else f"{value:.{digits}f}"

        logger.debug(
            f"biophysics_merger: {site_id} → ΔG={_shown(dg, 2)} "
            f"shape={_shown(shape_acc, 2)} normalized={_shown(normalized, 4)}"
        )

    payload: dict[str, Any] = {"biophysics_scores": biophysics_scores}
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"biophysics_merger: {len(biophysics_scores)} sites → {output_path}")
