#!/usr/bin/env bash
# Kabul kriteri — H23: "bir `.py`'yi bozup geri yükleyen bir kapı, geri
# yüklemeden sonra diskteki kodu yüklediği GÖSTERİLİYOR; ve tarama testi
# `.py` bozan her kapıyı kapsıyor".
#
# Altı ölçüm. 2, 3 ve 5 ayırt edici olanlar.
#
#   1  TARAMA: hiçbir kapı kendi perturb yardımcısını tutmuyor, ve iki
#      kapı (`A13`, `H21`) gerçekten `_perturb`'e devredilmiş
#   2  DAVRANIŞ, ayırt edici: TUZAK GERÇEK — aynı saniyede, aynı boyutta
#      yeniden yazılan bir `.py` bayat bytecode'dan okunuyor. Bu ölçüm
#      düşerse `_perturb`'ün var olma sebebi yok demektir
#   3  DAVRANIŞ, ayırt edici: `_perturb` tuzağı İKİ YÖNDE de yeniyor —
#      bozma görünüyor (yanlış-YEŞİL yönü) ve geri yükleme görünüyor
#      (yanlış-kırmızı yönü, `A10b`'nin canlı yaşadığı)
#   4  KONTROL: `invalidate_bytecode` gerçekten bir dosya siliyor. Bu
#      olmadan 3. ölçüm başka bir sebeple de geçebilirdi
#   5  AYNA, ayırt edici (`H21`'in dersi): `_perturb`'ün geçersiz kılma
#      çağrısı KALDIRILINCA testler kırmızıya düşüyor — yani testler API'nin
#      varlığını değil geçersiz kılmanın KENDİSİNİ ölçüyor
#   6  birim testleri yeşil
#
# ⚠️ 5. ölçüm bir `.py`'yi bozuyor — yani tam bu maddenin konusu olan tuzağa
# maruz. O yüzden geri yükleme `_perturb`'e DEĞİL, elle silmeye dayanıyor:
# ölçtüğü şeyin bozulmuş haline güvenmek ölçümü dairesel yapardı.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

fail() { echo "GEÇMEDİ — $1"; exit 1; }

# shellcheck source=_lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

PY=""
for cand in "${PYTHON:-}" python3 python; do
    [ -n "$cand" ] || continue
    if "$cand" -c "import pytest" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || fail "pytest içeren yorumlayıcı bulunamadı; PYTHON=... ile ver"
echo "# yorumlayıcı: $PY"

warn_untracked .claude tests || true

TESTS="tests/hooks/test_perturb.py"
[ -f ".claude/hooks/_perturb.py" ] || fail "_perturb.py yok"

echo "# 1  tarama: hiçbir kapı kendi yardımcısını tutmuyor"
ORCSONAR_SUITE_RECEIPT="$(mktemp -u)" "$PY" -m pytest \
    "$TESTS::TestEveryPerturbingGateUsesTheSharedHelper" \
    -q -o addopts="" -p no:cacheprovider >/dev/null \
    || fail "tarama testi kırmızı — bir kapı kendi perturb yardımcısını tutuyor"
for gate in A13 H21; do
    grep -q "_perturb" ".claude/acceptance/$gate.sh" \
        || fail "$gate.sh `_perturb`'e devredilmemiş"
done
echo "  geçti (A13 ve H21 devredilmiş)"

echo "# 2-4  tuzağın gerçekliği, iki yönde yenilmesi, ve kontrol"
"$PY" - <<'INNER' || exit 1
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".claude/hooks")
import _perturb  # noqa: E402

problems: list[str] = []


def value_in(directory: Path) -> str:
    done = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, '.'); import demo; print(demo.VALUE)"],
        cwd=directory, capture_output=True, text=True, timeout=60, check=False,
    )
    return done.stdout.strip()


with tempfile.TemporaryDirectory() as tmp:
    work = Path(tmp)
    module = work / "demo.py"

    # ---- 2  TUZAK GERÇEK Mİ ------------------------------------------
    module.write_bytes(b"VALUE = 0.5\n")
    pinned = module.stat().st_mtime
    if value_in(work) != "0.5":
        problems.append("temiz import 0.5 vermedi — ölçüm kurulamadı")
    module.write_bytes(b"VALUE = 0.6\n")          # aynı boyut
    os.utime(module, (pinned, pinned))            # aynı saniye
    stale = value_in(work)
    if stale != "0.5":
        problems.append(
            f"aynı saniye/aynı boyut yeniden yazma görünür oldu ({stale}) — "
            "CPython'un kuralı değişmiş olabilir, `_perturb`'ün gerekçesi "
            "yeniden ölçülmeli"
        )
    else:
        print("  2  tuzak gerçek: diskte 0.6, import 0.5 (bayat bytecode)")

    # ---- 4  KONTROL: geçersiz kılma gerçekten siliyor ----------------
    removed = _perturb.invalidate_bytecode(module)
    if not removed:
        problems.append(
            "invalidate_bytecode hiçbir dosya silmedi — 3. ölçüm başka bir "
            "sebeple geçebilirdi"
        )
    else:
        print(f"  4  kontrol: invalidate_bytecode {len(removed)} önbellek "
              f"dosyası sildi ({removed[0].name})")

