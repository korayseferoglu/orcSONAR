"""Snakemake run() adapter — merges Stage 4 epigenetic & topology outputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger

_NEUTRAL = 0.5

# Saturation constants for signal normalization
_ATAC_SAT = 50.0
_H3K4ME3_SAT = 20.0
_H3K27AC_SAT = 20.0
_GROSEQ_SAT = 10.0
_HIC_SAT = 1.0
_CCLE_SAT = 8.0  # log2(TPM+1) typical max


def _load(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        logger.warning(f"epigenetic_merger: {path} not found — using empty dict")
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"epigenetic_merger: failed to parse {path}: {exc}")
        return {}


def _normalize_signal(raw: float, saturation: float) -> float:
    return min(1.0, max(0.0, raw / saturation)) if saturation > 0 else 0.0


def _compute_normalized(
    atac: float,
    h3k4me3: float,
    h3k27ac: float,
    groseq: float,
    hic: float,
    ccle: float,
) -> float:
    atac_n = _normalize_signal(atac, _ATAC_SAT)
    k4_n = _normalize_signal(h3k4me3, _H3K4ME3_SAT)
    k27_n = _normalize_signal(h3k27ac, _H3K27AC_SAT)
    gro_n = _normalize_signal(groseq, _GROSEQ_SAT)
    hic_n = _normalize_signal(hic, _HIC_SAT)
    ccle_n = _normalize_signal(ccle, _CCLE_SAT)
    return round(
        0.25 * atac_n
        + 0.15 * k4_n
        + 0.15 * k27_n
        + 0.10 * gro_n
        + 0.15 * hic_n
        + 0.20 * ccle_n,
        4,
    )


def run(
    atac_path: str,
    histones_path: str,
    groseq_path: str,
    hic_path: str,
    ccle_path: str,
    output_path: str,
    log_path: str,
) -> None:
    """Merge ATAC, histone, GRO-seq, Hi-C, CCLE into stage4_epigenetic.json.

    Args:
        atac_path: Path to stage4_atac.json.
        histones_path: Path to stage4_histones.json.
        groseq_path: Path to stage4_groseq.json.
        hic_path: Path to stage4_hic.json.
        ccle_path: Path to stage4_ccle.json.
        output_path: Destination for stage4_epigenetic.json.
        log_path: Log file path.
    """
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(log_path, level="DEBUG")
    logger.add(sys.stderr, level="INFO")

    atac_data = _load(atac_path)
    histones_data = _load(histones_path)
    groseq_data = _load(groseq_path)
    hic_data = _load(hic_path)
    ccle_data = _load(ccle_path)

    atac_signals: dict[str, float] = atac_data.get("atac_signals", {})
    h3k4me3_signals: dict[str, float] = histones_data.get("h3k4me3_signals", {})
    h3k27ac_signals: dict[str, float] = histones_data.get("h3k27ac_signals", {})
    groseq_signals: dict[str, float] = groseq_data.get("groseq_signals", {})
    hic_contacts: dict[str, float] = hic_data.get("hic_contacts", {})
    ccle_results: dict[str, Any] = ccle_data.get("ccle_results", {})

    all_site_ids: set[str] = (
        set(atac_signals)
        | set(h3k4me3_signals)
        | set(groseq_signals)
        | set(hic_contacts)
    )

    epigenetic_scores: dict[str, Any] = {}
    for site_id in sorted(all_site_ids):
        # CCLE is keyed by gene, not by site. site_id puts the gene at field 0
        # by contract — pinned by tests/unit/test_models.py::test_site_id_layout.
        # If that ever changes, this lookup misses for every site and silently
        # degrades expression to 0.0.
        gene = site_id.split(":", 1)[0]
        atac = float(atac_signals.get(site_id, 0.0))
        k4 = float(h3k4me3_signals.get(site_id, 0.0))
        k27 = float(h3k27ac_signals.get(site_id, 0.0))
        gro = float(groseq_signals.get(site_id, 0.0))
        hic = float(hic_contacts.get(site_id, 0.0))
        ccle_expr = float(
            ccle_results.get(gene, {}).get("expression_value", 0.0)
        )

        normalized = _compute_normalized(atac, k4, k27, gro, hic, ccle_expr)
        epigenetic_scores[site_id] = {
            "atac_signal": atac,
            "h3k4me3_signal": k4,
            "h3k27ac_signal": k27,
            "groseq_signal": gro,
            "hic_contact": hic,
            "ccle_expression": ccle_expr,
            "normalized_score": normalized,
        }
        logger.debug(f"epigenetic_merger: {site_id} → normalized={normalized:.4f}")

    # Compute cell-level context scores (means across sites)
    n = max(len(epigenetic_scores), 1)
    mean_atac = sum(v["atac_signal"] for v in epigenetic_scores.values()) / n
    mean_ccle = sum(v["ccle_expression"] for v in epigenetic_scores.values()) / n
    mean_norm = sum(v["normalized_score"] for v in epigenetic_scores.values()) / n

    cell_context: dict[str, float] = {
        "atac_score": round(_normalize_signal(mean_atac, _ATAC_SAT), 4),
        "expression_score": round(_normalize_signal(mean_ccle, _CCLE_SAT), 4),
        "execution_score": round(mean_norm, 4),
    }

    payload: dict[str, Any] = {
        "epigenetic_scores": epigenetic_scores,
        "cell_context": cell_context,
    }
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(
        f"epigenetic_merger: {len(epigenetic_scores)} sites — "
        f"cell_context={cell_context} → {output_path}"
    )
