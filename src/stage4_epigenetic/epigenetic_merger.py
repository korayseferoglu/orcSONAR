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


def _as_optional(value: Any) -> float | None:
    """Coerce a raw JSON value to a float, keeping an unknown unknown.

    ``None`` — whether it was an explicit ``null`` or a site absent from a
    channel's output — stays ``None``. Both mean the same thing: nothing was
    measured here (roadmap B2).

    Args:
        value: Raw value from a stage JSON.

    Returns:
        The value as a float, or ``None`` if it was absent or unparseable.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        logger.warning(f"epigenetic_merger: unparseable signal {value!r} — treated as unknown")
        return None


def _mean_of_known(values: list[float | None]) -> float | None:
    """Mean over the measured values, or ``None`` if none were measured.

    Counting unknowns as zeros would drag a cell-level mean toward "closed
    chromatin" / "not expressed", which is the safe-looking direction.

    Args:
        values: Per-site values, some possibly unknown.

    Returns:
        Mean of the known values, or ``None``.
    """
    known = [v for v in values if v is not None]
    return sum(known) / len(known) if known else None


def _round_or_none(value: float | None, digits: int = 4) -> float | None:
    """Round a value, or pass an unknown through untouched."""
    return None if value is None else round(value, digits)


#: Channel weights and the saturation each raw signal is scaled against. They
#: sum to 1.0, so with every channel measured the result is unchanged from the
#: fixed-weight version this replaced.
_CHANNELS: dict[str, tuple[float, float]] = {
    "atac": (0.25, _ATAC_SAT),
    "h3k4me3": (0.15, _H3K4ME3_SAT),
    "h3k27ac": (0.15, _H3K27AC_SAT),
    "groseq": (0.10, _GROSEQ_SAT),
    "hic": (0.15, _HIC_SAT),
    "ccle": (0.20, _CCLE_SAT),
}


def _normalize_signal(raw: float | None, saturation: float) -> float | None:
    """Scale a raw signal into [0, 1], propagating an unknown unchanged.

    ``None`` means the source could not be read (roadmap B2). It is never
    turned into a number here. A 0.0 would assert "no signal", and for every
    source in this stage less signal reads as *lower* risk — which is how a
    dead source produced a site that looked safe rather than an error
    (AUDIT.md Bulgu-10).

    Args:
        raw: Raw signal in native units, or ``None`` if not measured.
        saturation: Value mapped to 1.0.

    Returns:
        Normalised signal, or ``None`` if the input was unknown.
    """
    if raw is None:
        return None
    return min(1.0, max(0.0, raw / saturation)) if saturation > 0 else 0.0


def _compute_normalized(
    atac: float | None,
    h3k4me3: float | None,
    h3k27ac: float | None,
    groseq: float | None,
    hic: float | None,
    ccle: float | None,
) -> float | None:
    """Weighted epigenetic score over the channels that were measured.

    An unknown channel is **excluded** and the remaining weights are
    renormalised, rather than contributing a zero. Contributing zero would pull
    the score toward "safe" on the strength of data nobody has — the whole of
    Bulgu-10. Excluding it reports what the measured channels actually say.

    Whether a score may be produced at all when too little was measured is a
    separate question with a separate answer: roadmap ``B3`` adds ``coverage``
    and refuses below a threshold. This function only declines the degenerate
    case where *nothing* was measured.

    Args:
        atac: Raw ATAC signal, or ``None``.
        h3k4me3: Raw H3K4me3 signal, or ``None``.
        h3k27ac: Raw H3K27ac signal, or ``None``.
        groseq: Raw nascent-transcription signal, or ``None``.
        hic: Raw Hi-C contact, or ``None``.
        ccle: Raw CCLE expression, or ``None``.

    Returns:
        Score in [0, 1], or ``None`` if no channel was measured.
    """
    raw: dict[str, float | None] = {
        "atac": atac,
        "h3k4me3": h3k4me3,
        "h3k27ac": h3k27ac,
        "groseq": groseq,
        "hic": hic,
        "ccle": ccle,
    }
    total = 0.0
    weight_used = 0.0
    for name, value in raw.items():
        weight, saturation = _CHANNELS[name]
        normalised = _normalize_signal(value, saturation)
        if normalised is None:
            continue
        total += weight * normalised
        weight_used += weight
    if weight_used == 0.0:
        return None
    return round(total / weight_used, 4)


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
        # Absent from a channel's output means never measured there, which is
        # the same unknown as an explicit null — not a measured zero (B2).
        atac = _as_optional(atac_signals.get(site_id))
        k4 = _as_optional(h3k4me3_signals.get(site_id))
        k27 = _as_optional(h3k27ac_signals.get(site_id))
        gro = _as_optional(groseq_signals.get(site_id))
        hic = _as_optional(hic_contacts.get(site_id))
        ccle_expr = _as_optional(ccle_results.get(gene, {}).get("expression_value"))

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
        shown = "ÖLÇÜLMEDİ" if normalized is None else f"{normalized:.4f}"
        logger.debug(f"epigenetic_merger: {site_id} → normalized={shown}")

    # Cell-level context, averaged over the sites that were actually measured.
    # An unknown is skipped rather than counted as zero: a mean dragged down by
    # missing data reads as closed chromatin or an unexpressed gene, and both
    # of those lower the final risk (B2 / AUDIT.md Bulgu-10).
    mean_atac = _mean_of_known([v["atac_signal"] for v in epigenetic_scores.values()])
    mean_ccle = _mean_of_known([v["ccle_expression"] for v in epigenetic_scores.values()])
    mean_norm = _mean_of_known([v["normalized_score"] for v in epigenetic_scores.values()])

    cell_context: dict[str, float | None] = {
        "atac_score": _round_or_none(_normalize_signal(mean_atac, _ATAC_SAT)),
        "expression_score": _round_or_none(_normalize_signal(mean_ccle, _CCLE_SAT)),
        "execution_score": _round_or_none(mean_norm),
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
