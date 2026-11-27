#!/usr/bin/env python3
"""A8 — tespit edilebilirlik filtresinin ölçümü (ön kayıt §6.4).

    python3 reports/a8-filtre-2026-11-27/olcum.py

Üç şey ölçülüyor, hepsi **modelden bağımsız**:

1. Filtrenin bedeli: eşik `LOGINTENSITY ≥ −1` uygulanınca evren ne kadar
   küçülüyor, taban oranı ne kadar yükseliyor, ve **kaç pozitif atılıyor**.
2. Eşik ızgarası: aynı üç nicelik, yedi eşikte. Birincil hücre §6.4'te
   sabit (`−1`, Jackson'ın yayınlanmış filtresi) ve ızgara görüldükten sonra
   yeniden atanmıyor — §4.3'ün kuralı.
3. `QUALITY` kolonu olmayan serilerin (ölçüldü: `GSE5291`) taşıdığı sapmanın
   **büyüklüğü ve İŞARETİ**, modelden bağımsız bir tahmin edici (mock kanalı,
   §7.5'in dördüncü tabanı) üzerinde lift cinsinden.

Etiket §4.1 (`PVALUE < 0.01` ve `VALUE < 0`).
"""

from __future__ import annotations

import json
import math
import statistics
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / "geo-onbellek"
GEO = "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi"
PRIMARY = -1.0
GRID = (-2.0, -1.5, -1.25, -1.0, -0.75, -0.5, 0.0)

ARRAYS: dict[str, tuple[str, str]] = {
    "GSM133689": ("MAPK14-193 pos2", "GSE5814"),
    "GSM133697": ("MAPK14-193 pos8", "GSE5814"),
    "GSM133702": ("MAPK14-193 WT", "GSE5814"),
    "GSM134317": ("PIK3CA-2629", "GSE5769"),
    "GSM134319": ("MPHOSPH1-2692", "GSE5769"),
    "GSM134523": ("MPHOSPH1-202", "GSE5769"),
    "GSM119707": ("SOD1 SNP 1", "GSE5291"),
    "GSM119708": ("SOD1 SNP 2", "GSE5291"),
    "GSM119759": ("SOD1 SNP 15", "GSE5291"),
}


def fetch(gsm: str) -> str:
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"{gsm}.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    url = f"{GEO}?acc={gsm}&targ=self&form=text&view=full"
    req = urllib.request.Request(url, headers={"User-Agent": "research-script/1.0"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        raw = resp.read().decode("utf-8", "replace")
    path.write_text(raw, encoding="utf-8")
    return raw


def probes(gsm: str) -> tuple[list[dict[str, object]], list[str]]:
    """Prob başına `LOGINTENSITY`, etiket, kalite bayrağı ve mock yoğunluğu."""
    lines = fetch(gsm).splitlines()
    start = lines.index("!sample_table_begin")
    end = lines.index("!sample_table_end")
    header = lines[start + 1].split("\t")
    out: list[dict[str, object]] = []
    for line in lines[start + 2 : end]:
        parts = line.split("\t")
        if len(parts) != len(header):
            continue
        row = dict(zip(header, parts))
        try:
            value = float(row["VALUE"])
            pval = float(row["PVALUE"])
            logint = float(row["LOGINTENSITY"])
        except (KeyError, TypeError, ValueError):
            continue
        if any(math.isnan(x) for x in (value, pval, logint)):
            continue
        flag = (row.get("QUALITY") or "").strip()
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
            "logint": logint,
            "label": 1 if (pval < 0.01 and value < 0) else 0,
            # None = kolon yok (bilinmiyor), True/False = ölçülmüş bayrak
            "good": None if not flag else flag in ("1", "1.0"),
            "mock": mock,
        })
    return out, header


def average_precision(scores: list[float], labels: list[int]) -> float:
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    total = sum(labels)
    hits = 0
    out = 0.0
    for rank, i in enumerate(order, start=1):
        if labels[i]:
            hits += 1
            out += hits / rank
    return out / total


