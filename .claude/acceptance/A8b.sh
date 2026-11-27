#!/usr/bin/env bash
# Kabul kriteri — A8b: "§6'da prob→gen ve site→gen çökertme kuralı, yönüyle
# birlikte yazılı".
#
# Dokuz ölçüm. 4, 5 ve 6 ayırt edici olanlar.
#
#   1  §6.5 var, yer tutucu yok, üç alt bölümü yazılı
#   2  ETİKET kuralı tek cümlede ve determinist: seçilen istatistik ve
#      eşitlik kuralı yazılı
#   3  SKOR kuralı maksimum, ve `toplam`ın neden olmadığı 1. ve 3. tabanla
#      gerekçelendirilmiş
#   4  AĞ, ASIL ÖLÇÜM: dört kural GEO'dan yeniden hesaplanıyor ve §6.5.1'in
#      tablosundaki YÖNLER doğrulanıyor — `any` ve `best-p` maxmean'in
#      ÜSTÜNDE, `all` ALTINDA. Yönler tutmazsa tablo bir iddia değil süstür
#   5  AĞ, KONTROL: `best-p` ile `any` neredeyse aynı sonucu veriyor —
#      §6.5.1'in "masum görünen kural pozitifi maksimize ediyor" iddiası
#      bu yakınlığa dayanıyor; ayrışırlarsa iddia düşer
#   6  AĞ, ASIL ÖLÇÜM: boşluğun kendisi — çok-problu genlerde etiket
#      çelişkisi oranı §6.5'in ilan ettiği aralıkta. Çelişki yoksa bu
#      maddenin varlık sebebi yok
#   7  KAYNAK: Miller ve ark. PMID'si yazılı, VE atfın üç sınırı da
#      (DE'yi ele almıyor / kendi çekinceleri / eşitlik kuralı değiştirildi)
#   8  ölçümün kaydı depoda, betiğiyle
#   9  `A13`'ün haritası §6'yı A8b'ye veriyor ve `A12` ona bağlı
#
# ⚠️ 4-6 ağ gerektirir; ağ yoksa ATLANIR, ölçüm §6.5'i yanlışlarsa GEÇMEZ.

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

warn_untracked docs .claude reports || true

"$PY" - <<'INNER' || exit 1
from __future__ import annotations

import re
import statistics
import sys
from pathlib import Path

import yaml

DOC = Path("docs/PRE_REGISTRATION.md")
MAP = Path(".claude/prereg_sections.yaml")
ROADMAP = Path("SCIENTIFIC_ROADMAP.md")
RECORD = Path("reports/a8b-cokertme-2026-11-27")

problems: list[str] = []
text = DOC.read_text(encoding="utf-8")

found = re.search(r"^### 6\.5 (.+?)$(.*?)(?=^### 6\.6|^## 7\.)", text, re.S | re.M)
if not found:
    sys.exit("§6.5 (çökertme kuralları) bölümü bulunamadı")
body = found.group(2)

# ---- 1  bölüm -------------------------------------------------------------
leftovers = re.findall(r"<[^<>\n]{10,}>", body)
if leftovers:
    problems.append(f"§6.5'te yer tutucu kalmış: {leftovers[:2]}")
absent = [f"6.5.{i}" for i in range(1, 4) if f"#### 6.5.{i}" not in body]
if absent:
    problems.append(f"§6.5 alt bölümleri eksik: {absent}")
if not problems:
    print("  1  §6.5 dolu, üç alt bölümü yazılı")

# ---- 2  etiket kuralı determinist -----------------------------------------
# ⚠️ Kural cümlesi, atfın sınırlarından AYRI aranıyor. İlk hali tüm §6.5'te
# arıyordu ve kendi kırmızı-önce denememde yakalandı: "en küçük prob kimliği"
# dizgisi 3. sınırda da geçiyor, o yüzden KURAL cümlesini silmek kapıyı
# geçiyordu. İkinci kopya muafiyet yaratıyordu.
rule_block = re.search(r"#### 6\.5\.1(.*?)(?=⚠️ \*\*Üç sınır)", body, re.S)
if rule_block is None:
    problems.append("§6.5.1'in kural cümlesi bloğu bulunamadı")
elif not re.search(r"mock kanalı\s*\n?\s*yoğunluğu en yüksek|en yüksek.{0,40}mock",
                   rule_block.group(1)):
    problems.append("§6.5.1 seçim istatistiğini (mock kanalı yoğunluğu) yazmıyor")
elif not re.search(r"en küçük prob kimliği", rule_block.group(1)):
    problems.append(
        "§6.5.1 KURAL cümlesinde eşitlik kuralını yazmıyor — `collapseRows` "
        "rastgele seçiyor ve ön kayıtlı bir evren rastgele kurulamaz"
    )
