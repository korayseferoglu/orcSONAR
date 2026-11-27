#!/usr/bin/env bash
# Kabul kriteri — A11: "§10'da `validated: false` ile yazılı".
#
# Dokuz ölçüm. 3, 4, 5 ve 6 ayırt edici olanlar, ve dördü de **kodu** okur ya
# da aritmetiği yeniden türetir.
#
#   1  §10.2 var, yer tutucu yok, dört alt bölümü yazılı
#   2  makine-okunur `validated: false` bloğu, ve §10.1'den AYRI
#   3  KOD, ayırt edici: `define_promoter` gerçekten iplik-farkında ve kural
#      10'un −1000/+200'üyle birebir — fonksiyon KOŞTURULUP ölçülüyor, iki
#      iplikte ayrı ayrı
#   4  KOD, ayırt edici: pencere üretimde ÜRETİLİYOR ama hiçbir seed
#      taraması onu TÜKETMİYOR. Satırın "hiç okunmuyor" iddiasının neden
#      yanlış, "kullanılmıyor" ifadesinin neden doğru olduğu bu ayrımda
#   5  KOD, ayırt edici: pencere DİZİ taşımıyor — `GenomicRegion`'ın alanları
#      sayılıyor. "Maliyet ~0 değil" beyanının dayanağı bu
#   6  ARİTMETİK, ayırt edici: bilgi içeriği tablosu config'ten yeniden
#      hesaplanıyor (pencere uzunluğu, seed uzunluğu, seed'in GC'si)
#   7  YASAKLAR: dört yasak da yazılı, ve §4.4 ile tutarlı
#   8  KONTROL: kural 10'un Bulgu-8 listesinde promoter penceresi YOK —
#      "koordinat güvenilir" beyanının dayanağı; listeye girerse beyan düşer
#   9  `A13`'ün haritası §10'u A11'e veriyor
#
# ⚠️ Ağ istemiyor: ölçülen her şey depoda.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

fail() { echo "GEÇMEDİ — $1"; exit 1; }

# shellcheck source=_lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

PY=""
for cand in "${PYTHON:-}" python3 python; do
    [ -n "$cand" ] || continue
    if "$cand" -c "import yaml, pydantic" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || fail "pyyaml+pydantic içeren yorumlayıcı bulunamadı; PYTHON=... ile ver"
echo "# yorumlayıcı: $PY"

warn_untracked docs .claude || true

"$PY" - <<'INNER' || exit 1
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

import yaml

DOC = Path("docs/PRE_REGISTRATION.md")
MAP = Path(".claude/prereg_sections.yaml")
CONFIG = Path("config/config.yaml")
RULE10 = Path(".claude/rules/10-koordinatlar.md")
DEFINER = Path("src/stage1_genomic_map/promoter_definer.py")
ALIGNER = Path("src/stage2_offtarget_scan/seed_aligner.py")

problems: list[str] = []
text = DOC.read_text(encoding="utf-8")

found = re.search(r"^### 10\.2 (.+?)$(.*?)(?=^### 10\.3|^## Sapma)", text, re.S | re.M)
if not found:
    sys.exit("§10.2 (RNAa kolonu) bölümü bulunamadı")
body = found.group(2)

# ---- 1  bölüm -------------------------------------------------------------
leftovers = re.findall(r"<[^<>\n]{10,}>", body)
if leftovers:
    problems.append(f"§10.2'de yer tutucu kalmış: {leftovers[:2]}")
absent = [f"10.2.{i}" for i in range(1, 5) if f"#### 10.2.{i}" not in body]
if absent:
    problems.append(f"§10.2 alt bölümleri eksik: {absent}")
if not problems:
    print("  1  §10.2 dolu, dört alt bölümü yazılı")

# ---- 2  makine-okunur blok ----------------------------------------------
block = re.search(r"```ya?ml\n(.*?)```", body, re.S)
if block is None:
    problems.append("§10.2 makine-okunur bir `validated:` bloğu taşımıyor")
else:
    try:
        parsed = yaml.safe_load(block.group(1))
    except yaml.YAMLError as exc:
        parsed = None
        problems.append(f"§10.2'nin bloğu YAML olarak ayrıştırılamadı: {exc}")
    entry = (parsed or {}).get("rnaa_column") if isinstance(parsed, dict) else None
    if not isinstance(entry, dict):
        problems.append("§10.2'nin bloğunda `rnaa_column` yok")
    elif entry.get("validated") is not False:
        problems.append(f"`validated` False olmalı, {entry.get('validated')!r} yazıyor")
    elif not str(entry.get("reason_not_validated", "")).strip():
        problems.append("`reason_not_validated` boş")
    else:
        print(f"  2  §10.2 makine-okunur: validated=False, "
              f"referans seti sayısı {entry.get('reference_sets_available')}")

