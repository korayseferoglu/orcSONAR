#!/usr/bin/env python3
"""Which `verify-run` findings does a re-run remove, and which stay? (B12)

`B12`'s acceptance criterion says "`verify-run` clean on all four runs". Before
re-running anything, this script measures whether that sentence can be true at
all — because a re-run can only remove the findings that come from a run being
*stale*. A finding that comes from live code stays no matter how many times the
pipeline is re-run, and four of `verify-run`'s six checks were failing on the
run that is already the newest.

So the question is not "is it clean" but **"is every residual finding
attributable to a named open roadmap item"**. That is checkable, and it is what
a re-run can actually establish. Lowering the bar would be invariant 7's
violation; stating what the bar measures is not.

Usage:
    olcum.py OLD_RESULTS_DIR FRESH_RESULTS_DIR RUN_NAME [RUN_NAME ...]
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
VERIFY = ROOT / ".claude/skills/verify-run/scripts/verify_run.py"

#: Finding sets are compared on these identity fields. `verify-run` reports a
#: finding per (table, metric); the numbers inside it move between runs, which
#: is the point, so they are not part of the identity.
IDENTITY = ("table", "metric")

#: Checks whose findings are a list of (table, metric) records. `dynamic_range`
#: reports one aggregate object instead and is handled separately.
SET_CHECKS = ("degeneracy", "ranges", "fallback", "saturation")


def audit(results_dir: Path, run: str) -> dict[str, Any]:
    """Run `verify-run --json` for one run.

    Args:
        results_dir: The results tree holding ``run``.
        run: Run directory name, e.g. ``VEGFA_HeLa``.

    Returns:
        The parsed audit, or ``{"error": ...}`` if it could not be produced.
    """
    proc = subprocess.run(
        [sys.executable, str(VERIFY), run, "--json", "--results-dir", str(results_dir)],
        capture_output=True,
        text=True,
    )
    if not proc.stdout.strip():
        return {"error": proc.stderr.strip()[-400:] or f"exit {proc.returncode}"}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"error": f"unparseable audit: {exc}"}


def finding_ids(audit_result: dict[str, Any], check: str) -> set[tuple[str, ...]]:
    """The identity of every finding `check` reported.

    Args:
        audit_result: One `verify-run --json` document.
        check: Check name, e.g. ``degeneracy``.

    Returns:
        A set of ``(table, metric)`` tuples; empty when the check passed or is
        not a set-shaped check.
    """
    block = audit_result.get("checks", {}).get(check, {})
    findings = block.get("findings")
    if not isinstance(findings, list):
        return set()
    return {
        tuple(str(f.get(field, "")) for field in IDENTITY)
        for f in findings
        if isinstance(f, dict)
    }


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    old_dir, fresh_dir = Path(sys.argv[1]), Path(sys.argv[2])
    runs = sys.argv[3:]

    record: dict[str, Any] = {
        "question": (
            "Which verify-run findings does a re-run remove, and which are "
            "code findings that no re-run can touch?"
        ),
        "old_results_dir": str(old_dir),
        "fresh_results_dir": str(fresh_dir),
        "runs": {},
    }

    for run in runs:
        old = audit(old_dir, run)
        fresh = audit(fresh_dir, run)
        entry: dict[str, Any] = {
            "old": {"verdict": old.get("verdict"), "failed": old.get("failed"),
                    "sites": old.get("sites"), "error": old.get("error")},
            "fresh": {"verdict": fresh.get("verdict"), "failed": fresh.get("failed"),
                      "sites": fresh.get("sites"), "error": fresh.get("error")},
            "per_check": {},
        }
        for check in SET_CHECKS:
            before, after = finding_ids(old, check), finding_ids(fresh, check)
            entry["per_check"][check] = {
                "before": len(before),
                "after": len(after),
                "removed_by_rerun": sorted(":".join(t) for t in before - after),
                "new_in_fresh": sorted(":".join(t) for t in after - before),
                "unchanged": sorted(":".join(t) for t in before & after),
            }
        # ⚠️ The OLD side's numbers are recorded as evidence that the run was
        # stale, NOT as measurements. The roadmap forbids quoting any number
        # from `MYC_K562` (B12's own damage record) or from the pre-B17/B18
        # `VEGFA_HeLa` as a threshold, ceiling or distribution.
        entry["old"]["numbers_are_not_measurements"] = (
            "staleness evidence only — see SCIENTIFIC_ROADMAP.md B12/B17/B18"
        )
        for side, result in (("old", old), ("fresh", fresh)):
            block = result.get("checks", {}).get("dynamic_range", {})
            findings = block.get("findings")
            if isinstance(findings, dict):
                entry["per_check"].setdefault("dynamic_range", {})[side] = {
                    "span": findings.get("span"),
                    "min": findings.get("min"),
                    "max": findings.get("max"),
                    "never_triggered": findings.get("never_triggered"),
                }
        record["runs"][run] = entry

    out = Path(__file__).with_name("olcum.json")
    out.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"yazıldı: {out}")
    for run, entry in record["runs"].items():
        print(f"\n{run}: {entry['old']['verdict']} -> {entry['fresh']['verdict']}")
        for check, data in entry["per_check"].items():
            if "removed_by_rerun" not in data:
                continue
            print(f"  {check:12s} {data['before']:3d} -> {data['after']:3d} bulgu"
                  f"  | kalkan {len(data['removed_by_rerun']):2d}"
                  f"  | YENİ {len(data['new_in_fresh']):2d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
