#!/usr/bin/env bash
# Kabul kriteri — A8: "§6'da filtre tanımı + eşik, ve QUALITY kolonu olmayan
# seriler için davranış yazılı".
#
# Dokuz ölçüm. 4, 5 ve 6 ayırt edici olanlar.
#
#   1  §6.4 var, yer tutucu yok, dört alt bölümü yazılı, ve §6.3 ona işaret
#      ediyor (ikinci bir filtre tanımı iki kopya olurdu)
#   2  BİRİNCİL eşik sayıyla yazılı ve kaynağından alıntılanmış
#   3  IZGARA ilan edilmiş (≥ 6 satır), ve birincilin yeniden atanmayacağı
#      yazılı
#   4  AĞ, ASIL ÖLÇÜM: filtrenin bedeli GEO'dan yeniden ölçülüyor — evren
#      küçülmesi, taban yükselmesi ve **atılan pozitif oranı** §6.4.2'nin
#      yazdığı aralıkta. Bedava bir filtre iddiası bu ölçümle çürür
#   5  AĞ, KONTROL: ızgaranın monotonluğu — daha gevşek eşikte atılan pozitif
#      oranı KESİNLİKLE daha küçük. Bu olmadan 4. ölçüm eşiği değil veriyi
#      ölçmüş olurdu
#   6  AĞ, ASIL ÖLÇÜM: `GSE5291`'de `QUALITY` kolonu YOK, `GSE5814`'te VAR;
#      ve kolonu yok saymanın modelden bağımsız bir tahmin edicinin lift'ine
#      etkisi §6.4.4'ün ilan ettiği sınırın içinde **ve işareti negatif**.
#      İşaret önemli: pozitif olsa kolonu olmayan seri avantajlı olurdu
#   7  CCLE reddi bir YAPI argümanı, ve ulaşılabilirliği manifest'te kayıtlı
#      (reddi "ulaşılamıyor" sanmak kaydı yok eder)
#   8  ölçümün kaydı depoda, betiğiyle
#   9  `A13`'ün haritası §6'yı A8'e veriyor
#
# ⚠️ 4-6 ağ gerektirir; ağ yoksa ATLANIR, ama ölçüm §6.4'ü yanlışlarsa
# atlanmaz, GEÇMEZ (`H17`).

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

fail() { echo "GEÇMEDİ — $1"; exit 1; }

# shellcheck source=_lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

PY=""
for cand in "${PYTHON:-}" python3 python; do
    [ -n "$cand" ] || continue
    if "$cand" -c "import yaml" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || fail "pyyaml içeren yorumlayıcı bulunamadı; PYTHON=... ile ver"
echo "# yorumlayıcı: $PY"

warn_untracked docs .claude reports data/external || true

"$PY" - <<'INNER' || exit 1
from __future__ import annotations

import json
import math
import re
import statistics
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

DOC = Path("docs/PRE_REGISTRATION.md")
MAP = Path(".claude/prereg_sections.yaml")
MANIFEST = Path("data/external/manifest.json")
RECORD = Path("reports/a8-filtre-2026-11-27")

problems: list[str] = []
text = DOC.read_text(encoding="utf-8")

found = re.search(r"^### 6\.4 (.+?)$(.*?)(?=^## 7\.)", text, re.S | re.M)
if not found:
    sys.exit("§6.4 (tespit edilebilirlik filtresi) bölümü bulunamadı")
body = found.group(2)

# ---- 1  bölüm ve işaret ---------------------------------------------------
leftovers = re.findall(r"<[^<>\n]{10,}>", body)
if leftovers:
    problems.append(f"§6.4'te yer tutucu kalmış: {leftovers[:2]}")
absent = [f"6.4.{i}" for i in range(1, 5) if f"#### 6.4.{i}" not in body]
if absent:
    problems.append(f"§6.4 alt bölümleri eksik: {absent}")
if not re.search(r"§6\.4\*{0,2}'te \(`A8`\)|\*\*§6\.4\*\*'te", text):
    problems.append("§6.3 filtre tanımı için §6.4'e işaret etmiyor")
if not problems:
    print("  1  §6.4 dolu, dört alt bölümü yazılı, §6.3 ona işaret ediyor")

# ---- 2  birincil eşik -----------------------------------------------------
primary = re.search(r"`LOGINTENSITY ≥ (−|-)(\d+(?:[.,]\d+)?)`", body)
if primary is None:
    problems.append("§6.4 birincil eşiği `LOGINTENSITY ≥ −N` biçiminde yazmıyor")
    THRESHOLD = None
else:
    THRESHOLD = -float(primary.group(2).replace(",", "."))
    if "copy/cell" not in body:
        problems.append("§6.4 eşiği kaynağından alıntılamıyor (Jackson'ın filtresi)")
    else:
        print(f"  2  birincil eşik {THRESHOLD}, kaynağından alıntılanmış")

