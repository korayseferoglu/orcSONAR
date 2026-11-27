#!/usr/bin/env bash
# Kabul kriteri — B11b: "immün kanalın hata yolu risk kararı dönmüyor;
# `_load_motifs` okunamayanı ayırıyor; `risk_level` `Literal`".
#
# Dokuz ölçüm. 2, 3, 4, 5, 6 ve 8 ayırt edici olanlar.
#
#   1  KOD: `_load_motifs`'in dönüş tipi `None` taşıyor ve ÜÇ dalın üçü de
#      `None` dönüyor (yok / okunamıyor / boş)
#   2  DAVRANIŞ, ayırt edici: eksik motif dosyası → bilinmiyor
#   3  DAVRANIŞ, ayırt edici: BOŞ ama okunabilir dosya → bilinmiyor. `B11`'den
#      kasıtlı SAPMA: miRBase'in boş hali ölçülmüş bir yokluk, bu liste ise
#      bizim kürasyonumuz — boşsa hiçbir şeyle karşılaştırılmadı
#   4  KONTROL, ayırt edici: liste YÜKLENDİ ve dizide hit yok → `SAFE`, 0,
#      0.0. Bu olmadan düzeltme "her verdiyi bilinmiyor yap" olurdu
#   5  TİP, ayırt edici: `risk_level`'ın `Literal`'ı `_classify_risk`'in
#      ürettiği kümeyle BİREBİR — ne geniş ne dar. Geniş olması değişmez 3'ün
#      şekli (üretilmeyen bir değeri beyan etmek)
#   6  ZİNCİR, ayırt edici: birimin İKİ YARISI artık aynı şeyi söylüyor —
#      adaptör eksik dosyayla koşturulup çıktısı okunuyor. Asıl hata buydu:
#      saf mantık istisna ATMADIĞI için adaptörün `except`'i hiç tetiklenmiyor
#      ve `SAFE` doğru yer tutucunun üstüne yazıyordu
#   7  KONTROL: canlı tüketici `None`'ı tolere ediyor — `_normalize` tek
#      bilinmeyen kanalı dışlayıp ağırlıkları yeniden normalize ediyor, hepsi
#      bilinmiyorsa `None` dönüyor (`B2`'nin mekanizması)
#   8  TARAMA, ayırt edici: `src/` içinde `SAFE` fallback'i KALMADI. `B11`'in
#      carve-out'ları bu maddenin düzeltmesiyle bayatladı ve o kapı kırmızıya
#      düştü — muafiyetin kalkması hatırlama değil ölçüm sonucu
#   9  ölü modülün tek kalan sonucu kayıtlı: `domain_scores.py`'ın sıfır
#      üretim çağıranı var, yani genişletilen alanın tek mypy sonucu ölü
#      kodda sınırlı

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

fail() { echo "GEÇMEDİ — $1"; exit 1; }

# shellcheck source=_lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

PY=""
for cand in "${PYTHON:-}" python3 python; do
    [ -n "$cand" ] || continue
    if "$cand" -c "import pytest, pydantic" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || fail "pytest+pydantic içeren yorumlayıcı bulunamadı; PYTHON=... ile ver"
echo "# yorumlayıcı: $PY"

warn_untracked src tests .claude || true

"$PY" - <<'INNER' || exit 1
from __future__ import annotations

import inspect
import json
import re
import subprocess
import sys
import tempfile
import typing
from pathlib import Path

sys.path.insert(0, ".")

from src.core.models import ImmuneResult  # noqa: E402
from src.stage2_offtarget_scan import mirbase_checker  # noqa: E402,F401
from src.stage6_execution import immune_screener  # noqa: E402
from src.stage6_execution.execution_merger import _normalize  # noqa: E402
from src.stage6_execution.immune_screen import (  # noqa: E402
    _classify_risk,
    _load_motifs,
    screen_immune_motifs,
)

problems: list[str] = []
MOTIFS = "UGUGU\nGUUGUGU\nUUGU\nUUAU\nAUAU\nUUUU\n"

# ---- 1  KOD: dönüş tipi ve üç dal ---------------------------------------
hints = typing.get_type_hints(_load_motifs)
if type(None) not in typing.get_args(hints.get("return") or int):
    problems.append(
        f"`_load_motifs`'in dönüş tipi `None` taşımıyor ({hints.get('return')})"
    )
else:
    source = inspect.getsource(_load_motifs)
    returns_none = len(re.findall(r"^\s+return None$", source, re.M))
    if returns_none < 3:
        problems.append(
            f"`_load_motifs` yalnız {returns_none} dalda `None` dönüyor, üç "
            "dal olmalı (yok / okunamıyor / boş)"
        )
    else:
        print(f"  1  kod: dönüş tipi `None` taşıyor, {returns_none} dal `None` dönüyor")

