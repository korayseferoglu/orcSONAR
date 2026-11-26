#!/usr/bin/env bash
# Kabul kriteri — H18: "kapı betikleri izlenmeyen dosya varken uyarıyor;
# dedektörler kendilerini kapsam dışı bırakıyor".
#
# İki yarı, iki ayrı arıza:
#   1  git-kapsamlı her kapı `warn_untracked` çağırıyor VE uyarı gerçekten
#      ateşleniyor (sentetik bir izlenmeyen dosyayla ölçülüyor)
#   2  deseni metin olarak taşımak zorunda olan her dedektör kendini kapsam
#      dışı bırakıyor
#
# ⚠️ 1'de "çağırıyor" yetmez, "ateşleniyor" ölçülür: `warn_untracked`'i
# çağırıp çıktısını yutan bir kapı da grep'i geçerdi.

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

echo "# 1  git-kapsamlı kapılar uyarıyı çağırıyor"
MISSING=""
for gate in H9 H10 H11; do
    grep -q "warn_untracked" ".claude/acceptance/$gate.sh" || MISSING="$MISSING $gate"
done
grep -q "git ls-files --others" .claude/acceptance/H17.sh \
    || MISSING="$MISSING H17"
[ -z "$MISSING" ] || fail "uyarıyı çağırmayan git-kapsamlı kapı:$MISSING"
echo "  H9, H10, H11 warn_untracked · H17 doğrudan reddediyor"

echo "# 1b  uyarı gerçekten ateşleniyor"
PROBE=".claude/hooks/zzz_h18_probe.tmp"
[ -e "$PROBE" ] && fail "$PROBE zaten var"
: > "$PROBE"
OUT="$(PYTHON="$PY" bash .claude/acceptance/H9.sh 2>&1 | head -8 || true)"
rm -f "$PROBE"
if ! printf '%s' "$OUT" | grep -q "İZLENMİYOR"; then
    printf '%s\n' "$OUT" | sed 's/^/  /'
    fail "izlenmeyen dosya varken uyarı basılmadı"
fi
printf '%s' "$OUT" | grep -q "zzz_h18_probe" \
    || fail "uyarı basıldı ama sentetik dosyayı adlandırmadı"
echo "  uyarı basıldı ve dosyayı adlandırdı"

echo "# 2  dedektörler kendilerini kapsam dışı bırakıyor"
"$PY" -I - <<'INNER' || fail "öz-muafiyet denetimi geçmedi"
import pathlib
import sys

# Her biri aradığı deseni metin olarak taşımak ZORUNDA, o yüzden kendini
# kapsam dışı bırakmazsa kendisiyle eşleşir. Üçü de bunu bir kez yaptı.
CASES = [
    (".claude/hooks/_single_copy.py", "_single_copy.py"),
    (".claude/hooks/_single_copy.py", ".claude/acceptance/"),
    (".claude/hooks/_single_copy.py", "tests/hooks/test_single_copy.py"),
    ("src/core/run_manifest.py", ":!src/core/run_manifest.py"),
]
problems: list[str] = []
for path, needle in CASES:
    text = pathlib.Path(path).read_text(encoding="utf-8")
    if needle not in text:
        problems.append(f"{path}: kendini kapsam dışı bırakmıyor ({needle!r} yok)")
    else:
        print(f"  {path} → {needle}")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo
echo "GEÇTİ — git-kapsamlı kapılar izlenmeyen dosyayı adlandırarak uyarıyor"
echo "        (sentetik dosyayla ölçüldü), ve dedektörler kendilerini kapsıyor."
