#!/usr/bin/env python3
"""Audit the scientific health of one completed orcSONAR run.

Usage:  verify_run.py {gene}_{cell_line} [--results-dir results] [--json]

Reads results/{gene}_{cell_line}/*.json and answers six questions that a green
Snakemake exit does not: does any metric actually vary across sites, are the
values physically possible, do the stages agree on where each site is, how much
of the run is real data versus neutral fallback, does the score range ever
reach its upper classes, and does normalisation flatten the raw signals before
they get to the score.

Exit status is 0 when every check passes, 1 when any check fails, 2 when the
run cannot be read at all.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
from typing import Any

# --------------------------------------------------------------------------
# Where the per-site numbers live. Each entry: file -> top-level key holding a
# {site_id: {...}} mapping, or a {site_id: scalar} mapping.
# --------------------------------------------------------------------------

SITE_MAPS: list[tuple[str, str]] = [
    ("stage2_repeats.json", "repeat_results"),
    ("stage3_clinvar.json", "clinvar_results"),
    ("stage3_cosmic.json", "cosmic_results"),
    ("stage3_gnomad.json", "gnomad_results"),
    ("stage3_phylop.json", "phylop_results"),
    ("stage3_variants.json", "variant_scores"),
    ("stage4_atac.json", "atac_signals"),
    ("stage4_ccle.json", "ccle_results"),
    ("stage4_epigenetic.json", "epigenetic_scores"),
    ("stage4_groseq.json", "groseq_signals"),
    ("stage4_hic.json", "hic_contacts"),
    ("stage4_histones.json", "h3k4me3_signals"),
    ("stage4_histones.json", "h3k27ac_signals"),
    ("stage4_histones.json", "h3k27me3_signals"),
    ("stage5_adar.json", "adar_results"),
    ("stage5_biophysics.json", "biophysics_scores"),
    ("stage5_deltag.json", "deltag_results"),
    ("stage5_g4.json", "g4_results"),
    ("stage5_m6a.json", "m6a_results"),
    ("stage5_shape.json", "shape_results"),
    ("stage6_ago2.json", "ago2_results"),
    ("stage6_circrna.json", "circrna_results"),
    ("stage6_execution.json", "execution_scores"),
    ("stage6_immune.json", "offtarget_immune"),
    ("stage6_rbp.json", "rbp_results"),
    ("stage7_classification.json", "site_classifications"),
]

# Fields that are labels or free-form, never a measured quantity.
NON_METRIC = {"cell_line", "gene", "rbp_name", "risk_class", "risk_level", "transcript_id"}

# Collection fields: their length is the metric, not their content.
COUNTED = {"mutations", "variants", "repeats", "motifs", "sites", "overlapping_circrnas",
           "motifs_found", "immune_motifs_found", "g4_motifs"}

# Physical-plausibility rules: field name -> (low, high, note). None = unbounded.
RANGE_RULES: dict[str, tuple[float | None, float | None, str]] = {
    "delta_g": (None, 0.0, "duplex ΔG must be negative (kcal/mol); positive means no duplex formed"),
    "conservation_score": (0.0, 1.0, "phyloP-derived conservation is normalised to [0,1]"),
    "mean_score": (-20.0, 10.0, "raw phyloP score"),
    "max_af": (0.0, 1.0, "allele frequency"),
    "expression_percentile": (0.0, 100.0, "percentile"),
}
SCORE_SUFFIXES = ("_score", "_risk", "_signal", "_fraction", "_accessibility", "_contact", "_density")

# --------------------------------------------------------------------------
# Raw-signal fields — measured quantities stored deliberately UNnormalised.
#
# stage4_epigenetic.json keeps ATAC fold-change, ChIP fold-change, Hi-C
# contact frequency, GRO-seq coverage and CCLE log2(TPM+1) in their native
# units; normalisation happens in the consumers, against the saturation
# constants below. Applying the [0,1] score rule to them is therefore a false
# positive — an H3K4me3 fold-change of 24 is a strong promoter, not a bug.
# Check 2 keeps only the rule that is genuinely physical for them (a
# fold-change or a coverage cannot be negative) and audits `normalized_score`,
# the field that actually claims to be in [0,1], instead.
#
# What can go wrong with a raw signal is saturation, which check 6 measures:
# normalisation is a saturating ramp, min(1, raw / SAT), so every site at or
# above SAT collapses to exactly 1.0 and stops being distinguishable from any
# other saturated site.
#
# The two consumers do not agree on the constants, so both are reported.
# --------------------------------------------------------------------------
RAW_SIGNAL_TABLES = {"stage4_epigenetic.json:epigenetic_scores"}

SATURATION_SETS: list[tuple[str, dict[str, float]]] = [
    (
        "src/scoring/domain_scores.py:42-46 -> the risk score",
        {"atac_signal": 10.0, "h3k4me3_signal": 15.0, "h3k27ac_signal": 15.0,
         "h3k27me3_signal": 15.0, "groseq_signal": 5.0, "hic_contact": 0.2,
         "ccle_expression": 6.0},
    ),
    (
        "src/stage4_epigenetic/epigenetic_merger.py:15-20 -> normalized_score",
        {"atac_signal": 50.0, "h3k4me3_signal": 20.0, "h3k27ac_signal": 20.0,
         "groseq_signal": 10.0, "hic_contact": 1.0, "ccle_expression": 8.0},
    ),
]

RAW_SIGNAL_FIELDS = {f for _, consts in SATURATION_SETS for f in consts}

SATURATED_FAIL_PCT = 50.0  # past half the sites, the metric ranks nothing

# --------------------------------------------------------------------------
# TWO sentinels, in two different spaces (AUDIT.md Bulgu-10).
#
# CLAUDE.md documents graceful degradation as a neutral score-space value, and
# one merger does define such a constant while never reading it. The value, the
# module and why writing it would not have fixed anything are invariant 2's
# (`.claude/rules/00-degismezler.md`) and are not restated here.
#
# Production used to substitute `_NEUTRAL_SIGNAL = 0.0` in RAW-SIGNAL space,
# reached from six modules (ATAC, the three histone marks, GRO-seq, Ago2, RBP).
# 0.5 and 0.0 mean opposite things in a safety tool: 0.5 is "unknown", 0.0 is
# "no signal", and for every one of those sources less signal reads as LOWER
# risk, so a failed source pushed a site toward SAFE.
#
# **Roadmap B2 changed this, and this comment used to claim otherwise.** The
# fallback is now an explicit unknown — `null` in the JSON — and a raw `0.0`
# means the assay covered the locus and recorded nothing. So there are three
# things to count, not two:
#
#   null  not measured. ATTRIBUTABLE on its own: this is the unavailability
#         rate the check was built to report, and before B2 it could not be
#         measured at all.
#   0.0   a measured zero under today's contract — but still the fallback in
#         any run produced BEFORE B2. The result JSON cannot date itself
#         (SCIENTIFIC_ROADMAP.md H10 adds a run manifest), so it is reported
#         without being attributed, and the wording says which reading applies
#         to which era rather than asserting one.
#   0.5   the documented score-space contract, still reached through
#         `score_integrator._clamp(None)`. B3 replaces it with a coverage
#         threshold that refuses to score.
#
# Counting nulls is not cosmetic: `is_number()` drops them, so after B2 the
# old accounting would have shown the fallback rate FALLING — an improvement
# that never happened.
# --------------------------------------------------------------------------
SENTINEL_SCORE = 0.5  # the documented contract; expected to be unreachable
MEASURED_ZERO = 0.0  # post-B2: a real zero; pre-B2 runs: the old fallback

# Fields held in raw-signal space, where `null` means not measured.
NO_DATA_FIELDS = RAW_SIGNAL_FIELDS | {"raw_signal"}


def load(path: str) -> Any | None:
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and not math.isnan(float(value))


def site_metrics(blob: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Normalise a {site: {...}} or {site: scalar} mapping to {site: {field: value}}."""
    out: dict[str, dict[str, Any]] = {}
    for site, value in blob.items():
        if isinstance(value, dict):
            fields = {}
            for key, item in value.items():
                if key in NON_METRIC or key == "region":
                    continue
                if key in COUNTED and isinstance(item, list):
                    fields[f"{key}[n]"] = len(item)
                elif is_number(item) or isinstance(item, bool):
                    fields[key] = item
            out[site] = fields
        elif is_number(value) or isinstance(value, bool):
            out[site] = {"value": value}
    return out


