#!/usr/bin/env bash
# Kabul kriteri — C3: ΔG off-target'ın KENDİ dizisine karşı, doğru yönelimde
# ve site başına hesaplanıyor.
#
# Kriter üç maddeydi: "ΔG negatif, siteler arası varyans > 0, hiçbir site
# 1.0'a saplanmıyor". Bu kapı birinci ve ikinciyi ölçer; üçüncü **ölçülemez**
# ve neden ölçülemediği aşağıda yazılı — kapı onu geçmiş gibi göstermiyor.
#
# Altı ölçüm, hepsi ağsız (yalnız yerel Turner tabloları, `data/` salt-okunur):
#   1  mükemmel dupleks çapası: −43.80 / 0 mismatch
#   2  yönelim stage 2'nin KENDİ konvansiyonuyla aynı — Turner'ın
#      eşleşmemiş-pozisyon sayımı `_score_alignment`'ın mismatch sayımına eşit
#   3  siteler arası varyans > 0 (eski hatanın imzası tek bir aynı değerdi)
#   4  `target_window` yoksa ΔG **bilinmiyor**, sayı değil (değişmez 2)
#   5  mismatch eklemek ΔG'yi asla daha negatif yapmıyor; 0 mismatch negatif
#   6  kırmızı-önce testleri yeşil
#
# Hangi ölçüm kırmızı olabiliyor (2026-11-26'da `e8bde8b`, yani düzeltme
# öncesi kodda koşturularak doğrulandı): **3 ve 4** kırmızıya döndü —
# beş ayrı pencere için aynı `[31.1, 31.1, 31.1, 31.1, 31.1]`, ve penceresiz
# site `ΔG=31.1` döndürüyordu. 1, 2 ve 5 düzeltme öncesinde de geçiyor,
# çünkü onlar `TurnerCalculator`'ı ölçüyor ve `C3` adapter'daydı; o üçü
# ayrım değil **regresyon çapası**. Kapının ayırt edici gücü 3 ve 4'te.
#
# ⚠️ ÖLÇÜLMEYEN: "hiçbir site 1.0'a saplanmıyor". Bu, kodun değil **aday
# kümesinin** özelliği: VEGFA_HeLa'nın 41 sitesi 5–11 mismatch taşıdığı için
# en güçlüsü −13.20'de kalıyor ve −30 eşiğine ulaşamıyor. Ama bu bir garanti
# DEĞİL — bu kapı yazılırken ölçüldü: 5 mismatch'li bir pencere uygun
# pozisyonlarda −37.40'a kadar inebiliyor, yani başka bir guide ya da başka
# bir aday kümesi siteleri 1.0'a saplayabilir. Ölçmek canlı bir Ensembl
# çekimi gerektirir; ağsız kapı bunu sessizce atlamak yerine açıkça
# kapsamıyor. Gerçek dağılım `SCIENTIFIC_ROADMAP.md`'nin C3 satırında kayıtlı.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

fail() { echo "GEÇMEDİ — $1"; exit 1; }

PY=""
for cand in "${PYTHON:-}" python3 python; do
    [ -n "$cand" ] || continue
    if "$cand" -c "import pytest" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || fail "pytest içeren yorumlayıcı bulunamadı; PYTHON=... ile ver"
echo "# yorumlayıcı: $PY"

echo "# 1-5  ΔG davranış ölçümleri"
"$PY" -I - <<'INNER' || fail "C3 davranış ölçümleri geçmedi"
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")

import yaml

from src.stage2_offtarget_scan.seed_aligner import _score_alignment
from src.stage5_biophysics.delta_g_calculator import run as dg_run
from src.stage5_biophysics.thermodynamics import TurnerCalculator

cfg = yaml.safe_load(Path("config/config.yaml").read_text(encoding="utf-8"))
turner_dir = cfg["data_paths"]["turner_rules_dir"]
guide = cfg["sarna_sequence"].upper().replace("T", "U")
calc = TurnerCalculator(turner_dir)

COMP = {"A": "U", "U": "A", "G": "C", "C": "G"}
# `target_window` is the transcript slice 5'->3'. A perfectly complementary
# window is revcomp(guide); stage 5 reverses it for index alignment.
perfect_window = "".join(COMP[b] for b in guide)[::-1]

problems = []


def dg_of(window: str):
    return calc.calculate_duplex_dg(guide, window[::-1])


