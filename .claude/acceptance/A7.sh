#!/usr/bin/env bash
# Kabul kriteri — A7: "§7'de ayrışma, §10'da doğrulanamayan yarı
# `validated: false` ile".
#
# Dokuz ölçüm. 3, 4 ve 5 ayırt edici olanlar, ve üçü de **kodu** okuyor:
# bir ayrışma kararı kanalların ne ölçtüğüne dayanıyorsa, kapı o iddiayı
# prose'dan değil üretim kaynağından doğrulamak zorunda.
#
#   1  §7.6 var, iki kolonu adlandırıyor, ve §2'nin hangisini sıraladığı yazılı
#   2  §10.1 `validated: false` **makine-okunur** bir blokla duruyor
#   3  KOD, ayırt edici: `execution_safety`'nin dört girdisi gerçekten
#      `ago2_loading`, `rbp_competition`, `circrna_overlap` ve immün; ve
#      `_normalize`'ın docstring'i hâlâ "more silencing activity expected"
#      diyor. §7.6'nın kanal ataması düzeltmesi tam bu iki olguya dayanıyor —
#      kod değişirse bu madde yeniden açılmalı
#   4  KOD, ayırt edici: immün kanalın site kaydı yoksa saRNA düzeyine
#      DÜŞTÜĞÜ (`offtarget_immune.get(site_id, sarna_immune)`) — `Impact`'ın
#      `per_site: false` olmasının sebebi
#   5  KONTROL: `variant_toxicity`'nin vekili hâlâ COSMIC yoğunluğu, yani
#      §7.6'nın çürütme cümlesi bugünkü kodu tarif ediyor. Vekil değişmişse
#      çürütme bayatlamıştır ve bu kapı onu geçirmemeli
#   6  dört doğrulanamazlık sebebi de kaynağıyla yazılı (PMID'ler)
#   7  BİRLEŞTİRME yasağı yazılı, ve çarpımsal formun neden varsayım olduğu
#   8  §4.4'ün karar kuralı `Impact`'tan girdi almadığını söylüyor
#   9  `A13`'ün haritası §7 ve §10'u A7'ye veriyor
#
# ⚠️ Bu kapı pytest koşmuyor ve ağ istemiyor: ölçtüğü her şey depoda.

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
MERGER = Path("src/stage6_execution/execution_merger.py")
COSMIC = Path("src/stage3_variant_tox/cosmic_scanner.py")

problems: list[str] = []
text = DOC.read_text(encoding="utf-8")


def section(number: str, stop: str) -> str:
    found = re.search(rf"^#{{3,4}} {re.escape(number)} (.+?)$(.*?)(?={stop})",
                      text, re.S | re.M)
    if found is None:
        problems.append(f"§{number} bölümü bulunamadı")
        return ""
    return found.group(2)


s76 = section("7.6", r"^## 8\.")
s101 = section("10.1", r"^### 10\.2|^## Sapma")
s44 = section("4.4", r"^## 5\.")

# ---- 1  ayrışma yazılı ----------------------------------------------------
if s76:
    leftovers = re.findall(r"<[^<>\n]{10,}>", s76)
    if leftovers:
        problems.append(f"§7.6'da yer tutucu kalmış: {leftovers[:2]}")
    for token in ("`P_silence`", "`Impact`"):
        if token not in s76:
            problems.append(f"§7.6 {token} kolonunu adlandırmıyor")
    if not re.search(r"§2'nin birincil metriği \*\*bunu\*\* sıralar|"
                     r"birincil metri\w+ `?P_silence`? sıralar", s76):
        problems.append(
            "§7.6 §2'nin HANGİ kolonu sıraladığını söylemiyor — ayrışmanın "
            "bütün kazancı bu cümlede"
        )
    if not problems:
        print("  1  §7.6 iki kolonu adlandırıyor, birincil metriğin sıraladığı yazılı")

# ---- 2  makine-okunur validated: false -----------------------------------
if s101:
    block = re.search(r"```ya?ml\n(.*?)```", s101, re.S)
    if block is None:
        problems.append("§10.1 makine-okunur bir `validated:` bloğu taşımıyor")
    else:
        try:
            parsed = yaml.safe_load(block.group(1))
        except yaml.YAMLError as exc:
            parsed = None
            problems.append(f"§10.1'in bloğu YAML olarak ayrıştırılamadı: {exc}")
        entry = (parsed or {}).get("impact_column") if isinstance(parsed, dict) else None
        if not isinstance(entry, dict):
            problems.append("§10.1'in bloğunda `impact_column` yok")
        else:
            if entry.get("validated") is not False:
                problems.append(
                    f"`validated` False olmalı, {entry.get('validated')!r} yazıyor"
                )
            if entry.get("per_site") is not False:
                problems.append(
                    "`per_site` False olmalı — immün kanal saRNA düzeyine düşüyor"
                )
            if not str(entry.get("reason_not_validated", "")).strip():
                problems.append("`reason_not_validated` boş")
            if not [p for p in problems if "validated" in p or "per_site" in p]:
                print("  2  §10.1 makine-okunur: validated=False, per_site=False")

# ---- 3  KOD: execution_safety'nin girdileri ------------------------------
merger = MERGER.read_text(encoding="utf-8") if MERGER.exists() else ""
if not merger:
    problems.append(f"{MERGER} okunamadı — 3. ölçüm yapılamaz")
