#!/usr/bin/env python3
"""A6a — ön kaydın §4.4'teki marjının, σ̂_d'sinin, çözünürlük talebinin ve güç
tablosunun ölçümü. Tek dosyada, yeniden koşturulabilir.

    python3 reports/a6a-marj-2026-11-27/olcum.py

Yazdığı dosyalar bu dizinde: ``marj.json``, ``cozunurluk.json``.

⚠️ Bu ölçümün tamamı **modelden bağımsızdır**: kullanılan iki tahmin edici de
(mock kanalı yoğunluğu ve probun diğer array'lerdeki ifade oynaklığı) hiçbir
dizi bilgisi taşımıyor, ve orcSONAR'ın hiçbir çıktısı okunmuyor. Marjı modelin
çıktısını gördükten sonra sabitlemek değişmez 6'nın ihlali olurdu; bu yüzden
ölçüm kilitten **önce** ve modelden bağımsız yapıldı.

Etiket §4.1 (`PVALUE < 0.01` ve `VALUE < 0`), evren §6.3 (Jackson'ın
yayınlanmış filtresi, `LOGINTENSITY ≥ −1`, ve `QUALITY == 1`), birim §6.2'nin
ayrık 2-8 seed heptameri — her seed için bir array.
"""

from __future__ import annotations

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
CACHE = HERE / "geo-onbellek"
GEO = "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi"

# Her ayrık 2-8 seed heptameri için BİR array. Kol başlıkları GEO'dan
# doğrulandı (2026-11-27). `GSE5814`'ün 1. ve 9-19. pozisyon mutantları
# yabani-tip seed'i aynen taşıdığı için listede yok (§7.1'in sızıntı kuralı);
# `GSE5291` kanal-başına yoğunluk taşımadığı için bu ölçümde yer almıyor
# (§7.5'in ikinci düzeltmesi).
ARRAYS: dict[str, str] = {
    "GSM133689": "MAPK14-193 pos2",
    "GSM133701": "MAPK14-193 pos3",
    "GSM133700": "MAPK14-193 pos4",
    "GSM133699": "MAPK14-193 pos6",
    "GSM133698": "MAPK14-193 pos7",
    "GSM133697": "MAPK14-193 pos8",
    "GSM133702": "MAPK14-193 WT",
    "GSM133703": "Luc",
    "GSM134483": "MAPK14-193 pos5",
    "GSM134466": "PLK1-319",
    "GSM134467": "PLK-772",
    "GSM134511": "PIK3CB-6338",
    "GSM134512": "PIK3CB-6340",
    "GSM134317": "PIK3CA-2629",
    "GSM134319": "MPHOSPH1-2692",
    "GSM134321": "SOS1-1582",
    "GSM134323": "PRKCE-1295",
    "GSM134325": "VHL-2651",
    "GSM134327": "VHL-2652",
    "GSM134523": "MPHOSPH1-202",
}

LEVELS = (1, 12, 50, 100, 250, 500, 1000, 2500, 5000)
SEED = 20261127


# --------------------------------------------------------------------------
# GEO
# --------------------------------------------------------------------------
def fetch(gsm: str) -> str:
    """GEO'nun SOFT metnini getir, bu dizinde önbelleğe al."""
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


def parse(gsm: str) -> dict[str, dict[str, float]]:
    """Prob başına `VALUE`, `PVALUE`, `LOGINTENSITY` ve `log10(INTENSITY1)`."""
    lines = fetch(gsm).splitlines()
    start = lines.index("!sample_table_begin")
    end = lines.index("!sample_table_end")
    header = lines[start + 1].split("\t")
    out: dict[str, dict[str, float]] = {}
    for line in lines[start + 2 : end]:
        parts = line.split("\t")
        if len(parts) != len(header):
            continue
        row = dict(zip(header, parts))
        if (row.get("QUALITY") or "").strip() not in ("1", "1.0"):
            continue
        try:
            value = float(row["VALUE"])
            pval = float(row["PVALUE"])
            logint = float(row["LOGINTENSITY"])
            raw1 = float(row["INTENSITY1"])
        except (KeyError, TypeError, ValueError):
            continue
        if any(math.isnan(x) for x in (value, pval, logint, raw1)) or raw1 <= 0:
            continue
        out[row["ID_REF"]] = {
            "value": value,
            "pval": pval,
            "logint": logint,
            "mock": math.log10(raw1),
        }
    return out


