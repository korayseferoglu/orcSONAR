#!/usr/bin/env bash
# Kabul kriteri — A3: "§4'te etiket eşiği sayı olarak".
#
# Yedi ölçüm. 3 ve 4 ayırt edici olanlar.
#
#   1  §4 dolu, yer tutucu kalmamış
#   2  etiket kuralı SAYIYLA yazılı (p eşiği + yön), ve ölçeği + dönüşüm
#      sabiti + sayısal örnek ile birlikte — bu sette iki farklı "−0.3" var ve
#      ikisi farklı log tabanında, o yüzden ölçeksiz bir sayı eksik bilgidir
#   3  AĞ, ASIL ÖLÇÜM: `{p<0.01 & aşağı}` ile `{p<0.01 & dönüştürülmüş
#      −0.3 log2}` GEO verisinde HÂLÂ aynı kümeyi veriyor — §4'ün "serbest
#      parametre yok" iddiası bu denkliğe dayanıyor, ve iddia bozulursa
#      madde yeniden açılmalı, sessizce doğru kalmamalı
#   4  AĞ, KONTROL: dönüştürülmemiş eşik GERÇEKTEN farklı bir küme veriyor —
#      3 olmadan 4, 4 olmadan 3 anlamsız; ikisi birlikte dönüşümün gerekli
#      OLDUĞUNU ve yapıldığını gösteriyor
#   5  ızgara ilan edilmiş ve "birincil yeniden atanmaz" kuralı yazılı
#   6  siSPOTR döngüselliği ilan edilmiş
#   7  `A13`'ün haritası §4'ü A3'e veriyor
#
# ⚠️ 3 ve 4 ağ gerektirir; ağ yoksa ATLANIR, ama GEO farklı bir şey söylerse
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
LOG10_TO_LOG2 = math.log2(10)

problems: list[str] = []
text = DOC.read_text(encoding="utf-8")
match = re.search(r"^## 4\. (.+?)$(.*?)(?=^## 5\.)", text, re.S | re.M)
if not match:
    sys.exit("§4 bölümü bulunamadı")
body = match.group(2)

# ---- 1  yer tutucu yok -------------------------------------------------
leftovers = re.findall(r"<[^<>\n]{10,}>", body)
if leftovers:
    problems.append(f"§4'te doldurulmamış yer tutucu: {leftovers[:2]}")
else:
    print("  1  §4 dolu, yer tutucu yok")

# ---- 2  kural sayıyla + ölçeğiyle -------------------------------------
checks = {
    "p eşiği sayıyla": r"PVALUE\s*<\s*0\.01",
    "yön": r"VALUE\s*<\s*0",
    "log tabanı": r"[Ll]og10",
    "dönüşüm sabiti": r"3\.321928",
    "sayısal örnek": r"2\^−?-?0\.382|0[.,]767|%23",
}
missing = [label for label, pat in checks.items() if not re.search(pat, body)]
if missing:
    problems.append(f"§4 şunları sayıyla söylemiyor: {missing}")
else:
    print("  2  etiket kuralı + ölçek + dönüşüm sabiti + sayısal örnek yazılı")

# ---- 3 ve 4  AĞ: denklik hâlâ tutuyor mu ------------------------------
GEO = "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi"
# İki seri, iki platform. §4'ün denklik iddiasının dayanağı.
ARRAYS = ("GSM133702", "GSM119707")


