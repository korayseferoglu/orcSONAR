#!/usr/bin/env python3
"""B12's eight measurements. Called by `B12.sh`, which documents them."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
RUNS = ("VEGFA_HeLa", "VEGFA_K562", "CEBPA_HepG2", "MYC_K562")
ATTRIBUTION = ROOT / ".claude/residual_findings.yaml"
BEFORE = ROOT / "reports/b12-yeniden-kosu-2026-11-28/before-manifests"
VERIFY = ROOT / ".claude/skills/verify-run/scripts/verify_run.py"

#: The fixes a run must have been produced *after*. Each is the commit that
#: closed the roadmap item named beside it; the list is the measurable form of
#: the criterion's phrase "current code".
REQUIRED_FIXES = {
    "397978f": "B1 — ClinVar query",
    "c8d7f8c": "B2 — fallback sentinel",
    "9eb0dcf": "B4 — gnomAD sign",
    "a166a18": "R12a — background coverage",
    "f49096e": "B17 — pinned Ensembl",
    "b56da0d": "B18 — DepMap ids",
    "a7b977f": "C3d — ΔG thresholds removed",
}

problems: list[str] = []


def git(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip()


def load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"__error__": str(exc)}


def contains_fixes(commit: str) -> list[str]:
    """Which required fixes `commit` does NOT contain."""
    missing = []
    for sha, label in REQUIRED_FIXES.items():
        code, _ = git(["merge-base", "--is-ancestor", sha, commit])
        if code != 0:
            missing.append(label)
    return missing


def four_part_ids(run_dir: Path) -> tuple[int, int]:
    """Count site ids and how many are not four-part.

    Returns:
        ``(total, malformed)`` over every stage file that keys by site id.
    """
    total = malformed = 0
    for path in sorted(run_dir.glob("stage*.json")):
        doc = load(path)
        if not isinstance(doc, dict):
            continue
        for value in doc.values():
            keys: list[str] = []
            if isinstance(value, dict):
                keys = [k for k in value if ":" in k]
            elif isinstance(value, list):
                keys = [s["site_id"] for s in value
                        if isinstance(s, dict) and isinstance(s.get("site_id"), str)]
            for key in keys:
                total += 1
                if len(key.split(":")) != 4:
                    malformed += 1
    return total, malformed


def main() -> int:
    results = ROOT / "results"

    # ---- 1  dizinler -----------------------------------------------------
    missing_dirs = [r for r in RUNS if not (results / r / "manifest.json").is_file()]
    if missing_dirs:
        problems.append(f"manifest'i olmayan koşu: {missing_dirs}")
    else:
        print(f"  1  dört koşu dizini ve manifest'i var: {', '.join(RUNS)}")

    manifests = {r: load(results / r / "manifest.json") for r in RUNS
                 if (results / r / "manifest.json").is_file()}

    # ---- 2  tam kapsam ---------------------------------------------------
    partial = []
    for run in manifests:
        hits = load(results / run / "stage2_seed_hits.json")
        cov = hits.get("background_coverage") if isinstance(hits, dict) else None
        if not isinstance(cov, dict):
            partial.append(f"{run}: background_coverage ALANI YOK (R12a öncesi koşu)")
        elif cov.get("fraction") != 1.0:
            partial.append(
                f"{run}: kapsam {cov.get('resolved')}/{cov.get('requested')} "
                f"= {cov.get('fraction')}"
            )
    if partial:
        problems.append("tam olmayan arka plan kapsamı: " + "; ".join(partial))
    elif manifests:
        print("  2  dört koşunun hepsi TAM arka plan kapsamı taşıyor (fraction 1.0)")

    # ---- 3  güncel kod ---------------------------------------------------
    stale = []
    for run, manifest in manifests.items():
        commit = (manifest.get("code") or {}).get("head_commit", "")
        if not commit:
            stale.append(f"{run}: manifest commit kaydetmiyor")
            continue
        gaps = contains_fixes(commit)
        if gaps:
            stale.append(f"{run} ({commit[:7]}) şunları İÇERMİYOR: {', '.join(gaps)}")
    if stale:
        problems.append("eski kodla üretilmiş koşu: " + "; ".join(stale))
    elif manifests:
        print("  3  dört koşu da yedi düzeltmenin hepsini içeren bir commit’ten")

    # ---- 4  kesinti işareti ---------------------------------------------
    interrupted = []
    for run, manifest in manifests.items():
        marks = (manifest.get("snakemake_state") or {}).get("incomplete_outputs")
        if marks:
            interrupted.append(f"{run}: {marks}")
    if interrupted:
        problems.append("yarıda kesilmiş koşu: " + "; ".join(interrupted))
    elif manifests:
        print("  4  hiçbir koşuda kesinti işareti yok")

    # ---- 5  site_id biçimi ----------------------------------------------
    bad_ids = []
    for run in manifests:
        total, malformed = four_part_ids(results / run)
        if total == 0:
            bad_ids.append(f"{run}: hiç site id'si bulunamadı")
        elif malformed:
            bad_ids.append(f"{run}: {malformed}/{total} id dört parçalı değil")
    if bad_ids:
        problems.append("eski site_id biçimi: " + "; ".join(bad_ids))
    elif manifests:
        print("  5  her koşuda her site id'si dört parçalı")

    # ---- 6  pinlenmiş Ensembl -------------------------------------------
    raw = yaml.safe_load((ROOT / "config/config.yaml").read_text(encoding="utf-8"))
    declared = raw.get("ensembl_release")
    base = str(raw.get("ensembl_base_url", ""))
    if not declared or "rest.ensembl.org" not in base:
        problems.append(f"config pinlenmiş bir Ensembl arşivi beyan etmiyor: {base}")
    else:
        print(f"  6a config pinlenmiş arşiv beyan ediyor: {base} sürüm {declared}")
        sys.path.insert(0, str(ROOT))
        try:
            from src.core import ensembl_release

            live = ensembl_release.live_release(base)
        except Exception as exc:  # noqa: BLE001 — ağ yokluğu ölçüm değil
            print(f"  6b ATLANDI — canlı sürüm okunamadı ({type(exc).__name__})")
        else:
            if live is None:
                print("  6b ATLANDI — host sürüm bildirmedi (ağsız olabilir)")
            elif int(live) != int(declared):
                problems.append(
                    f"pinlenmiş host sürüm {live} diyor, config {declared} — "
                    "koşular beyan edilenden başka bir derlemeden"
                )
            else:
                print(f"  6b canlı doğrulandı: host sürüm {live} = beyan {declared}")

    # ---- 7  kalıntı bulgu atfı (AYIRT EDİCİ) ----------------------------
    if not ATTRIBUTION.is_file():
        problems.append(f"atıf dosyası yok: {ATTRIBUTION}")
    else:
        spec = yaml.safe_load(ATTRIBUTION.read_text(encoding="utf-8")) or {}
        listed = {
            str(e.get("finding")): str(e.get("owner"))
            for e in (spec.get("residual") or [])
            if isinstance(e, dict)
        }
        sys.path.insert(0, str(ROOT / ".claude/hooks"))
        import _status

        roadmap = _status.parse_roadmap(
            (ROOT / "SCIENTIFIC_ROADMAP.md").read_text(encoding="utf-8")
        )
        status_of = {item.id: item.status for item in roadmap}

        observed: set[str] = set()
        for run in manifests:
            proc = subprocess.run(
                [sys.executable, str(VERIFY), run, "--json"],
                cwd=ROOT, capture_output=True, text=True,
            )
            if not proc.stdout.strip():
                problems.append(f"{run}: verify-run çıktı vermedi")
                continue
            audit = json.loads(proc.stdout)
            for block in (audit.get("checks") or {}).values():
                findings = block.get("findings")
                if not isinstance(findings, list):
                    continue
                for finding in findings:
                    if isinstance(finding, dict) and finding.get("metric"):
                        observed.add(f"{finding['table']}:{finding['metric']}")

        unowned = sorted(observed - set(listed))
        if unowned:
            problems.append(
                f"{len(unowned)} kalıntı bulgunun sahibi yok — ilk üç: "
                f"{unowned[:3]}"
            )
        closed_owners = sorted(
            f"{f} -> {o} ({status_of.get(o, 'BİLİNMEYEN MADDE')})"
            for f, o in listed.items()
            if f in observed and "DONE" in status_of.get(o, "")
        )
        if closed_owners:
            problems.append(
                "kapanmış maddeye atfedilen bulgu HÂLÂ duruyor — ilk üç: "
                f"{closed_owners[:3]}"
            )
        unknown = sorted(o for o in set(listed.values()) if o not in status_of)
        if unknown:
            problems.append(f"atıf var olmayan maddeye işaret ediyor: {unknown}")
        if not (unowned or closed_owners or unknown):
            print(f"  7  {len(observed)} kalıntı bulgunun hepsi açık bir maddeye "
                  f"atfedilmiş ({len(set(listed.values()))} farklı sahip)")

    # ---- 8  KONTROL ------------------------------------------------------
    if not BEFORE.is_dir():
        problems.append(f"kontrol kaydı yok: {BEFORE}")
    else:
        old_pass = []
        for path in sorted(BEFORE.glob("*.json")):
            manifest = load(path)
            commit = (manifest.get("code") or {}).get("head_commit", "")
            marks = (manifest.get("snakemake_state") or {}).get("incomplete_outputs")
            if commit and not contains_fixes(commit) and not marks:
                old_pass.append(path.stem)
        if old_pass:
            problems.append(
                f"KONTROL BAŞARISIZ: eski koşular da 3. ve 4. ölçümü geçiyor "
                f"({old_pass}) — kapı hiçbir şeyi ayırt etmiyor"
            )
        else:
            print(f"  8  kontrol: korunmuş {len(list(BEFORE.glob('*.json')))} eski "
                  "manifest 3./4. ölçümü GEÇMİYOR")

    for problem in problems:
        print(f"  HATA {problem}")
    if problems:
        print("\nGEÇMEDİ — yukarıdaki ölçümler")
        return 1
    print("\nGEÇTİ — dört koşu güncel kodla, tam kapsamla ve pinlenmiş sürümle")
    print("        yeniden üretilmiş; her kalıntı `verify-run` bulgusu adı konmuş")
    print("        AÇIK bir maddeye atfedilmiş, ve kontrol eski koşuların bu")
    print("        kapıyı geçmediğini gösteriyor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