def collect(run_dir: str) -> dict[str, dict[str, dict[str, Any]]]:
    """{'file:key': {site: {field: value}}} for every per-site map present."""
    tables: dict[str, dict[str, dict[str, Any]]] = {}
    for filename, key in SITE_MAPS:
        blob = load(os.path.join(run_dir, filename))
        if not isinstance(blob, dict):
            continue
        inner = blob.get(key)
        if isinstance(inner, dict) and inner:
            tables[f"{filename}:{key}"] = site_metrics(inner)
    return tables


def reference_regions(run_dir: str) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """Every seed-hit region stage 2 recorded per site.

    Stage 2 emits a *list*, so one gene:transcript can carry several hits with
    different mismatch counts. Downstream stages store a dict keyed by
    gene:transcript, which silently collapses those to one — and different
    stages keep different ones. Keeping all of them here is what makes that
    collapse visible: the best hit (fewest mismatches) is the locus a stage
    should be using.
    """
    blob = load(os.path.join(run_dir, "stage2_offtargets.json")) or {}
    regions: dict[str, list[dict[str, Any]]] = {}
    for site in blob.get("offtarget_sites", []) or []:
        if not isinstance(site, dict) or not isinstance(site.get("region"), dict):
            continue
        # Prefer the id stage 2 actually stored — that is what the downstream
        # dicts are keyed on. Rebuilding it here would silently stop matching
        # the moment the format changes, leaving check 3 comparing empty sets
        # and reporting PASS having checked nothing.
        site_id = site.get("site_id")
        if not isinstance(site_id, str) or not site_id:
            site_id = f"{site.get('gene')}:{site.get('transcript_id')}"  # pre-Bulgu-2 runs
        entry = dict(site["region"])
        entry["_mismatches"] = site.get("mismatches")
        regions.setdefault(site_id, [])
        if entry not in regions[site_id]:
            regions[site_id].append(entry)
    multi = sorted(s for s, hits in regions.items() if len(hits) > 1)
    return regions, multi


