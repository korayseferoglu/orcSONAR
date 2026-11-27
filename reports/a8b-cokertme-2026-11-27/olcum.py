#!/usr/bin/env python3
"""A8b — prob→gen çökertme kurallarının YÖNÜ (ön kayıt §6.5).

    python3 reports/a8b-cokertme-2026-11-27/olcum.py

Dört kural karşılaştırılıyor, ve ölçülen şey hangisinin "doğru" olduğu değil,
her birinin **pozitif sayısını hangi yöne** ittiği:

    any       bir genin herhangi bir probu pozitifse gen pozitif
    all       hepsi pozitifse
    maxmean   etiketten BAĞIMSIZ bir istatistikle seçilen tek prob
              (mock kanalı varsa onun, yoksa `LOGINTENSITY`'nin en büyüğü;
              eşitlikte en küçük prob kimliği — determinist)
    best-p    en küçük `PVALUE`'lu prob — **etiket-bağımlı**, karşıtlık için

Ayrıca gen düzeyine geçişin kendi bedeli ölçülüyor: sembole eşleşmeyen
problar gen evreninden düşüyor.

Etiket §4.1, evren §6.4 (`LOGINTENSITY ≥ −1`, ve `QUALITY` kolonu varsa o).
"""

from __future__ import annotations

import json
import math
import statistics
import sys
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / "geo-onbellek"
GEO = "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi"

ARRAYS: dict[str, tuple[str, str]] = {
    "GSM133689": ("GPL2029", "GSE5814"),
    "GSM133697": ("GPL2029", "GSE5814"),
    "GSM133702": ("GPL2029", "GSE5814"),
    "GSM134317": ("GPL3991", "GSE5769"),
    "GSM134319": ("GPL3991", "GSE5769"),
    "GSM134523": ("GPL3992", "GSE5769"),
    "GSM119707": ("GPL3992", "GSE5291"),
    "GSM119708": ("GPL3992", "GSE5291"),
    "GSM119759": ("GPL3992", "GSE5291"),
}
RULES = ("any", "all", "maxmean", "bestp")


