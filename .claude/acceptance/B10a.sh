#!/usr/bin/env bash
# Kabul kriteri — B10a: "iki hata kapandı, regresyon testi var".
#
# Altı ölçüm. 2, 3 ve 4 ayırt edici olanlar; 5 kontrol.
#
#   1  KOD: `shape_profile.py`'da artık hiçbir `type: ignore` yok ve daralma
#      satır-içi — bir bool değişkende değil. Daralmayı bool'a toplamak tip
#      denetleyicisinin göremediği şeydi, ve üstüne konan iki
#      `ignore[arg-type]` gerçek hatayı (`type-var`) hiç kapsamıyordu: hiçbir
#      şeyi bastırmayan bir bastırma, değişmez 3'ün sınıfı
#   2  DAVRANIŞ, ayırt edici: `strand: null` gelen bir Ensembl cevabı artık
#      sessizce `"-"` ÜRETMİYOR. `None != 1` olduğu için eski ifade bilinmeyen
#      bir yönü kesin ve YANLIŞ bir yöne çeviriyordu — kural 10'un sınıfı
#   3  DAVRANIŞ, ayırt edici: `start: null` gelen bir gen düşürülüyorsa bunu
#      WARNING seviyesinde SÖYLÜYOR. Eskiden `debug`'du, yani gen arama
#      uzayından iz bırakmadan çıkıyordu — ve küçülen arka plan *daha az
#      off-target* olarak okunur, yani arıza SAFE yönüne (değişmez 2)
#   4  TİP: `mypy` bu iki modülde sıfır hata veriyor
#   5  KONTROL, ayırt edici: `_first_int` sıradan girdide DEĞİŞMİYOR — geçerli
#      bir koordinat ve `strand: 1` aynen geçiyor. Bu olmadan 2. ve 3. ölçüm
#      "her şeyi düşür" ile de geçerdi
#   6  mypy toplamı `B10a` öncesindeki 82'den DÜŞÜK — iki hatayı kapatırken
#      yenisini açmadığının ölçümü (kalanlar `B10`'un işi, bu kapı onları
#      istemiyor)
#
# ⚠️ Ağ istemiyor: Ensembl cevapları `responses` ile mock'lanıyor.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

fail() { echo "GEÇMEDİ — $1"; exit 1; }

# shellcheck source=_lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

PY=""
for cand in "${PYTHON:-}" python3 python; do
    [ -n "$cand" ] || continue
    if "$cand" -c "import pytest, responses" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || fail "pytest + responses içeren yorumlayıcı bulunamadı; PYTHON=... ile ver"
echo "# yorumlayıcı: $PY"

warn_untracked src tests .claude || true

SP="src/stage5_biophysics/shape_profile.py"
TF="src/stage2_offtarget_scan/transcriptome_fetcher.py"

# ---- 1  KOD ------------------------------------------------------------
# ⚠️ 1. ölçüm KODA bakıyor, düzyazıya değil. İlk hali `grep -q "type: ignore"`
# ve `grep -q "use_icshape"` idi; ikisi de kapının KENDİ açıklama yorumunu
# yakaladı — `H24`'ün rastgelelik dedektöründe kapattığı yanlış-pozitif
# sınıfının aynısı, ve iki kez üst üste. Yorumu kapıya uydurmak tersine
# çevrilmiş bağımlılık olurdu (kayıt dedektörün körlüğüne göre yazılır), o
# yüzden kapı düzeltildi: dosyanın yorumları ve docstring'leri `tokenize` ile
# atılıyor, kontroller kalan kod üzerinde çalışıyor.
code_only() {
    "$PY" - "$1" <<'SNIP'
import io
import sys
import tokenize
from pathlib import Path

source = Path(sys.argv[1]).read_text(encoding="utf-8")
kept = []
for tok in tokenize.generate_tokens(io.StringIO(source).readline):
    if tok.type in (tokenize.COMMENT, tokenize.STRING):
        continue
    kept.append(tok.string)
print(" ".join(kept))
SNIP
}

SP_CODE=$(code_only "$SP") || fail "$SP tokenize edilemedi"
if printf '%s' "$SP_CODE" | grep -q "type: ignore"; then
    fail "$SP hâlâ kod üzerinde bir bastırma taşıyor — B10a'nın kapattığı şey
        tam bu: gerçek hatayı kapsamayan, yalnız denetleyiciyi susturan bir yorum"
