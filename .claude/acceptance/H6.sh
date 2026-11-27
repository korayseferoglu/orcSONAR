#!/usr/bin/env bash
# Kabul kriteri — H6: CI kurulu, kararları kilitli, ve koştuğu komutlar geçiyor.
#
# Bu kapı kriterin YALNIZ yerelde ölçülebilir yarısını ölçer:
#   1  workflow'un kararları (pin'ler, kapsam, ne bloke eder) testlerle kilitli
#   2  ruff — workflow'un koştuğu kapsamda, bloke edici
#   3  pytest — tam takım, workflow'un koştuğu gibi
#   4  tek-kopya kapısı — CI'ın bloke edici adımı (H9)
#   5  yol haritası sıra kapısı — CI'ın bloke edici adımı (H9b)
#   6  mypy — koşuyor ve bir sayı veriyor (bilgilendirici, bloke etmez)
#
# 4 ve 5 `H21`'de eklendi. Bu betik CI'ın YEREL AYNASI: amacı "CI bunu
# reddeder miydi?" sorusunu push etmeden cevaplamak. Cevaplayamıyordu —
# o iki kapı workflow'a sonradan eklenmişti ve ayna takip etmemişti, ve
# 2026-11-27'de iki commit yerelde yeşilken CI'da kırmızıya düştü.
# `tests/hooks/test_ci_workflow.py::test_the_local_gate_runs_every_blocking_ci_step`
# artık workflow'un bloke edici adımlarını bu dosyayla KARŞILAŞTIRIYOR, yani
# CI'a yeni bir kapı eklemek ayna onu da koşana kadar kırmızı kalıyor.
#
# ⚠️ Ölçmediği: GitHub Actions'da ilk koşunun yeşil olması ve main için
# "required status check" olarak işaretlenmesi. İkisi de ağ + repo ayarı
# gerektiriyor (`gh` bu makinede kurulu değil) ve bu kapıdan görülemez.
# O yarısı ayrı bir madde: H6b, yalnız beyanla kapanabilir. Buraya `exit 0`
# yazıp "zorunlu" olduğunu varsaymak kapıyı yalanlamak olurdu
# (.claude/acceptance/README.md).

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

fail() { echo "GEÇMEDİ — $1"; exit 1; }

PY=""
for cand in "${PYTHON:-}" python3 python; do
    [ -n "$cand" ] || continue
    if "$cand" -c "import pytest" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || fail "pytest içeren yorumlayıcı bulunamadı; PYTHON=... ile ver (.claude/acceptance/README.md)"
echo "# yorumlayıcı: $PY"

[ -f .github/workflows/ci.yml ] || fail ".github/workflows/ci.yml yok"

# -------------------------------------------------- 1  kararlar kilitli mi
echo "# 1  workflow kararları"
"$PY" -m pytest tests/hooks/test_ci_workflow.py -q -o addopts="" \
    || fail "workflow kararlarını kilitleyen testler geçmiyor"

# --------------------------------------------------------------- 2  ruff
# Kapsam tek otoriteden okunuyor (_status.RUFF_SCOPE); burada üçüncü bir
# kopya tutmak H9'un kapatacağı kayma olurdu.
SCOPE="$("$PY" -I -c "import sys; sys.path.insert(0, '.claude/hooks'); import _status; print(' '.join(_status.RUFF_SCOPE))")"
[ -n "$SCOPE" ] || fail "_status.RUFF_SCOPE okunamadı"
echo "# 2  ruff — $SCOPE"
# shellcheck disable=SC2086
"$PY" -m ruff check $SCOPE || fail "ruff kapsamda temiz değil — CI bloke ederdi"

# ------------------------------------------------------------- 3  pytest
echo "# 3  pytest — tam takım"
"$PY" -m pytest -q -rs -o addopts="" || fail "tam takım yeşil değil — CI bloke ederdi"

# ----------------------------------------------------- 4  tek-kopya kapısı
# CI'ın bloke edici adımı, ve bugünkü yerel-yeşil/CI-kırmızı vakalarından
# birinin sebebi (B18): bir yorum fallback sentinelinin değerini tekrar
# ediyordu. Kapı stdlib + pyyaml, kurulum gerektirmiyor.
# Her komut TEK kez yazılıyor ve hata mesajı o değişkeni gösteriyor: yolu
# ikinci kez yazmak, aynanın kapsamını ölçen testin bir YARDIM METNİYLE
# tatmin edilmesine yol açıyordu — `H21`'in kapısı bunu yakaladı.
SINGLE_COPY=".claude/hooks/check-single-copy.py"
ORDER_GATE=".claude/acceptance/H9b.sh"

echo "# 4  tek-kopya kapısı"
"$PY" "$SINGLE_COPY" >/dev/null \
    || fail "tek-kopya kapısı reddetti — CI bloke ederdi (ayrıntı: $PY $SINGLE_COPY)"
echo "  geçti"

# --------------------------------------------- 5  yol haritası sıra kapısı
echo "# 5  yol haritası sıra kapısı"
PYTHON="$PY" bash "$ORDER_GATE" >/dev/null \
    || fail "yol haritası sıra kapısı reddetti — CI bloke ederdi (ayrıntı: bash $ORDER_GATE)"
echo "  geçti"

# --------------------------------------------------------------- 6  mypy
# Bilgilendirici: hata sayısı kapıyı düşürmez, ama mypy'nin hiç koşmaması
# düşürür — koşmayan bir araç, sessizce temiz görünür (değişmez 2).
echo "# 6  mypy — bilgilendirici"
MYPY_OUT="$("$PY" -m mypy src/ 2>&1)"
MYPY_CODE=$?
if [ $MYPY_CODE -ge 2 ] && ! printf '%s' "$MYPY_OUT" | grep -qE "Found [0-9]+ error"; then
    fail "mypy koşamadı: $(printf '%s' "$MYPY_OUT" | tail -2)"
fi
printf '%s\n' "$MYPY_OUT" | tail -1

echo
echo "GEÇTİ — CI kurulu, kararları kilitli, ve CI'ın BLOKE EDİCİ adımlarının"
echo "        hepsi yerelde koştu: ruff + pytest + tek-kopya + sıra kapısı"
echo "        (+ bilgilendirici mypy)"
echo "ÖLÇÜLMEDİ — Actions'da yeşil koşu ve 'required' işareti: H6b (beyan)"
