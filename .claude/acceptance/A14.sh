#!/usr/bin/env bash
# Kabul kriteri — A14: "§8'de koşu sayısı/koşulu sayıyla yazılı".
#
# Dokuz ölçüm. 3, 4, 5 ve 6 ayırt edici olanlar.
#
#   1  §8 var, yer tutucu yok, dört alt bölümü yazılı
#   2  DENEME SAYISI sayıyla yazılı, ve "bir deneme"nin tanımı var
#   3  ARİTMETİK, ayırt edici: aile-düzeyi hata tablosu `1 − 0,95^K`'dan
#      yeniden hesaplanıyor, VE seçilen K'nın %10'un altında kalan EN BÜYÜK
#      K olduğu doğrulanıyor. Sayı bir gelenek değilse türetilebilir olmak
#      zorunda
#   4  YOL HARİTASI, ayırt edici: §8.1'in ilan ettiği her önkoşul gerçekten
#      var OLMAKLA kalmıyor, `E3a`'nın bağımlılıklarında da duruyor — yani
#      saat yalnız tarif edilmiyor, yol haritası tarafından UYGULANIYOR
#   5  KONTROL, ayırt edici: §8.1'in "önkoşul DEĞİL" diye saydığı maddeler
#      `E3a`'nın bağımlılıklarında DURMUYOR. Bu kontrol olmadan 4. ölçüm
#      "her şeyi listeye koy" ile de geçerdi
#   6  DAVRANIŞ: önkoşulların bugünkü durumu raporlanıyor, ve en az biri
#      açıkken saatin başlamadığı gösteriliyor — kuralın bugün bağlayıcı
#      olduğu ölçülüyor
#   7  `SONUÇSUZ`'un devam izni OLMADIĞI yazılı, ve dört verdinin dördü de
#      §8.3'te eşleniyor
#   8  §8.4'ün yasak listesi §4.3 ve değişmez 7 ile tutarlı, ve kilitlenen
#      bölümleri adıyla sayıyor
#   9  `A13`'ün haritası §8'i A14'e veriyor
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

found = re.search(r"^## 8\. (.+?)$(.*?)(?=^## 9\.)", text, re.S | re.M)
if not found:
    sys.exit("§8 (durdurma kuralı) bölümü bulunamadı")
body = found.group(2)

# ---- 1  bölüm -------------------------------------------------------------
leftovers = re.findall(r"<[^<>\n]{10,}>", body)
if leftovers:
    problems.append(f"§8'de yer tutucu kalmış: {leftovers[:2]}")
absent = [f"8.{i}" for i in range(1, 5) if f"### 8.{i}" not in body]
if absent:
    problems.append(f"§8 alt bölümleri eksik: {absent}")
if not problems:
    print("  1  §8 dolu, dört alt bölümü yazılı")

# ---- 2  deneme sayısı ve tanımı ------------------------------------------
attempts = re.search(r"en çok \*\*(\d+)\*\*", body)
if attempts is None:
    problems.append("§8.2 en çok kaç deneme olduğunu sayıyla yazmıyor")
    MAX_ATTEMPTS = None
else:
    MAX_ATTEMPTS = int(attempts.group(1))
    if not re.search(r"\*\*Bir birincil değerlendirme\*\*\s*=", body):
        problems.append(
            "§8.2 'bir birincil değerlendirme'nin tanımını vermiyor — sayı "
            "tanımsız bir birimde sayılırsa kural uygulanamaz"
        )
    elif "commit" not in body:
        problems.append("§8.2 her denemenin commit hash'iyle raporlandığını yazmıyor")
    else:
        print(f"  2  en çok {MAX_ATTEMPTS} deneme, ve 'bir deneme'nin tanımı yazılı")

# ---- 3  ARİTMETİK: aile-düzeyi hata --------------------------------------
ALPHA = 0.05
rows = re.findall(r"^\|\s*(\d+)\s*\|\s*\*{0,2}%(\d+),(\d+)\*{0,2}\s*\|", body, re.M)
if len(rows) < 3:
    problems.append(f"§8.2'nin aile-düzeyi hata tablosu {len(rows)} satır, ≥3 olmalı")
