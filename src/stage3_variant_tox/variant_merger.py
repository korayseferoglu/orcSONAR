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
) -> float | None:
    """Weighted variant-toxicity score over the channels that were measured.

    An unknown channel is **excluded** and the remaining weights renormalised,
    matching what B2 did for the epigenetic and execution mergers. Before this,
    a missing COSMIC record scored 0.0 and a missing ClinVar record scored 0.0
    — both the *safe* end — so a source that failed made a site look cleaner
    than one that was measured, and a site with no variant data at all scored a
    fabricated 0.325 (audit 2026-11-19, Bulgu 2).

    ⚠️ Two notes on what this does and does not settle:

    * Excluding-and-renormalising is a modelling choice, and the audit's
      statistical review argues it pre-empted roadmap ``B3``. It is matched
      here anyway because four mergers using three different rules is worse:
      ``B3`` can then change one rule in one place.
    * It supersedes ``B4``'s "a missing field defaults to 1.0, the risky end".
      That default was fabricated too — it claims a site is maximally
      conserved when nobody measured it. ``B4``'s actual fix, dropping the
      ``1.0 - score`` inversion, is untouched.

    Returns:
        Score in [0, 1], or ``None`` if no channel was measured.
    """
    cosmic_risk = (
        float(cosmic["density_score"]) if cosmic.get("density_score") is not None else None
    )
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
    gnomad_risk = (
        float(gnomad["polymorphism_score"])
        if gnomad.get("polymorphism_score") is not None
        else None
    )
    if clinvar.get("pathogenic_count") is None and clinvar.get("likely_pathogenic_count") is None:
        clinvar_risk = None
    else:
        clinvar_risk = 0.8 if clinvar.get("pathogenic_count", 0) > 0 else (
            0.4 if clinvar.get("likely_pathogenic_count", 0) > 0 else 0.0
        )
    phylop_risk = (
        float(phylop["conservation_score"])
        if phylop.get("conservation_score") is not None
        else None
    )

    contributions: dict[str, tuple[float, float | None]] = {
        "cosmic": (0.30, cosmic_risk),
        "gnomad": (0.20, gnomad_risk),
        "clinvar": (0.25, clinvar_risk),
        "phylop": (0.25, phylop_risk),
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

    # The tier-1 boost rides on COSMIC, so it only applies when COSMIC spoke.
    score = total / weight_used + (tier1_boost if cosmic_risk is not None else 0.0)
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

        # The reported fields follow the same rule as the score: a channel
        # that was not measured is reported as unknown, not as a confident
        # zero/False/0.5. These values reach the HTML report, where a
        # fabricated "0 COSMIC mutations" reads exactly like a measured one.
        variant_scores[site_id] = {
            "cosmic_count": (
                int(cosmic["mutation_count"])
                if cosmic.get("mutation_count") is not None
                else None
            ),
            "cosmic_mutations": [
                m.get("so_term", "") for m in cosmic.get("mutations", [])
            ],
            "gnomad_max_af": (
                float(gnomad["max_af"]) if gnomad.get("max_af") is not None else None
            ),
            "clinvar_pathogenic": (
                clinvar["pathogenic_count"] > 0
                if clinvar.get("pathogenic_count") is not None
                else None
            ),
            "phylop_score": (
                float(phylop["conservation_score"])
                if phylop.get("conservation_score") is not None
                else None
            ),
            "normalized_score": normalized,
        }
        shown = "ÖLÇÜLMEDİ" if normalized is None else f"{normalized:.4f}"
        logger.debug(f"variant_merger: {site_id} → normalized_score={shown}")

    payload: dict[str, Any] = {"variant_scores": variant_scores}
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"variant_merger: {len(variant_scores)} sites → {output_path}")