fi
if printf '%s' "$SP_CODE" | grep -q "use_icshape"; then
    fail "$SP daralmayı hâlâ \`use_icshape\` bool'unda topluyor; bir tip
        denetleyicisi bool değişken üzerinden daraltamaz"
fi
echo "  1  kod: \`type: ignore\` yok, daralma satır-içi"

if ! grep -q "_first_int" "$TF"; then
    fail "$TF \`_first_int\` kullanmıyor — \`a.get(k, b.get(k, d))\` idiomu
        anahtar VARSA ve null ise d'ye hiç düşmez"
fi
echo "  1b kod: null-atlayan \`_first_int\` yerinde"

# ---- 2, 3, 5  DAVRANIŞ -------------------------------------------------
"$PY" - <<'INNER' || exit 1
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, ".")

import responses as resp_mock
from loguru import logger

from src.core.config import config_from_mapping
from src.stage2_offtarget_scan.transcriptome_fetcher import (
    _batch_lookup_symbols,
    _first_int,
)

import yaml

problems: list[str] = []
raw = yaml.safe_load(Path("config/config.yaml").read_text(encoding="utf-8"))
raw["data_paths"]["cache_db"] = "/tmp/orcsonar-b10a-gate.db"
CONFIG = config_from_mapping(raw)
URL = f"{CONFIG.ensembl_base_url}/lookup/symbol/homo_sapiens"


def gene(symbol: str, *, start, end, strand):
    return {symbol: {
        "id": "ENSG00000000000", "seq_region_name": "7",
        "start": start, "end": end, "strand": strand,
        "Transcript": [{"id": "ENST00000000000", "is_canonical": 1,
                        "start": start, "end": end, "strand": strand}],
    }}


def lookup(payload, symbol):
    """One mocked lookup; returns (result, warnings)."""
    collected: list[str] = []
    sink = logger.add(collected.append, level="WARNING")
    try:
        with resp_mock.RequestsMock() as mock:
            mock.add(resp_mock.POST, URL, json=payload, status=200)
            return _batch_lookup_symbols([symbol], CONFIG), collected
    finally:
        logger.remove(sink)


# ---- 2  null strand ---------------------------------------------------
result, _ = lookup(gene("TP53", start=7668402, end=7687550, strand=None), "TP53")
if "TP53" in result and result["TP53"].strand == "-":
    problems.append(
        "null strand hâlâ sessizce '-' oluyor — bilinmeyen bir yön kesin ve "
        "yanlış bir yöne çevrildi (kural 10)"
    )
else:
    got = result["TP53"].strand if "TP53" in result else "gen düşürüldü"
    print(f"  2  null strand '-' ÜRETMİYOR (sonuç: {got})")

# ---- 3  null koordinat sessiz değil -----------------------------------
result, warnings = lookup(gene("ACTB", start=None, end=5530601, strand=1), "ACTB")
if "ACTB" not in result and not any("ACTB" in w for w in warnings):
    problems.append(
        "null koordinatlı gen WARNING'siz düşürüldü — arama uzayından iz "
        "bırakmadan çıkıyor ve küçülen arka plan daha az off-target olarak "
        "okunur (değişmez 2)"
    )
else:
    how = "korundu" if "ACTB" in result else "WARNING ile düşürüldü"
    print(f"  3  null koordinat sessiz DEĞİL ({how})")

# ---- 5  KONTROL: sıradan girdi değişmiyor -----------------------------
result, warnings = lookup(gene("ACTB", start=5527148, end=5530601, strand=1), "ACTB")
if "ACTB" not in result:
    problems.append(
        "KONTROL BAŞARISIZ: geçerli koordinatlı gen de düşürülüyor — 2. ve 3. "
        "ölçüm 'her şeyi düşür' ile de geçerdi"
    )
elif result["ACTB"].strand != "+" or result["ACTB"].start != 5527148:
    problems.append(
        f"KONTROL BAŞARISIZ: geçerli girdi bozuldu "
        f"(strand={result['ACTB'].strand}, start={result['ACTB'].start})"
    )
elif warnings:
    problems.append(f"KONTROL BAŞARISIZ: sıradan girdi uyarı üretti: {warnings}")
else:
    print("  5  kontrol: geçerli koordinat ve strand aynen geçiyor, uyarı yok")