# --------------------------------------------------------------------------
# AP ve bağlantı açıklığı
# --------------------------------------------------------------------------
def ap_from_order(labels: list[int]) -> float:
    """İnterpolasyonsuz ortalama kesinlik, verilmiş sıra üzerinde."""
    total = sum(labels)
    hits = 0
    ap = 0.0
    for rank, lab in enumerate(labels, start=1):
        if lab:
            hits += 1
            ap += hits / rank
    return ap / total


def average_precision(scores: list[float], labels: list[int]) -> float:
    """`sklearn.metrics.average_precision_score` ile aynı nicelik (§2)."""
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    return ap_from_order([labels[i] for i in order])


def ap_span(scores: list[float], labels: list[int]) -> tuple[float, float]:
    """(en kötü, en iyi) AP: bağlantı grupları içinde pozitifler sonda / başta."""
    idx = sorted(range(len(scores)), key=lambda i: -scores[i])
    pess: list[int] = []
    opt: list[int] = []
    i = 0
    while i < len(idx):
        j = i
        while j < len(idx) and scores[idx[j]] == scores[idx[i]]:
            j += 1
        group = [labels[k] for k in idx[i:j]]
        ones = sum(group)
        pess.extend([0] * (len(group) - ones) + [1] * ones)
        opt.extend([1] * ones + [0] * (len(group) - ones))
        i = j
    return ap_from_order(pess), ap_from_order(opt)


# --------------------------------------------------------------------------
# Tam Wilcoxon ve güç
# --------------------------------------------------------------------------
@lru_cache(maxsize=None)
def null_counts(n: int) -> tuple[int, ...]:
    """`W+`'ın null dağılımı: 1..n sıralarının altküme toplamlarının sayımı."""
    total = n * (n + 1) // 2
    counts = [0] * (total + 1)
    counts[0] = 1
    for r in range(1, n + 1):
        for s in range(total, r - 1, -1):
            counts[s] += counts[s - r]
    return tuple(counts)


def wilcoxon_greater_p(d: list[float]) -> float:
    """H1: medyan(d) > 0 için TAM tek-yanlı p-değeri (sıfırlar atılır)."""
    vals = [x for x in d if x != 0.0]
    n = len(vals)
    if n == 0:
        return 1.0
    order = sorted(range(n), key=lambda i: abs(vals[i]))
    ranks = [0.0] * n
    for rank, i in enumerate(order, start=1):
        ranks[i] = float(rank)
    w_plus = sum(ranks[i] for i in range(n) if vals[i] > 0)
    counts = null_counts(n)
    tail = sum(counts[s] for s in range(int(math.ceil(w_plus)), len(counts)))
    return tail / float(2**n)


def power(n: int, delta: float, sigma: float, reps: int = 4000,
          alpha: float = 0.05, seed: int = 11) -> float:
    """Simülasyonla güç: `d_i ~ N(delta, sigma)`, tek-yanlı tam Wilcoxon."""
    gen = random.Random(seed)
    hits = 0
    for _ in range(reps):
        hits += wilcoxon_greater_p([gen.gauss(delta, sigma) for _ in range(n)]) < alpha
    return hits / reps


