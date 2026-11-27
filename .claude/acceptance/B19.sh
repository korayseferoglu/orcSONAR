#!/usr/bin/env bash
# Kabul kriteri — B19: "DepMap ID'si olmayan hat için `expression_value`
# `None`; merger o kanalı dışlıyor; hiçbir yerde 0.0 yazılmıyor".
#
# Beş ölçüm. 3 ve 4 ayırt edici olanlar; 1 ve 2 onlar olmadan "yeşil" olabilen
# yüzey kontrolleri.
#
#   1  MODEL: `CCLEResult`'ın varsayılanı üç alanda da bilinmiyor
#   2  KAYNAK: bilinmiyor yollarında sabit 0.0 yazılmıyor
#   3  DAVRANIŞ: bilinmeyen bir hat için arama `None` dönüyor **ve
#      CACHE'LENMİYOR** — `_CCLE_TTL_HOURS` 8760, yani bir kez cache'lenen
#      bilinmiyor bir yıl yaşar; `B2` bu kuralı zaten kurmuştu
#   4  DAVRANIŞ: merger bilinmeyen kanalı ortalamadan **dışlıyor**, sıfır
#      sayarak aşağı çekmiyor — arıza yönünün tamamı bu
#   5  birim testleri yeşil
#
# ⚠️ 4 olmadan 1-3 bir şey söylemez: kaynakta `None` üretip tüketicide 0.0
# sayan bir boru hattı da ilk üçünü geçer. Bu projenin kaybettiği şeyler
# hep dikişte kayboldu (`H4`'ün porcelain hatası).

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

fail() { echo "GEÇMEDİ — $1"; exit 1; }

# shellcheck source=_lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

PY=""
for cand in "${PYTHON:-}" python3 python; do
    [ -n "$cand" ] || continue
    if "$cand" -c "import pytest, yaml, pydantic" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || fail "pytest+pyyaml+pydantic içeren yorumlayıcı bulunamadı; PYTHON=... ile ver"
echo "# yorumlayıcı: $PY"

warn_untracked src tests config || true

echo "# 1-4  model, kaynak ve iki davranış ölçümü"
"$PY" - <<'INNER' || exit 1
import json
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")

problems: list[str] = []

# ---- 1  model varsayılanı ------------------------------------------------
from src.core.models import CCLEResult  # noqa: E402

blank = CCLEResult(gene="X", cell_line="HeLa")
for field in ("expression_value", "is_expressed", "expression_percentile"):
    if getattr(blank, field) is not None:
        problems.append(f"CCLEResult.{field} varsayılanı {getattr(blank, field)!r}, None değil")
if not problems:
    print("  1  CCLEResult varsayılanı: üç alan da bilinmiyor")

# ---- 2  kaynakta sabit sıfır --------------------------------------------
for rel in ("src/stage4_epigenetic/ccle_reader.py",):
    text = Path(rel).read_text(encoding="utf-8")
    for bad in ('"expression_value": 0.0', '"expression_percentile": 0.0',
                '"is_expressed": False'):
        if bad in text:
            problems.append(f"{rel} hâlâ {bad} yazıyor")
src_expr = Path("src/stage4_epigenetic/ccle_expression.py").read_text(encoding="utf-8")
if re.search(r"expression_value\s*=\s*0\.0", src_expr):
    problems.append("ccle_expression.py bir yerde expression_value=0.0 atıyor")
print("  2  bilinmiyor yollarında sabit 0.0 yok")

# ---- 3  davranış: bilinmiyor dönüyor VE cache'lenmiyor -------------------
import yaml as _yaml  # noqa: E402