# ---- config ---------------------------------------------------------------
config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
sarna = str(config["sarna_sequence"]).upper()
seed_length = int(config["seed_length"])

# ---- 3  KOD: define_promoter iplik-farkında ------------------------------
sys.path.insert(0, ".")
try:
    from src.core.models import TSSInfo
    from src.stage1_genomic_map.promoter_region import define_promoter
except Exception as exc:  # noqa: BLE001
    problems.append(f"promoter_region içe alınamadı: {exc}")
    define_promoter = None  # type: ignore[assignment]

UPSTREAM, DOWNSTREAM = 1000, 200
if define_promoter is not None:
    try:
        plus = define_promoter(
            TSSInfo(gene="PROBE", chrom="chr1", position=100_000, strand="+", source="EPDnew"),
            upstream=UPSTREAM, downstream=DOWNSTREAM,
        )
        minus = define_promoter(
            TSSInfo(gene="PROBE", chrom="chr1", position=100_000, strand="-", source="EPDnew"),
            upstream=UPSTREAM, downstream=DOWNSTREAM,
        )
    except Exception as exc:  # noqa: BLE001
        plus = minus = None
        problems.append(f"define_promoter koşmadı: {exc}")
    if plus is not None and minus is not None:
        want_plus = (100_000 - UPSTREAM, 100_000 + DOWNSTREAM)
        want_minus = (100_000 - DOWNSTREAM, 100_000 + UPSTREAM)
        if (plus.start, plus.end) != want_plus:
            problems.append(
                f"(+) iplikte pencere {(plus.start, plus.end)}, kural 10 "
                f"{want_plus} diyor"
            )
        elif (minus.start, minus.end) != want_minus:
            problems.append(
                f"(−) iplikte pencere {(minus.start, minus.end)}, kural 10 "
                f"{want_minus} diyor — iplik farkındalığı yok"
            )
        elif (plus.start, plus.end) == (minus.start, minus.end):
            problems.append("iki iplik aynı pencereyi veriyor — iplik körü")
        else:
            print(f"  3  kod: (+) {want_plus}, (−) {want_minus} — iplik-farkında "
                  "ve kural 10'la birebir")
        # ---- 5  pencere DİZİ taşımıyor --------------------------------
        fields = set(type(plus).model_fields)
        if fields & {"sequence", "seq", "bases"}:
            problems.append(
                f"pencere dizi alanı taşıyor ({fields}) — §10.2.1'in "
                "'maliyet ~0 değil' beyanı düşer"
            )
        elif not {"chrom", "start", "end", "strand"} <= fields:
            problems.append(f"pencere beklenen koordinat alanlarını taşımıyor: {fields}")
        else:
            print(f"  5  kod: pencere yalnız koordinat taşıyor ({sorted(fields)})")

# ---- 4  KOD: üretiliyor ama tüketilmiyor --------------------------------
definer = DEFINER.read_text(encoding="utf-8") if DEFINER.exists() else ""
aligner = ALIGNER.read_text(encoding="utf-8") if ALIGNER.exists() else ""
if not definer or not aligner:
    problems.append("promoter_definer / seed_aligner okunamadı")
else:
    produced = "define_promoter" in definer and "promoter_region" in definer
    consumed = re.search(r'promoter_data\.get\(\s*"promoter_region"', aligner) is not None
    if not produced:
        problems.append(
            "`promoter_definer` artık pencereyi üretmiyor — §10.2.1'in ölçümü "
            "bayatlamış, madde yeniden açılmalı"
        )
    elif consumed:
        problems.append(
            "`seed_aligner` artık `promoter_region`'ı TÜKETİYOR — §10.2.1 "
            "pencerenin kullanılmadığını yazıyor, madde yeniden açılmalı"
        )
    elif not re.search(r"hiç okunmuyor.{0,40}YANLIŞ|iddiası YANLIŞ", body):
        problems.append(
            "§10.2.1 yol haritasının 'hiç okunmuyor' iddiasını düzeltmiyor — "
            "modül üretimde çağrılıyor, düzeltilmeyen bir iddia kayıtta kalır"
        )
    else:
        print("  4  kod: pencere üretiliyor, hiçbir seed taraması tüketmiyor")

# ---- 6  ARİTMETİK: bilgi içeriği ----------------------------------------
window = UPSTREAM + DOWNSTREAM
positions = window - seed_length + 1
declared_positions = re.search(r"\*\*(\d+)\*\* pozisyon", body)
if declared_positions is None:
    problems.append("§10.2.2 pencere içindeki pozisyon sayısını yazmıyor")