# ---- 3  ızgara ------------------------------------------------------------
grid_rows = re.findall(r"^\|\s*\*{0,2}(−|-)?(\d+[.,]\d+)[^|]*\|", body, re.M)
if len(grid_rows) < 6:
    problems.append(f"§6.4.3'ün ızgarası {len(grid_rows)} satır, en az 6 olmalı")
elif not re.search(r"yeniden atanmaz", body):
    problems.append("§6.4.3 birincilin yeniden atanmayacağını yazmıyor")
else:
    print(f"  3  ızgara {len(grid_rows)} satır, birincil yeniden atanmaz yazılı")

# ---- ölçüm altyapısı ------------------------------------------------------
GEO = "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi"
WITH_QUALITY = "GSM133702"     # GSE5814
NO_QUALITY = "GSM119707"       # GSE5291


def probes(gsm: str) -> tuple[list[dict[str, object]], list[str]] | None:
    url = f"{GEO}?acc={gsm}&targ=self&form=text&view=full"
    req = urllib.request.Request(url, headers={"User-Agent": "research-script/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=240) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError):
        return None
    lines = raw.splitlines()
    try:
        start = lines.index("!sample_table_begin")
        end = lines.index("!sample_table_end")
    except ValueError:
        return None
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
            "good": None if not flag else flag in ("1", "1.0"),
            "mock": mock,
        })
    return out, header


def lost_fraction(data: list[dict[str, object]], threshold: float) -> float:
    kept = [p for p in data if p["good"] is not False]
    positives = sum(int(p["label"]) for p in kept)
    lost = sum(int(p["label"]) for p in kept if float(p["logint"]) < threshold)
    return lost / max(positives, 1)


def lift(subset: list[dict[str, object]]) -> float:
    labels = [int(p["label"]) for p in subset]
    scores = [float(p["mock"]) for p in subset]  # type: ignore[arg-type]
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    total = sum(labels)
    hits = 0
    value = 0.0
    for rank, i in enumerate(order, start=1):
        if labels[i]:
            hits += 1
            value += hits / rank
    return (value / total) / (total / len(labels))


first = probes(WITH_QUALITY) if THRESHOLD is not None else None
if THRESHOLD is None:
    pass
elif first is None:
    print("  4  ATLANDI — GEO'ya ulaşılamadı (ağ yok)")
    print("  5  ATLANDI")
    print("  6  ATLANDI")
else:
    data_q, header_q = first
    other = probes(NO_QUALITY)
    if other is None:
        problems.append(f"{NO_QUALITY}: GEO'ya ilk istek geçti ama bu geçmedi")
        data_n, header_n = [], []
    else:
        data_n, header_n = other

    # ---- 4  filtrenin bedeli --------------------------------------------
    declared = re.search(r"aralık \*\*%(\d+[.,]\d+)-(\d+[.,]\d+)\*\*", body)
    if declared is None:
        problems.append("§6.4.2 atılan pozitif oranının aralığını yazmıyor")
    else:
        low = float(declared.group(1).replace(",", ".")) / 100
        high = float(declared.group(2).replace(",", ".")) / 100
        for gsm, data in ((WITH_QUALITY, data_q), (NO_QUALITY, data_n)):
            if not data:
                continue
            frac = lost_fraction(data, THRESHOLD)
            if not low * 0.5 <= frac <= high * 1.5:
                problems.append(
                    f"{gsm}: eşik pozitiflerin %{frac * 100:.1f}'ini atıyor, "
                    f"§6.4.2 %{low * 100:.1f}-%{high * 100:.1f} diyor"
                )
            else:
                kept = [p for p in data if p["good"] is not False]
                passed = [p for p in kept if float(p["logint"]) >= THRESHOLD]
                pi_raw = sum(int(p["label"]) for p in kept) / len(kept)
                pi_new = sum(int(p["label"]) for p in passed) / len(passed)
                if pi_new <= pi_raw:
                    problems.append(
                        f"{gsm}: filtre taban oranını yükseltmiyor "
                        f"({pi_raw:.4f} → {pi_new:.4f}) — §6.4.2'nin iddiası düşer"
                    )
                else:
                    print(f"  4  {gsm}: n {len(kept)} → {len(passed)}, taban "
                          f"{pi_raw:.4f} → {pi_new:.4f}, atılan pozitif "
                          f"%{frac * 100:.1f}")

    # ---- 5  KONTROL: ızgaranın monotonluğu -------------------------------
    if data_q:
        loose = lost_fraction(data_q, THRESHOLD - 0.5)
        tight = lost_fraction(data_q, THRESHOLD + 0.5)
        strict = lost_fraction(data_q, THRESHOLD)
        if not loose < strict < tight:
            problems.append(
                f"atılan pozitif oranı eşikle monoton değil: "
                f"{loose:.3f} / {strict:.3f} / {tight:.3f} — 4. ölçüm eşiği "
                "değil veriyi ölçmüş olurdu"
            )
        else:
            print(f"  5  kontrol: gevşek {loose:.1%} < birincil {strict:.1%} < "
                  f"sıkı {tight:.1%} (monoton)")

    # ---- 6  QUALITY: yokluğu ve sapmanın İŞARETİ -------------------------
    if data_n and "QUALITY" in header_n:
        problems.append(
            f"{NO_QUALITY} tablosunda QUALITY kolonu VAR — §6.4.4 onu "
            "yokluğu üzerine kuruyor, madde yeniden açılmalı"
        )
    if "QUALITY" not in header_q:
        problems.append(
            f"{WITH_QUALITY} tablosunda QUALITY kolonu YOK — karşılaştırma "
            "anlamsız"
        )
    bound = re.search(r"en büyüğü \*\*(−|-)(\d+[.,]\d+)%\*\*", body)
    if bound is None:
        problems.append("§6.4.4 lift sapmasının sınırını yazmıyor")
    elif data_q and "QUALITY" in header_q:
        usable = [p for p in data_q
                  if p["mock"] is not None and float(p["logint"]) >= THRESHOLD]
        flagged = [p for p in usable if p["good"]]
        if not flagged or len(flagged) == len(usable):
            print("  6  bu array'de QUALITY hiçbir probu elemiyor — sapma 0")
        else:
            delta = (lift(usable) - lift(flagged)) / lift(flagged)
            limit = float(bound.group(2).replace(",", ".")) / 100
            if delta > 0:
                problems.append(
                    f"sapmanın işareti POZİTİF ({delta:+.2%}) — kolonu olmayan "
                    "seri avantajlı olurdu, §6.4.4 bunu negatif ilan ediyor"
                )
            elif abs(delta) > limit * 1.5:
                problems.append(
                    f"lift sapması {delta:+.2%}, §6.4.4'ün sınırı "
                    f"−{limit * 100:.2f}% — ilan edilen sınır tutmuyor"
                )
            else:
                print(f"  6  QUALITY yok sayılınca lift {delta:+.2%} "
                      f"(negatif ve sınırın içinde); GSE5291'de kolon yok")

