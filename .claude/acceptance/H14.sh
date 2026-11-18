#!/usr/bin/env bash
# Kabul kriteri — H14: "`ruff check tests` mekanik kuralların hepsinde temiz;
# kapsam henüz genişletilmedi".
#
# Dört ölçüm:
#   1  mekanik kurallar (`F401`, `I001`, `UP041`) `tests/` içinde temiz
#   2  yargı gerektiren 18 bulgu HÂLÂ ORADA — H14, H15'in alanına girmedi
#   3  `_status.RUFF_SCOPE` genişletilmedi (kriter bunu açıkça istiyor)
#   4  tam takım yeşil — "davranış-nötr" iddiasının tek kanıtı bu
#
# 2 numarası ters yönde bir kontrol ve kasıtlı: bu maddenin bütün tasarımı
# mekanik temizliği yargı gerektiren bulgulardan AYRI tutmak. Eğer `--fix`
# ya da bir elle düzeltme 7 `B017`'den birini de kapatmış olsaydı, gerçek bir
# bulgu kosmetik bir commit'in içinde kaybolmuş olurdu — `H9`'un kapatmaya
# çalıştığı gizlenme tipi. Kapı o yüzden "hepsi temiz" değil, "yalnız mekanik
# olanlar temiz" diyor.

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

# ------------------------------- 2  yargı bulguları hâlâ orada (ters kontrol)
echo "# 2  yargı gerektiren bulgular hâlâ açık (H15'in işi)"
"$PY" -I - <<'INNER' || fail "yargı bulguları beklenmedik durumda"
import json
import subprocess
import sys

JUDGEMENT = {"B017", "F841", "B007", "E741", "E402", "SIM117"}
proc = subprocess.run(
    [sys.executable, "-m", "ruff", "check", "tests", "--output-format", "json"],
    capture_output=True, text=True,
)
try:
    found = json.loads(proc.stdout or "[]")
except json.JSONDecodeError:
    sys.exit(f"HATA: ruff çıktısı okunamadı: {proc.stdout[:200]} {proc.stderr[:200]}")

codes: dict[str, int] = {}
for item in found:
    code = item.get("code") or "?"
    codes[code] = codes.get(code, 0) + 1
print("  kalan:", ", ".join(f"{c}={n}" for c, n in sorted(codes.items())) or "hiç")

leaked = sorted(c for c in codes if c not in JUDGEMENT)
if leaked:
    sys.exit(f"HATA: mekanik olması gereken kurallar hâlâ açık: {leaked}")
if "B017" not in codes:
    sys.exit(
        "HATA: 7 kör `pytest.raises(Exception)` bulgusu kaybolmuş. H14 onları "
        "düzeltmemeliydi — `H15` onları tek tek inceleyecek, ve bir bulgunun "
        "kosmetik bir commit içinde sessizce kapanması bu maddenin önlemek "
        "için ayrıldığı şeydir."
    )
INNER

# --------------------------------------------- 3  kapsam genişletilmedi mi
echo "# 3  RUFF_SCOPE genişletilmedi"
"$PY" -I -c "
import sys
sys.path.insert(0, '.claude/hooks')
import _status
expected = ('src', '.claude/hooks', 'tests/hooks')
if tuple(_status.RUFF_SCOPE) != expected:
    sys.exit(f'HATA: kapsam değişmiş: {_status.RUFF_SCOPE} (beklenen {expected}) — '
             'genişletme H15 bittikten sonra, workflow ve testiyle birlikte yapılır')
print('  ', ' '.join(_status.RUFF_SCOPE))
" || fail "RUFF_SCOPE beklenen üçlü değil"

# ------------------------------------------------------ 4  davranış-nötrlük
echo "# 4  tam takım (davranış-nötrlük kanıtı)"
"$PY" -m pytest -q -o addopts="" -p no:cacheprovider \
    || fail "tam takım yeşil değil — import silmek bir şeyi bozmuş"

echo
echo "GEÇTİ — mekanik borç temiz, 18 yargı bulgusu H15 için duruyor, kapsam aynı"
