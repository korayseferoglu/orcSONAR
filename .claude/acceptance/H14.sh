#!/usr/bin/env bash
# Kabul kriteri — H14: "`ruff check tests` mekanik kuralların hepsinde temiz".
#
# ⚠️ EMEKLİYE AYRILAN İKİ KONTROL (2026-11-19 denetimi, Bulgu 4).
# Bu kapı iki **ters yönlü** kontrol içeriyordu:
#   (eski 2) 7 `B017` kör istisna iddiası HÂLÂ AÇIK olmalı
#   (eski 3) `_status.RUFF_SCOPE` genişletilmemiş olmalı
# İkisi de o an için doğruydu: `H14` mekanik borcu temizlerken `H15`'in
# yargı gerektiren bulgularına girmemeliydi. Ama `H15` tam da onları
# kapatmak için vardı ve `H14` satırı bunu zaten öngörüyordu — yani kapı
# `H15` kapandığında emekliye ayrılmalıydı, ayrılmadı ve o günden beri
# `DONE` bir maddenin kapısı "GEÇMEDİ" diyordu.
#
# Bir kabul kapısı bir ANI değil bir ÖZELLİĞİ ölçmeli. Kalıcı kırmızı bir
# kapı, kırmızı kapıyı normalleştirir ve `.claude/acceptance/README.md`'nin
# "çıkış ≠ 0 = geçmedi, başka anlam yok" kuralını işlevsiz bırakır.
#
# Kalan iki ölçüm, `H14`'ün özelliğini ölçenler:
#   1  mekanik kurallar (`F401`, `I001`, `UP041`) `tests/` içinde temiz
#   2  tam takım yeşil — "davranış-nötr" iddiasının tek kanıtı bu

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

# ------------------------------------------------- 1  mekanik kurallar temiz
echo "# 1  mekanik kurallar (F401, I001, UP041)"
"$PY" -m ruff check tests --select F401,I001,UP041 \
    || fail "tests/ içinde mekanik ruff bulgusu kaldı"

# ------------------------------------------------------ 2  davranış-nötrlük
echo "# 2  tam takım (davranış-nötrlük kanıtı)"
"$PY" -m pytest -q -o addopts="" -p no:cacheprovider \
    || fail "tam takım yeşil değil — import silmek bir şeyi bozmuş"

echo
echo "GEÇTİ — mekanik borç temiz (iki ters kontrol H15 kapanınca emekliye ayrıldı)"