# ---- 2  eksik dosya ------------------------------------------------------
if _load_motifs("/no/such/dir/motifs.txt") is not None:
    problems.append("eksik motif dosyası `None` dönmüyor")
else:
    missing = screen_immune_motifs("GCUUUUGC", "/no/such/dir/motifs.txt")
    if (missing.risk_level, missing.total_hits, missing.risk_score) != (None, None, None):
        problems.append(
            f"eksik dosyada verdi üretildi: {missing.risk_level!r}/"
            f"{missing.total_hits!r}/{missing.risk_score!r}"
        )
    else:
        print("  2  eksik motif dosyası → risk_level/total_hits/risk_score = None")

with tempfile.TemporaryDirectory() as tmp:
    work = Path(tmp)

    # ---- 3  BOŞ ama okunabilir (B11'den kasıtlı sapma) ------------------
    empty = work / "empty.txt"
    empty.write_text("# yalnız yorum\n\n", encoding="utf-8")
    if _load_motifs(empty) is not None:
        problems.append(
            "boş ama okunabilir motif dosyası `None` dönmüyor — bu liste elle "
            "küratörlü, boşsa hiçbir şeyle karşılaştırılmadı"
        )
    else:
        verdict = screen_immune_motifs("GCUUUUGC", empty)
        if verdict.risk_level is not None:
            problems.append(f"boş dosyada verdi üretildi: {verdict.risk_level!r}")
        else:
            print("  3  boş ama okunabilir dosya → bilinmiyor (B11'den kasıtlı sapma)")

    # ---- 4  KONTROL: yüklenen liste + hitsiz dizi → SAFE ----------------
    good = work / "motifs.txt"
    good.write_text(MOTIFS, encoding="utf-8")
    loaded = _load_motifs(good)
    if loaded is None or len(loaded) != 6:
        problems.append(f"iyi motif dosyası yüklenmedi: {loaded!r}")
    else:
        clean = screen_immune_motifs("GCGCGCGCGCGCGCGCGCGC", good)
        if (clean.risk_level, clean.total_hits, clean.risk_score) != ("SAFE", 0, 0.0):
            problems.append(
                f"yüklenmiş listeyle hitsiz dizi `SAFE`/0/0.0 vermiyor "
                f"({clean.risk_level!r}/{clean.total_hits!r}/{clean.risk_score!r}) "
                "— düzeltme ölçülmüş yokluğu da bilinmiyor yapmış, 2 ve 3 boş"
            )
        else:
            print("  4  kontrol: yüklenmiş liste + hitsiz dizi → SAFE, 0, 0.0")

    # ---- 6  ZİNCİR: birimin iki yarısı aynı şeyi söylüyor ---------------
    offtargets = work / "stage2_offtargets.json"
    offtargets.write_text(json.dumps({"offtarget_sites": [
        {"site_id": "G1:ENST1:chr1:100"}]}), encoding="utf-8")
    out = work / "stage6_immune.json"
    immune_screener.run(
        sarna_sequence="GCUUUUGC",
        offtargets_path=str(offtargets),
        immune_motifs_file="/no/such/dir/motifs.txt",
        output_path=str(out),
        log_path=str(work / "log.txt"),
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    sarna_side = payload.get("sarna_immune", {})
    site_side = next(iter(payload.get("offtarget_immune", {}).values()), {})
    if sarna_side.get("risk_level") is not None:
        problems.append(
            f"adaptörün saRNA çıktısı verdi taşıyor: {sarna_side.get('risk_level')!r} — "
            "saf mantık istisna atmadığı için `except` tetiklenmiyor ve `SAFE` "
            "doğru yer tutucunun üstüne yazıyor"
        )
    elif site_side.get("risk_level") is not None:
        problems.append(
            f"adaptörün site çıktısı verdi taşıyor: {site_side.get('risk_level')!r}"
        )
    else:
        print("  6  zincir: adaptörün hem saRNA hem site çıktısı bilinmiyor")

# ---- 5  TİP: Literal, üretilen kümeyle birebir --------------------------
annotation = ImmuneResult.model_fields["risk_level"].annotation
allowed = {
    value
    for arg in typing.get_args(annotation)
    for value in typing.get_args(arg)
    if isinstance(value, str)
}
emitted = {_classify_risk(n)[1] for n in (0, 1, 2, 3, 5, 10, 50)}
if not allowed:
    problems.append(
        f"`risk_level` bir `Literal` değil ({annotation}) — `str` olduğu "
        "sürece bir yazım hatası geçerli bir risk seviyesi olur"
    )
elif emitted - allowed:
    problems.append(f"sınıflandırıcı {sorted(emitted - allowed)} üretiyor ama model kabul etmiyor")
elif allowed - emitted:
    problems.append(
        f"model {sorted(allowed - emitted)} kabul ediyor ama sınıflandırıcı hiç "
        "üretmiyor — üretilmeyen bir değeri beyan etmek değişmez 3'ün şekli"
    )
else:
    print(f"  5  tip: Literal{sorted(allowed)} = sınıflandırıcının ürettiği küme")

bare = ImmuneResult()
if (bare.risk_level, bare.total_hits, bare.risk_score) != (None, None, None):
    problems.append(f"modelin varsayılanı verdi taşıyor: {bare.risk_level!r}")

# ---- 7  KONTROL: canlı tüketici `None`'ı tolere ediyor ------------------
all_unknown = _normalize(None, None, None, None)
one_unknown = _normalize(0.5, 0.5, False, None)
if all_unknown is not None:
    problems.append(
        f"`_normalize` her şey bilinmiyorken {all_unknown!r} döndü, `None` olmalı"
    )
elif one_unknown is None:
    problems.append(
        "`_normalize` tek bilinmeyen kanalda tümünü bilinmiyor yaptı — "
        "`B2`'nin yeniden normalizasyonu çalışmıyor"
    )
else:
    print(f"  7  kontrol: canlı tüketici toleranslı — hepsi None → None, "
          f"biri None → {one_unknown} (ağırlıklar yeniden normalize)")

# ---- 8  TARAMA: `SAFE` fallback'i kalmadı ------------------------------
scan = subprocess.run(
    ["git", "grep", "-n", "-E", r'risk_level"?\s*(:[^=]*)?[=:]\s*"SAFE"', "--", "src"],
    capture_output=True, text=True, check=False,
)
remaining = [line for line in scan.stdout.splitlines() if line.strip()]
if remaining:
    problems.append(
        f"`src/` içinde hâlâ {len(remaining)} `SAFE` fallback'i var: "
        + "; ".join(remaining[:3])
    )
else:
    carve = Path(".claude/acceptance/B11.sh").read_text(encoding="utf-8")
    if not re.search(r"CARVE_OUTS: dict\[str, str\] = \{\}", carve):
        problems.append(
            "`B11.sh`'ın carve-out sözlüğü boşaltılmamış — bayat bir muafiyet "
            "sessiz bir silmedir"
        )
    else:
        print("  8  tarama: `src/` içinde `SAFE` fallback'i kalmadı, ve `B11`'in "
              "carve-out'ları boşaltıldı")

# ---- 9  ölü modülün sonucu --------------------------------------------
callers = subprocess.run(
    ["git", "grep", "-l", "-E", r"from src\.scoring\.domain_scores|import domain_scores\b",
     "--", "src", "rules", "Snakefile"],
    capture_output=True, text=True, check=False,
)
live = [p for p in callers.stdout.split() if p != "src/scoring/domain_scores.py"]
if live:
    problems.append(
        f"`domain_scores.py` artık üretimden çağrılıyor ({live}) — genişletilen "
        "alanın mypy sonucu ölü kodda sınırlı değil, madde yeniden açılmalı"
    )
else:
    print("  9  ölü modül: `domain_scores.py` sıfır üretim çağıranı (B8 siliyor), "
          "yani genişletilen alanın tek mypy sonucu orada sınırlı")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo "# birim testleri"
ORCSONAR_SUITE_RECEIPT="$(mktemp -u)" "$PY" -m pytest \
    tests/unit/test_immune_screen.py tests/unit/test_execution_merger.py \
    -q -o addopts="" -p no:cacheprovider || fail "B11b birim testleri yeşil değil"

echo
echo "GEÇTİ — immün kanalı artık veri yokluğundan risk kararı üretmiyor, ve"
echo "        birimin İKİ YARISI aynı şeyi söylüyor: adaptörün doğru yer"
echo "        tutucusunun üstüne yazan saf-mantık verdisi kalktı. Kontrol"
echo "        ölçümü yüklenmiş bir listeyle hitsiz bir dizinin hâlâ \`SAFE\`"
echo "        olduğunu doğruluyor, ve \`risk_level\`'ın \`Literal\`'ı"
echo "        sınıflandırıcının ürettiği kümeyle birebir."
echo "        NOT: kanalın AYIRT EDİCİLİĞİ bu madde değil — \`B11c\`."
