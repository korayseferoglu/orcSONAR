"""Snakemake run() adapter — merges Stage 6 execution & safety outputs."""

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
        logger.warning(f"execution_merger: {path} not found — using empty dict")
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"execution_merger: failed to parse {path}: {exc}")
        return {}



def _as_optional(value: Any) -> float | None:
    """Coerce a raw JSON value to a float, keeping an unknown unknown (B2)."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        logger.warning(f"execution_merger: unparseable value {value!r} — treated as unknown")
        return None

#: Channel weights; they sum to 1.0, so with everything measured the result is
#: unchanged from the fixed-weight version this replaced.
_WEIGHTS: dict[str, float] = {"ago2": 0.40, "rbp": 0.15, "circrna": 0.20, "immune": 0.25}


def _normalize(
    ago2_loading: float | None,
    rbp_competition: float | None,
    circrna_overlap: bool | None,
    immune_risk: float | None,
) -> float | None:
    """Compute normalised execution safety risk score in [0, 1].

    Higher score = more execution risk (more silencing activity expected).

    - High Ago2 loading → higher risk.
    - High RBP competition → blocks saRNA → lower risk, so it is inverted.
      Unlike the gnomAD channel (roadmap B4), the field name matches its
      contract here: `_competition_score` really does emit a competition level,
      and `1 - competition` is the risk it implies. Checked, not assumed.
    - circRNA sponge → potential off-target amplification.
    - Immune motifs → TLR activation risk.

    Ago2 and RBP come from eCLIP BigWigs and are ``None`` when nothing was
    measured (roadmap B2). An unknown channel is excluded and the remaining
    weights renormalised. Contributing a zero instead would lower the risk on
    the strength of data nobody has, and for Ago2 — the heaviest channel at
    0.40 — that single substitution moved a site most of the way to "safe".

    Args:
        ago2_loading: Ago2 loading score, or ``None`` if not measured.
        rbp_competition: RBP competition score, or ``None`` if not measured.
        circrna_overlap: Whether the site overlaps a circRNA.
        immune_risk: Immune-motif risk score.

    Returns:
        Score in [0, 1], or ``None`` if nothing was measured.
    """
    # All four channels can be unknown. circrna and immune used to be
    # unconditional numbers (`0.5 if overlap else 0.0`, and a `.get(..., 0.0)`),
    # so `weight_used == 0.0` below was dead code and this function could never
    # return None: a missing circRNA file read as "no sponge" and a missing
    # immune file as "no motifs", 0.45 of the weight contributing
    # measured-looking zeros from files nobody read (audit 2026-11-19).
    contributions: dict[str, float | None] = {
        "ago2": ago2_loading,
        "rbp": None if rbp_competition is None else max(0.0, 1.0 - rbp_competition),
        "circrna": None if circrna_overlap is None else (0.5 if circrna_overlap else 0.0),
        "immune": immune_risk,
    }
    total = 0.0
    weight_used = 0.0
    for name, value in contributions.items():
        if value is None:
            continue
        total += _WEIGHTS[name] * value
        weight_used += _WEIGHTS[name]
    if weight_used == 0.0:
        return None
    return min(1.0, round(total / weight_used, 4))


def run(
    ago2_path: str,
    rbp_path: str,
    circrna_path: str,
    immune_path: str,
    output_path: str,
    log_path: str,
) -> None:
    """Merge Ago2, RBP, circRNA, immune data into stage6_execution.json.

    Args:
        ago2_path: Path to stage6_ago2.json.
        rbp_path: Path to stage6_rbp.json.
        circrna_path: Path to stage6_circrna.json.
        immune_path: Path to stage6_immune.json.
        output_path: Destination for stage6_execution.json.
        log_path: Log file path.
    """
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(log_path, level="DEBUG")
    logger.add(sys.stderr, level="INFO")

    ago2_data = _load(ago2_path)
    rbp_data = _load(rbp_path)
    circrna_data = _load(circrna_path)
    immune_data = _load(immune_path)

    ago2_results: dict[str, Any] = ago2_data.get("ago2_results", {})
    rbp_results: dict[str, Any] = rbp_data.get("rbp_results", {})
    circrna_results: dict[str, Any] = circrna_data.get("circrna_results", {})
    offtarget_immune: dict[str, Any] = immune_data.get("offtarget_immune", {})
    sarna_immune: dict[str, Any] = immune_data.get("sarna_immune", {})

    all_site_ids: set[str] = (
        set(ago2_results)
        | set(rbp_results)
        | set(circrna_results)
        | set(offtarget_immune)
    )

    execution_scores: dict[str, Any] = {}
    for site_id in sorted(all_site_ids):
        # Absent from a stage's output means never measured there, which is the
        # same unknown as an explicit null — not a measured zero (roadmap B2).
        ago2 = _as_optional(ago2_results.get(site_id, {}).get("loading_score"))
        rbp = _as_optional(rbp_results.get(site_id, {}).get("competition_score"))
        raw_sponge = circrna_results.get(site_id, {}).get("sponge_risk")
        circrna_overlap = None if raw_sponge is None else bool(raw_sponge)
        immune_risk = _as_optional(
            offtarget_immune.get(site_id, sarna_immune).get("risk_score")
        )
        immune_motifs = [
            h.get("motif", "") if isinstance(h, dict) else str(h)
            for h in offtarget_immune.get(site_id, sarna_immune).get("motifs_found", [])
        ]

        normalized = _normalize(ago2, rbp, circrna_overlap, immune_risk)
        execution_scores[site_id] = {
            "ago2_loading": ago2,
            "rbp_competition": rbp,
            "circrna_overlap": circrna_overlap,
            "immune_motif_count": (
                None
                if (_hits := offtarget_immune.get(site_id, sarna_immune).get("total_hits"))
                is None
                else int(_hits)
            ),
            "immune_motifs_found": immune_motifs,
            "normalized_score": normalized,
        }
        # Formatting an unknown with `:.3f` raises, and this line sits inside
        # the per-site loop outside any try — so the very first null Ago2
        # killed run() before `_normalize`'s renormalisation (the behaviour
        # B2 is credited with) could ever write a score. epigenetic_merger
        # already guards its equivalent log line; this one did not
        # (audit 2026-11-19, Bulgu 6).
        def _shown(value: float | None, digits: int) -> str:
            return "ÖLÇÜLMEDİ" if value is None else f"{value:.{digits}f}"

        logger.debug(
            f"execution_merger: {site_id} → ago2={_shown(ago2, 3)} "
            f"rbp={_shown(rbp, 3)} normalized={_shown(normalized, 4)}"
        )

    payload: dict[str, Any] = {"execution_scores": execution_scores}
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"execution_merger: {len(execution_scores)} sites → {output_path}")
