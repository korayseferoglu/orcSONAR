#!/usr/bin/env bash
# Kabul kriteri — B1: ">0 patojenik varyant; regresyon testi".
#
# Üç ölçüm:
#   1  regresyon testi: boolean ayırıcı tele literal artı olarak gitmiyor
#      (ve sunucunun şikâyeti boş sonuç sanılmıyor) — ağ gerektirmez
#   2  CANLI: yoğun bir pencerede >0 UID, gen-arası pencerede 0 UID ve istisna
#      yok — kriterin ">0 patojenik" kısmı ancak böyle ölçülür
#   3  birim testleri yeşil
#
# ⚠️ **Bu kapı ağ gerektirir.** Ağ yoksa GEÇMEZ, atlamaz: kriter canlı bir
# iddia ve "ölçemedim" geçti demek değildir (.claude/acceptance/README.md).
#
# ⚠️ NCBI E-utilities nazik kullanım ister; bu kapı üç istek atar ve aralarına
# bekleme koyar. Kişisel e-posta GÖNDERİLMEZ.

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

# ------------------------------------------------ 1  regresyon (ağsız)
echo "# 1  terim biçimi regresyonu"
"$PY" -m pytest tests/unit/test_clinvar_client.py -q -o addopts="" -p no:cacheprovider \
    -k "literal_plus or query_complaint or empty_window or errorlist" \
    || fail "terim biçimi / şikâyet kontrolü testleri geçmiyor"

# --------------------------------------------------------- 2  canlı ölçüm
echo "# 2  canlı E-utilities ölçümü"
"$PY" -I - <<'INNER' || fail "canlı ClinVar ölçümü geçmedi"
import sys
import time

sys.path.insert(0, ".")
from loguru import logger  # noqa: E402

from src.core.models import GenomicRegion  # noqa: E402
from src.stage3_variant_tox.clinvar_client import _esearch  # noqa: E402

logger.remove()
BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
problems = []

# TP53 — bu pencerede patojenik varyant bulunmaması ClinVar'ın çöktüğü anlamına
# gelir, eşik ayarı değil: ham count 972, istemci _RETMAX=100 ile tavanlıyor.
dense = GenomicRegion(chrom="chr17", start=7668000, end=7688000, strand="-")
quiet = GenomicRegion(chrom="chr2", start=20000000, end=20000500, strand="+")

try:
    hits = _esearch(dense, BASE)
except Exception as exc:  # noqa: BLE001
    sys.exit(f"HATA: canlı sorgu başarısız ({type(exc).__name__}: {exc}) — ağ yok ya da API değişti")
print(f"  TP53 chr17:7668000-7688000 → {len(hits)} UID")
if len(hits) == 0:
    problems.append("yoğun pencerede 0 patojenik UID — kanal yine ölü")

time.sleep(1)
try:
    empty = _esearch(quiet, BASE)
except Exception as exc:  # noqa: BLE001
    problems.append(f"gen-arası pencere istisna attı: {type(exc).__name__}: {exc}")
    empty = None
if empty is not None:
    print(f"  gen-arası chr2:20000000-20000500 → {len(empty)} UID")
    if len(empty) != 0:
        problems.append("boş beklenen pencerede UID döndü — terim fazla geniş olabilir")

for problem in problems:
    print(f"  HATA: {problem}")
sys.exit(1 if problems else 0)
INNER

# --------------------------------------------------------- 3  birim testleri
echo "# 3  birim testleri"
"$PY" -m pytest tests/unit/test_clinvar_client.py -q -o addopts="" -p no:cacheprovider \
    || fail "ClinVar birim testleri yeşil değil"

echo
echo "GEÇTİ — canlı sorgu patojenik varyant buluyor, bozuk terim artık sessiz kalmıyor"