# ---- 7  CCLE reddi --------------------------------------------------------
if not re.search(r"ulaşılamadığı için değil|ulaşılamıyor olduğu için değil", body):
    problems.append(
        "§6.4.1 CCLE'yi reddederken bunun bir ulaşılabilirlik sorunu OLMADIĞINI "
        "yazmıyor — reddin gerekçesi yapı, ve karıştırılması kaydı yok eder"
    )
try:
    artifacts = json.loads(MANIFEST.read_text(encoding="utf-8"))["artifacts"]
except (OSError, ValueError, KeyError) as exc:
    artifacts = []
    problems.append(f"{MANIFEST} okunamadı: {exc}")
profile = next((a for a in artifacts if "OmicsProfiles" in str(a.get("name", ""))), None)
if profile is None:
    problems.append(
        "manifest'te `OmicsProfiles` kaydı yok — HeLa'nın RNA profilinin VAR "
        "olduğu ölçümünün otoritesi bu dosya"
    )
elif "A8" not in (profile.get("used_by") or []):
    problems.append("OmicsProfiles kaydı `used_by` içinde A8'i saymıyor")
elif "PR-pI7d1A" not in body:
    problems.append("§6.4.1 HeLa'nın profil kimliğini yazmıyor")
else:
    print("  7  CCLE reddi yapı argümanı; ulaşılabilirlik manifest'te kayıtlı")

# ---- 8  kayıt -------------------------------------------------------------
if not RECORD.is_dir():
    problems.append(f"{RECORD} yok — filtrenin ölçümü depoda kayıtlı değil")
else:
    needed = {"README.md", "olcum.py", "olcum.json"}
    have = {p.name for p in RECORD.iterdir()}
    if not needed <= have:
        problems.append(f"{RECORD} eksik: {sorted(needed - have)}")
    else:
        print(f"  8  ölçüm kaydı {RECORD} içinde, betiğiyle")

# ---- 9  harita ------------------------------------------------------------
mapping = yaml.safe_load(MAP.read_text(encoding="utf-8"))["sections"]
owners = (mapping.get(6) or {}).get("owners") or []
if "A8" not in owners:
    problems.append(f"harita §6'yı A8'e vermiyor: {owners}")
else:
    print(f"  9  harita §6'yı A8'e veriyor (sahipler: {owners})")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo
echo "GEÇTİ — §6.4 filtreyi array-içsel olarak tanımlıyor, eşiğini kaynağından"
echo "        alıntılıyor, bedelini (atılan pozitif oranı) ilan ediyor, ızgarayı"
echo "        yazıyor, ve QUALITY kolonu olmayan serilerin sapmasını"
echo "        büyüklüğüyle VE işaretiyle bağlıyor. CCLE reddi bir yapı"
echo "        argümanı, ve ulaşılabilirliği ayrıca kayıtlı."
echo "        NOT: filtrenin UYGULANMASI bu madde değil; Faz A'da kod yazılmıyor."
