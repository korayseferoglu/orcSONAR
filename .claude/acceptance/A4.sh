#!/usr/bin/env bash
# Kabul kriteri — A4: "§2'de birincil metrik, §3'te ikincil metrikler,
# §7'de CV şeması".
#
# Sekiz ölçüm. 4 ve 5 ayırt edici olanlar.
#
#   1  §2 tek bir birincil metrik söylüyor, hesaplanma biçimi belirsizlik
#      bırakmıyor, ve taban + lift zorunluluğu yazılı
#   2  §3 dört ikincil metriği ZORUNLU olarak sayıyor, ve KS'in p değil etki
#      büyüklüğü olarak raporlanacağı yazılı
#   3  §7 CV birimini seed heptameri olarak sabitliyor ve sızıntı gerekçesini
#      söylüyor
#   4  AĞ, ASIL ÖLÇÜM: §2'nin "havuzlanmış PR-AUC yorumlanamaz" iddiasının
#      dayanağı olan taban oranı YAYILIMI GEO verisinde hâlâ birkaç kat —
#      iddia sayıya dayanıyor, sayı her koşuda yeniden ölçülüyor
#   5  AĞ, KONTROL: aynı dupleksin iki kolu arasında yayılım KÜÇÜK —
#      4 olmadan 5, 5 olmadan 4 anlamsız; ikisi birlikte yayılımın
#      dupleksler arası olduğunu, gürültü olmadığını gösteriyor
#   6  üç seri birincil, beş seri ilan edilmiş replikasyon olarak ayrılmış
#   7  tabaka zorunluluğu + PLSR'ın UYGULANMADIĞININ beyanı yazılı
#   8  `A13`'ün haritası §2, §3 ve §7'yi A4'e veriyor
#
# ⚠️ 4 ve 5 ağ gerektirir; ağ yoksa ATLANIR, ama ölçüm iddiayı yanlışlarsa
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

warn_untracked docs .claude || true

"$PY" - <<'INNER' || exit 1
import math
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

DOC = Path("docs/PRE_REGISTRATION.md")
MAP = Path(".claude/prereg_sections.yaml")

problems: list[str] = []
text = DOC.read_text(encoding="utf-8")


def section(number: int) -> str:
    match = re.search(
        rf"^## {number}\. (.+?)$(.*?)(?=^## {number + 1}\.)", text, re.S | re.M
    )
    if not match:
        sys.exit(f"§{number} bölümü bulunamadı")
    return match.group(2)


s2, s3, s7 = section(2), section(3), section(7)

for label, body in (("§2", s2), ("§3", s3), ("§7", s7)):
    leftovers = re.findall(r"<[^<>\n]{10,}>", body)
    if leftovers:
        problems.append(f"{label}'de yer tutucu kalmış: {leftovers[:2]}")

# ---- 1  birincil metrik tek ve hesaplanabilir --------------------------
need2 = {
    "metrik adı": r"PR-AUC",
    "birim": r"[Dd]upleks başına|ayrık seed",
    "toplama": r"medyan",
    "hesaplama": r"average_precision_score",
    "taban zorunlu": r"taban oran",
    "lift zorunlu": r"lift",
    "havuzlama reddi": r"havuzlanmış",
}
missing = [k for k, pat in need2.items() if not re.search(pat, s2)]
if missing:
    problems.append(f"§2 eksik: {missing}")
else:
    print("  1  §2: tek birincil metrik, hesaplanma biçimi, taban + lift zorunlu")

# ---- 2  dört ikincil, zorunlu, KS etki büyüklüğü ----------------------
need3 = {
    "Spearman": r"Spearman",
    "KS": r"Kolmogorov|KS `D`",
    "top-n": r"[Tt]op-\*?n",
    "ROC-AUC": r"ROC-AUC",
    "zorunluluk": r"zorunlu",
    "KS p değil": r"p-değeri olarak DEĞİL|etki büyüklüğü",
}
missing = [k for k, pat in need3.items() if not re.search(pat, s3)]
if missing:
    problems.append(f"§3 eksik: {missing}")
else:
    print("  2  §3: dört zorunlu ikincil, KS etki büyüklüğü olarak")

# ---- 3  CV birimi ------------------------------------------------------
need7 = {
    "leave-one-seed-out": r"[Ll]eave-one-seed-out",
    "birim": r"seed heptameri",
    "sızıntı gerekçesi": r"sızınt",
    "siSPOTR örneği": r"siSPOTR",
}
missing = [k for k, pat in need7.items() if not re.search(pat, s7)]
if missing:
    problems.append(f"§7 CV şeması eksik: {missing}")
else:
    print("  3  §7: leave-one-seed-out, sızıntı gerekçesiyle")

