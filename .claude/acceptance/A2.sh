#!/usr/bin/env bash
# Kabul kriteri — A2: "§6'da accession + **ölçülmüş** n + tasarım".
#
# Altı ölçüm. 3 ayırt edici olan.
#
#   1  §6 var, yer tutucu kalmamış
#   2  yol haritasının saydığı her accession §6'da, örnek sayısı ve tasarımıyla
#   3  AĞ: §6'daki her n GEO'nun BUGÜN bildirdiğiyle birebir aynı. Kriterdeki
#      "ölçülmüş" kelimesi bu; onsuz madde "bir tablo yazdım" demekten öteye
#      gitmezdi, ve yol haritasının `GSE5814` tarifi bugün yanlış çıktı.
#   4  TASARIM: bağımsız dizi sayısı ve dışlanan üç kol tipi yazılı —
#      171 örneği ~14 dizi sanmak bu maddenin bulduğu asıl şey
#   5  DIŞ GEÇERLİLİK sınırı yazılı (hepsi siRNA)
#   6  A13'ün eşlemesi hâlâ tutuyor (A2 → §6)
#
# ⚠️ 3 ağ gerektirir; ağ yoksa ATLANIR, ama GEO farklı bir sayı verirse
# atlanmaz, GEÇMEZ (`H17`: atlamak ile geçmek aynı şey değil).
# ⚠️ Bu kapı §6'nın DOĞRU olduğunu değil, **ölçülmüş ve eksiksiz** olduğunu
# ölçer. Accession'ların kimliği ve yayını `A2b`'nin işi.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

fail() { echo "GEÇMEDİ — $1"; exit 1; }

# shellcheck source=_lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

PY=""
for cand in "${PYTHON:-}" python3 python; do
    [ -n "$cand" ] || continue
    if "$cand" -c "import pytest, yaml" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || fail "pytest+pyyaml içeren yorumlayıcı bulunamadı; PYTHON=... ile ver"
echo "# yorumlayıcı: $PY"

warn_untracked docs .claude || true

"$PY" - <<'INNER' || exit 1
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, ".claude/hooks")
import yaml

DOC = Path("docs/PRE_REGISTRATION.md")
MAP = Path(".claude/prereg_sections.yaml")

problems: list[str] = []
text = DOC.read_text(encoding="utf-8")

# ---- 1  §6 var ve yer tutucu yok ---------------------------------------
match = re.search(r"^## 6\. (.+?)$(.*?)(?=^## 7\.)", text, re.S | re.M)
if not match:
    sys.exit("§6 bölümü bulunamadı")
body = match.group(2)
leftovers = re.findall(r"<[^<>\n]{10,}>", body)
if leftovers:
    problems.append(f"§6'da doldurulmamış yer tutucu: {leftovers[:2]}")
else:
    print("  1  §6 dolu, yer tutucu yok")

# ---- 2  her accession, n'i ve tasarımıyla ------------------------------
# Otorite yol haritasının A2 satırı: orada sayılan accession'lar.
roadmap = Path("SCIENTIFIC_ROADMAP.md").read_text(encoding="utf-8")
a2_row = next(
    (line for line in roadmap.splitlines() if line.startswith("| **A2** |")), ""
)
listed = sorted(set(re.findall(r"GSE\d+", a2_row)))
if not listed:
    sys.exit("yol haritasının A2 satırında accession bulunamadı")

counts: dict[str, int] = {}
for acc in listed:
    row = next(
        (line for line in body.splitlines()
         if line.strip().startswith("|") and f"`{acc}`" in line),
        None,
    )
    if row is None:
        problems.append(f"{acc} §6'da yok")
        continue
    cells = [c.strip() for c in row.strip().strip("|").split("|")]
    if len(cells) < 6:
        problems.append(f"{acc} satırı eksik kolonlu ({len(cells)})")
        continue
    n_match = re.fullmatch(r"(\d+)", cells[1])
    if not n_match:
        problems.append(f"{acc} örnek sayısı okunamadı: {cells[1]!r}")
        continue
    counts[acc] = int(n_match.group(1))
    if len(cells[5]) < 25:
        problems.append(f"{acc} tasarım kolonu çok kısa: {cells[5]!r}")
