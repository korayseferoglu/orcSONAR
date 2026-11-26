#!/usr/bin/env bash
# Kabul kriteri — H19: "`A12` açıkken commit'li taslak düzenlenebiliyor, `A12`
# kapandığında reddediliyor, ve kapı iki durumu ayırt ediyor".
#
# Üçüncü şart kriterin en önemli parçası. `H8` iki uygulamada da yeşildi,
# çünkü fixture'ı dosyayı **"A12" mesajıyla** commit'liyordu: "herhangi bir
# commit" ile "A12 kapandı" tasarımları kapıya aynı görünüyordu. Bir kapı
# ölçmek istediği ayrımı yapamıyorsa, yeşil olması bir şey söylemez.
#
# Dört ölçüm:
#   1  karar `a12` üzerinden veriliyor; `committed` artık kararın girdisi değil
#   2  `a12_closed` üç durumu ayrı döndürüyor (kapalı / açık / okunamadı)
#   3  `H8.sh` fixture'ı İKİ `A12` durumunu da koşuyor (ayrıştırıcı)
#   4  birim testleri + `H8.sh` yeşil

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

echo "# 1-2  karar A12'ye bağlı ve üç durum ayrı"
"$PY" -I - <<'INNER' || fail "karar mantığı denetimi geçmedi"
import inspect
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, ".claude/hooks")
import _prereg

problems: list[str] = []

# 1  imza: karar `a12` üzerinden
params = set(inspect.signature(_prereg.refuses).parameters)
if "a12" not in params:
    problems.append(f"refuses() `a12` almıyor: {sorted(params)}")
if "committed" in params:
    problems.append(
        "refuses() hâlâ `committed` alıyor — kilidin anahtarı dosyanın commit'i "
        "değil, A12'nin durumu (H19)"
    )
if not _prereg.refuses(locked=True, a12=True):
    problems.append("A12 kapalıyken reddetmiyor")
if _prereg.refuses(locked=True, a12=False):
    problems.append("A12 açıkken reddediyor — FAZ A bloke olur")
if not _prereg.refuses(locked=True, a12=None):
    problems.append("durum okunamazken reddetmiyor — bilinmiyor izin değildir")

# 2  a12_closed üç durumu ayırıyor
head = (
    "### FAZ A — On kayit\n\n"
    "| id | is | bagimlilik | kabul kriteri | durum |\n"
    "|---|---|---|---|---|\n"
)
cases = [("TODO", False), ("**DONE**", True), (None, None)]
for status, expected in cases:
    with tempfile.TemporaryDirectory() as tmp:
        repo = pathlib.Path(tmp)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        text = head
        if status is not None:
            text += f"| **A12** | on kayit | — | kilitli | {status} |\n"
        (repo / "SCIENTIFIC_ROADMAP.md").write_text(text, encoding="utf-8")
        got = _prereg.a12_closed(str(repo))
    if got is not expected:
        problems.append(f"a12_closed({status!r}) = {got!r}, beklenen {expected!r}")
    else:
        print(f"  a12_closed({str(status):>8}) → {got!r}")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo "# 3  H8 fixture'ı iki A12 durumunu da koşuyor"
grep -q "roadmap TODO" .claude/acceptance/H8.sh \
    || fail "H8.sh A12=TODO durumunu kurmuyor"
grep -q "roadmap '\*\*DONE\*\*'" .claude/acceptance/H8.sh \
    || fail "H8.sh A12=DONE durumunu kurmuyor"
grep -q "A12 açıkken commit'li taslağa edit engellendi" .claude/acceptance/H8.sh \
    || fail "H8.sh commit'li+A12-açık durumunu ÖLÇMÜYOR — ayrıştırıcı değil"
echo "  TODO ve DONE durumları + commit'li/A12-açık ölçümü mevcut"

echo "# 4  testler ve H8 kapısı"
"$PY" -m pytest tests/hooks/test_prereg_lock.py tests/hooks/test_pre_register.py \
    -q -o addopts="" -p no:cacheprovider || fail "kilit testleri yeşil değil"
PYTHON="$PY" bash .claude/acceptance/H8.sh >/dev/null 2>&1 || fail "H8 kapısı yeşil değil"
echo "  H8 kapısı yeşil"

echo
echo "GEÇTİ — kilit A12'nin durumuna bağlı, üç durum ayrı, ve H8'in fixture'ı artık"
echo "        'herhangi bir commit' ile 'A12 kapandı' tasarımlarını ayırt ediyor."
