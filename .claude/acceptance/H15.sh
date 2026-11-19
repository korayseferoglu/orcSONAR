#!/usr/bin/env bash
# Kabul kriteri — H15: "7 `B017`'nin hepsi tipli ve her biri daraltıldıktan
# sonra da geçiyor".
#
# Dört ölçüm:
#   1  `tests/` içinde hiç kör istisna iddiası yok (ruff B017 + ham grep)
#   2  daraltılan iddialar GERÇEKTEN daraltılmış: her `pytest.raises` bir tip
#      alıyor ve `Exception`/`BaseException` değil
#   3  `tests/` tamamen ruff-temiz — kalan 11 yargı bulgusu da kapandı, yani
#      kapsam genişletmesi güvenli
#   4  tam takım yeşil: daraltma hiçbir testi kırmadı
#
# 2 numarası ruff'ın üstüne bir kat: `B017` yalnız `Exception` ve
# `BaseException`'ı bilir. Buradaki ham tarama, ileride birinin
# `pytest.raises()` yazıp tipi başka bir yoldan gevşetmesini de yakalar.
#
# ⚠️ Bu kapı "daraltınca da geçiyor" iddiasını 4. adımla ölçüyor. Daraltılmış
# bir iddianın kırmızıya düşmesi bir bulgudur: o test, iddia ettiği şeyi değil
# başka bir arızayı doğruluyormuş demektir.

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

# ------------------------------------------------------- 1  kör iddia yok
echo "# 1  kör istisna iddiası yok"
"$PY" -m ruff check tests --select B017 >/dev/null 2>&1 \
    || fail "ruff hâlâ B017 (kör istisna iddiası) buluyor"

# --------------------------------------------- 2  her raises bir tip alıyor
echo "# 2  her pytest.raises bir tip alıyor"
"$PY" -I - <<'INNER' || fail "tipsiz ya da gevşek pytest.raises bulundu"
import pathlib
import re
import sys

# Only real call sites: a `with` statement that opens the context. A comment
# or docstring that *mentions* the old pattern — this repo has several, since
# the narrowing is explained where it happened — must not trip the check.
BAD = re.compile(r"with\s[^#]*pytest\.raises\(\s*(\)|Exception|BaseException)")
offenders = []
for path in pathlib.Path("tests").rglob("*.py"):
    if "__pycache__" in path.parts:
        continue
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        if BAD.search(line):
            offenders.append(f"{path}:{n}: {line.strip()[:70]}")
for item in offenders:
    print(f"  HATA: {item}")
print(f"  taranan dosya: {len(list(pathlib.Path('tests').rglob('*.py')))}")
sys.exit(1 if offenders else 0)
INNER

# ------------------------------------------------ 3  tests/ tamamen temiz
echo "# 3  tests/ ruff-temiz (kapsam genişletmesinin önkoşulu)"
"$PY" -m ruff check tests || fail "tests/ ruff-temiz değil; kapsam genişletilemez"

# ------------------------------------------------------ 4  daraltma kırmadı
echo "# 4  tam takım (daraltılan iddialar hâlâ geçiyor)"
"$PY" -m pytest -q -o addopts="" -p no:cacheprovider \
    || fail "tam takım yeşil değil — daraltılan bir iddia tutmuyor, bu bir BULGU"

echo
echo "GEÇTİ — 7 kör iddia tipli, tests/ temiz, hepsi daraltıldıktan sonra da geçiyor"