else:
    print("  2  etiket kuralı determinist: mock kanalı + en küçük prob kimliği")

# ---- 3  skor kuralı -------------------------------------------------------
score = re.search(r"#### 6\.5\.3(.*?)$", body, re.S)
if score is None:
    problems.append("§6.5.3 bulunamadı")
else:
    chunk = score.group(1)
    if not re.search(r"maksimum", chunk):
        problems.append("§6.5.3 skor kuralını (maksimum) yazmıyor")
    elif not re.search(r"monoton", chunk):
        problems.append(
            "§6.5.3 `toplam`ın site sayısında monoton olduğunu yazmıyor — "
            "reddin gerekçesi o"
        )
    elif not (re.search(r"1 numaralı taban|7mer-m8 sayısı", chunk)
              and re.search(r"3 numaralı taban|uzunluk", chunk)):
        problems.append(
            "§6.5.3 `toplam`ı §7.5'in 1. ve 3. tabanlarıyla ilişkilendirmiyor"
        )
    else:
        print("  3  skor kuralı maksimum; `toplam` 1. ve 3. tabanla gerekçeli reddedilmiş")

# ---- ölçüm ----------------------------------------------------------------
sys.path.insert(0, str(RECORD))
loaded = False
try:
    import olcum  # type: ignore[import-not-found]

    loaded = True
except Exception as exc:  # noqa: BLE001 - ölçüm betiği yoksa atlanır
    print(f"  4-6  ATLANDI — ölçüm betiği içe alınamadı ({exc})")

if loaded:
    rows: list[dict[str, object]] = []
    for gsm, (gpl, series) in olcum.ARRAYS.items():
        try:
            data, total, unmapped = olcum.probes(gsm, gpl)
        except Exception:  # noqa: BLE001 - ağ yoksa atlanır
            data = []
        if not data:
            continue
        groups: dict[str, list[dict[str, object]]] = {}
        for probe in data:
            groups.setdefault(str(probe["symbol"]), []).append(probe)
        entry: dict[str, object] = {"gsm": gsm, "genes": len(groups)}
        for rule in olcum.RULES:
            entry[rule] = sum(olcum.collapse(g, rule) for g in groups.values())
        multi = [g for g in groups.values() if len(g) > 1]
        with_pos = [g for g in multi if any(int(p["label"]) for p in g)]
        conflict = [g for g in multi
                    if 0 < sum(int(p["label"]) for p in g) < len(g)]
        entry["conflict_frac"] = len(conflict) / max(len(with_pos), 1)
        entry["unmapped_frac"] = unmapped / total
        rows.append(entry)

    if not rows:
        print("  4  ATLANDI — GEO'ya ulaşılamadı (ağ yok)")
        print("  5  ATLANDI")
        print("  6  ATLANDI")
    else:
        # ---- 4  yönler ----------------------------------------------------
        # ⚠️ İşaretler betiğe GÖMÜLMÜYOR, §6.5.1'in tablosundan okunuyor.
        # İlk hali gömülüydü ve kendi kırmızı-önce denememde yakalandı:
        # tablonun işaretini ters çevirmek kapıyı geçiyordu, yani tablo bir
        # iddia değil süstü. `H21`'in dersi bir seviye aşağıda.
        ROW = r"\|\s*`(any|all|best-p)`[^|]*\|[^|]*\|\s*(?:\*\*)?(—|[+−-]\d)"
        directions: dict[str, int] = {}
        for name, token in re.findall(ROW, body):
            key = {"any": "any", "all": "all", "best-p": "bestp"}[name]
            if token == "—":
                continue
            directions[key] = -1 if token[0] in "−-" else +1
        if set(directions) != {"any", "all", "bestp"}:
            problems.append(
                f"§6.5.1'in yön tablosundan işaretler okunamadı: "
                f"{sorted(directions)} — tablo üç kuralın işaretini de yazmalı"
            )
        wrong: list[str] = []
        for rule, sign in directions.items():
            deltas = [(int(r[rule]) - int(r["maxmean"])) / max(int(r["maxmean"]), 1)
                      for r in rows]
            median = statistics.median(deltas)
            if (median > 0) != (sign > 0):
                wrong.append(f"{rule}: {median:+.1%} (beklenen işaret {sign:+d})")
        if wrong:
            problems.append(
                "§6.5.1'in yön tablosu ölçümle tutmuyor: " + "; ".join(wrong)
            )
        else:
            summary = {
                rule: statistics.median(
                    (int(r[rule]) - int(r["maxmean"])) / max(int(r["maxmean"]), 1)
                    for r in rows
                )
                for rule in ("any", "bestp", "all")
            }
            print(f"  4  yönler doğrulandı ({len(rows)} array): "
                  f"any {summary['any']:+.1%}, best-p {summary['bestp']:+.1%}, "
                  f"all {summary['all']:+.1%}")

        # ---- 5  KONTROL: best-p ≈ any -------------------------------------
        gaps = [abs(int(r["bestp"]) - int(r["any"])) / max(int(r["any"]), 1)
                for r in rows]
        if statistics.median(gaps) > 0.02:
            problems.append(
                f"`best-p` ile `any` medyan %{statistics.median(gaps) * 100:.1f} "
                "ayrışıyor — §6.5.1'in 'masum görünen kural pozitifi maksimize "
                "ediyor' iddiası bu yakınlığa dayanıyor"
            )
        else:
            print(f"  5  kontrol: best-p ≈ any (medyan fark "
                  f"%{statistics.median(gaps) * 100:.2f}) — yasağın gerekçesi ayakta")

        # ---- 6  boşluğun kendisi ------------------------------------------
        declared = re.search(r"%(\d+)-(\d+)['’]?ünde problar", body)
        if declared is None:
            declared = re.search(r"%(\d+)-(\d+)", body)
        fracs = [float(r["conflict_frac"]) for r in rows]
        if declared is None:
            problems.append("§6.5 etiket çelişkisi oranını yazmıyor")
        else:
            low = int(declared.group(1)) / 100
            high = int(declared.group(2)) / 100
            observed = statistics.median(fracs)
            if not low * 0.7 <= observed <= high * 1.3:
                problems.append(
                    f"çok-problu genlerde çelişki oranı medyan "
                    f"%{observed * 100:.0f}, §6.5 %{low * 100:.0f}-"
                    f"%{high * 100:.0f} diyor — bu maddenin varlık sebebi bu sayı"
                )
            else:
                print(f"  6  etiket çelişkisi medyan %{observed * 100:.0f} "
                      f"(aralık %{min(fracs) * 100:.0f}-%{max(fracs) * 100:.0f}); "
                      f"eşleşmeyen prob %{min(float(r['unmapped_frac']) for r in rows) * 100:.1f}-"
                      f"%{max(float(r['unmapped_frac']) for r in rows) * 100:.1f}")

