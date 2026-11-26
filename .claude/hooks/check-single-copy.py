#!/usr/bin/env python3
"""Single-copy gate runner — roadmap H9.

One implementation, two callers: ``.claude/acceptance/H9.sh`` runs it so
``fix-done H9`` can verify the item, and the CI workflow runs it as a blocking
step. The logic lives in ``_single_copy.py``; this file is I/O and wording.

Exit status: ``0`` when no file states a canonical fact it is not the
authority for, ``1`` otherwise, ``2`` when the registry or the authority table
could not be read at all — an unreadable registry must never read as a pass.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _single_copy import (  # noqa: E402
    Report,
    authority_table_ids,
    load_registry,
    scan,
)

REGISTRY = ".claude/authority.yaml"
RULES = ".claude/rules/00-degismezler.md"


def tracked_files(root: Path) -> list[str]:
    """Every file git tracks, as repository-relative paths.

    Using the git index rather than a filesystem walk keeps generated and
    ignored trees out without a second ignore list to drift.

    Args:
        root: Repository root.

    Returns:
        Sorted repository-relative paths.

    Raises:
        RuntimeError: If git cannot list the files.
    """
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"git ls-files failed: {exc}") from exc
    return sorted(p for p in out.stdout.split("\0") if p)


def build_report(root: Path) -> Report:
    """Run the whole check and return its report.

    Args:
        root: Repository root.

    Returns:
        The populated report.

    Raises:
        RuntimeError: If the registry or the rules file is unreadable.
    """
    import yaml

    registry_path = root / REGISTRY
    rules_path = root / RULES
    try:
        raw = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise RuntimeError(f"{REGISTRY} unreadable: {exc}") from exc
    try:
        markdown = rules_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"{RULES} unreadable: {exc}") from exc

    facts = load_registry(raw)
    violations, skipped = scan(root, facts, tracked_files(root))

    table = authority_table_ids(markdown)
    registry_ids = [f.id for f in facts]
    mismatch = sorted(set(table) ^ set(registry_ids))

    # A carve-out that names an item the roadmap does not define is a silent
    # permanent exemption: nobody will ever close `H99`. The roadmap parser is
    # reused rather than reimplemented — a second parser is the drift this gate
    # exists to prevent.
    import _status

    try:
        known = {
            item.id.lower()
            for item in _status.parse_roadmap(
                (root / "SCIENTIFIC_ROADMAP.md").read_text(encoding="utf-8")
            )
        }
    except OSError as exc:
        raise RuntimeError(f"SCIENTIFIC_ROADMAP.md unreadable: {exc}") from exc

    dangling = sorted(
        {
            f"{carve.roadmap} ({carve.path})"
            for fact in facts
            for carve in fact.carve_outs
            if carve.roadmap.lower() not in known
        }
    )

    return Report(
        violations=violations,
        skipped=skipped,
        unmeasured={f.id: f.unmeasured_reason for f in facts if not f.patterns},
        carve_out_count=sum(len(f.carve_outs) for f in facts),
        table_mismatch=mismatch,
        dangling_carve_outs=dangling,
    )


def main() -> int:
    """Print the report and return the process exit status.

    Returns:
        ``0`` pass, ``1`` fail, ``2`` the check could not run.
    """
    root = Path(__file__).resolve().parents[2]
    try:
        report = build_report(root)
    except (RuntimeError, ValueError) as exc:
        print(f"ÖLÇÜLEMEDİ — {exc}")
        return 2

    if report.table_mismatch:
        print(
            "GEÇMEDİ — otorite tablosu ile kayıt uyuşmuyor; yalnız birinde olan "
            f"id'ler: {', '.join(report.table_mismatch)}"
        )
        print(f"  tablo: {RULES}   kayıt: {REGISTRY}")

    for dangling in report.dangling_carve_outs:
        print(
            f"  HATA carve-out var olmayan bir maddeyi gösteriyor: {dangling} — "
            "kimsenin kapatmayacağı bir muafiyet sessiz bir silmedir"
        )

    for v in report.violations:
        print(f"  HATA [{v.fact_id}] {v.path}:{v.line}  {v.text}")

    print()
    print(f"# kapsam: {len(report.skipped)} muafiyet tipi, "
          f"{report.carve_out_count} gerekçeli carve-out")
    for reason, count in sorted(report.skipped.items(), key=lambda kv: -kv[1]):
        print(f"#   {count:4d} dosya · {reason}")
    for fact_id, reason in report.unmeasured.items():
        print(f"# ÖLÇÜLMEYEN gerçek: {fact_id} — {' '.join(reason.split())}")

    if not report.ok:
        print()
        print(f"GEÇMEDİ — {len(report.violations)} satır otoritesi olmadığı bir "
              "gerçeği ifade ediyor")
        return 1

    print()
    print("GEÇTİ — hiçbir dosya otoritesi olmadığı bir kanonik gerçeği ifade etmiyor")
    return 0


if __name__ == "__main__":
    sys.exit(main())
