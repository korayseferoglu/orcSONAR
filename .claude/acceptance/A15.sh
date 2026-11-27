#!/usr/bin/env bash
# Kabul kriteri — A15: "§9'da negatif sonucun raporlanacağı yer ve içerik
# yazılı".
#
# Dokuz ölçüm. 2, 3, 4 ve 5 ayırt edici olanlar.
#
#   1  §9 var, yer tutucu yok, yedi alt bölümü yazılı
#   2  AYIRT EDİCİ: dört verdinin HEPSİ eşlenmiş, ve `GEÇERSİZ` ile
#      `SONUÇSUZ` negatif sonuç SAYILMIYOR. §9'un "PASS olmayan her şeyin
#      çöplüğü" olmaması bu satırlara bağlı
#   3  AYIRT EDİCİ: venue kümesi YOL HARİTASININ §0 tablosundan okunup
#      karşılaştırılıyor — belgede yeniden yazılmış bir liste iki kopya olur
#      ve kayabilir
#   4  AYIRT EDİCİ: ürün listesi maddelenmiş, her maddesi onu tanımlayan
#      bölüme işaret ediyor, VE işaret ettiği her bölüm gerçekten var
#   5  KONTROL: ürün listesi verdiye BAĞLI DEĞİL — simetri yazılı. Bu
#      kontrol olmadan 4. ölçüm "negatifte şunları da ekleriz" ile de
#      geçerdi, ki rafa kaldırmanın tam yolu o
#   6  `E6`/`E7` accession'larıyla ve kapsam sınırlarıyla yazılı, artı
#      "dış kontrol birincili kurtarmaz" kuralı
#   7  `F5`'ten AYRI olduğu ve ona devredilemeyeceği yazılı
#   8  yasak listesi değişmez 7 ve §8.2 ile bağlı
#   9  `A13`'ün haritası §9'u A15'e veriyor ve `A12` ona bağlı
#
# ⚠️ Ağ istemiyor.

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
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

DOC = Path("docs/PRE_REGISTRATION.md")
MAP = Path(".claude/prereg_sections.yaml")
ROADMAP = Path("SCIENTIFIC_ROADMAP.md")

problems: list[str] = []
text = DOC.read_text(encoding="utf-8")
roadmap = ROADMAP.read_text(encoding="utf-8")

found = re.search(r"^## 9\. (.+?)$(.*?)(?=^## 10\.)", text, re.S | re.M)
if not found:
    sys.exit("§9 (negatif sonuç) bölümü bulunamadı")
body = found.group(2)

# ---- 1  bölüm -------------------------------------------------------------
leftovers = re.findall(r"<[^<>\n]{10,}>", body)
if leftovers:
    problems.append(f"§9'da yer tutucu kalmış: {leftovers[:2]}")
absent = [f"9.{i}" for i in range(1, 8) if f"### 9.{i}" not in body]
if absent:
    problems.append(f"§9 alt bölümleri eksik: {absent}")
if not problems:
    print("  1  §9 dolu, yedi alt bölümü yazılı")

# ---- 2  AYIRT EDİCİ: dört verdi, ve ikisi negatif DEĞİL -----------------
rows = re.findall(
    r"^\|\s*`(GEÇTİ|EŞDEĞER|DAHA KÖTÜ|SONUÇSUZ|GEÇERSİZ)`\s*\|\s*"
    r"\*{0,2}(evet|hayır)\*{0,2}[^|]*\|",
    body, re.M,
)
mapping_rows = dict(rows)
expected = {
    "EŞDEĞER": "evet",
    "DAHA KÖTÜ": "evet",
    "SONUÇSUZ": "hayır",
    "GEÇERSİZ": "hayır",
}
missing = [v for v in expected if v not in mapping_rows]
if missing:
    problems.append(f"§9.1 şu verdileri negatif-mi tablosunda eşlemiyor: {missing}")
else:
    wrong = [
        f"{v}: '{mapping_rows[v]}' (beklenen '{want}')"
        for v, want in expected.items() if mapping_rows[v] != want
    ]
    if wrong:
        problems.append("§9.1'in negatif-mi eşlemesi yanlış: " + "; ".join(wrong))
    elif not re.search(r"çöplüğü", body):
        problems.append(
            "§9.1 §9'un 'PASS olmayan her şeyin çöplüğü' olmadığını yazmıyor"
        )
    else:
        print("  2  dört verdi eşlenmiş; `GEÇERSİZ` ve `SONUÇSUZ` negatif değil")

