#!/usr/bin/env bash
# Kabul kriteri — B18: "yedi ID'nin hepsi DepMap `Model.csv`'de adıyla
# eşleşiyor; eşleşmeyi doğrulayan test var".
#
# Altı ölçüm. 4 ve 5 ayırt edici olanlar.
#
#   1  YAML: her ID, DepMap'in `StrippedCellLineName`'i ile eşleşiyor
#   2  YAML: DepMap modeli olmayan hatlar `null` (başkasının ID'si değil)
#   3  OTORİTE PİNLİ: vendor'lanan `Model.csv`'nin sha256'sı manifest'le
#      birebir — digest'siz vendor'lanmış dosya kimsenin doğrulayamadığı dosya
#   4  DAVRANIŞ: okuyucu HeLa için GERÇEK HeLa satırını döndürüyor, ve bu
#      sayı CSV kolonundan **bağımsız olarak** okunarak karşılaştırılıyor —
#      sabitle değil. Yalnız YAML'a bakan bir kapı, okuyucu başka bir yerden
#      okusa bile geçerdi.
#   5  REGRESYON ÇAPASI: eski ID gerçekten BAŞKA bir satır — yoksa 4. ölçüm
#      boş olurdu. Artı sapmanın büyüklüğü yeniden ölçülüyor, çünkü yol
#      haritası satırı o sayıyı iddia ediyor.
#   6  birim testleri yeşil
#
# ⚠️ Bu kapı `results/` altındaki koşuların tazeliğini ölçMEZ. Etkilenen
# koşuların yeniden koşulması `B12`'ye taşındı (gerekçe o satırda): yeniden
# koşum bu düzeltmenin kanıtı değil, ayrı bir iş, ve `B17` inmeden koşulan bir
# yeniden koşum Ensembl sürümlerini yine karıştırır.

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

warn_untracked src tests config data/external || true

echo "# 1-5  eşleşme, pin, davranış ve regresyon çapası"
"$PY" - <<'INNER' || exit 1
import csv
import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")

import yaml

CONFIG = Path("config/ccle_depmap_ids.yaml")
MODELS = Path("data/external/depmap/Model_24Q2.csv")
MANIFEST = Path("data/external/manifest.json")
CCLE = Path("data/3_Topoloji_Epigenetik/CCLE/CCLE_Expression.csv")
NO_MODEL = {"HEK293T", "GM12878"}

problems: list[str] = []

if not MODELS.is_file():
    sys.exit(f"{MODELS} yok — otorite vendor'lanmamış, ölçüm yapılamaz")

config = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
with MODELS.open(encoding="utf-8", newline="") as handle:
    models = {row["ModelID"]: row for row in csv.DictReader(handle)}

# ---- 1  her ID adıyla eşleşiyor ----------------------------------------
checked = 0
for name, ach in config.items():
    if ach is None:
        continue
    checked += 1
    row = models.get(ach)
    if row is None:
        problems.append(f"{name}={ach} Model.csv'de hiç yok")
        continue
    stripped = (row.get("StrippedCellLineName") or "").upper()
    if stripped != name.upper():
        problems.append(
            f"{name}={ach} gerçekte {row.get('CellLineName')} "
            f"({row.get('OncotreePrimaryDisease')})"
        )
print(f"  1  {checked} ID'nin hepsi adıyla eşleşiyor")

# ---- 2  modeli olmayan hatlar null -------------------------------------
for name in sorted(NO_MODEL):
    if name not in config:
        problems.append(f"{name} config'de hiç yok")
    elif config[name] is not None:
        problems.append(f"{name} {config[name]!r} gösteriyor, null olmalı")
print(f"  2  DepMap modeli olmayan {len(NO_MODEL)} hat null")

# ---- 3  otorite pinli ---------------------------------------------------
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
entry = next(
    (a for a in manifest.get("artifacts", []) if a.get("name") == MODELS.name), None
)
if entry is None:
    problems.append(f"{MODELS.name} manifest'te kayıtlı değil")
