"""Snakemake run() wrapper for Stage 7 score integration.

Reads the five stage merge JSONs, computes per-site DomainScores using the
ScoreIntegrator, and writes stage7_scores.json.

Stage JSON schemas (all dict-of-site-id → score-object):
    stage2_offtargets.json  → {offtarget_sites, mirbase_result, repeat_results,
                                sequence_scores}
    stage3_variants.json    → {variant_scores}      (normalized_score per site)
    stage4_epigenetic.json  → {epigenetic_scores,   cell_context}
    stage5_biophysics.json  → {biophysics_scores}   (normalized_score per site)
    stage6_execution.json   → {execution_scores}    (normalized_score per site)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from src.scoring.integrator import ScoreIntegrator
from src.core.models import DomainScores

_NEUTRAL = 0.5


def _clamp(value: Any) -> float:
    """Clamp upstream domain score to the [0, 1] contract of DomainScores.

    Why: stage producers (e.g. seed_aligner) emit raw alignment scores that
    can exceed 1.0; DomainScores rejects them with a Pydantic ValidationError.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return _NEUTRAL
    if v != v:  # NaN guard
        return _NEUTRAL
    return max(0.0, min(1.0, v))


def _load(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        logger.warning(f"score_integrator: {path} not found — using empty dict")
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"score_integrator: failed to parse {path}: {exc} — using empty dict")
        return {}


def run(
    offtargets_path: str,
    variants_path: str,
    epigenetic_path: str,
    biophysics_path: str,
    execution_path: str,
    weights: dict[str, float],
    output_path: str,
    log_path: str,
) -> None:
    """Compute weighted domain scores for every off-target site and write JSON.

    Args:
        offtargets_path: Path to stage2_offtargets.json.
        variants_path: Path to stage3_variants.json.
        epigenetic_path: Path to stage4_epigenetic.json.
        biophysics_path: Path to stage5_biophysics.json.
        execution_path: Path to stage6_execution.json.
        weights: Domain weight mapping (must sum to 1.0).
        output_path: Destination for stage7_scores.json.
        log_path: Log file path.
    """
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(log_path, level="DEBUG")
    logger.add(sys.stderr, level="INFO")

    logger.info("score_integrator: loading stage outputs")
    stage2 = _load(offtargets_path)
    stage3 = _load(variants_path)
    stage4 = _load(epigenetic_path)
    stage5 = _load(biophysics_path)
    stage6 = _load(execution_path)

    offtarget_sites: list[dict[str, Any]] = stage2.get("offtarget_sites", [])
    sequence_scores: dict[str, float] = stage2.get("sequence_scores", {})
    variant_scores: dict[str, Any] = stage3.get("variant_scores", {})
    epigenetic_scores: dict[str, Any] = stage4.get("epigenetic_scores", {})
    cell_context: dict[str, float] = stage4.get(
        "cell_context", {"atac_score": _NEUTRAL, "expression_score": _NEUTRAL, "execution_score": _NEUTRAL}
    )
    biophysics_scores: dict[str, Any] = stage5.get("biophysics_scores", {})
    execution_scores: dict[str, Any] = stage6.get("execution_scores", {})

    integrator = ScoreIntegrator()

    domain_scores_out: dict[str, dict[str, float]] = {}
    base_scores_out: dict[str, float] = {}

    site_ids: list[str] = list(
        dict.fromkeys(
            list(sequence_scores)
            + list(variant_scores)
            + list(epigenetic_scores)
            + list(biophysics_scores)
            + list(execution_scores)
        )
    )

    if not site_ids and offtarget_sites:
        site_ids = [f"{s['gene']}:{s['transcript_id']}" for s in offtarget_sites]

    for site_id in site_ids:
        seq = _clamp(sequence_scores.get(site_id, _NEUTRAL))
        var = _clamp(variant_scores.get(site_id, {}).get("normalized_score", _NEUTRAL))
        epi = _clamp(epigenetic_scores.get(site_id, {}).get("normalized_score", _NEUTRAL))
        bio = _clamp(biophysics_scores.get(site_id, {}).get("normalized_score", _NEUTRAL))
        exe = _clamp(execution_scores.get(site_id, {}).get("normalized_score", _NEUTRAL))

        ds = DomainScores(
            sequence_specificity=seq,
            variant_toxicity=var,
            epigenetic_context=epi,
            biophysics_structure=bio,
            execution_safety=exe,
        )

        base = integrator.integrate(ds, weights)
        domain_scores_out[site_id] = ds.model_dump()
        base_scores_out[site_id] = round(base, 6)
        logger.debug(f"site {site_id}: base_score={base:.4f}")

    payload: dict[str, Any] = {
        "offtarget_sites": offtarget_sites,
        "domain_scores": domain_scores_out,
        "base_scores": base_scores_out,
        "cell_context": cell_context,
        "weights": weights,
    }

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"score_integrator: wrote {len(site_ids)} sites → {output_path}")