from src.core.config import config_from_mapping  # noqa: E402
from src.stage4_epigenetic.ccle_expression import CCLEReader  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    tmpd = Path(tmp)
    csv_path = tmpd / "mock.csv"
    csv_path.write_text(
        ",SequencingID,ModelConditionID,ModelID,IsDefaultEntryForMC,"
        "IsDefaultEntryForModel,VEGFA (7422)\n"
        "0,CDS-a,MC-1,ACH-MOCK01,Yes,Yes,6.5\n",
        encoding="utf-8",
    )
    ids = tmpd / "ids.yaml"
    ids.write_text(_yaml.dump({"MockLine": "ACH-MOCK01", "NoModelLine": None}),
                   encoding="utf-8")
    cache_db = tmpd / "cache.db"
    # `cell_line` on the config is validated against the supported set, so
    # the config says HeLa while the *lookups* use the mock names — which is
    # how `get_expression` is actually called: the name is an argument, not
    # config state.
    config = config_from_mapping(
        {"target_gene": "VEGFA", "cell_line": "HeLa",
         "data_paths": {"cache_db": str(cache_db), "ccle_csv": str(csv_path)}},
        cell_line="HeLa",
        data_paths={"cache_db": str(cache_db), "ccle_csv": str(csv_path)},
    )
    reader = CCLEReader(config, csv_path=csv_path, depmap_ids_yaml=ids)

    known = reader.get_expression("VEGFA", "MockLine")
    if known.expression_value is None:
        problems.append("ölçülmüş değer de None döndü — kontrol ölçümü bozuk")
    unknown = reader.get_expression("VEGFA", "NoModelLine")
    if unknown.expression_value is not None:
        problems.append(
            f"DepMap ID'si olmayan hat {unknown.expression_value!r} döndürdü, None değil"
        )
    if unknown.is_expressed is not None:
        problems.append(f"is_expressed {unknown.is_expressed!r}, None değil")

    keys = []
    if cache_db.exists():
        con = sqlite3.connect(f"file:{cache_db}?mode=ro", uri=True)
        keys = [k for (k,) in con.execute("select key from cache where key like 'ccle:%'")]
    if any("NoModelLine" in k for k in keys):
        problems.append("BİLİNMİYOR CACHE'LENDİ — TTL 8760 saat, bir yıl yaşar (B2)")
    if not any("MockLine" in k for k in keys):
        problems.append("ölçülmüş değer cache'lenmedi — cache tamamen kapanmış olabilir")
    print(f"  3  bilinmiyor None ve cache'lenmedi (cache'te {len(keys)} ccle anahtarı)")

# ---- 4  davranış: merger bilinmeyeni DIŞLIYOR ---------------------------
from src.stage4_epigenetic.epigenetic_merger import (  # noqa: E402
    _as_optional,
    _mean_of_known,
)

if _as_optional(None) is not None:
    problems.append("_as_optional(None) None dönmüyor")
if _as_optional(0.0) != 0.0:
    problems.append("_as_optional ölçülmüş 0.0'ı kaybediyor — sıfır bir ölçümdür")
# Üç site: ikisi ölçülmüş (8.0, 6.0), biri bilinmiyor.
mean = _mean_of_known([8.0, None, 6.0])
if mean != 7.0:
    problems.append(f"_mean_of_known bilinmeyeni dışlamıyor: {mean} (beklenen 7.0)")
if _mean_of_known([None, None]) is not None:
    problems.append("hiç ölçüm yokken ortalama bir sayı döndü")
# Sıfır sayılsaydı 4.666… olurdu; aradaki fark arıza yönünün kendisi.
if mean == (8.0 + 0.0 + 6.0) / 3:
    problems.append("bilinmeyen sıfır sayılıyor")
print(f"  4  merger bilinmeyeni dışlıyor: ortalama {mean} (sıfır sayılsa 4.667)")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo "# 5  birim testleri"
ORCSONAR_SUITE_RECEIPT="$(mktemp -u)" "$PY" -m pytest \
    tests/unit/test_ccle_expression.py tests/unit/test_models.py \
    tests/unit/test_epigenetic_merger.py \
    -q -o addopts="" -p no:cacheprovider \
    || fail "B19 birim testleri yeşil değil"

echo
echo "GEÇTİ — CCLE'nin bilinmiyor yolu artık sayı değil bilinmiyor dönüyor,"
echo "        cache'lenmiyor, ve merger o kanalı ortalamadan dışlıyor."
echo "        NOT: bu madde ID'lerin DOĞRU olduğunu ölçmez — o B18."