else:
    bad: list[str] = []
    table: dict[int, float] = {}
    for k_raw, whole, frac in rows:
        k = int(k_raw)
        claimed = float(f"{whole}.{frac}") / 100
        actual = 1 - (1 - ALPHA) ** k
        table[k] = actual
        if abs(claimed - actual) > 5e-5:
            bad.append(f"K={k}: {claimed:.5f} ≠ {actual:.5f}")
    if bad:
        problems.append("§8.2'nin tablosu yeniden hesapla tutmuyor: " + "; ".join(bad))
    elif MAX_ATTEMPTS is not None:
        largest_under_10 = max(
            (k for k in range(1, 20) if 1 - (1 - ALPHA) ** k < 0.10), default=0
        )
        if MAX_ATTEMPTS != largest_under_10:
            problems.append(
                f"§8.2 en çok {MAX_ATTEMPTS} deneme diyor, ama %10'un altında "
                f"kalan en büyük K {largest_under_10} — sayı türetilmiyor"
            )
        elif not re.search(r"üst sınır", body):
            problems.append(
                "§8.2 `1 − 0,95^K`'nın bir ÜST SINIR olduğunu (denemeler korele) "
                "yazmıyor"
            )
        else:
            print(f"  3  aile-düzeyi hata yeniden hesaplandı: "
                  + ", ".join(f"K={k}→%{100 * v:.2f}" for k, v in sorted(table.items()))
                  + f"; %10 altındaki en büyük K = {largest_under_10}")

# ---- yol haritası --------------------------------------------------------
sys.path.insert(0, ".claude/hooks")
import _status  # noqa: E402

items = {i.id: i for i in _status.parse_roadmap(ROADMAP.read_text(encoding="utf-8"))}

# §8.1'in iki listesi tablodan ve prose'dan okunuyor
precondition_block = re.search(r"### 8\.1(.*?)(?=⚠️ \*\*Ve üç madde)", body, re.S)
exempt_block = re.search(r"⚠️ \*\*Ve üç madde(.*?)(?=### 8\.2)", body, re.S)
if precondition_block is None or exempt_block is None:
    problems.append("§8.1'in önkoşul ve 'önkoşul değil' blokları ayrıştırılamadı")
    declared: list[str] = []
    exempt: list[str] = []
else:
    declared = re.findall(r"^\|\s*`([A-Z]\d+[a-z]?)`\s*\|", precondition_block.group(1),
                          re.M)
    exempt = re.findall(r"\*\*`([A-Z]\d+[a-z]?)`\*\*", exempt_block.group(1))

# ---- 4  AYIRT EDİCİ: saat yol haritası tarafından uygulanıyor -----------
if not declared:
    problems.append("§8.1 hiçbir önkoşul adlandırmıyor")
else:
    missing_items = [d for d in declared if d not in items]
    if missing_items:
        problems.append(f"§8.1 var olmayan maddeleri sayıyor: {missing_items}")
    else:
        target = items.get("E3a")
        if target is None:
            problems.append("`E3a` yol haritasında yok — saat neye bağlanacak?")
        else:
            unenforced = [d for d in declared if d not in target.deps]
            if unenforced:
                problems.append(
                    f"§8.1 şu önkoşulları ilan ediyor ama `E3a` onlara bağlı "
                    f"değil: {unenforced} — saat tarif edilmiş, uygulanmamış"
                )
            else:
                print(f"  4  {len(declared)} önkoşul ilan edilmiş ve hepsi "
                      f"`E3a`'nın bağımlılıklarında: {declared}")

# ---- 5  KONTROL: muaf maddeler bağımlılıkta DEĞİL ----------------------
if not exempt:
    problems.append(
        "§8.1 hiçbir maddeyi 'önkoşul değil' diye saymıyor — listeyi şişirmek "
        "de aynı döngüyü açar, o yüzden ayrım yazılmak zorunda"
    )
