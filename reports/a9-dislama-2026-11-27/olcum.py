#!/usr/bin/env python3
"""A9 — on-target ve ikincil etki dışlamasının ölçümü (ön kayıt §6.6).

    python3 reports/a9-dislama-2026-11-27/olcum.py

Üç ölçüm:

1. **Hedef genin kendisi** — her kolun hedefi array'de var mı, pozitif mi,
   ne kadar susmuş; ve birinci sıradaki bir pozitifin AP'ye katkısı (`1/P`).
2. **İkincil etki kümesi var mı** — SIGNOR'un insan nedensel ilişkileri,
   **transkripsiyonel** mekanizmaya süzülerek, on hedef gen için.
3. **Silmenin YÖNÜ** — pozitifleri RASTGELE silmek ile tahmin edicinin
   KAÇIRDIKLARINI silmek arasındaki fark. İkincisi elle küratörlenmiş bir
   "ikincil etki" listesinin modeli; birincisi değil. İlk simülasyon yanlış
   modeli ölçüyordu ve bu dosya ikisini birlikte raporluyor.

Tahmin edici her yerde **modelden bağımsız** (mock kanalı, §7.5'in dördüncü
tabanı): orcSONAR'ın hiçbir çıktısı okunmuyor.
"""

from __future__ import annotations

import csv
import json
import math
import random
import statistics
import sys
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CACHE = HERE / "geo-onbellek"
GEO = "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi"
SIGNOR = ROOT / "data" / "external" / "signor" / "signor_human_all.tsv"

# kol → (platform, hedef gen sembolü). Başlıklar GEO'dan doğrulandı.
ARRAYS: dict[str, tuple[str, str]] = {
    "GSM133689": ("GPL2029", "MAPK14"),
    "GSM133697": ("GPL2029", "MAPK14"),
    "GSM133702": ("GPL2029", "MAPK14"),
    "GSM133703": ("GPL2029", "LUC"),
    "GSM134317": ("GPL3991", "PIK3CA"),
    "GSM134319": ("GPL3991", "MPHOSPH1"),
    "GSM134523": ("GPL3992", "MPHOSPH1"),
    "GSM119707": ("GPL3992", "SOD1"),
    "GSM119708": ("GPL3992", "SOD1"),
    "GSM119759": ("GPL3992", "SOD1"),
}
TARGETS = ("MAPK14", "PLK1", "PIK3CA", "PIK3CB", "SOS1", "PRKCE", "VHL",
           "MPHOSPH1", "SOD1", "GAPDH")
# SIGNOR'un MECHANISM kolonunda mRNA düzeyini değiştiren mekanizmalar
TRANSCRIPTIONAL = ("transcription", "expression", "repression")
LOG10_TO_LOG2 = 3.321928   # ön kayıt §4.2


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


def universe(gsm: str, gpl: str) -> list[dict[str, object]]:
    """§6.4'ün evreni, prob başına; mock kanalı olmayan problar atlanır."""
    header, rows = _rows(gsm, "sample")
    mapping = symbols(gpl)
    out: list[dict[str, object]] = []
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
            "probe": row["ID_REF"].strip(),
            "symbol": mapping.get(row["ID_REF"].strip()),
            "label": 1 if (pval < 0.01 and value < 0) else 0,
            "value": value, "mock": mock,
        })
    return out


def ap_and_lift(pairs: list[tuple[float, int]]) -> tuple[float, float]:
    order = sorted(range(len(pairs)), key=lambda i: -pairs[i][0])
    total = sum(p[1] for p in pairs)
    hits = 0
    value = 0.0
    for rank, i in enumerate(order, start=1):
        if pairs[i][1]:
            hits += 1
            value += hits / rank
    precision = value / total
    return precision, precision / (total / len(pairs))


def signor_downstream() -> dict[str, list[str]]:
    """Hedef başına **transkripsiyonel** alt akış. Yoksa boş liste."""
    if not SIGNOR.exists():
        return {}
    out: dict[str, set[str]] = {t: set() for t in TARGETS}
    with SIGNOR.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.reader(handle, delimiter="\t"):
            if len(row) < 10:
                continue
            source, target, mechanism = row[0], row[4], (row[9] or "").lower()
            if source in out and any(k in mechanism for k in TRANSCRIPTIONAL):
                out[source].add(target)
    return {k: sorted(v) for k, v in out.items()}