else:
    signature = re.search(
        r"def _normalize\(\s*(.*?)\)\s*->", merger, re.S
    )
    if signature is None:
        problems.append("`_normalize` imzası bulunamadı — kanal ataması doğrulanamaz")
    else:
        params = set(re.findall(r"(\w+):", signature.group(1)))
        want = {"ago2_loading", "rbp_competition", "circrna_overlap", "immune_risk"}
        if params != want:
            problems.append(
                f"`execution_safety`'nin girdileri değişmiş: {sorted(params)} — "
                f"§7.6'nın kanal ataması {sorted(want)} üzerine kurulu, madde "
                "yeniden açılmalı"
            )
        elif "more silencing activity expected" not in merger:
            problems.append(
                "`_normalize` artık 'more silencing activity expected' demiyor — "
                "§7.6'nın düzeltmesi bu sözleşmeye dayanıyordu"
            )
        else:
            print("  3  kod: dört girdi beklendiği gibi, ve sözleşme hâlâ "
                  "'more silencing activity expected'")
    for channel in ("ago2_loading", "rbp_competition", "circrna_overlap"):
        if f"`{channel}`" not in s76:
            problems.append(f"§7.6 {channel} kanalını tabloda saymıyor")

# ---- 4  KOD: immün kanalın saRNA düzeyine düşmesi ------------------------
if merger:
    if "offtarget_immune.get(site_id, sarna_immune)" not in merger:
        problems.append(
            "immün kanalın saRNA düzeyine düştüğü satır bulunamadı — "
            "`per_site: false` gerekçesi bu davranışa dayanıyor"
        )
    elif "sarna_immune" not in s76:
        problems.append("§7.6 saRNA düzeyine düşme davranışını yazmıyor")
    else:
        print("  4  kod: immün kanal site kaydı yoksa saRNA düzeyine düşüyor")

# ---- 5  KONTROL: variant_toxicity'nin vekili ----------------------------
if not COSMIC.exists():
    problems.append(f"{COSMIC} yok — §7.6'nın çürütmesi bugünkü kodu tarif etmiyor")
else:
    cosmic = COSMIC.read_text(encoding="utf-8")
    if not re.search(r"mutations?_per_kb|per_kb|density|yoğunluk", cosmic):
        problems.append(
            "`cosmic_scanner.py` artık yoğunluk vekili kullanmıyor gibi — "
            "§7.6'nın çürütme cümlesi bayatlamış olabilir, madde yeniden açılmalı"
        )
    elif "cosmic_scanner" not in s76:
        problems.append("§7.6 çürütülen vekili dosya adıyla göstermiyor")
    else:
        print("  5  kontrol: vekil hâlâ COSMIC yoğunluğu, çürütme güncel")

# ---- 6  dört sebep, kaynaklarıyla ---------------------------------------
if s101:
    sources = {
        "DEMETER2 seed tanımı": "30389920",
        "pTriplo (yön)": "35917817",
        "toksisite precedent'i (Janas)": "29459660",
        "toksisite precedent'i (Schlegel)": "35736224",
    }
    missing = [k for k, pmid in sources.items() if pmid not in s101]
    if missing:
        problems.append(f"§10.1'de kaynaksız sebep(ler): {missing}")
    reasons = {
        "referans seti ölçmüyor": r"Referans seti onu ölçmüyor",
        "yön": r"Yön uyuşmuyor",
        "arıza yönü": r"Arıza yönü yanlış",
        "precedent yok": r"Precedent yok",
    }
    absent = [k for k, pat in reasons.items() if not re.search(pat, s101)]
    if absent:
        problems.append(f"§10.1 dört sebebi başlıkla saymıyor: {absent}")
    if not [p for p in problems if "§10.1" in p]:
        print("  6  dört doğrulanamazlık sebebi de başlıkla ve PMID'siyle yazılı")

# ---- 7  birleştirme yasağı ----------------------------------------------
if s76:
    if not re.search(r"birleştir\w*", s76):
        problems.append("§7.6 iki kolonun birleştirilmesine dair bir kural yazmıyor")
    elif not re.search(r"çarpımsal", s76):
        problems.append(
            "§7.6 çarpımsal formun neden kanıtsız bir etkileşim modeli olduğunu "
            "yazmıyor — yasağın gerekçesi o"
        )
    else:
        print("  7  birleştirme yasağı ve çarpımsal formun gerekçesi yazılı")

# ---- 8  karar kuralı Impact'tan girdi almıyor ---------------------------
if s44 and not re.search(r"`Impact`", s44):
    problems.append(
        "§4.4 `Impact`'tan girdi almadığını söylemiyor — karar kuralı "
        "doğrulanamayan bir kolondan beslenmediğini açıkça yazmak zorunda"
    )
elif s44:
    print("  8  §4.4 `Impact`'tan girdi almadığını söylüyor")

# ---- 9  harita -----------------------------------------------------------
mapping = yaml.safe_load(MAP.read_text(encoding="utf-8"))["sections"]
for number in (7, 10):
    owners = (mapping.get(number) or {}).get("owners") or []
    if "A7" not in owners:
        problems.append(f"harita §{number}'ü A7'ye vermiyor: {owners}")
if not [p for p in problems if "harita" in p]:
    print("  9  harita §7 ve §10'u A7'ye veriyor")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo
echo "GEÇTİ — §7.6 skoru iki kolona ayırıyor ve kanal atamasını ÜRETİM"
echo "        KAYNAĞINDAN doğruluyor; §10.1 doğrulanamayan yarıyı makine-okunur"
echo "        \`validated: false\` ile, dört sebebin dördünü de kaynağıyla"
echo "        taşıyor; birleştirme yasaklı ve karar kuralı o kolondan"
echo "        beslenmiyor."
echo "        NOT: \`Impact\`'ın UYGULANMASI bu madde değil; bu bir ön kayıt"
echo "        maddesi ve Faz A'da kod yazılmıyor."