# --------------------------------------------------------------------------
def main() -> int:
    tables: dict[str, dict[str, dict[str, float]]] = {}
    for gsm in ARRAYS:
        try:
            tables[gsm] = parse(gsm)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            print(f"  {gsm}: alınamadı ({exc})", file=sys.stderr)
    if not tables:
        print("GEO'ya ulaşılamadı — ölçüm yapılamadı", file=sys.stderr)
        return 2

    rng = random.Random(SEED)
    rows: list[dict[str, object]] = []
    for gsm, table in tables.items():
        others = [t for g, t in tables.items() if g != gsm]
        probes = [p for p, r in table.items() if r["logint"] >= -1.0]
        labels = [
            1 if (table[p]["pval"] < 0.01 and table[p]["value"] < 0) else 0
            for p in probes
        ]
        if sum(labels) < 5:
            print(f"  {gsm}: {sum(labels)} pozitif — atlandı", file=sys.stderr)
            continue
        b4 = [table[p]["mock"] for p in probes]
        var: list[float] = []
        vol: list[float] = []
        for p in probes:
            mocks = [t[p]["mock"] for t in others if p in t]
            vals = [abs(t[p]["value"]) for t in others if p in t]
            var.append(statistics.pstdev(mocks) if len(mocks) > 2 else 0.0)
            vol.append(statistics.median(vals) if vals else 0.0)
        rows.append({
            "gsm": gsm,
            "arm": ARRAYS[gsm],
            "n": len(probes),
            "pos": sum(labels),
            "pi": sum(labels) / len(labels),
            "B4": average_precision(b4, labels),
            "VAR": average_precision(var, labels),
            "VOL": average_precision(vol, labels),
            "R1": average_precision([rng.random() for _ in probes], labels),
            "R2": average_precision([rng.random() for _ in probes], labels),
        })

    print(f"\n{'kol':22s} {'n':>6s} {'poz':>5s} {'taban':>7s} "
          f"{'B4':>7s} {'VAR':>7s} {'VOL':>7s} {'R1':>7s} {'R2':>7s}")
    for r in rows:
        print(f"{r['arm']:22s} {r['n']:6d} {r['pos']:5d} {r['pi']:7.4f} "
              f"{r['B4']:7.4f} {r['VAR']:7.4f} {r['VOL']:7.4f} "
              f"{r['R1']:7.4f} {r['R2']:7.4f}")

    pairs = [("B4", "VAR"), ("B4", "VOL"), ("VAR", "VOL"), ("R1", "R2"),
             ("B4", "R1"), ("VAR", "R1"), ("VOL", "R1")]
    summary: dict[str, dict[str, float]] = {}
    print(f"\n{'çift':12s} {'n':>3s} {'medyan |d|':>11s} {'sd(d)':>9s} "
          f"{'medyan d':>9s}")
    for a, b in pairs:
        d = [float(r[a]) - float(r[b]) for r in rows]
        summary[f"{a}-{b}"] = {
            "n": len(d),
            "median_abs": statistics.median(abs(x) for x in d),
            "sd": statistics.stdev(d),
            "median": statistics.median(d),
        }
        s = summary[f"{a}-{b}"]
        print(f"{a + '-' + b:12s} {int(s['n']):3d} {s['median_abs']:11.4f} "
              f"{s['sd']:9.4f} {s['median']:9.4f}")

    margin = 0.020  # §4.4.1: ölçülen 0,0162'nin ikinci ondalığa yukarı yuvarlanmışı
    sigma = max(summary[k]["sd"] for k in ("B4-VAR", "B4-VOL", "VAR-VOL"))
    print(f"\nmedyan taban oranı = {statistics.median(float(r['pi']) for r in rows):.4f}")
    print(f"marj m = {margin:.3f} AP, ihtiyatlı σ̂_d = {sigma:.4f}")

    (HERE / "marj.json").write_text(json.dumps({
        "measured_at": "2026-11-27",
        "arrays": rows,
        "pairs": summary,
        "label_rule": "PVALUE < 0.01 and VALUE < 0",
        "universe": "QUALITY == 1 and LOGINTENSITY >= -1",
    }, indent=2), encoding="utf-8")

    # ---- çözünürlük ------------------------------------------------------
    spans: dict[int, list[float]] = {k: [] for k in LEVELS}
    for r in rows:
        table = tables[str(r["gsm"])]
        probes = [p for p, q in table.items() if q["logint"] >= -1.0]
        labels = [
            1 if (table[p]["pval"] < 0.01 and table[p]["value"] < 0) else 0
            for p in probes
        ]
        b4 = [table[p]["mock"] for p in probes]
        lo, hi = min(b4), max(b4)
        for k in LEVELS:
            if k == 1:
                sc: list[float] = [1.0] * len(b4)
            else:
                sc = [math.floor((v - lo) / (hi - lo) * (k - 0.001)) for v in b4]
            worst, best = ap_span(sc, labels)
            spans[k].append(best - worst)

    print(f"\n{'kademe':>8s} {'medyan açıklık':>15s} {'maks açıklık':>13s} "
          f"{'maks ≤ m/2':>11s}")
    for k in LEVELS:
        v = spans[k]
        print(f"{k:8d} {statistics.median(v):15.4f} {max(v):13.4f} "
              f"{'evet' if max(v) <= margin / 2 else 'hayır':>11s}")
    (HERE / "cozunurluk.json").write_text(json.dumps(
        {str(k): {"median": statistics.median(v), "max": max(v)}
         for k, v in spans.items()}, indent=2), encoding="utf-8")

    # ---- güç -------------------------------------------------------------
    print("\nguç — tek-yanlı eşleşmiş tam Wilcoxon, α=0,05, δ=m")
    for n, what in ((43, "tüm seed'ler"), (25, "dördüncü taban"),
                    (14, "tabaka içi")):
        print(f"  n={n:3d}  {what:16s} {power(n, margin, sigma):.3f}")
    inner = power(14, margin, sigma)
    print(f"  12 kesişimsel koşul, bağımsızlık alt sınırı: {inner**12:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
