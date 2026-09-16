#!/usr/bin/env python3
"""Audit the scientific health of one completed orcSONAR run.

Usage:  verify_run.py {gene}_{cell_line} [--results-dir results] [--json]

Reads results/{gene}_{cell_line}/*.json and answers five questions that a
green Snakemake exit does not: does any metric actually vary across sites, are
the values physically possible, do the stages agree on where each site is, how
much of the run is real data versus neutral fallback, and does the score range
ever reach its upper classes.

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

NEUTRAL = 0.5  # graceful-degradation sentinel: source failed -> neutral score


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
            if base in RANGE_RULES:
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
    """Count how many sites carry the neutral 0.5 sentinel rather than measured data."""
    lines, findings = [], []
    worst = 0.0
    for table, sites in sorted(tables.items()):
        fields = sorted({f for v in sites.values() for f in v})
        for field in fields:
            values = [v[field] for v in sites.values() if field in v and is_number(v[field])]
            if len(values) < 2:
                continue
            neutral = sum(1 for x in values if abs(float(x) - NEUTRAL) < 1e-9)
            zero = sum(1 for x in values if float(x) == 0.0)
            pct = 100.0 * neutral / len(values)
            if neutral:
                worst = max(worst, pct)
                findings.append({"table": table, "metric": field, "neutral": neutral,
                                 "zero": zero, "of": len(values), "pct_neutral": round(pct, 1)})
                lines.append(f"  {pct:5.1f}%  {table}  {field}: {neutral}/{len(values)} sites at the "
                             f"neutral {NEUTRAL} sentinel" + (f" ({zero} at 0.0)" if zero else ""))
    if not findings:
        lines.append("  no metric sits at the neutral 0.5 sentinel — every site carries measured data")
    # Advisory: a high fallback rate is a warning, not a hard failure.
    return worst < 50.0, lines, findings


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

    titles = {
        "degeneracy": "1. DEGENERACY — does any metric actually vary across sites?",
        "ranges": "2. PHYSICAL RANGE — are the values physically possible?",
        "coordinates": "3. COORDINATE CONSISTENCY — do the stages agree where each site is?",
        "fallback": "4. FALLBACK RATE — measured data, or the neutral 0.5 sentinel?",
        "dynamic_range": "5. DYNAMIC RANGE — which risk classes can this run reach?",
    }

    n_sites = max(len(v) for v in tables.values())
    print(f"\norcSONAR run audit — {args.run}   ({n_sites} sites, {len(tables)} per-site tables)")
    print("=" * 78)
    failed = []
    for name, (ok, lines, _) in results.items():
        print(f"\n[{'PASS' if ok else 'FAIL'}] {titles[name]}")
        for line in lines:
            print(line)
        if not ok:
            failed.append(name)

    print("\n" + "=" * 78)
    if failed:
        print(f"VERDICT: FAIL — {len(failed)} of 5 checks failed: {', '.join(failed)}")
    else:
        print("VERDICT: PASS — all 5 checks passed")

    if args.json:
        payload = {name: {"pass": ok, "findings": findings}
                   for name, (ok, _, findings) in results.items()}
        print("\n--- json ---")
        print(json.dumps(payload, indent=2, default=str))

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