# ---- 3  AYIRT EDİCİ: venue YOL HARİTASINDAN okunuyor -------------------
row = re.search(r"^\|\s*Tabanları \*\*geçmiyor\*\*\s*\|(.*?)\|\s*$", roadmap, re.M)
if row is None:
    problems.append(
        "yol haritasının §0 tablosunda 'Tabanları geçmiyor' satırı bulunamadı — "
        "venue kümesinin otoritesi orası"
    )
else:
    # Kalın (`**...**`) parçalar önce çıkarılıyor, yoksa `\*(...)\*` kalının
    # içini ve aralarındaki noktalama parçalarını da yakalıyor. Alıntı cümlesi
    # de italik olduğu için uzunluk ve tırnakla ayıklanıyor.
    cell = re.sub(r"\*\*.*?\*\*", " ", row.group(1))
    declared_venues = {v.strip() for v in re.findall(r"\*([^*]+?)\*", cell)}
    declared_venues = {
        v for v in declared_venues
        if 3 < len(v) < 40 and not v.startswith(("\u201c", '"', ".", ","))
    }
    named = {v for v in declared_venues if v in body}
    if named != declared_venues:
        problems.append(
            f"§9.2 yol haritasının venue kümesini tam saymıyor: eksik "
            f"{sorted(declared_venues - named)}"
        )
    elif not re.search(r"fazla iyimser", body):
        problems.append(
            "§9.2 §0'ın tavan uyarısını (NAR / Genome Biology fazla iyimser) "
            "devralmıyor — negatif sonucun yukarı pazarlanmaması o uyarıya bağlı"
        )
    else:
        print(f"  3  venue kümesi yol haritasından okundu ve tam: "
              f"{sorted(declared_venues)}")

# ---- 4  AYIRT EDİCİ: ürün listesi ve işaret ettiği bölümler ------------
artefacts = re.findall(r"^\s*(\d+)\.\s+(.*?)(?=^\s*\d+\.\s|\n\*\*Şekiller|\Z)",
                       body, re.S | re.M)
if len(artefacts) < 10:
    problems.append(f"§9.3'ün tablo listesi {len(artefacts)} madde, ≥10 olmalı")
else:
    numbered = {int(n) for n, _ in artefacts}
    if numbered != set(range(1, len(artefacts) + 1)):
        problems.append(f"§9.3'ün listesi sıralı değil: {sorted(numbered)}")
    # her maddenin bir bölüme işaret ettiği, ve o bölümün var olduğu
    headings = set(re.findall(r"^#{2,4} (\d+(?:\.\d+)*)[\. ]", text, re.M))
    unreferenced: list[str] = []
    dangling: list[str] = []
    for number, chunk in artefacts:
        referenced = re.findall(r"§(\d+(?:\.\d+)*)", chunk)
        if not referenced:
            unreferenced.append(number)
            continue
        for ref in referenced:
            if ref not in headings:
                dangling.append(f"madde {number} → §{ref}")
    if unreferenced:
        problems.append(f"§9.3'ün şu maddeleri hiçbir bölüme işaret etmiyor: {unreferenced}")
    elif dangling:
        problems.append(f"§9.3 var olmayan bölümlere işaret ediyor: {dangling}")
    else:
        figures = re.findall(r"\*\*Ş(\d+)\*\*", body)
        if len(figures) < 4:
            problems.append(f"§9.3 {len(figures)} şekil sayıyor, ≥4 olmalı")
        else:
            print(f"  4  {len(artefacts)} tablo + {len(figures)} şekil, hepsi var "
                  "olan bölümlere işaret ediyor")

# ---- 5  KONTROL: liste verdiye bağlı DEĞİL -----------------------------
if not re.search(r"verdiye bağlı değildir", body):
    problems.append(
        "§9.3 ürün listesinin verdiye bağlı OLMADIĞINI yazmıyor — simetri "
        "olmadan liste 'negatifte şunları da ekleriz' olur, ki rafa "
        "kaldırmanın tam yolu o"
    )