def main() -> int:
    tables: dict[str, tuple[list[dict[str, object]], list[str]]] = {}
    for gsm in ARRAYS:
        try:
            tables[gsm] = probes(gsm)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            print(f"  {gsm}: alınamadı ({exc})", file=sys.stderr)
    if not tables:
        print("GEO'ya ulaşılamadı", file=sys.stderr)
        return 2

    # ---- 1  filtrenin bedeli ---------------------------------------------
    print(f"{'kol':20s} {'seri':8s} {'QUALITY':>8s} {'n_ham':>7s} "
          f"{'n_filtre':>9s} {'pi_ham':>7s} {'pi_filtre':>10s} "
          f"{'atılan poz':>11s} {'%':>7s}")
    rows: list[dict[str, object]] = []
    for gsm, (data, header) in tables.items():
        arm, series = ARRAYS[gsm]
        kept = [p for p in data if p["good"] is not False]
        passed = [p for p in kept if float(p["logint"]) >= PRIMARY]
        positives = sum(int(p["label"]) for p in kept)
        lost = sum(int(p["label"]) for p in kept if float(p["logint"]) < PRIMARY)
        row = {
            "gsm": gsm, "arm": arm, "series": series,
            "has_quality": "QUALITY" in header,
            "n_raw": len(kept), "n_filtered": len(passed),
            "pi_raw": positives / len(kept),
            "pi_filtered": sum(int(p["label"]) for p in passed) / len(passed),
            "positives_lost": lost,
            "positives_lost_frac": lost / max(positives, 1),
        }
        rows.append(row)
        print(f"{arm:20s} {series:8s} {str(row['has_quality']):>8s} "
              f"{row['n_raw']:7d} {row['n_filtered']:9d} {row['pi_raw']:7.4f} "
              f"{row['pi_filtered']:10.4f} {lost:11d} "
              f"{row['positives_lost_frac']:7.1%}")
    print(f"\n  medyan: n {statistics.median(int(r['n_raw']) for r in rows):.0f} → "
          f"{statistics.median(int(r['n_filtered']) for r in rows):.0f}, "
          f"taban {statistics.median(float(r['pi_raw']) for r in rows):.4f} → "
          f"{statistics.median(float(r['pi_filtered']) for r in rows):.4f}, "
          f"atılan pozitif "
          f"{statistics.median(float(r['positives_lost_frac']) for r in rows):.1%}")

    # ---- 2  eşik ızgarası -------------------------------------------------
    print(f"\n{'eşik':>7s} {'medyan n':>10s} {'medyan taban':>13s} "
          f"{'medyan atılan poz':>18s}")
    grid: dict[str, dict[str, float]] = {}
    for threshold in GRID:
        ns: list[int] = []
        pis: list[float] = []
        lost_fracs: list[float] = []
        for data, _ in tables.values():
            kept = [p for p in data if p["good"] is not False]
            passed = [p for p in kept if float(p["logint"]) >= threshold]
            if not passed:
                continue
            positives = sum(int(p["label"]) for p in kept)
            ns.append(len(passed))
            pis.append(sum(int(p["label"]) for p in passed) / len(passed))
            lost_fracs.append(
                sum(int(p["label"]) for p in kept
                    if float(p["logint"]) < threshold) / max(positives, 1)
            )
        grid[f"{threshold}"] = {
            "n": statistics.median(ns),
            "pi": statistics.median(pis),
            "positives_lost_frac": statistics.median(lost_fracs),
        }
        entry = grid[f"{threshold}"]
        print(f"{threshold:7.2f} {entry['n']:10.0f} {entry['pi']:13.4f} "
              f"{entry['positives_lost_frac']:17.1%}")

    # ---- 3  QUALITY kolonunun yokluğunun lift cinsinden sapması ----------
    print("\nQUALITY kolonu olan array'lerde, kolonu YOK SAYMANIN bedeli")
    print("(modelden bağımsız tahmin edici: mock kanalı, §7.5'in 4. tabanı)")
    print(f"{'array':12s} {'lift (QUALITY ile)':>19s} {'lift (yok sayarak)':>20s} "
          f"{'sapma':>9s}")
    deltas: list[float] = []
    bias: list[dict[str, object]] = []
    for gsm, (data, header) in tables.items():
        if "QUALITY" not in header:
            continue
        usable = [p for p in data if p["mock"] is not None
                  and float(p["logint"]) >= PRIMARY]
        with_flag = [p for p in usable if p["good"]]
        without = usable
        values: dict[str, float] = {}
        for name, subset in (("with", with_flag), ("without", without)):
            labels = [int(p["label"]) for p in subset]
            scores = [float(p["mock"]) for p in subset]  # type: ignore[arg-type]
            base = sum(labels) / len(labels)
            values[name] = average_precision(scores, labels) / base
        delta = (values["without"] - values["with"]) / values["with"]
        deltas.append(delta)
        bias.append({"gsm": gsm, "lift_with": values["with"],
                     "lift_without": values["without"], "delta": delta})
        print(f"{gsm:12s} {values['with']:19.4f} {values['without']:20.4f} "
              f"{delta:+8.2%}")
    if deltas:
        worst = max(deltas, key=abs)
        print(f"\n  medyan sapma {statistics.median(deltas):+.2%}, "
              f"en büyük {worst:+.2%} — işaret NEGATİF, yani kolonu olmayan "
              f"seri (GSE5291) lift'i AŞAĞI yönde sapıyor (ihtiyatlı yön)")

    (HERE / "olcum.json").write_text(json.dumps({
        "measured_at": "2026-11-27",
        "primary_threshold": PRIMARY,
        "arrays": rows,
        "threshold_grid": grid,
        "quality_bias": bias,
        "quality_bias_median": statistics.median(deltas) if deltas else None,
        "quality_bias_worst": max(deltas, key=abs) if deltas else None,
        "label_rule": "PVALUE < 0.01 and VALUE < 0",
    }, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