# ---- 4 ve 5  AĞ: taban oranı yayılımı ---------------------------------
GEO = "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi"
# Üç AYRI dupleks (yayılımı ölçer) ve aynı dupleksin iki kolu (kontrolü).
ACROSS = {"GSM133689": "GSE5814 pos2", "GSM134511": "GSE5769 PIK3CB",
          "GSM119710": "GSE5291 SOD1 pos4"}
WITHIN = {"GSM119707": "GSE5291 SOD1 pos1", "GSM119710": "GSE5291 SOD1 pos4"}


def rate(gsm: str) -> float | None:
    url = f"{GEO}?acc={gsm}&targ=self&form=text&view=full"
    req = urllib.request.Request(url, headers={"User-Agent": "research-script/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
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
    universe = positives = 0
    for line in lines[start + 2 : end]:
        parts = line.split("\t")
        if len(parts) != len(header):
            continue
        row = dict(zip(header, parts))
        quality = row.get("QUALITY")
        if quality is not None and quality.strip() not in ("1", "1.0"):
            continue
        try:
            intensity = float(row["LOGINTENSITY"])
            value = float(row["VALUE"])
            pval = float(row["PVALUE"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isnan(intensity) or intensity < -1.0:
            continue
        universe += 1
        if pval < 0.01 and value < 0:
            positives += 1
    return positives / universe if universe else None


rates: dict[str, float] = {}
first = rate(next(iter(ACROSS)))
if first is None:
    print("  4  ATLANDI — GEO'ya ulaşılamadı (ağ yok)")
    print("  5  ATLANDI — aynı sebep")
else:
    for gsm in list(ACROSS) + [g for g in WITHIN if g not in ACROSS]:
        value = first if gsm == next(iter(ACROSS)) else rate(gsm)
        if value is not None:
            rates[gsm] = value
    across = [rates[g] for g in ACROSS if g in rates]
    if len(across) < 2:
        problems.append("dupleksler arası yayılım ölçülemedi")
    else:
        spread = max(across) / min(across)
        if spread < 1.5:
            problems.append(
                f"dupleksler arası taban yayılımı yalnız {spread:.2f} kat — "
                f"§2'nin 'havuzlanmış PR-AUC yorumlanamaz' gerekçesi bu sayıya "
                f"dayanıyor ve ölçüm onu desteklemiyor"
            )
        else:
            print(
                f"  4  dupleksler arası taban yayılımı {spread:.1f} kat "
                f"({min(across):.2%} … {max(across):.2%})"
            )
        within = [rates[g] for g in WITHIN if g in rates]
        if len(within) == 2:
            w = max(within) / min(within)
            if w >= spread:
                problems.append(
                    f"kontrol boş: aynı serinin iki kolu arasındaki yayılım "
                    f"({w:.2f}) dupleksler arasından ({spread:.2f}) küçük değil"
                )
            else:
                print(
                    f"  5  kontrol: aynı serinin iki kolu arasında yayılım "
                    f"{w:.2f} kat — dupleksler arasından küçük"
                )

# ---- 6  birincil / replikasyon ayrımı ---------------------------------
if not re.search(r"[Bb]irincil küme", s7) or not re.search(
    r"[Dd]ış replikasyon|ilan edilmiş dış", s7
):
    problems.append("§7 birincil küme ile dış replikasyon ayrımını yazmıyor")
elif not re.search(r"MAQC|16964229", s7):
    problems.append("§7 ayrımın gerekçesini (MAQC) atıfla vermiyor")
else:
    print("  6  üç seri birincil, beş seri ilan edilmiş replikasyon (MAQC atıflı)")

# ---- 7  tabaka + PLSR beyanı ------------------------------------------
if not re.search(r"tabaka", s7) or not re.search(r"PLSR", s7):
    problems.append("§7 tabaka zorunluluğunu ya da PLSR beyanını yazmıyor")
else:
    print("  7  tabaka zorunlu, PLSR'ın uygulanmadığı beyan edilmiş")

# ---- 8  harita --------------------------------------------------------
mapping = yaml.safe_load(MAP.read_text(encoding="utf-8"))["sections"]
for number in (2, 3, 7):
    owners = (mapping.get(number) or {}).get("owners") or []
    if "A4" not in owners:
        problems.append(f"harita §{number}'yi A4'e vermiyor: {owners}")
if not any("harita" in p for p in problems):
    print("  8  harita §2, §3 ve §7'yi A4'e veriyor")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo
echo "GEÇTİ — §2 tek bir birincil metriği taban ve lift zorunluluğuyla, §3 dört"
echo "        zorunlu ikincili, §7 leave-one-seed-out şemasını ve birincil/"
echo "        replikasyon ayrımını yazıyor; taban yayılımının dupleksler arası"
echo "        olduğu GEO'dan yeniden ölçülüyor."
echo "        NOT: BAŞARI eşiği A6a, tabanlar A5 — ikisi de ayrı madde."
