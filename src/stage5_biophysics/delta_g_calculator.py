"""Snakemake run() adapter for Stage 5 Turner nearest-neighbor ΔG calculation."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from src.stage5_biophysics.thermodynamics import TurnerCalculator

# No ΔG → risk mapping lives here any more (roadmap C3d), and nothing replaced
# it. `C3` closed on the grounds that the literature offers no transportable
# per-site ΔG threshold; the physics fix it made stands, but the grounds were
# wrong — per-site scoring functions exist (RIsearch2, PMID 28108657; PITA's
# ddG, PMID 17893677). What the literature does not offer is a *threshold*, and
# it declines to offer one deliberately: PITA states "our model employs no such
# parameters or thresholds", context++ is a percentile-scaled regression, Lu &
# Mathews use continuous features. The two published cutoffs (Shao 2007,
# RNAxs) are accessibility quantities fitted to labelled data, so they do not
# transport to a duplex energy — and no scale makes -30/-25 right.
#
# Keeping the old mapping would be worse than deleting it, for reasons that are
# measured rather than stylistic. Kamola et al. 2015 (PMID 26657993, Ui-Tei's
# own group) report that "siRNA with high GC content in the non-seed region
# have 'weaker' off-target effects" and that high GC in target positions 8-15
# *reduces* off-target potency (r = 0.23, p = 1.2e-13) — so a monotone
# "more negative ⇒ riskier" score has the **sign inverted** over the duplex's
# 3' half. The same paper objects to the calculation itself: "the currently
# established calculation procedure of thermodynamic profiles is not applicable
# for such **discontinuous** duplexes", which is exactly what a Turner
# nearest-neighbour sum over a mismatched 20-mer is.
#
# So this module emits the raw per-site energy in native units (rule 10) and
# **no derived score**. Choosing a mapping now would be an unregistered
# modelling decision taken after seeing the data, which is what `A10` and
# invariant 6 exist to prevent. The accessibility term that makes the energy
# interpretable is `C3e`.


def run(
    sarna_sequence: str,
    offtargets_path: str,
    turner_dir: str,
    output_path: str,
    log_path: str,
) -> None:
    """Compute RNA:DNA hybrid ΔG for each off-target site and write stage5_deltag.json.

    Args:
        sarna_sequence: saRNA guide strand (DNA or RNA).
        offtargets_path: Path to stage2_offtargets.json.
        turner_dir: Directory containing Turner parameter files.
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
        window = s.get("target_window")
        try:
            if calc is None:
                dg = None
                has_mm = None
            elif not window:
                # No target to bind to is not a measurement (invariant 2).
                # Pre-C3 runs have no target_window at all.
                logger.warning(
                    f"delta_g_calculator: {site_id} has no target_window — "
                    f"ΔG is unknown, not neutral"
                )
                dg = None
                has_mm = None
            else:
                # The OFF-TARGET window, not the saRNA's own complement. The
                # old code built `revcomp(saRNA)` and used it for every site,
                # so one identical ΔG covered a whole run (roadmap C3).
                #
                # `calculate_duplex_dg` documents its contract as "target:
                # Complementary strand 3'→5' relative to sarna (same index
                # alignment), target[i] is paired with sarna[i]". A window
                # read 5'→3' therefore has to be REVERSED to be index-aligned
                # — it must not also be complemented, which is what the stray
                # `reversed()` on top of a complement amounted to. Measured:
                # the documented orientation gives -43.80 on a perfect
                # duplex, the old one +31.10 with 18/20 "mismatches".
                target = window.upper().replace("T", "U")[::-1]
                result = calc.calculate_duplex_dg(sarna_rna, target)
                dg = result.delta_g
                has_mm = result.has_mismatches
        except Exception as exc:
            logger.debug(f"delta_g_calculator: ΔG failed for {site_id}: {exc}")
            dg = None
            has_mm = None

        deltag_results[site_id] = {
            "delta_g": None if dg is None else round(dg, 4),
            "has_mismatches": has_mm,
            # Deliberately always null until a mapping is pre-registered (C3d).
            # The field is kept rather than dropped so a consumer reading it
            # gets an explicit "not derived" instead of a KeyError it might
            # paper over with a default.
            "risk_score": None,
        }
        shown = "ÖLÇÜLMEDİ" if dg is None else f"ΔG={dg:.2f} (skor ön kayıt bekliyor)"
        logger.debug(f"delta_g_calculator: {site_id} → {shown}")

    payload: dict[str, Any] = {"deltag_results": deltag_results}
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"delta_g_calculator: {len(deltag_results)} sites → {output_path}")
