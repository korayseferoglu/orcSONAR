#!/usr/bin/env bash
# Kabul kriteri — A5: "§7'de üç taban tanımlı, bölge açıkça yazılı".
#
# Altı ölçüm. 4 ayırt edici olan.
#
#   1  §7.5 var ve yer tutucu kalmamış
#   2  DÖRT taban ayrı ayrı tanımlı (satır üçünü istiyordu; dördüncüsünün
#      gerekçesi de yazılı olmak zorunda — çıtayı yükselten bir ekleme
#      sessizce yapılmaz)
#   3  BÖLGE açıkça yazılı: dördü de 3′UTR tanımlı, ve tabanlar modelle AYNI
#      koşuda ölçülüyor, literatürden alıntılanmıyor
#   4  AĞ, ASIL ÖLÇÜM: dördüncü tabanın gerekçesi olan ifade-şiddeti farkı
#      GEO verisinde hâlâ var — pozitiflerin medyan LOGINTENSITY'si tüm
#      probların medyanından belirgin yüksek. Bu fark yoksa dördüncü taban
#      gerekçesiz kalır ve madde yeniden açılmalı.
#   5  POTS'un döngüselliği taban listesinde de ilan edilmiş
#   6  `A13`'ün haritası §7'yi A5'e veriyor
#
# ⚠️ 4 ağ gerektirir; ağ yoksa ATLANIR, ama ölçüm gerekçeyi yanlışlarsa
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
import statistics
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

DOC = Path("docs/PRE_REGISTRATION.md")
MAP = Path(".claude/prereg_sections.yaml")

problems: list[str] = []
text = DOC.read_text(encoding="utf-8")

match = re.search(r"^### 7\.5 (.+?)$(.*?)(?=^## 8\.|^### 7\.6)", text, re.S | re.M)
if not match:
    sys.exit("§7.5 (tabanlar) bölümü bulunamadı")
body = match.group(2)

# ---- 1  yer tutucu yok -------------------------------------------------
leftovers = re.findall(r"<[^<>\n]{10,}>", body)
if leftovers:
    problems.append(f"§7.5'te yer tutucu kalmış: {leftovers[:2]}")
else:
    print("  1  §7.5 dolu, yer tutucu yok")

# ---- 2  dört taban ayrı ayrı -------------------------------------------
# Madde başlığı kalın ama önünde bir işaret olabilir (🆕 gibi); ilk hali
# `^\d+\.\s+\*\*` istiyordu ve dördüncü tabanı bu yüzden saymadı.
numbered = re.findall(r"^\d+\.\s+[^\n*]*?\*\*(.+?)\*\*", body, re.M)
if len(numbered) < 4:
    problems.append(f"§7.5 yalnız {len(numbered)} taban tanımlıyor: {numbered}")
else:
    print(f"  2  {len(numbered)} taban ayrı ayrı tanımlı")
if not re.search(r"çıtayı\s+\*{0,2}YÜKSELTİYOR|çıtayı yükselt", body, re.I):
    problems.append(
        "dördüncü tabanın çıtayı yükselttiği (yani ihtiyat yönünde olduğu) "
        "yazılı değil — çıtayı değiştiren bir ekleme gerekçesiz kalamaz"
    )

# ---- 3  bölge ve 'aynı koşuda ölçülür' ---------------------------------
checks = {
    "bölge": r"3′UTR|3'UTR",
    "aynı koşuda ölçüm": r"aynı\*{0,2}\s*koşuda|literatürden alıntılanmaz",
}
missing = [k for k, pat in checks.items() if not re.search(pat, body)]
if missing:
    problems.append(f"§7.5 eksik: {missing}")
else:
    print("  3  bölge 3′UTR olarak yazılı, tabanlar aynı koşuda ölçülüyor")

# ---- 4  AĞ: ifade-şiddeti farkı hâlâ var -------------------------------
GEO = "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi"
ARRAYS = ("GSM133689", "GSM119707")


def intensities(gsm: str) -> tuple[list[float], list[float]] | None:
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
    everything: list[float] = []
    positives: list[float] = []
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
        if math.isnan(intensity):
            continue
        everything.append(intensity)
        if pval < 0.01 and value < 0:
            positives.append(intensity)
    return (everything, positives) if everything and positives else None


first = intensities(ARRAYS[0])
if first is None:
    print("  4  ATLANDI — GEO'ya ulaşılamadı (ağ yok)")
else:
    for gsm in ARRAYS:
        got = first if gsm == ARRAYS[0] else intensities(gsm)
        if got is None:
            problems.append(f"{gsm}: GEO'ya ilk istek geçti ama bu geçmedi")
            continue
        everything, positives = got
        med_all = statistics.median(everything)
        med_pos = statistics.median(positives)
        gap = med_pos - med_all
        if gap <= 0.2:
            problems.append(
                f"{gsm}: pozitiflerin ifade şiddeti farkı yalnız {gap:.3f} — "
                f"dördüncü tabanın gerekçesi bu farka dayanıyor ve ölçüm onu "
                f"desteklemiyor; madde yeniden açılmalı"
            )
        else:
            print(
                f"  4  {gsm}: pozitif medyan LOGINTENSITY {med_pos:.3f} vs "
                f"tüm problar {med_all:.3f} (fark {gap:.3f})"
            )

# ---- 5  POTS döngüselliği ----------------------------------------------
if not re.search(r"POTS", body) or not re.search(r"döngüsel", body, re.I):
    problems.append("§7.5 POTS'un döngüselliğini taban listesinde ilan etmiyor")
else:
    print("  5  POTS'un döngüselliği taban listesinde ilan edilmiş")

# ---- 6  harita ---------------------------------------------------------
mapping = yaml.safe_load(MAP.read_text(encoding="utf-8"))["sections"]
owners = (mapping.get(7) or {}).get("owners") or []
if "A5" not in owners:
    problems.append(f"harita §7'yi A5'e vermiyor: {owners}")
else:
    print(f"  6  harita §7'yi A5'e veriyor (sahipler: {owners})")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo
echo "GEÇTİ — §7.5 dört tabanı ayrı ayrı, bölgesiyle ve aynı koşuda ölçülmek"
echo "        kaydıyla tanımlıyor; dördüncünün gerekçesi olan ifade-şiddeti"
echo "        farkı GEO'dan yeniden ölçülüyor; POTS'un döngüselliği ilan"
echo "        edilmiş."
echo "        NOT: POTS tablosunun KURULMASI E0b, bu kapı onu ölçmez."