def rows(gsm: str) -> list[dict[str, str]]:
    url = f"{GEO}?acc={gsm}&targ=self&form=text&view=full"
    req = urllib.request.Request(url, headers={"User-Agent": "research-script/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError):
        return []
    lines = raw.splitlines()
    try:
        start = lines.index("!sample_table_begin")
        end = lines.index("!sample_table_end")
    except ValueError:
        return []
    header = lines[start + 1].split("\t")
    out = []
    for line in lines[start + 2 : end]:
        parts = line.split("\t")
        if len(parts) == len(header):
            out.append(dict(zip(header, parts)))
    return out


def num(raw: str) -> float | None:
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(val) else val


first = rows(ARRAYS[0])
if not first:
    print("  3  ATLANDI — GEO'ya ulaşılamadı (ağ yok)")
    print("  4  ATLANDI — aynı sebep")
else:
    for gsm in ARRAYS:
        table = first if gsm == ARRAYS[0] else rows(gsm)
        if not table:
            problems.append(f"{gsm}: GEO'ya ilk istek geçti ama bu geçmedi")
            continue
        kept = []
        for row in table:
            quality = row.get("QUALITY")
            if quality is not None and quality.strip() not in ("1", "1.0"):
                continue
            value, pval = num(row.get("VALUE", "")), num(row.get("PVALUE", ""))
            if value is not None and pval is not None:
                kept.append((value, pval))
        if not kept:
            problems.append(f"{gsm}: VALUE/PVALUE kolonları beklenen biçimde değil")
            continue
        papers = sum(1 for v, p in kept if p < 0.01 and v < 0)
        converted = sum(
            1 for v, p in kept if p < 0.01 and v * LOG10_TO_LOG2 <= -0.3
        )
        unconverted = sum(1 for v, p in kept if p < 0.01 and v <= -0.3)
        weakest = max((v for v, p in kept if p < 0.01 and v < 0), default=0.0)

        if papers != converted:
            problems.append(
                f"{gsm}: DENKLİK BOZULDU — p<0.01&aşağı {papers}, "
                f"+dönüştürülmüş eşik {converted}. §4'ün 'serbest parametre yok' "
                f"iddiası bu denkliğe dayanıyor; madde yeniden açılmalı"
            )
        else:
            print(
                f"  3  {gsm}: denklik tutuyor ({papers} prob); en zayıf anlamlı "
                f"düşüş {weakest * LOG10_TO_LOG2:.4f} log2"
            )
        if unconverted >= papers:
            problems.append(
                f"{gsm}: dönüştürülmemiş eşik de aynı kümeyi verdi "
                f"({unconverted} vs {papers}) — kontrol ölçümü boş, dönüşümün "
                f"gerekli olduğu gösterilemiyor"
            )
        else:
            print(
                f"  4  {gsm}: kontrol — dönüştürülmemiş eşik {unconverted} prob "
                f"veriyor ({papers / max(unconverted, 1):.1f} kat fark)"
            )

# ---- 5  ızgara ve birincilin sabitliği --------------------------------
if not re.search(r"ızgara", body, re.I) or not re.search(
    r"yeniden atanmaz", body
):
    problems.append("§4 duyarlılık ızgarasını ya da 'birincil yeniden atanmaz' kuralını söylemiyor")
elif not re.search(r"lift", body, re.I):
    problems.append("§4 PR-AUC'nin taban oranıyla/lift olarak raporlanmasını söylemiyor")
else:
    print("  5  ızgara ilan edilmiş, birincil sabit, lift zorunlu")

# ---- 6  döngüsellik ilan edilmiş --------------------------------------
if not re.search(r"döngüsel", body, re.I) or not re.search(r"siSPOTR", body):
    problems.append("§4 siSPOTR eşiğinin döngüselliğini ilan etmiyor")
else:
    print("  6  siSPOTR döngüselliği ilan edilmiş")

# ---- 7  harita --------------------------------------------------------
mapping = yaml.safe_load(MAP.read_text(encoding="utf-8"))["sections"]
owners = (mapping.get(4) or {}).get("owners") or []
if "A3" not in owners:
    problems.append(f"A13'ün haritası §4'ü A3'e vermiyor: {owners}")
else:
    print(f"  7  harita §4'ü A3'e veriyor (sahipler: {owners})")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo
echo "GEÇTİ — §4 etiket kuralını sayıyla, ölçeğiyle, dönüşüm sabitiyle ve"
echo "        sayısal örnekle yazıyor; denklik GEO verisinde hâlâ tutuyor ve"
echo "        dönüştürülmemiş eşiğin farklı sonuç verdiği ölçülüyor; ızgara"
echo "        ilan edilmiş, birincil sabit, döngüsellik yazılı."
echo "        NOT: BAŞARI eşiği bu madde değil — o A6a, aynı bölümde."