def fetch(acc: str) -> str:
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"{acc}.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    url = f"{GEO}?acc={acc}&targ=self&form=text&view=full"
    req = urllib.request.Request(url, headers={"User-Agent": "research-script/1.0"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        raw = resp.read().decode("utf-8", "replace")
    path.write_text(raw, encoding="utf-8")
    return raw


def _rows(acc: str, kind: str) -> tuple[list[str], list[list[str]]]:
    lines = fetch(acc).splitlines()
    start = lines.index(f"!{kind}_table_begin")
    end = lines.index(f"!{kind}_table_end")
    return lines[start + 1].split("\t"), [
        line.split("\t") for line in lines[start + 2 : end]
    ]


@lru_cache(maxsize=None)
def symbols(gpl: str) -> dict[str, str]:
    """prob → gen sembolü. `GPL2029` `GeneSymbol`, diğerleri `ORF` taşıyor."""
    header, rows = _rows(gpl, "platform")
    column = "GeneSymbol" if "GeneSymbol" in header else "ORF"
    out: dict[str, str] = {}
    for parts in rows:
        if len(parts) < len(header):
            parts = parts + [""] * (len(header) - len(parts))
        row = dict(zip(header, parts))
        symbol = (row.get(column) or "").strip()
        if symbol:
            out[row["ID"].strip()] = symbol
    return out


def probes(gsm: str, gpl: str) -> tuple[list[dict[str, object]], int, int]:
    """Evrendeki problar, toplam sayısı ve sembole eşleşmeyenlerin sayısı."""
    header, rows = _rows(gsm, "sample")
    mapping = symbols(gpl)
    out: list[dict[str, object]] = []
    total = 0
    unmapped = 0
    for parts in rows:
        if len(parts) != len(header):
            continue
        row = dict(zip(header, parts))
        flag = (row.get("QUALITY") or "").strip()
        if flag and flag not in ("1", "1.0"):
            continue
        try:
            value = float(row["VALUE"])
            pval = float(row["PVALUE"])
            logint = float(row["LOGINTENSITY"])
        except (KeyError, TypeError, ValueError):
            continue
        if any(math.isnan(x) for x in (value, pval, logint)) or logint < -1.0:
            continue
        total += 1
        probe = row["ID_REF"].strip()
        symbol = mapping.get(probe)
        if not symbol:
            unmapped += 1
            continue
        mock: float | None = None
        raw1 = row.get("INTENSITY1")
        if raw1:
            try:
                intensity = float(raw1)
            except (TypeError, ValueError):
                intensity = float("nan")
            if not math.isnan(intensity) and intensity > 0:
                mock = math.log10(intensity)
        out.append({
            "probe": probe, "symbol": symbol,
            "label": 1 if (pval < 0.01 and value < 0) else 0,
            "pval": pval, "mock": mock, "logint": logint,
        })
    return out, total, unmapped


def selector(probe: dict[str, object]) -> float:
    """Etiketten bağımsız seçim istatistiği: mock kanalı varsa o."""
    mock = probe["mock"]
    return float(mock) if mock is not None else float(probe["logint"])


def collapse(group: list[dict[str, object]], rule: str) -> int:
    if rule == "any":
        return 1 if any(int(p["label"]) for p in group) else 0
    if rule == "all":
        return 1 if all(int(p["label"]) for p in group) else 0
    if rule == "maxmean":
        top = max(selector(p) for p in group)
        tied = [p for p in group if selector(p) == top]
        return int(min(tied, key=lambda p: str(p["probe"]))["label"])
    if rule == "bestp":
        return int(min(group, key=lambda p: (float(p["pval"]), str(p["probe"])))["label"])
    raise ValueError(rule)


def main() -> int:
    rows: list[dict[str, object]] = []
    for gsm, (gpl, series) in ARRAYS.items():
        try:
            data, total, unmapped = probes(gsm, gpl)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            print(f"  {gsm}: alınamadı ({exc})", file=sys.stderr)
            continue
        groups: dict[str, list[dict[str, object]]] = {}
        for probe in data:
            groups.setdefault(str(probe["symbol"]), []).append(probe)
        multi = sum(1 for g in groups.values() if len(g) > 1)
        conflict = sum(
            1 for g in groups.values()
            if len(g) > 1 and 0 < sum(int(p["label"]) for p in g) < len(g)
        )
        with_pos = sum(
            1 for g in groups.values()
            if len(g) > 1 and any(int(p["label"]) for p in g)
        )
        entry: dict[str, object] = {
            "gsm": gsm, "platform": gpl, "series": series,
            "probes": total, "unmapped": unmapped,
            "unmapped_frac": unmapped / total,
            "genes": len(groups), "multi_probe_genes": multi,
            "label_conflicts": conflict,
            "conflict_frac_of_positive_multi": conflict / max(with_pos, 1),
        }
        for rule in RULES:
            positives = sum(collapse(g, rule) for g in groups.values())
            entry[f"pos_{rule}"] = positives
            entry[f"pi_{rule}"] = positives / len(groups)
        rows.append(entry)

    if not rows:
        print("GEO'ya ulaşılamadı", file=sys.stderr)
        return 2

    print(f"{'array':11s} {'prob':>6s} {'eşleşmz':>8s} {'%':>5s} {'gen':>6s} "
          f"{'çok-prob':>9s} {'çelişki':>8s} "
          + " ".join(f"{r:>13s}" for r in RULES))
    for r in rows:
        print(f"{r['gsm']:11s} {r['probes']:6d} {r['unmapped']:8d} "
              f"{float(r['unmapped_frac']) * 100:5.1f} {r['genes']:6d} "
              f"{r['multi_probe_genes']:9d} {r['label_conflicts']:8d} "
              + " ".join(f"{r['pos_' + k]:4d}/{float(r['pi_' + k]):.4f}".rjust(13)
                         for k in RULES))

    print("\nmedyan taban oranı ve maxmean'e göre pozitif sayısı farkı:")
    summary: dict[str, dict[str, float]] = {}
    for rule in RULES:
        pis = [float(r[f"pi_{rule}"]) for r in rows]
        delta = statistics.median(
            (int(r[f"pos_{rule}"]) - int(r["pos_maxmean"])) / max(int(r["pos_maxmean"]), 1)
            for r in rows
        )
        summary[rule] = {"median_pi": statistics.median(pis), "delta_vs_maxmean": delta}
        print(f"  {rule:8s} taban {summary[rule]['median_pi']:.4f}   "
              f"fark {delta:+.1%}")
    print(f"\nsembole eşleşmeyen prob oranı: "
          f"%{min(float(r['unmapped_frac']) for r in rows) * 100:.1f}-"
          f"%{max(float(r['unmapped_frac']) for r in rows) * 100:.1f} "
          f"(bu problar gen evreninden düşüyor)")
    print(f"çok-problu genlerde etiket çelişkisi, pozitif içerenlerin "
          f"%{min(float(r['conflict_frac_of_positive_multi']) for r in rows) * 100:.0f}-"
          f"%{max(float(r['conflict_frac_of_positive_multi']) for r in rows) * 100:.0f}'ı")

    (HERE / "olcum.json").write_text(json.dumps({
        "measured_at": "2026-11-27",
        "arrays": rows,
        "summary": summary,
        "label_rule": "PVALUE < 0.01 and VALUE < 0",
        "universe": "LOGINTENSITY >= -1 (and QUALITY == 1 where present)",
    }, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
