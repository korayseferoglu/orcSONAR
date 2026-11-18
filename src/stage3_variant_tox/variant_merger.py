"""Snakemake run() adapter — merges Stage 3 variant & toxicity outputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger

_NEUTRAL = 0.5


def _load(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        logger.warning(f"variant_merger: {path} not found — using empty dict")
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"variant_merger: failed to parse {path}: {exc}")
        return {}


def _normalize(
    cosmic: dict[str, Any],
    gnomad: dict[str, Any],
    clinvar: dict[str, Any],
    phylop: dict[str, Any],
) -> float:
    """Compute normalized variant toxicity score in [0, 1]."""
    cosmic_risk = float(cosmic.get("density_score", 0.0))
    tier1_boost = 0.15 if cosmic.get("has_tier1_gene", False) else 0.0
    # `polymorphism_score` is named for what was measured but its contract is
    # already a RISK score, as gnomad_client's own docstring states: no common
    # variants -> conserved -> 1.0; a common variant present -> tolerated ->
    # 0.0. So it is used as-is. Inverting it here (`1.0 - score`) read the
    # field name instead of the contract and pointed the whole channel
    # backwards: every conserved site scored zero risk and every polymorphic
    # one scored maximum (roadmap B4). The default also matters — a missing
    # field becomes 1.0, the risky end, which is the direction absent data must
    # fail in (invariant 2).
    gnomad_risk = float(gnomad.get("polymorphism_score", 1.0))
    clinvar_risk = 0.8 if clinvar.get("pathogenic_count", 0) > 0 else (
        0.4 if clinvar.get("likely_pathogenic_count", 0) > 0 else 0.0
    )
    phylop_risk = float(phylop.get("conservation_score", 0.5))

    score = (
        0.30 * cosmic_risk
        + 0.20 * gnomad_risk
        + 0.25 * clinvar_risk
        + 0.25 * phylop_risk
        + tier1_boost
    )
    return min(1.0, round(score, 4))


def run(
    cosmic_path: str,
    gnomad_path: str,
    clinvar_path: str,
    phylop_path: str,
    output_path: str,
    log_path: str,
) -> None:
    """Merge COSMIC, gnomAD, ClinVar, phyloP into stage3_variants.json.

    Computes a ``normalized_score`` in [0, 1] for each off-target site as a
    weighted combination of the four data sources.

    Args:
        cosmic_path: Path to stage3_cosmic.json.
        gnomad_path: Path to stage3_gnomad.json.
        clinvar_path: Path to stage3_clinvar.json.
        phylop_path: Path to stage3_phylop.json.
        output_path: Destination for stage3_variants.json.
        log_path: Log file path.
    """
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(log_path, level="DEBUG")
    logger.add(sys.stderr, level="INFO")

    cosmic_data = _load(cosmic_path)
    gnomad_data = _load(gnomad_path)
    clinvar_data = _load(clinvar_path)
    phylop_data = _load(phylop_path)

    cosmic_results: dict[str, Any] = cosmic_data.get("cosmic_results", {})
    gnomad_results: dict[str, Any] = gnomad_data.get("gnomad_results", {})
    clinvar_results: dict[str, Any] = clinvar_data.get("clinvar_results", {})
    phylop_results: dict[str, Any] = phylop_data.get("phylop_results", {})

    all_site_ids: set[str] = (
        set(cosmic_results)
        | set(gnomad_results)
        | set(clinvar_results)
        | set(phylop_results)
    )

    variant_scores: dict[str, Any] = {}
    for site_id in sorted(all_site_ids):
        cosmic = cosmic_results.get(site_id, {})
        gnomad = gnomad_results.get(site_id, {})
        clinvar = clinvar_results.get(site_id, {})
        phylop = phylop_results.get(site_id, {})

        normalized = _normalize(cosmic, gnomad, clinvar, phylop)

        variant_scores[site_id] = {
            "cosmic_count": int(cosmic.get("mutation_count", 0)),
            "cosmic_mutations": [
                m.get("so_term", "") for m in cosmic.get("mutations", [])
            ],
            "gnomad_max_af": float(gnomad.get("max_af", 0.0)),
            "clinvar_pathogenic": clinvar.get("pathogenic_count", 0) > 0,
            "phylop_score": float(phylop.get("conservation_score", 0.5)),
            "normalized_score": normalized,
        }
        logger.debug(f"variant_merger: {site_id} → normalized_score={normalized:.4f}")

    payload: dict[str, Any] = {"variant_scores": variant_scores}
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"variant_merger: {len(variant_scores)} sites → {output_path}")
