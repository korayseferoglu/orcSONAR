#!/usr/bin/env bash
# Kabul kriteri — B4: "işaret testi: korunmuş > polimorfik".
#
# Üç ölçüm:
#   1  bağımsız işaret kontrolü (pytest'ten geçmeden, doğrudan _normalize)
#   2  kanal monotonik ve ölü değil
#   3  birim testleri yeşil
#
# 1 kasıtlı olarak testlerden bağımsız: "testler geçiyor" diyen bir kapı,
# testler zayıflatıldığında da geçer. Burada sayı doğrudan hesaplanıp
# karşılaştırılıyor.
#
# ⚠️ Bu kapı kalibrasyon ölçmüyor, yalnız YÖN. Hiçbir eşik bir şeyin geçmesi
# için ayarlanmadı ve ayarlanmamalı (değişmez 7).

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

# -------------------------------------------- 1 + 2  bağımsız işaret kontrolü
echo "# 1  işaret: korunmuş > polimorfik   # 2  monotonluk"
"$PY" -I - <<'INNER' || fail "gnomAD kanalı yön/monotonluk kontrolünü geçmedi"
import sys
sys.path.insert(0, ".")
from src.stage3_variant_tox.variant_merger import _normalize

QUIET_COSMIC = {"density_score": 0.0, "has_tier1_gene": False}
QUIET_CLINVAR = {"pathogenic_count": 0, "likely_pathogenic_count": 0}
QUIET_PHYLOP = {"conservation_score": 0.0}


def score(value):
    return _normalize(QUIET_COSMIC, {"polymorphism_score": value}, QUIET_CLINVAR, QUIET_PHYLOP)


conserved, polymorphic = score(1.0), score(0.0)
print(f"  korunmuş={conserved}  polimorfik={polymorphic}")
if not conserved > polymorphic:
    sys.exit(f"HATA: korunmuş ({conserved}) polimorfikten ({polymorphic}) daha riskli değil")

ladder = [score(v) for v in (0.0, 0.25, 0.5, 0.75, 1.0)]
print(f"  merdiven={ladder}")
if ladder != sorted(ladder):
    sys.exit(f"HATA: kanal monotonik değil: {ladder}")
if ladder[0] == ladder[-1]:
    sys.exit("HATA: kanal hiç hareket etmiyor — 0.20 ağırlık bilgi taşımıyor")

missing = _normalize(QUIET_COSMIC, {}, QUIET_CLINVAR, QUIET_PHYLOP)
print(f"  eksik alan={missing}")
if missing < polymorphic:
    sys.exit(f"HATA: eksik gnomAD verisi ({missing}) polimorfik siteden ({polymorphic}) güvenli görünüyor")
INNER

# ------------------------------------------------------------- 3  birim testleri
echo "# 3  birim testleri"
"$PY" -m pytest tests/unit/test_variant_merger.py tests/unit/test_gnomad_client.py \
    -q -o addopts="" || fail "B4'ün testleri yeşil değil"

echo
echo "GEÇTİ — korunmuş > polimorfik, kanal monotonik, eksik veri güvenli görünmüyor"
