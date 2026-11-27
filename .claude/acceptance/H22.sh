#!/usr/bin/env bash
# Kabul kriteri — H22: "kasten kırmızı koşan bir kapı sonraki commit'i
# reddettirmiyor; her alt-süreç pytest çağrısının makbuzu yönlendirdiği testle
# taranıyor".
#
# Beş ölçüm. 2 ve 3 ayırt edici olanlar.
#
#   1  TARAMA: kabul betiklerindeki her alt-süreç pytest çağrısının makbuzu
#      yönlendirdiğini denetleyen test yeşil, ve listesi gerçekle örtüşüyor
#      (sessizce eskiyen bir liste hiç listeden kötüdür)
#   2  DAVRANIŞ: kasten kırmızı koşan kapılar GERÇEK makbuza HİÇ DOKUNMUYOR —
#      öncesi ve sonrası **birebir aynı bayt**. "Kırmızı bırakmıyor" demek
#      yetmez; dokunmamak ölçülebilir ve daha güçlü.
#   3  DAVRANIŞ: o kapılar koştuktan SONRA commit kapısı izin veriyor —
#      maddenin kriterinin kendisi
#   4  KONTROL: makbuzun son koşusu elle kırmızı yapılınca commit kapısı
#      hâlâ REDDEDİYOR — 2 ve 3'ü boş olmaktan kurtaran şey; her şeye izin
#      veren bir kapı da ikisini geçerdi
#   5  birim testleri yeşil
#
# ⚠️ Bu kapı kendisi pytest koşmuyor; koşsaydı ölçtüğü şeyi bozardı.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

fail() { echo "GEÇMEDİ — $1"; exit 1; }

# shellcheck source=_lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

PY=""
for cand in "${PYTHON:-}" python3 python; do
    [ -n "$cand" ] || continue
    if "$cand" -c "import pytest, yaml" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || fail "pytest+pyyaml içeren yorumlayıcı bulunamadı; PYTHON=... ile ver"
echo "# yorumlayıcı: $PY"

warn_untracked .claude tests || true

RECEIPT="reports/last-suite.json"
[ -f "$RECEIPT" ] || fail "$RECEIPT yok — önce tam takımı koş"

echo "# 1  tarama testi"
ORCSONAR_SUITE_RECEIPT="$(mktemp -u)" "$PY" -m pytest \
    "tests/hooks/test_suite_receipt.py::TestDeliberatelyRedGatesRedirectTheReceipt" \
    -q -o addopts="" -p no:cacheprovider >/dev/null \
    || fail "tarama testi kırmızı — bir kapı makbuzu yönlendirmiyor"
echo "  geçti"

echo "# 2  kasten kırmızı kapılar gerçek makbuza dokunmuyor"
BEFORE="$(mktemp)"
cp "$RECEIPT" "$BEFORE"
for g in A13 H21; do
    PYTHON="$PY" bash ".claude/acceptance/$g.sh" >/dev/null 2>&1 \
        || fail "$g.sh kapısı geçmedi — ölçüm anlamsız"
done
if ! cmp -s "$BEFORE" "$RECEIPT"; then
    echo "  HATA makbuz DEĞİŞTİ — kapılar gerçek makbuza yazıyor"
    "$PY" - "$BEFORE" "$RECEIPT" <<'INNER'
import json
import sys

before = json.load(open(sys.argv[1], encoding="utf-8"))
after = json.load(open(sys.argv[2], encoding="utf-8"))
print(
    f"       önce: {before.get('collected')} test exit "
    f"{before.get('exitstatus')} args={before.get('args')}"
)
print(
    f"       sonra: {after.get('collected')} test exit "
    f"{after.get('exitstatus')} args={after.get('args')}"
)
INNER
    rm -f "$BEFORE"
    exit 1
fi
echo "  iki kapı koştu, makbuz birebir aynı"

echo "# 3  o kapılardan sonra commit kapısı izin veriyor"
# ⚠️ Ölçüm İZOLE edilmek zorunda. İlk hali gerçek makbuzu kapıya veriyordu ve
# **doğru sebeple** düştü: makbuz BAYAT'tı, çünkü bu maddeyi yazarken bir test
# dosyası düzenlenmişti. Bayatlık `H7`'nin kendi koşulu ve çalışma ağacına
# bağlı; bu maddenin ölçtüğü şey **kapıların geriye kırmızı bırakıp
# bırakmadığı**. O yüzden gerçek makbuzun yapısı korunup yalnız zaman damgası
# ileriye alınıyor: böylece tek değişken kalan şey `exitstatus`.
FRESH="$(mktemp)"
"$PY" - "$RECEIPT" "$FRESH" <<'INNER'
import json
import sys
import time

receipt = json.load(open(sys.argv[1], encoding="utf-8"))
future = time.time() + 3600
receipt["at"] = future
if isinstance(receipt.get("last_whole_suite"), dict):
    receipt["last_whole_suite"]["at"] = future
with open(sys.argv[2], "w", encoding="utf-8") as handle:
    json.dump(receipt, handle)
INNER
OUT="$(printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git commit -m probe"}}' \
    | ORCSONAR_SUITE_RECEIPT="$FRESH" "$PY" .claude/hooks/block-stale-commit.py 2>&1 || true)"
rm -f "$FRESH"
if printf '%s' "$OUT" | grep -q "BLOCKED"; then
    echo "  HATA commit kapısı hâlâ reddediyor:"
    printf '%s\n' "$OUT" | head -4 | sed 's/^/       /'
    rm -f "$BEFORE"
    exit 1
fi
echo "  izin verdi (bayatlık dışlanarak; o H7'nin koşulu)"

echo "# 4  kontrol: elle kırmızı makbuz hâlâ reddediliyor"
CRAFTED="$(mktemp)"
"$PY" - "$RECEIPT" "$CRAFTED" <<'INNER'
import json
import sys

receipt = json.load(open(sys.argv[1], encoding="utf-8"))
receipt["exitstatus"] = 1
receipt["failed"] = 2
with open(sys.argv[2], "w", encoding="utf-8") as handle:
    json.dump(receipt, handle)
INNER
OUT="$(printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git commit -m probe"}}' \
    | ORCSONAR_SUITE_RECEIPT="$CRAFTED" "$PY" .claude/hooks/block-stale-commit.py 2>&1 || true)"
rm -f "$CRAFTED"
if ! printf '%s' "$OUT" | grep -q "BLOCKED"; then
    rm -f "$BEFORE"
    fail "kırmızı bir makbuza izin verildi — 2 ve 3. ölçümler boş"
fi
echo "  reddetti (kontrol anlamlı)"

echo "# 5  birim testleri"
ORCSONAR_SUITE_RECEIPT="$(mktemp -u)" "$PY" -m pytest \
    tests/hooks/test_suite_receipt.py tests/hooks/test_commit_gate.py \
    -q -o addopts="" -p no:cacheprovider \
    || { rm -f "$BEFORE"; fail "H22 birim testleri yeşil değil"; }

# Ölçüm bittikten sonra makbuzu olduğu gibi bırak: 5. adım kendi geçici
# makbuzuna yazdı, ama bir kapı yine de girdiği durumu geri vermeli.
cp "$BEFORE" "$RECEIPT"
rm -f "$BEFORE"

echo
echo "GEÇTİ — kasten kırmızı koşan kapılar gerçek makbuza dokunmuyor, sonraki"
echo "        commit'i reddettirmiyorlar, ve bu izin her makbuza verilen bir"
echo "        izin değil: elle kırmızı yapılmış bir makbuz hâlâ reddediliyor."