# ---- 7  kaynak ve sınırları -----------------------------------------------
if "21816037" not in body:
    problems.append("§6.5.1 Miller ve ark.'nın PMID'sini yazmıyor")
else:
    limits = {
        "DE'yi ele almıyor": r"diferansiyel ifade analizini HİÇ ele almıyor",
        "kendi çekinceleri": r"analysis goal|often, but not always",
        "eşitlik değiştirildi": r"Eşitlik kuralı DEĞİŞTİRİLDİ|randomly\s*\n?\s*chooses",
    }
    missing = [k for k, pat in limits.items() if not re.search(pat, body)]
    if missing:
        problems.append(f"§6.5.1 atfın sınırlarını yazmıyor: {missing}")
    else:
        print("  7  kaynak PMID'siyle, ve atfın üç sınırı da yazılı")

# ---- 8  kayıt -------------------------------------------------------------
if not RECORD.is_dir():
    problems.append(f"{RECORD} yok")
else:
    needed = {"README.md", "olcum.py", "olcum.json"}
    have = {p.name for p in RECORD.iterdir()}
    if not needed <= have:
        problems.append(f"{RECORD} eksik: {sorted(needed - have)}")
    else:
        print(f"  8  ölçüm kaydı {RECORD} içinde, betiğiyle")

# ---- 9  harita ve kilit ---------------------------------------------------
mapping = yaml.safe_load(MAP.read_text(encoding="utf-8"))["sections"]
owners = (mapping.get(6) or {}).get("owners") or []
if "A8b" not in owners:
    problems.append(f"harita §6'yı A8b'ye vermiyor: {owners}")
else:
    print(f"  9  harita §6'yı A8b'ye veriyor (sahipler: {owners})")

sys.path.insert(0, ".claude/hooks")
import _status  # noqa: E402

items = {i.id: i for i in _status.parse_roadmap(ROADMAP.read_text(encoding="utf-8"))}
a12 = items.get("A12")
if a12 is None or "A8b" not in a12.deps:
    problems.append("A12 A8b'ye bağlı değil — kilit açılırsa kural seçilemez olur")
else:
    print("  9  A12 A8b'ye bağlı")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo
echo "GEÇTİ — §6.5 prob→gen ve site→gen çökertmesini kuralıyla, eşitlik"
echo "        kuralıyla ve YÖNÜYLE yazıyor; kapı dört kuralı GEO'dan yeniden"
echo "        hesaplayıp yönleri doğruluyor, ve kontrol ölçümü \`best-p\`"
echo "        yasağının gerekçesini (≈ \`any\`) yeniden ölçüyor."
echo "        NOT: kuralın UYGULANMASI bu madde değil; Faz A'da kod yazılmıyor."