with tempfile.TemporaryDirectory() as tmp:
    work = Path(tmp)
    module = work / "demo.py"
    module.write_bytes(b"VALUE = 0.5\n")
    pinned = module.stat().st_mtime
    value_in(work)                                 # pyc yazılsın

    # ---- 3a  BOZMA görünüyor mu (yanlış-YEŞİL yönü) ------------------
    with _perturb.perturbed(module, "0.5", "0.6"):
        os.utime(module, (pinned, pinned))         # düşman koşulu geri kur
        seen = value_in(work)
        if seen != "0.6":
            problems.append(
                f"bozma maskelendi (import {seen}) — bir kapı burada "
                "'mekanizma doğrulandı' der ama hiçbir şey doğrulamamıştır"
            )
        else:
            print("  3a bozma görünüyor (yanlış-yeşil yönü kapalı)")
    # ---- 3b  GERİ YÜKLEME görünüyor mu ------------------------------
    os.utime(module, (pinned, pinned))
    back = value_in(work)
    if back != "0.5":
        problems.append(
            f"geri yükleme maskelendi (import {back}) — `A10b`'nin canlı "
            "yaşadığı yanlış-kırmızı"
        )
    else:
        print("  3b geri yükleme görünüyor (yanlış-kırmızı yönü kapalı)")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo "# 5  ayna: geçersiz kılma çağrısı kaldırılınca testler kırmızı"
HELPER=".claude/hooks/_perturb.py"
BEFORE="$(mktemp)"
cp "$HELPER" "$BEFORE"
# ⚠️ Geri yükleme ELLE yapılıyor (bkz. başlıktaki uyarı): ölçülen şeyin
# bozulmuş hali kendi geri yüklemesini maskeleyebilirdi.
restore_helper() {
    cp "$BEFORE" "$HELPER"
    rm -rf .claude/hooks/__pycache__
    cmp -s "$BEFORE" "$HELPER" || fail "ayna ölçümü $HELPER'ı geri yükleyemedi"
}
trap 'restore_helper; rm -f "$BEFORE"' EXIT

"$PY" - "$HELPER" <<'INNER' || { echo "GEÇMEDİ — ayna bozulamadı"; exit 1; }
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
anchor = "    target.write_bytes(data)\n    invalidate_bytecode(target)"
if text.count(anchor) != 1:
    sys.exit("beklenen çapa bulunamadı — kapı güncellenmeli")
path.write_text(text.replace(anchor, "    target.write_bytes(data)", 1),
                encoding="utf-8")
INNER
rm -rf .claude/hooks/__pycache__
if ORCSONAR_SUITE_RECEIPT="$(mktemp -u)" "$PY" -m pytest "$TESTS" \
        -q -o addopts="" -p no:cacheprovider >/dev/null 2>&1; then
    restore_helper
    fail "geçersiz kılma çağrısı KALDIRILDI ve testler yine geçti — testler
        API'nin varlığını ölçüyor, geçersiz kılmanın kendisini değil"
fi
echo "  geçersiz kılma kaldırılınca testler kırmızı (ölçüm gerçek)"
restore_helper

echo "# 6  birim testleri"
ORCSONAR_SUITE_RECEIPT="$(mktemp -u)" "$PY" -m pytest "$TESTS" \
    -q -o addopts="" -p no:cacheprovider || fail "H23 birim testleri yeşil değil"

echo
echo "GEÇTİ — tek bir perturb/geri yükleme yardımcısı var, iki kapı ona"
echo "        devredilmiş, ve tuzak İKİ YÖNDE de kapalı: bozma da geri"
echo "        yükleme de görünür oluyor. Tuzağın gerçekliği her koşuda"
echo "        yeniden üretiliyor, ve geçersiz kılma çağrısı kaldırılınca"
echo "        testler kırmızıya düşüyor — yani ölçüm beyanı değil davranışı"
echo "        okuyor."