def best_hit(hits: list[dict[str, Any]]) -> dict[str, Any]:
    """The hit a stage ought to use: fewest mismatches, earliest on ties."""
    return min(hits, key=lambda h: (h.get("_mismatches") if h.get("_mismatches") is not None else 1e9))


def same_locus(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return a.get("chrom") == b.get("chrom") and a.get("start") == b.get("start") and a.get("end") == b.get("end")


def region_maps(run_dir: str) -> dict[str, dict[str, dict[str, Any]]]:
    """Every per-site `region` a downstream stage recorded, by file."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for filename, key in SITE_MAPS:
        blob = load(os.path.join(run_dir, filename))
        if not isinstance(blob, dict):
            continue
        inner = blob.get(key)
        if not isinstance(inner, dict):
            continue
        regions = {
            site: value["region"]
            for site, value in inner.items()
            if isinstance(value, dict) and isinstance(value.get("region"), dict)
        }
        if regions:
            out[filename] = regions
    return out


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

def check_degeneracy(tables) -> tuple[bool, list[str], list[dict]]:
    lines, findings = [], []
    for table, sites in sorted(tables.items()):
        n = len(sites)
        if n < 2:
            continue
        fields = sorted({f for v in sites.values() for f in v})
        for field in fields:
            values = [v[field] for v in sites.values() if field in v]
            if len(values) < 2:
                continue
            distinct = len({(type(x).__name__, x) for x in values})
            if distinct == 1:
                findings.append({"table": table, "metric": field, "sites": len(values),
                                 "distinct": 1, "constant": values[0]})
                lines.append(f"  FAIL  {table}  {field}: 1 distinct value across "
                             f"{len(values)} sites (every site = {values[0]!r})")
    ok = not findings
    if ok:
        lines.append("  every per-site metric varies across sites")
    return ok, lines, findings


def check_ranges(tables) -> tuple[bool, list[str], list[dict]]:
    lines, findings = [], []
    for table, sites in sorted(tables.items()):
        fields = sorted({f for v in sites.values() for f in v})
        for field in fields:
            values = [v[field] for v in sites.values() if field in v and is_number(v[field])]
            if not values:
                continue
            base = field.split("[")[0]
            if table in RAW_SIGNAL_TABLES and base in RAW_SIGNAL_FIELDS:
                # Raw by design (see RAW_SIGNAL_TABLES): the only physical
                # rule left is that it cannot be negative. Saturation, the
                # failure mode that does apply, is check 6.
                low, high, note = 0.0, None, "a raw fold-change / coverage cannot be negative"
            elif base in RANGE_RULES:
                low, high, note = RANGE_RULES[base]
            elif base.endswith(SCORE_SUFFIXES) or base in ("normalized_score", "final_score", "base_score"):
                low, high, note = 0.0, 1.0, "scores are normalised to [0,1]"
            else:
                continue
            bad = [x for x in values
                   if (low is not None and x < low) or (high is not None and x > high)]
            if bad:
                findings.append({"table": table, "metric": field, "violations": len(bad),
                                 "of": len(values), "example": bad[0], "rule": note})
                bounds = f"[{low if low is not None else '-inf'}, {high if high is not None else '+inf'}]"
                lines.append(f"  FAIL  {table}  {field}: {len(bad)}/{len(values)} outside {bounds} "
                             f"(e.g. {bad[0]}) — {note}")
    ok = not findings
    if ok:
        lines.append("  every checked metric sits inside its physical range")
    # Say out loud which fields were exempted, so a reader can tell "no
    # violations" from "not checked".
    raw_seen = sorted(
        f for table, sites in tables.items() if table in RAW_SIGNAL_TABLES
        for f in {k for v in sites.values() for k in v} if f in RAW_SIGNAL_FIELDS
    )
    if raw_seen:
        lines.append(f"  raw by design, [0,1] not applied (see check 6): {', '.join(raw_seen)}")
    return ok, lines, findings


def check_coordinates(ref, multi_hit, downstream) -> tuple[bool, list[str], list[dict]]:
    lines, findings = [], []
    if not ref:
        return False, ["  FAIL  stage2_offtargets.json has no reference regions to compare against"], []

    lines.append(f"  reference: stage2_offtargets.json best hit per site, {len(ref)} sites")
    if multi_hit:
        example = multi_hit[0]
        hits = sorted(ref[example], key=lambda h: h.get("start", 0))
        spread = abs(int(hits[-1]["start"]) - int(hits[0]["start"]))
        lines.append(
            f"  NOTE  stage 2 recorded more than one seed hit for {len(multi_hit)} of {len(ref)} sites. "
            f"Downstream stages key on gene:transcript, so each silently keeps ONE."
        )
        lines.append(
            f"        e.g. {example}: "
            + " vs ".join(f"{h['chrom']}:{h['start']}-{h['end']} ({h.get('_mismatches')}mm)" for h in hits)
            + f"  — {spread} bp apart"
        )

    # A key-format change between stage 2 and the rest makes every comparison
    # below iterate an empty set, which would look exactly like success. Refuse
    # to report PASS on nothing.
    comparable = sum(1 for regions in downstream.values() if set(regions) & set(ref))
    if downstream and comparable == 0:
        sample_ref = sorted(ref)[:1]
        sample_ds = sorted(next(iter(downstream.values())))[:1]
        lines.append(
            "  FAIL  no downstream file shares a single site id with stage 2, so nothing "
            "could be compared."
        )
        lines.append(f"        stage 2 key looks like: {sample_ref}")
        lines.append(f"        downstream key looks like: {sample_ds}")
        lines.append("        The stages are keyed differently — this check is blind, not passing.")
        return False, lines, [{"error": "no overlapping site ids", "stage2_sample": sample_ref,
                               "downstream_sample": sample_ds}]

    for filename, regions in sorted(downstream.items()):
        shared = [s for s in regions if s in ref]
        if not shared:
            lines.append(f"  WARN  {filename}: no site ids in common with stage 2 — not compared")
            continue
        offsets: list[int] = []
        wrong_duplicate = off_reference = chrom_mismatch = 0
        example = None
        for site in shared:
            hits, got = ref[site], regions[site]
            best = best_hit(hits)
            if same_locus(best, got):
                continue
            if got.get("chrom") != best.get("chrom"):
                chrom_mismatch += 1
                continue
            if any(same_locus(h, got) for h in hits):
                wrong_duplicate += 1  # a real stage-2 hit, just not the best one
            else:
                off_reference += 1  # a locus stage 2 never reported at all
            try:
                delta = abs(int(got.get("start", 0)) - int(best.get("start", 0)))
            except (TypeError, ValueError):
                continue
            offsets.append(delta)
            if example is None:
                example = f"{site} {best['chrom']}:{best['start']} -> {got['start']} ({delta} bp)"

        if not offsets and not chrom_mismatch:
            lines.append(f"  ok    {filename}: all {len(shared)} regions match stage 2's best hit")
            continue
        median = int(statistics.median(offsets)) if offsets else 0
        worst = max(offsets) if offsets else 0
        findings.append({"file": filename, "sites": len(shared), "disagreeing": len(offsets),
                         "kept_worse_duplicate": wrong_duplicate, "not_a_stage2_locus": off_reference,
                         "chrom_mismatch": chrom_mismatch,
                         "median_offset_bp": median, "max_offset_bp": worst})
        detail = []
        if wrong_duplicate:
            detail.append(f"{wrong_duplicate} kept a worse-scoring duplicate")
        if off_reference:
            detail.append(f"{off_reference} use a locus stage 2 never reported")
        if chrom_mismatch:
            detail.append(f"{chrom_mismatch} on a different chromosome")
        lines.append(f"  FAIL  {filename}: {len(offsets)}/{len(shared)} regions differ — "
                     f"median {median} bp, max {worst} bp ({'; '.join(detail)})")
        if example:
            lines.append(f"        e.g. {example}")
    return not findings, lines, findings


def check_fallback(tables) -> tuple[bool, list[str], list[dict]]:
    """How much of this run is measured data rather than a no-data sentinel?

    Counts three things (see the block above SENTINEL_SCORE): `null`, which
    since roadmap B2 is how an unread source is recorded and is attributable on
    its own; a raw `0.0`, which is a measured zero today but was the fallback
    before B2; and the documented score-space `0.5`. A metric that is wholly
    sentinel is decoration — the source failed and the pipeline substituted a
    number that reads like a result.

    The advisory pass/fail threshold counts **all three**, nulls included. That
    is required rather than incidental: before B2 a wholly dead source showed
    up as 100% zeros and tripped the threshold, and after B2 it shows up as
    100% nulls. Leaving unknowns out of the count would mean a dead source
    stopped tripping it — the very regression this function was repaired for.
    """
    lines, findings = [], []
    worst = 0.0
    saw_raw = False
    for table, sites in sorted(tables.items()):
        fields = sorted({f for v in sites.values() for f in v})
        for field in fields:
            present = [v[field] for v in sites.values() if field in v]
            values = [float(x) for x in present if is_number(x)]
            base = field.split("[")[0]

            # Not measured. Counted before the numeric filter, because that
            # filter is what used to make this invisible.
            n_unknown = sum(1 for x in present if x is None)
            if n_unknown and base in NO_DATA_FIELDS:
                pct = 100.0 * n_unknown / len(present)
                worst = max(worst, pct)
                findings.append({"table": table, "metric": field, "space": "unknown",
                                 "sentinel": None, "hits": n_unknown,
                                 "of": len(present), "pct": round(pct, 1),
                                 "attributable": True})
                lines.append(f"  {pct:5.1f}%  {table}  {field}: {n_unknown}/{len(present)} "
                             f"sites NOT MEASURED (null) — source unavailable, "
                             f"not a silent locus")

            if len(values) < 2:
                continue

            n_score = sum(1 for x in values if abs(x - SENTINEL_SCORE) < 1e-9)
            if n_score:
                pct = 100.0 * n_score / len(values)
                worst = max(worst, pct)
                findings.append({"table": table, "metric": field, "space": "score",
                                 "sentinel": SENTINEL_SCORE, "hits": n_score,
                                 "of": len(values), "pct": round(pct, 1),
                                 "attributable": True})
                lines.append(f"  {pct:5.1f}%  {table}  {field}: {n_score}/{len(values)} "
                             f"sites at the documented {SENTINEL_SCORE} sentinel")

            n_raw = sum(1 for x in values if abs(x - MEASURED_ZERO) < 1e-9)
            if n_raw and base in NO_DATA_FIELDS:
                saw_raw = True
                pct = 100.0 * n_raw / len(values)
                worst = max(worst, pct)
                findings.append({"table": table, "metric": field, "space": "raw",
                                 "sentinel": MEASURED_ZERO, "hits": n_raw,
                                 "of": len(values), "pct": round(pct, 1),
                                 "attributable": False})
                lines.append(f"  {pct:5.1f}%  {table}  {field}: {n_raw}/{len(values)} "
                             f"sites at 0.0 — a measured zero since B2, but the "
                             f"old fallback in any run made before it")

    if not findings:
        lines.append("  no metric sits at either sentinel — every site carries measured data")
    if saw_raw:
        lines.append("  0.0 is NOT attributable from the JSON alone. Since roadmap B2 an")
        lines.append("  unread source is written as null, so a 0.0 should mean the assay")
        lines.append("  covered the locus and found nothing — but a run produced BEFORE B2")
        lines.append("  used 0.0 as its fallback, and the result JSON cannot date itself")
        lines.append("  (H10 adds a run manifest). Check the run's git SHA before reading")
        lines.append("  these zeros as measurements. For every one of these sources less")
        lines.append("  signal reads as LOWER risk, so under the old contract a failed")
        lines.append("  source pushed the site toward SAFE rather than toward unknown.")
    # Advisory: a high fallback rate is a warning, not a hard failure.
    return worst < 50.0, lines, findings


def check_saturation(tables) -> tuple[bool, list[str], list[dict]]:
    """How much of each raw signal's dynamic range survives normalisation?

    Normalisation is a saturating ramp, ``min(1, raw / SAT)``. Every site at
    or above ``SAT`` maps to exactly 1.0, so it can no longer be ranked
    against any other saturated site — the discrimination is thrown away
    before scoring. A handful of saturated sites is expected (the most active
    promoters really are the most active); past half the sites the metric has
    stopped separating anything and the constant is simply too low.

    The two consumers normalise with different constants, so the same run
    saturates at two different rates. Both are reported: a signal that is
    healthy for `normalized_score` can still be flat by the time it reaches
    the risk score.
    """
    lines, findings = [], []
    worst = 0.0
    for table, sites in sorted(tables.items()):
        if table not in RAW_SIGNAL_TABLES:
            continue
        present = {k for v in sites.values() for k in v}
        for label, consts in SATURATION_SETS:
            lines.append(f"  {label}")
            for field in sorted(present & set(consts)):
                sat = consts[field]
                values = [v[field] for v in sites.values()
                          if field in v and is_number(v[field])]
                if len(values) < 2:
                    continue
                hit = sum(1 for x in values if float(x) >= sat)
                pct = 100.0 * hit / len(values)
                worst = max(worst, pct)
                headroom = max(values) / sat if sat > 0 else float("inf")
                flag = "FAIL " if pct > SATURATED_FAIL_PCT else "     "
                lines.append(
                    f"  {flag} {field:<16} SAT={sat:<6g} saturated {hit:>3}/{len(values)} "
                    f"= {pct:5.1f}%   max/SAT = {headroom:.2f}x"
                )
                findings.append({"table": table, "consumer": label, "metric": field,
                                 "saturation": sat, "saturated": hit, "of": len(values),
                                 "pct_saturated": round(pct, 1),
                                 "max_over_saturation": round(headroom, 2)})
    if not findings:
        lines.append("  no raw-signal fields in this run — nothing to saturate")
        return True, lines, findings
    if worst > SATURATED_FAIL_PCT:
        lines.append(f"  FAIL  a raw signal saturates on more than {SATURATED_FAIL_PCT:.0f}% of sites: "
                     "above the cap every site scores 1.0, so the metric no longer ranks them")
    else:
        lines.append(f"  worst saturation {worst:.1f}% of sites — under the "
                     f"{SATURATED_FAIL_PCT:.0f}% discrimination-loss threshold")
    return worst <= SATURATED_FAIL_PCT, lines, findings


CLASSES = [("SAFE", 0.0, 0.3), ("WARNING", 0.3, 0.6), ("HIGH_RISK", 0.6, 0.8), ("DANGEROUS", 0.8, 1.0)]


def check_dynamic_range(run_dir) -> tuple[bool, list[str], dict]:
    blob = load(os.path.join(run_dir, "stage7_classification.json"))
    if not isinstance(blob, dict):
        return False, ["  FAIL  stage7_classification.json missing or unreadable"], {}
    per_site = blob.get("site_classifications") or {}
    finals = [v["final_score"] for v in per_site.values()
              if isinstance(v, dict) and is_number(v.get("final_score"))]
    if not finals:
        return False, ["  FAIL  no per-site final_score found"], {}
    seen: dict[str, int] = {}
    for value in per_site.values():
        if isinstance(value, dict) and isinstance(value.get("risk_class"), str):
            seen[value["risk_class"]] = seen.get(value["risk_class"], 0) + 1
    lines = [
        f"  sites: {len(finals)}   min {min(finals):.4f}   median {statistics.median(finals):.4f}   "
        f"max {max(finals):.4f}   span {max(finals) - min(finals):.4f}",
        f"  overall: {blob.get('overall_risk_score')} -> {blob.get('overall_risk_class')}",
    ]
    never = []
    for name, low, high in CLASSES:
        count = sum(1 for x in finals if low <= x < high or (high == 1.0 and x == 1.0))
        mark = "     " if count else "  <-- never triggered"
        lines.append(f"  {name:<10} [{low}, {high}): {count:>3} sites{mark}")
        if not count:
            never.append(name)
    summary = {"n": len(finals), "min": min(finals), "max": max(finals),
               "median": statistics.median(finals), "span": max(finals) - min(finals),
               "classes_seen": seen, "never_triggered": never}
    if never:
        lines.append(f"  NOTE  {len(never)} of 4 risk classes are unreachable in this run: {', '.join(never)}")
    return not never, lines, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", help="run directory name, e.g. VEGFA_HeLa")
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--json", action="store_true", help="emit machine-readable findings")
    args = parser.parse_args()

    run_dir = os.path.join(args.results_dir, args.run)
    if not os.path.isdir(run_dir):
        print(f"No such run: {run_dir}", file=sys.stderr)
        return 2

    tables = collect(run_dir)
    if not tables:
        print(f"No per-site data found under {run_dir}", file=sys.stderr)
        return 2
    ref, conflicts = reference_regions(run_dir)
    downstream = region_maps(run_dir)

    results = {}
    results["degeneracy"] = check_degeneracy(tables)
    results["ranges"] = check_ranges(tables)
    results["coordinates"] = check_coordinates(ref, conflicts, downstream)
    results["fallback"] = check_fallback(tables)
    results["dynamic_range"] = check_dynamic_range(run_dir)
    results["saturation"] = check_saturation(tables)

    titles = {
        "degeneracy": "1. DEGENERACY — does any metric actually vary across sites?",
        "ranges": "2. PHYSICAL RANGE — are the values physically possible?",
        "coordinates": "3. COORDINATE CONSISTENCY — do the stages agree where each site is?",
        "fallback": "4. FALLBACK RATE — measured data, or a no-data sentinel?",
        "dynamic_range": "5. DYNAMIC RANGE — which risk classes can this run reach?",
        "saturation": "6. SATURATION HEADROOM — does normalisation flatten the raw signals?",
    }

    n_sites = max(len(v) for v in tables.values())
    failed = [name for name, (ok, _, _) in results.items() if not ok]

    # --json emits ONLY json, so the output can be piped to jq or read by a
    # hook. It used to append the json after the human report behind a
    # "--- json ---" line, which made the documented "machine-readable"
    # contract false: nothing could parse it.
    if args.json:
        payload = {
            "run": args.run,
            "sites": n_sites,
            "tables": len(tables),
            "verdict": "FAIL" if failed else "PASS",
            "failed": failed,
            "checks": {name: {"pass": ok, "findings": findings}
                       for name, (ok, _, findings) in results.items()},
        }
        print(json.dumps(payload, indent=2, default=str))
        return 1 if failed else 0

    print(f"\norcSONAR run audit — {args.run}   ({n_sites} sites, {len(tables)} per-site tables)")
    print("=" * 78)
    for name, (ok, lines, _) in results.items():
        print(f"\n[{'PASS' if ok else 'FAIL'}] {titles[name]}")
        for line in lines:
            print(line)

    print("\n" + "=" * 78)
    if failed:
        print(f"VERDICT: FAIL — {len(failed)} of {len(results)} checks failed: {', '.join(failed)}")
    else:
        print(f"VERDICT: PASS — all {len(results)} checks passed")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
