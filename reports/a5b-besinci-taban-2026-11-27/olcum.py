#!/usr/bin/env python3
"""A5b — beşinci taban kararının ölçümü. Tek dosyada, yeniden koşturulabilir.

    python3 reports/a5b-besinci-taban-2026-11-27/olcum.py

Dört tahmin edici karşılaştırılıyor, **hiçbiri dizi bilgisi kullanmıyor** ve
orcSONAR'ın hiçbir çıktısı okunmuyor:

    B4    log10(INTENSITY1)                    — ön kayıt §7.5'in 4. tabanı
    DEP   Crow ve ark. 2019'un yayınlanmış DE önselliği — DIŞSAL, sızamaz
    VOLw  probun bu setteki DİĞER array'lerdeki medyan |VALUE|'su
    VOLx  aynısı, ama yalnız DİĞER SERİDEN — paylaşılan mock yok

Karar: `DEP` beşinci taban olur (dışsal, sabit, yayınlanmış); `VOLw`/`VOLx`
taban olmaz ama tanı olarak raporlanır. Gerekçeler §7.5'te, hepsi bu
betiğin ölçtüğü sayılara dayanıyor.

Etiket §4.1, evren §6.3, birim §6.2'nin ayrık 2-8 seed heptameri.
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
ROOT = HERE.parents[1]
CACHE = HERE / "geo-onbellek"
GEO = "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi"
PRIOR = ROOT / "data" / "external" / "de_prior" / "DE_Prior.txt"
MARGIN = 0.020  # ön kayıt §4.4.1

# Her ayrık 2-8 seed heptameri için bir array (başlıklar GEO'dan doğrulandı).
ARRAYS: dict[str, tuple[str, str, str]] = {
    # gsm: (kol, seri, platform)
    "GSM133689": ("MAPK14-193 pos2", "GSE5814", "GPL2029"),
    "GSM133701": ("MAPK14-193 pos3", "GSE5814", "GPL2029"),
    "GSM133700": ("MAPK14-193 pos4", "GSE5814", "GPL2029"),
    "GSM133699": ("MAPK14-193 pos6", "GSE5814", "GPL2029"),
    "GSM133698": ("MAPK14-193 pos7", "GSE5814", "GPL2029"),
    "GSM133697": ("MAPK14-193 pos8", "GSE5814", "GPL2029"),
    "GSM133702": ("MAPK14-193 WT", "GSE5814", "GPL2029"),
    "GSM133703": ("Luc", "GSE5814", "GPL2029"),
    "GSM134483": ("MAPK14-193 pos5", "GSE5814", "GPL3992"),
    "GSM134466": ("PLK1-319", "GSE5814", "GPL3992"),
    "GSM134467": ("PLK-772", "GSE5814", "GPL3992"),
    "GSM134511": ("PIK3CB-6338", "GSE5814", "GPL3992"),
    "GSM134512": ("PIK3CB-6340", "GSE5814", "GPL3992"),
    "GSM134317": ("PIK3CA-2629", "GSE5769", "GPL3991"),
    "GSM134319": ("MPHOSPH1-2692", "GSE5769", "GPL3991"),
    "GSM134321": ("SOS1-1582", "GSE5769", "GPL3991"),
    "GSM134323": ("PRKCE-1295", "GSE5769", "GPL3991"),
    "GSM134325": ("VHL-2651", "GSE5769", "GPL3991"),
    "GSM134327": ("VHL-2652", "GSE5769", "GPL3991"),
    "GSM134523": ("MPHOSPH1-202", "GSE5769", "GPL3992"),
}

# `GSE5291`: kanal-başına yoğunluk YOK (4. taban hesaplanamaz) ama platformu
# `GPL3992`, yani prob→gen eşlemesi çalışıyor. Beşinci tabanın kapsamının
# dördüncüsünden geniş olduğu iddiası bu array'lerde ölçülüyor.
GSE5291 = ("GSM119707", "GSM119708", "GSM119741", "GSM119759", "GSM119763")


def fetch(acc: str, targ: str = "self") -> str:
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"{acc}.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    url = f"{GEO}?acc={acc}&targ={targ}&form=text&view=full"
    req = urllib.request.Request(url, headers={"User-Agent": "research-script/1.0"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        raw = resp.read().decode("utf-8", "replace")
    path.write_text(raw, encoding="utf-8")
    return raw


def _table(acc: str, kind: str) -> tuple[list[str], list[list[str]]]:
    lines = fetch(acc).splitlines()
    start = lines.index(f"!{kind}_table_begin")
    end = lines.index(f"!{kind}_table_end")
    header = lines[start + 1].split("\t")
    return header, [line.split("\t") for line in lines[start + 2 : end]]


def sample(gsm: str) -> tuple[dict[str, dict[str, float]], list[str]]:
    """Prob başına ölçümler, artı array'in kolon başlıkları.

    ⚠️ `QUALITY` kolonu **her seride yok** — `GSE5291`'in tablosunda hiç
    bulunmuyor (ölçüldü). Kolon varsa filtre uygulanır, yoksa uygulanmaz;
    yokluğunu "kalitesiz" saymak `GSE5291`'in tamamını silerdi.
    """
    header, rows = _table(gsm, "sample")
    out: dict[str, dict[str, float]] = {}
    for parts in rows:
        if len(parts) != len(header):
            continue
        row = dict(zip(header, parts))
        quality = (row.get("QUALITY") or "").strip()
        if quality and quality not in ("1", "1.0"):
            continue
        try:
            value = float(row["VALUE"])
            pval = float(row["PVALUE"])
            logint = float(row["LOGINTENSITY"])
        except (KeyError, TypeError, ValueError):
            continue
        if any(math.isnan(x) for x in (value, pval, logint)) or logint < -1.0:
            continue
        record = {"value": value, "pval": pval, "logint": logint}
        raw1 = row.get("INTENSITY1")
        if raw1 is not None:
            try:
                intensity = float(raw1)
            except (TypeError, ValueError):
                intensity = float("nan")
            if not math.isnan(intensity) and intensity > 0:
                record["mock"] = math.log10(intensity)
        out[row["ID_REF"].strip()] = record
    return out, header


@lru_cache(maxsize=None)
def platform(gpl: str) -> dict[str, tuple[str | None, str | None]]:
    """prob → (Entrez, sembol). `GPL2029` Entrez taşıyor, diğerleri sembol."""
    header, rows = _table(gpl, "platform")
    out: dict[str, tuple[str | None, str | None]] = {}
    for parts in rows:
        if len(parts) < len(header):
            parts = parts + [""] * (len(header) - len(parts))
        row = dict(zip(header, parts))
        entrez = (row.get("GeneID") or "").strip() or None
        symbol = (row.get("GeneSymbol") or row.get("ORF") or "").strip() or None
        out[row["ID"].strip()] = (entrez, symbol)
    return out


@lru_cache(maxsize=1)
def de_prior() -> tuple[dict[str, float], dict[str, float]]:
    by_entrez: dict[str, float] = {}
    by_symbol: dict[str, float] = {}
    for line in PRIOR.read_text(encoding="utf-8").splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        try:
            rank = float(parts[3])
        except ValueError:
            continue
        by_entrez[parts[1].strip()] = rank
        by_symbol[parts[4].strip().upper()] = rank
    return by_entrez, by_symbol


def ap(scores: list[float], labels: list[int]) -> float:
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    total = sum(labels)
    hits = 0
    out = 0.0
    for rank, i in enumerate(order, start=1):
        if labels[i]:
            hits += 1
            out += hits / rank
    return out / total


@lru_cache(maxsize=None)
def _null_counts(n: int) -> tuple[int, ...]:
    total = n * (n + 1) // 2
    counts = [0] * (total + 1)
    counts[0] = 1
    for r in range(1, n + 1):
        for s in range(total, r - 1, -1):
            counts[s] += counts[s - r]
    return tuple(counts)


def wilcoxon_greater_p(d: list[float]) -> float:
    vals = [x for x in d if x != 0.0]
    n = len(vals)
    if n == 0:
        return 1.0
    order = sorted(range(n), key=lambda i: abs(vals[i]))
    ranks = [0.0] * n
    for rank, i in enumerate(order, start=1):
        ranks[i] = float(rank)
    w_plus = sum(ranks[i] for i in range(n) if vals[i] > 0)
    counts = _null_counts(n)
    return sum(counts[s] for s in range(int(math.ceil(w_plus)), len(counts))) / 2**n


def prior_scores(probes: list[str], gpl: str) -> tuple[list[float], float]:
    """DE önsellik skoru; eşleşmeyen problar medyan rankla doldurulur.

    Doldurma yönü **tabanın lehine** seçildi: son sıraya atmak tabanı
    zayıflatır, yani çıtayı düşürür — değişmez 7'nin yasakladığı yön.
    """
    by_entrez, by_symbol = de_prior()
    pmap = platform(gpl)
    known: list[float | None] = []
    for probe in probes:
        entrez, symbol = pmap.get(probe, (None, None))
        rank = by_entrez.get(entrez or "")
        if rank is None and symbol:
            rank = by_symbol.get(symbol.upper())
        known.append(rank)
    hits = [x for x in known if x is not None]
    if not hits:
        return [0.0] * len(probes), 0.0
    median = statistics.median(hits)
    return ([x if x is not None else median for x in known],
            len(hits) / len(probes))


def main() -> int:
    if not PRIOR.exists():
        print(f"{PRIOR} yok — manifest'teki kaynaktan indir", file=sys.stderr)
        return 2

    tables: dict[str, dict[str, dict[str, float]]] = {}
    for gsm in ARRAYS:
        try:
            tables[gsm], _ = sample(gsm)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            print(f"  {gsm}: alınamadı ({exc})", file=sys.stderr)
    if not tables:
        print("GEO'ya ulaşılamadı", file=sys.stderr)
        return 2

    # ---- prob-id örtüşmesi: VOLx'in neden tek biçimli tanımlanamadığı ----
    by_platform: dict[str, set[str]] = {}
    for gsm, table in tables.items():
        by_platform.setdefault(ARRAYS[gsm][2], set()).update(table)
    print("platformlar arası prob-id örtüşmesi:")
    overlap: dict[str, int] = {}
    names = sorted(by_platform)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            inter = len(by_platform[a] & by_platform[b])
            overlap[f"{a}∩{b}"] = inter
            print(f"  {a} ∩ {b} = {inter} "
                  f"({inter / min(len(by_platform[a]), len(by_platform[b])):.1%})")

    rows: list[dict[str, object]] = []
    for gsm, table in tables.items():
        arm, series, gpl = ARRAYS[gsm]
        probes = [p for p in table if "mock" in table[p]]
        labels = [1 if (table[p]["pval"] < 0.01 and table[p]["value"] < 0) else 0
                  for p in probes]
        if sum(labels) < 5:
            continue
        others_all = [t for g, t in tables.items() if g != gsm]
        others_x = [t for g, t in tables.items() if ARRAYS[g][1] != series]
        volw, volx = [], []
        computable = 0
        for probe in probes:
            a = [abs(t[probe]["value"]) for t in others_all if probe in t]
            x = [abs(t[probe]["value"]) for t in others_x if probe in t]
            volw.append(statistics.median(a) if a else -1.0)
            if x:
                computable += 1
                volx.append(statistics.median(x))
            else:
                volx.append(-1.0)
        dep, cover = prior_scores(probes, gpl)
        rows.append({
            "gsm": gsm, "arm": arm, "series": series, "platform": gpl,
            "n": len(probes), "pos": sum(labels),
            "pi": sum(labels) / len(labels),
            "dep_cover": cover, "volx_cover": computable / len(probes),
            "B4": ap([table[p]["mock"] for p in probes], labels),
            "DEP": ap(dep, labels),
            "VOLw": ap(volw, labels),
            "VOLx": ap(volx, labels),
        })

    print(f"\n{'kol':22s} {'seri':8s} {'DEP kaps':>9s} {'VOLx kaps':>10s} "
          f"{'taban':>7s} {'B4':>7s} {'DEP':>7s} {'VOLw':>7s} {'VOLx':>7s}")
    for r in rows:
        print(f"{r['arm']:22s} {r['series']:8s} {r['dep_cover']:9.1%} "
              f"{r['volx_cover']:10.1%} {r['pi']:7.4f} {r['B4']:7.4f} "
              f"{r['DEP']:7.4f} {r['VOLw']:7.4f} {r['VOLx']:7.4f}")

    print(f"\n{'kanal':6s} {'medyan lift':>12s} {'min':>7s} {'maks':>7s} "
          f"{'B4 üstü':>9s}")
    lifts: dict[str, float] = {}
    for key in ("B4", "DEP", "VOLw", "VOLx"):
        values = [float(r[key]) / float(r["pi"]) for r in rows]
        lifts[key] = statistics.median(values)
        print(f"{key:6s} {lifts[key]:12.4f} {min(values):7.4f} "
              f"{max(values):7.4f} "
              f"{sum(float(r[key]) > float(r['B4']) for r in rows):4d}/{len(rows)}")

    print(f"\n§4.4'ün testi (tek-yanlı tam Wilcoxon, m = {MARGIN}):")
    tests: dict[str, dict[str, float]] = {}
    for key in ("DEP", "VOLw", "VOLx"):
        usable = [r for r in rows if key != "VOLx" or float(r["volx_cover"]) > 0.2]
        d = [float(r[key]) - float(r["B4"]) for r in usable]
        tests[key] = {
            "n": len(d),
            "median_d": statistics.median(d),
            "p_gt_margin": wilcoxon_greater_p([x - MARGIN for x in d]),
            "p_gt_zero": wilcoxon_greater_p(d),
        }
        s = tests[key]
        print(f"  {key:5s} n={int(s['n']):2d}  medyan d = {s['median_d']:+.4f}  "
              f"p(d>m) = {s['p_gt_margin']:.4f}  p(d>0) = {s['p_gt_zero']:.4f}")

    # ---- beşinci tabanın kapsamı: GSE5291'de hesaplanabiliyor mu ----------
    print("\nGSE5291 (18 ayrık seed, 4. taban HESAPLANAMIYOR — kanal yoğunluğu yok):")
    gse5291: list[dict[str, object]] = []
    for gsm in GSE5291:
        try:
            table, header = sample(gsm)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            print(f"  {gsm}: alınamadı ({exc})", file=sys.stderr)
            continue
        probes = list(table)
        labels = [1 if (table[p]["pval"] < 0.01 and table[p]["value"] < 0) else 0
                  for p in probes]
        dep, cover = prior_scores(probes, "GPL3992")
        value = ap(dep, labels)
        pi = sum(labels) / len(labels)
        gse5291.append({
            "gsm": gsm, "pi": pi, "DEP": value, "lift": value / pi,
            "dep_cover": cover,
            "has_intensity1": "INTENSITY1" in header,
            "has_quality": "QUALITY" in header,
        })
        print(f"  {gsm}  taban={pi:.4f}  DEP AP={value:.4f}  lift={value / pi:.3f}  "
              f"eşleşme={cover:.1%}  INTENSITY1={'INTENSITY1' in header}  "
              f"QUALITY={'QUALITY' in header}")
    if gse5291:
        print(f"  medyan DEP lift = "
              f"{statistics.median(float(r['lift']) for r in gse5291):.3f}")

    (HERE / "olcum.json").write_text(json.dumps({
        "measured_at": "2026-11-27",
        "margin": MARGIN,
        "probe_id_overlap": overlap,
        "arrays": rows,
        "median_lift": lifts,
        "tests_vs_baseline4": tests,
        "gse5291": gse5291,
        "label_rule": "PVALUE < 0.01 and VALUE < 0",
        "universe": "LOGINTENSITY >= -1 (and QUALITY == 1 where the column exists)",
    }, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