else:
    target = items.get("E3a")
    wrongly_enforced = [e for e in exempt if target and e in target.deps]
    if wrongly_enforced:
        problems.append(
            f"§8.1 şunları 'önkoşul değil' diyor ama `E3a` onlara bağlı: "
            f"{wrongly_enforced} — belge ile yol haritası çelişiyor"
        )
    else:
        print(f"  5  kontrol: {exempt} 'önkoşul değil' ve `E3a` onlara bağlı değil")

# ---- 6  DAVRANIŞ: kural bugün bağlayıcı mı ------------------------------
if declared:
    open_now = [d for d in declared if "DONE" not in items[d].status]
    if not open_now:
        print("  6  önkoşulların hepsi kapalı — saat başlamış sayılır")
    else:
        print(f"  6  {len(open_now)}/{len(declared)} önkoşul AÇIK "
              f"({open_now}) — saat başlamadı, kural bugün bağlayıcı")

# ---- 7  SONUÇSUZ bir devam izni değil -----------------------------------
verdicts = ("GEÇTİ", "EŞDEĞER", "DAHA KÖTÜ", "SONUÇSUZ")
missing_verdicts = [v for v in verdicts if v not in body]
if missing_verdicts:
    problems.append(f"§8.3 şu verdileri eşlemiyor: {missing_verdicts}")
elif not re.search(r"`SONUÇSUZ` bir devam izni (?:DEĞİL|değil)", body):
    problems.append(
        "§8.3 `SONUÇSUZ`'un bir devam izni OLMADIĞINI yazmıyor — bu maddenin "
        "varlık sebebi tam o döngü"
    )
else:
    print("  7  dört verdi eşlenmiş ve `SONUÇSUZ` devam izni değil")

# ---- 8  yasak listesi ----------------------------------------------------
locked = {
    "§2 metriği": r"§2'nin birincil metriği",
    "§4.1 etiketi": r"§4\.1'in etiket kuralı",
    "§6.1 accession'ları": r"§6\.1'in \*\*sekiz accession",
    "§6.5 çökertme": r"§6\.5'in çökertme",
    "§7.5 tabanları": r"§7\.5'in \*\*beş taban",
    "§7.7 haritalaması": r"§7\.7'nin haritalaması",
    "§7.8 G:U": r"§7\.8'in\s*\n?G:U ağırlığı|§7\.8'in G:U",
}
missing_locked = [k for k, pat in locked.items() if not re.search(pat, body)]
if missing_locked:
    problems.append(f"§8.4 kilitlenen bölümleri saymıyor: {missing_locked}")
elif not re.search(r"değişmez 7", body):
    problems.append("§8.4 değişmez 7'ye atıf yapmıyor")
elif not re.search(r"PRE_REGISTRATION_v2", body):
    problems.append("§8.4 değişiklik gerekirse v2 yolunu yazmıyor (değişmez 6)")
else:
    print(f"  8  §8.4 {len(locked)} kilitli bölümü adıyla sayıyor, değişmez 6 ve 7 ile bağlı")

# ---- 9  harita ----------------------------------------------------------
mapping = yaml.safe_load(MAP.read_text(encoding="utf-8"))["sections"]
owners = (mapping.get(8) or {}).get("owners") or []
if "A14" not in owners:
    problems.append(f"harita §8'i A14'e vermiyor: {owners}")
else:
    print(f"  9  harita §8'i A14'e veriyor (sahipler: {owners})")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo
echo "GEÇTİ — §8 hem BAŞLAMA hem durdurma kuralını sayıyla yazıyor: önkoşullar"
echo "        ilan edilmiş VE \`E3a\`'nın bağımlılıklarında uygulanıyor, 'önkoşul"
echo "        değil' diye sayılanlar ise orada DURMUYOR; en çok 2 deneme sayısı"
echo "        aile-düzeyi hata tablosundan yeniden türetiliyor; ve \`SONUÇSUZ\`"
echo "        bir devam izni olarak yazılmamış."
echo "        NOT: önkoşulların KAPATILMASI bu madde değil — C1, B3, C0, C0b,"
echo "        D1, E0, E0b, E1'in işi."