elif int(declared_positions.group(1)) != positions:
    problems.append(
        f"§10.2.2 {declared_positions.group(1)} pozisyon diyor, config "
        f"({window} bp, {seed_length}-mer) {positions} veriyor"
    )
else:
    rows = re.findall(r"^\|\s*(0,\d+)\s*\|\s*(0,\d+)\s*\|\s*%(\d+[.,]\d+)\s*\|",
                      body, re.M)
    if len(rows) < 4:
        problems.append(f"§10.2.2'nin tablosu {len(rows)} satır, en az 4 olmalı")
    else:
        seed = sarna[1 : 1 + seed_length].replace("U", "T")
        bad: list[str] = []
        for gc_raw, expected_raw, prob_raw in rows:
            gc = float(gc_raw.replace(",", "."))
            p_gc, p_at = gc / 2, (1 - gc) / 2
            probability = 1.0
            for base in seed:
                probability *= p_gc if base in "GC" else p_at
            lam = 2 * positions * probability
            if abs(lam - float(expected_raw.replace(",", "."))) > 0.0015:
                bad.append(f"GC={gc}: beklenen {lam:.4f} ≠ {expected_raw}")
            elif abs((1 - math.exp(-lam)) * 100
                     - float(prob_raw.replace(",", "."))) > 0.15:
                bad.append(f"GC={gc}: P(≥1) {100 * (1 - math.exp(-lam)):.1f}% ≠ {prob_raw}%")
        if bad:
            problems.append("§10.2.2'nin tablosu yeniden hesapla tutmuyor: "
                            + "; ".join(bad[:3]))
        else:
            print(f"  6  bilgi içeriği yeniden hesaplandı: {positions} pozisyon, "
                  f"seed {seed}, {len(rows)} GC satırı tutuyor")

# ---- 7  YASAKLAR --------------------------------------------------------
bans = {
    "birincil metriğe girmez": r"birincil metriğine girmez",
    "karar kuralına girmez": r"karar kuralına girmez",
    "birleştirilmez": r"birleştirilmez",
    "etiketsiz raporlanmaz": r"etiketi olmadan.{0,30}raporlanmaz",
}
missing = [k for k, pat in bans.items() if not re.search(pat, body)]
if missing:
    problems.append(f"§10.2.3 yasakları eksik: {missing}")
else:
    section44 = re.search(r"#### 4\.4\.3(.*?)(?=#### 4\.4\.4)", text, re.S)
    if section44 is None or "P_silence" not in section44.group(1):
        problems.append(
            "§4.4.3 karar kuralını `P_silence`'a bağlamıyor — §10.2.3'ün "
            "yasağı o bağla tutarlı olmak zorunda"
        )
    else:
        print("  7  dört yasak yazılı ve §4.4.3 ile tutarlı")

# ---- 8  KONTROL: kural 10'un Bulgu-8 listesi ----------------------------
rule10 = RULE10.read_text(encoding="utf-8") if RULE10.exists() else ""
if not rule10:
    problems.append(f"{RULE10} okunamadı")
else:
    affected = re.search(r"Genomik lokusa dayanan her kaynak \(([^)]*)\)", rule10)
    if affected is None:
        problems.append("kural 10'daki etkilenen-kaynaklar listesi bulunamadı")
    elif re.search(r"promoter|EPDnew|FANTOM", affected.group(1), re.I):
        problems.append(
            "kural 10 artık promoter/TSS kaynaklarını da etkilenenler arasında "
            "sayıyor — §10.2.1'in 'koordinat güvenilir' beyanı düşer"
        )
    else:
        print("  8  kontrol: kural 10'un Bulgu-8 listesinde promoter penceresi yok")

# ---- 9  harita ----------------------------------------------------------
mapping = yaml.safe_load(MAP.read_text(encoding="utf-8"))["sections"]
owners = (mapping.get(10) or {}).get("owners") or []
if "A11" not in owners:
    problems.append(f"harita §10'u A11'e vermiyor: {owners}")
else:
    print(f"  9  harita §10'u A11'e veriyor (sahipler: {owners})")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo
echo "GEÇTİ — §10.2 RNAa kolonunu makine-okunur \`validated: false\` ile"
echo "        yazıyor; \`define_promoter\` KOŞTURULUP iki iplikte kural 10'la"
echo "        karşılaştırılıyor; pencerenin üretildiği ama tüketilmediği ve"
echo "        yalnız koordinat taşıdığı kodda ölçülüyor; ve kolonun bilgi"
echo "        içeriği config'ten yeniden hesaplanıyor."
echo "        NOT: kolonun UYGULANMASI bu madde değil; Faz A'da kod yazılmıyor."