def main() -> int:
    tables: dict[str, list[dict[str, object]]] = {}
    for gsm, (gpl, _) in ARRAYS.items():
        try:
            tables[gsm] = universe(gsm, gpl)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            print(f"  {gsm}: alınamadı ({exc})", file=sys.stderr)
    if not tables:
        print("GEO'ya ulaşılamadı", file=sys.stderr)
        return 2

    # ---- 1  hedef genin kendisi -----------------------------------------
    print("(1) hedef genin kendisi")
    print(f"{'array':11s} {'hedef':10s} {'prob':>5s} {'pozitif':>8s} "
          f"{'log2FC':>9s} {'P':>6s} {'1/P':>9s}")
    on_target: list[dict[str, object]] = []
    for gsm, data in tables.items():
        target = ARRAYS[gsm][1]
        probes = [d for d in data if d["symbol"] == target]
        positives = sum(int(d["label"]) for d in data)
        entry: dict[str, object] = {
            "gsm": gsm, "target": target, "probes": len(probes),
            "positives": positives, "rank1_contribution": 1.0 / positives,
        }
        if probes:
            strongest = min(probes, key=lambda d: float(d["value"]))
            entry["is_positive"] = bool(strongest["label"])
            entry["log2fc"] = float(strongest["value"]) * LOG10_TO_LOG2
            print(f"{gsm:11s} {target:10s} {len(probes):5d} "
                  f"{str(entry['is_positive']):>8s} {entry['log2fc']:9.3f} "
                  f"{positives:6d} {entry['rank1_contribution']:9.5f}")
        else:
            entry["is_positive"] = None
            entry["log2fc"] = None
            print(f"{gsm:11s} {target:10s} {0:5d} {'PROB YOK':>8s} "
                  f"{'—':>9s} {positives:6d} {entry['rank1_contribution']:9.5f}")
        on_target.append(entry)
    median_contribution = statistics.median(
        float(e["rank1_contribution"]) for e in on_target
    )
    print(f"  hedef {sum(1 for e in on_target if e['is_positive'])}/"
          f"{len(on_target)} array'de pozitif; "
          f"medyan 1/P = {median_contribution:.5f}")

    # ---- 2  ikincil etki kümesi -----------------------------------------
    print("\n(2) SIGNOR'da transkripsiyonel alt akış")
    downstream = signor_downstream()
    if not downstream:
        print(f"  {SIGNOR} yok — manifest'teki kaynaktan indir")
    else:
        for target in TARGETS:
            genes = downstream.get(target, [])
            print(f"  {target:10s} {len(genes):3d}"
                  + (f"  {genes}" if genes else ""))
        print(f"  on hedefte toplam "
              f"{sum(len(v) for v in downstream.values())} gen")

    # ---- 3  silmenin yönü ------------------------------------------------
    print("\n(3) pozitif silmenin yönü (modelden bağımsız tahmin edici)")
    print(f"{'silinen':>8s} | {'RASTGELE':^26s} | {'KAÇIRILANLAR':^26s}")
    print(f"{'':>8s} | {'ΔAP':>12s} {'Δlift':>13s} | {'ΔAP':>12s} {'Δlift':>13s}")
    rng = random.Random(7)
    directions: dict[str, dict[str, float]] = {}
    for fraction in (0.02, 0.05, 0.10, 0.20):
        random_deltas: list[tuple[float, float]] = []
        worst_deltas: list[tuple[float, float]] = []
        for data in tables.values():
            pairs = [(float(d["mock"]), int(d["label"])) for d in data
                     if d["mock"] is not None]
            if not pairs or not any(p[1] for p in pairs):
                continue
            base_ap, base_lift = ap_and_lift(pairs)
            positives = [i for i, p in enumerate(pairs) if p[1]]
            k = int(len(positives) * fraction)
            if k == 0:
                continue
            samples = []
            for _ in range(15):
                dropped = set(rng.sample(positives, k))
                samples.append(ap_and_lift(
                    [p for i, p in enumerate(pairs) if i not in dropped]
                ))
            random_deltas.append((
                statistics.fmean(s[0] for s in samples) - base_ap,
                statistics.fmean(s[1] for s in samples) - base_lift,
            ))
            worst = set(sorted(positives, key=lambda i: pairs[i][0])[:k])
            value = ap_and_lift([p for i, p in enumerate(pairs) if i not in worst])
            worst_deltas.append((value[0] - base_ap, value[1] - base_lift))
        directions[f"{fraction}"] = {
            "random_dap": statistics.median(d[0] for d in random_deltas),
            "random_dlift": statistics.median(d[1] for d in random_deltas),
            "worst_dap": statistics.median(d[0] for d in worst_deltas),
            "worst_dlift": statistics.median(d[1] for d in worst_deltas),
        }
        entry = directions[f"{fraction}"]
        print(f"{fraction * 100:7.0f}% | {entry['random_dap']:+12.5f} "
              f"{entry['random_dlift']:+13.5f} | {entry['worst_dap']:+12.5f} "
              f"{entry['worst_dlift']:+13.5f}")

    (HERE / "olcum.json").write_text(json.dumps({
        "measured_at": "2026-11-27",
        "on_target": on_target,
        "median_rank1_contribution": median_contribution,
        "signor_transcriptional_downstream": downstream,
        "deletion_directions": directions,
        "label_rule": "PVALUE < 0.01 and VALUE < 0",
        "universe": "LOGINTENSITY >= -1 (and QUALITY == 1 where present)",
    }, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