# --- 1  mükemmel dupleks çapası ------------------------------------------
r = dg_of(perfect_window)
if round(r.delta_g, 2) != -43.80:
    problems.append(f"mükemmel dupleks ΔG {r.delta_g} != -43.80 (yönelim kaymış)")
if r.mismatch_penalties:
    problems.append(f"mükemmel dupleksde {len(r.mismatch_penalties)} mismatch")

# --- 2  yönelim stage 2'nin konvansiyonuyla aynı -------------------------
# G:U wobble'ı iki taraf da eşleşme sayar; bu yüzden sayımlar karşılaştırılabilir.
SUB = {"A": "C", "C": "A", "G": "U", "U": "G"}  # wobble üretmeyen ikame
windows = []
for k in range(0, 9):
    w = list(perfect_window)
    # pencerenin 5' ucundan k pozisyon boz (indeks hizalamada 3' uç)
    for p in range(k):
        w[p] = SUB[w[p]]
    windows.append("".join(w))

for w in windows:
    turner_mm = len(dg_of(w).mismatch_penalties)
    stage2_mm = _score_alignment(guide, w, seed_length=cfg["seed_length"]).mismatches
    if turner_mm != stage2_mm:
        problems.append(
            f"yönelim uyuşmuyor: Turner {turner_mm} vs stage2 {stage2_mm} mismatch"
        )

# --- 5  mismatch eklemek ΔG'yi daha negatif yapmamalı --------------------
dgs = [dg_of(w).delta_g for w in windows]
if dgs[0] >= 0:
    problems.append(f"0 mismatch ΔG negatif değil: {dgs[0]}")
for a, b in zip(dgs, dgs[1:]):
    if b < a - 1e-9:
        problems.append(f"mismatch eklemek ΔG'yi daha negatif yaptı: {a} -> {b}")

# --- 3 + 4  run() site başına ve bilinmiyor yönü -------------------------
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    sites = [
        {"site_id": f"G{i}:T:chr1:{i}", "target_window": w}
        for i, w in enumerate(windows[1:6], start=1)
    ]
    sites.append({"site_id": "NOWIN:T:chr1:99", "target_window": None})
    (tmp / "off.json").write_text(json.dumps({"offtarget_sites": sites}))

    dg_run(
        sarna_sequence=cfg["sarna_sequence"],
        offtargets_path=str(tmp / "off.json"),
        turner_dir=turner_dir,
        dg_strong=cfg["delta_g_strong"],
        dg_moderate=cfg["delta_g_moderate"],
        output_path=str(tmp / "dg.json"),
        log_path=str(tmp / "dg.log"),
    )
    res = json.loads((tmp / "dg.json").read_text())["deltag_results"]

values = [v["delta_g"] for k, v in res.items() if k != "NOWIN:T:chr1:99"]
if len(set(values)) < 2:
    problems.append(f"siteler arası varyans yok: {values} (eski hatanın imzası)")
if any(v is None for v in values):
    problems.append("penceresi olan bir site ΔG üretmedi")

missing = res.get("NOWIN:T:chr1:99")
if missing is None:
    problems.append("penceresiz site hiç raporlanmadı")
elif missing["delta_g"] is not None or missing["risk_score"] is not None:
    problems.append(
        f"penceresiz site sayı döndü: ΔG={missing['delta_g']} "
        f"risk={missing['risk_score']} — bağlanacak hedef yoksa bu bir ölçüm değil"
    )

for p in problems:
    print(f"  HATA: {p}")
sys.exit(1 if problems else 0)
INNER

echo "# 6  kırmızı-önce testleri"
"$PY" -m pytest \
    tests/unit/test_thermodynamics.py::TestDeltaGUsesTheRealTargetPerSite \
    tests/unit/test_seed_aligner.py::TestTargetWindowTravelsWithTheSite \
    -q -o addopts="" -p no:cacheprovider \
    || fail "C3'ün kırmızı-önce testleri yeşil değil"

echo
echo "GEÇTİ — ΔG off-target'ın kendi penceresine karşı, stage 2 ile aynı yönelimde,"
echo "        site başına değişiyor; pencere yoksa bilinmiyor dönüyor."
echo "        KAPSAM DIŞI: 'hiçbir site 1.0'a saplanmıyor' — aday kümesinin özelliği,"
echo "        ağ gerektirir; gerçek dağılım roadmap C3 satırında kayıtlı."