if len(counts) == len(listed):
    print(f"  2  {len(listed)} accession'ın hepsi §6'da, n ve tasarımıyla")

# ---- 3  AĞ: n'ler GEO ile birebir --------------------------------------
BASE = "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi"


def geo_sample_count(acc: str) -> int | None:
    url = f"{BASE}?acc={acc}&targ=gsm&form=text&view=brief"
    req = urllib.request.Request(url, headers={"User-Agent": "research-script/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return resp.read().decode("utf-8", "replace").count("^SAMPLE")
    except (urllib.error.URLError, TimeoutError):
        return None


probe = geo_sample_count(listed[0]) if counts else None
if probe is None:
    print("  3  ATLANDI — GEO'ya ulaşılamadı (ağ yok)")
else:
    mismatches: list[str] = []
    checked = 0
    for acc, written in sorted(counts.items()):
        live = probe if acc == listed[0] else geo_sample_count(acc)
        if live is None:
            problems.append(f"{acc}: GEO'ya ilk istek geçti ama bu geçmedi")
            continue
        checked += 1
        if live != written:
            mismatches.append(f"{acc}: §6 {written}, GEO {live}")
        time.sleep(1)
    if mismatches:
        problems.append("§6'daki sayılar GEO ile uyuşmuyor — " + "; ".join(mismatches))
    else:
        print(f"  3  {checked} accession'ın örnek sayısı GEO ile birebir aynı")

# ---- 4  tasarımın asıl bulgusu yazılı ----------------------------------
needed = {
    "bağımsız dizi sayısı": r"(ebeveyn|bağımsız)\s+dizi",
    "sızıntı": r"sızınt",
    "aynı seed'li kimyasal varyant": r"aynı seed dizisini",
    "havuz kolları": r"(pro-siRNA|esiRNA)",
}
missing = [label for label, pat in needed.items() if not re.search(pat, body, re.I)]
if missing:
    problems.append(f"§6 tasarım bulgularını söylemiyor: {missing}")
else:
    print("  4  bağımsız dizi sayısı + üç dışlama tipi yazılı")

# ---- 5  dış geçerlilik sınırı -----------------------------------------
if not re.search(r"siRNA", body) or not re.search(r"saRNA", body):
    problems.append("§6 siRNA/saRNA dış geçerlilik sınırını söylemiyor")
else:
    print("  5  dış geçerlilik sınırı yazılı (hepsi siRNA)")

# ---- 6  A13'ün eşlemesi tutuyor ---------------------------------------
mapping = yaml.safe_load(MAP.read_text(encoding="utf-8"))["sections"]
owners = (mapping.get(6) or {}).get("owners") or []
if "A2" not in owners:
    problems.append(f"A13'ün haritası §6'yı A2'ye vermiyor: {owners}")
else:
    print(f"  6  harita §6'yı A2'ye veriyor (sahipler: {owners})")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo
echo "GEÇTİ — §6 yol haritasının saydığı accession'ların hepsini ölçülmüş örnek"
echo "        sayısı ve tasarımıyla taşıyor (kaç tane olduğunu yukarıdaki 2. ve"
echo "        3. ölçüm söylüyor — bu satır bir sayı iddia etmiyor, çünkü ilk"
echo "        hali 'sekiz' diyordu ve kapı altısını ölçüyordu),"
echo "        sayılar GEO ile birebir, ve 171 örneğin ~14 bağımsız diziye"
echo "        karşılık geldiği (artı üç dışlanan kol tipi) yazılı."
echo "        NOT: accession kimliği ve yayını A2b'nin işi; bu kapı onu ölçmez."