else:
    digest = hashlib.sha256(MODELS.read_bytes()).hexdigest()
    if entry.get("sha256") != digest:
        problems.append("manifest digest'i dosyanın baytlarıyla uyuşmuyor")
    else:
        print(f"  3  otorite pinli: sha256 {digest[:16]}… ({entry['bytes']} bayt)")

# ---- 4 ve 5  davranış + regresyon çapası -------------------------------
if not CCLE.is_file():
    print("  4-5 ATLANDI — CCLE_Expression.csv yok (veri indirilmemiş)")
else:
    OLD = "ACH-001113"   # config'in eski HeLa'sı: LC-1/sq-SF
    NEW = config["HeLa"]
    rows: dict[str, list[str]] = {}
    with CCLE.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        mid = header.index("ModelID")
        gi = header.index("VEGFA (7422)")
        for row in reader:
            if row[mid] in (OLD, NEW):
                rows[row[mid]] = row
            if len(rows) == 2:
                break
    if len(rows) != 2:
        problems.append(f"iki satırdan biri CSV'de bulunamadı: {sorted(rows)}")
    else:
        independent_new = float(rows[NEW][gi])
        independent_old = float(rows[OLD][gi])

        # 5  iki satır gerçekten farklı mı? (4. ölçümü boş olmaktan kurtaran şey)
        if abs(independent_new - independent_old) < 0.01:
            problems.append(
                "eski ve yeni ID aynı VEGFA değerini veriyor — regresyon "
                "çapası yok, 4. ölçüm hiçbir şey ayırt etmiyor"
            )
        n_diff = sum(
            1
            for a, b in zip(rows[OLD][6:], rows[NEW][6:])
            if a and b and abs(float(a) - float(b)) > 2.0
        )
        print(
            f"  5  iki satır farklı: VEGFA {independent_old:.3f} (eski) vs "
            f"{independent_new:.3f} (yeni); 2 log2TPM'den fazla sapan gen: {n_diff}"
        )

        # 4  okuyucu gerçekten yeni satırı okuyor mu?
        from src.core.config import config_from_mapping
        from src.stage4_epigenetic.ccle_expression import CCLEReader

        with tempfile.TemporaryDirectory() as tmp:
            cache_db = Path(tmp) / "cache.db"
            cfg = config_from_mapping(
                {"target_gene": "VEGFA", "cell_line": "HeLa",
                 "data_paths": {"cache_db": str(cache_db), "ccle_csv": str(CCLE)}},
                cell_line="HeLa",
                data_paths={"cache_db": str(cache_db), "ccle_csv": str(CCLE)},
            )
            reader_obj = CCLEReader(cfg, csv_path=CCLE, depmap_ids_yaml=CONFIG)
            got = reader_obj.get_expression("VEGFA", "HeLa")
        if got.expression_value is None:
            problems.append("okuyucu HeLa için bilinmiyor döndürdü")
        elif abs(got.expression_value - independent_new) > 0.01:
            problems.append(
                f"okuyucu {got.expression_value} döndürdü, CSV kolonundan "
                f"bağımsız okunan değer {independent_new}"
            )
        else:
            print(
                f"  4  okuyucu gerçek HeLa satırını okuyor: "
                f"{got.expression_value:.4f} == bağımsız okuma"
            )

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo "# 6  birim testleri"
ORCSONAR_SUITE_RECEIPT="$(mktemp -u)" "$PY" -m pytest \
    tests/unit/test_depmap_ids.py tests/unit/test_ccle_expression.py \
    -q -o addopts="" -p no:cacheprovider \
    || fail "B18 birim testleri yeşil değil"

echo
echo "GEÇTİ — yedi ID'nin hepsi DepMap'in kendi Model.csv'sinde adıyla eşleşiyor,"
echo "        otorite sha256 ile pinli, ve okuyucu gerçekten o satırı okuyor."
echo "        NOT: etkilenen koşuların yeniden koşumu B12'de; bu kapı onu ölçmez."