elif not re.search(r"tek bir\s*\n?\s*koşuda", body):
    problems.append("§9.3 ürünlerin TEK bir koşuda üretildiğini yazmıyor")
elif not re.search(r"verdi bu ürünler elde olduktan sonra okunur", body):
    problems.append(
        "§9.3 verdinin ürünler ÜRETİLDİKTEN SONRA okunduğunu yazmıyor — "
        "simetrinin kilit olmasının sebebi o sıra"
    )
else:
    print("  5  kontrol: liste verdiye bağlı değil, tek koşuda üretiliyor, "
          "verdi sonra okunuyor")

# ---- 6  E6/E7 ----------------------------------------------------------
externals = {
    "E7": r"`E7`",
    "E6": r"`E6`",
    "GSE32999": r"GSE32999",
    "GSE42024": r"GSE42024",
    "üç dupleks": r"üç dupleks",
    "havuzlanmaz": r"havuzlanmaz",
    "kurtarmaz": r"KURTARMAZ|kurtarmaz",
}
missing_ext = [k for k, pat in externals.items() if not re.search(pat, body)]
if missing_ext:
    problems.append(f"§9.5 eksik: {missing_ext}")
else:
    print("  6  E6/E7 accession'larıyla, kapsam sınırlarıyla ve "
          "'kurtarmaz' kuralıyla yazılı")

# ---- 7  F5 ayrımı ------------------------------------------------------
if not re.search(r"`F5`", body):
    problems.append("§9.6 `F5`'ten ayrımı yazmıyor")
elif not re.search(r"devredilemez|devredilemeyeceği", body):
    problems.append(
        "§9.6 §9'un işinin `F5`'e DEVREDİLEMEYECEĞİNİ yazmıyor — "
        "'sınırları LIMITATIONS'a yazdık' bir yayın yolu değil"
    )
else:
    print("  7  `F5`'ten ayrı ve ona devredilemez, yazılı")

# ---- 8  yasaklar -------------------------------------------------------
bans = {
    "rafa kaldırmak": r"[Rr]afa kaldırmak",
    "ön bulgu çerçevesi": r"ön bulgu",
    "taban/tabaka/seri çıkarmak": r"çıkarmak \(§8\.4\)",
    "validated:false'ı kısmi başarı": r"kısmi başarı",
}
missing_bans = [k for k, pat in bans.items() if not re.search(pat, body)]
if missing_bans:
    problems.append(f"§9.7 yasakları eksik: {missing_bans}")
elif not re.search(r"değişmez 7", body):
    problems.append("§9.7 değişmez 7'ye atıf yapmıyor")
elif not re.search(r"§8\.2", body):
    problems.append("§9.7 deneme sayısı kapağını (§8.2) bağlamıyor")
else:
    print(f"  8  {len(bans)} yasak yazılı, değişmez 7 ve §8.2 ile bağlı")

# ---- 9  harita ve kilit ------------------------------------------------
mapping = yaml.safe_load(MAP.read_text(encoding="utf-8"))["sections"]
owners = (mapping.get(9) or {}).get("owners") or []
if "A15" not in owners:
    problems.append(f"harita §9'u A15'e vermiyor: {owners}")
else:
    print(f"  9  harita §9'u A15'e veriyor (sahipler: {owners})")

sys.path.insert(0, ".claude/hooks")
import _status  # noqa: E402

items = {i.id: i for i in _status.parse_roadmap(roadmap)}
a12 = items.get("A12")
if a12 is None or "A15" not in a12.deps:
    problems.append("A12 A15'e bağlı değil")
else:
    print("  9  A12 A15'e bağlı")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo
echo "GEÇTİ — §9 negatif sonucun yolunu sonucu görmeden bağlıyor: dört verdi"
echo "        eşlenmiş ve \`GEÇERSİZ\`/\`SONUÇSUZ\` negatif SAYILMIYOR; venue"
echo "        kümesi yol haritasının §0 tablosundan OKUNUYOR; ve ürün listesi"
echo "        verdiye bağlı değil — pozitifle aynı tablolar ve şekiller tek"
echo "        koşuda üretiliyor, verdi sonra okunuyor."
echo "        NOT: ürünlerin ÜRETİLMESİ \`E3a\`'nın işi; bu kapı listeyi ölçer."