# `_first_int`'in kendisi: bool bir int'tir, ama koordinat değildir
checks = {
    "null atlanıyor": _first_int(None, 5, default=0) == 5,
    "ilk geçerli kazanıyor": _first_int(7, 5, default=0) == 7,
    "hiçbiri yoksa default": _first_int(None, None, default=None) is None,
    "bool reddediliyor": _first_int(True, 5, default=0) == 5,
}
bad = [name for name, ok in checks.items() if not ok]
if bad:
    problems.append(f"_first_int yanlış: {bad}")
else:
    print(f"  5b `_first_int` dört vakada doğru (bool dahil)")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

# ---- 4, 6  TİP ---------------------------------------------------------
SP_ERRORS=$("$PY" -m mypy "$SP" 2>&1 | grep -c "^$SP.*error:" || true)
TF_ERRORS=$("$PY" -m mypy "$TF" 2>&1 | grep -c "^$TF.*error:" || true)
if [ "$SP_ERRORS" -ne 0 ]; then
    "$PY" -m mypy "$SP" 2>&1 | grep "^$SP.*error:" | head -5
    fail "$SP hâlâ $SP_ERRORS mypy hatası veriyor"
fi
echo "  4  mypy: $SP sıfır hata"

# ---- 4b  TİP, hedefli -------------------------------------------------
# ⚠️ Bu ölçüm kapının kendi kırmızı-önce denemesinde EKLENDİ. `if start is None`
# kontrolünü `if False:` yapmak kapıyı GEÇİYORDU: gen yine düşüyor ama artık
# gürültülü düştüğü için 3. ölçüm (haklı olarak) memnun kalıyordu, ve tip
# sızıntısı 4. ölçümün kapsamadığı dosyada geri geliyordu. Ölçülerek bulundu:
# kontrol kaldırılınca bu dosyada tam İKİ hata geri geliyor —
# `Argument "start"/"end" to "TranscriptInfo" … "int | None"`. Desen `None`'a
# özgü, çünkü 379'daki `strand: str vs Literal` hatası iki durumda da var ve o
# `B10`'un işi, B10a'nın değil.
NONE_LEAKS=$("$PY" -m mypy "$TF" 2>&1 \
    | grep -E "^$TF.*Argument .* to \"TranscriptInfo\" has incompatible type \".*None\"" \
    || true)
if [ -n "$NONE_LEAKS" ]; then
    echo "$NONE_LEAKS"
    fail "null bir koordinat hâlâ \`TranscriptInfo\`'ya ulaşabiliyor — B10a'nın
        kapattığı sızıntının kendisi"
fi
echo "  4b mypy: null bir koordinat \`TranscriptInfo\`'ya ulaşamıyor"

# ⚠️ `transcriptome_fetcher`'ın kalan hataları `B20` ve `B10`'un işi; bu kapı
# yalnız B10a'nın iki hatasının kapandığını ve toplamın ARTMADIĞINI ölçüyor.
TOTAL=$("$PY" -m mypy src/ 2>&1 | grep -oE "Found [0-9]+ error" | grep -oE "[0-9]+" || echo 999)
if [ "$TOTAL" -ge 82 ]; then
    fail "mypy toplamı $TOTAL — B10a öncesi 82'den düşük olmalı; iki hatayı
        kapatırken yenisi açılmış"
fi
echo "  6  mypy toplamı $TOTAL (B10a öncesi 82) — yeni hata açılmamış"

echo
echo "# regresyon testleri"
ORCSONAR_SUITE_RECEIPT="$(mktemp -u)" "$PY" -m pytest \
    tests/unit/test_transcriptome_fetcher.py tests/unit/test_shape_profile.py \
    -q -o addopts="" -p no:cacheprovider || fail "B10a regresyon testleri yeşil değil"

echo
echo "GEÇTİ — iki mypy hatası kapandı ve ikisi de GERÇEKTİ: \`strand: null\`"
echo "        sessizce '-' üretiyordu (bilinmeyen bir yön kesin ve yanlış bir"
echo "        yöne dönüyordu) ve \`start: null\` geni debug seviyesinde"
echo "        düşürüyordu (küçülen arka plan daha az off-target olarak okunur)."
echo "        Kontrol ölçümü geçerli girdinin aynen geçtiğini gösteriyor."
