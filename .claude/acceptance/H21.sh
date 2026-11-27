#!/usr/bin/env bash
# Kabul kriteri — H21: "workflow'un her bloke edici adımı yerelde tek komutla
# koşuyor; kapsamı karşılaştıran test var ve yeni bir CI kapısı eklenince
# kırmızıya düşüyor".
#
# Beş ölçüm. 2 ve 3 ayırt edici olanlar.
#
#   1  KARŞILAŞTIRMA VAR: test bugünkü workflow'a karşı yeşil
#   2  MEKANİZMA ÇALIŞIYOR: workflow'un KOPYASINA yeni bir bloke edici adım
#      enjekte edilince test KIRMIZIYA düşüyor. Bu olmadan 1. ölçüm, yalnız
#      bugünkü adımları sayan bir liste olurdu — yarın eklenen kapıyı
#      yakalamayacak bir liste.
#   3  KONTROL: aynı adım `continue-on-error: true` ile enjekte edilince test
#      kırmızıya DÜŞMÜYOR — yani "bloke edici" ayrımı workflow'dan okunuyor,
#      varsayılmıyor. 2 olmadan 3, 3 olmadan 2 anlamsız.
#   4  YORUM YETMİYOR: aynanın yalnız bir YORUMUNDA geçen kapı adı testi
#      geçirmiyor — beyan ile uygulama ayrımı (değişmez 3)
#   5  AYNA GERÇEKTEN KOŞUYOR: iki yeni kapının komutu H6.sh içinde
#      çalıştırılabilir konumda ve tek tek koşturulup geçtikleri görülüyor
#
# ⚠️ Bu kapı `H6.sh`'ın tamamını koşmaz (tam takım ~4 dk; `H6`'nın kendi
# kapısı o). Burada ölçülen şey aynanın KAPSAMI, içeriğinin tekrar koşulması
# değil.

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

warn_untracked .claude .github tests || true

echo "# 1  karşılaştırma testi bugünkü workflow'a karşı yeşil"
ORCSONAR_SUITE_RECEIPT="$(mktemp -u)" "$PY" -m pytest \
    tests/hooks/test_ci_workflow.py -q -o addopts="" -p no:cacheprovider \
    >/dev/null || fail "karşılaştırma testi bugünkü workflow'da bile kırmızı"
echo "  geçti"

echo "# 2-4  mekanizma, kontrolü ve yorum ayrımı"
"$PY" - <<'INNER' || exit 1
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

WORKFLOW = Path(".github/workflows/ci.yml")
MIRROR = Path(".claude/acceptance/H6.sh")
TEST = "tests/hooks/test_ci_workflow.py::test_the_local_gate_runs_every_blocking_ci_step"

problems: list[str] = []


# Kasten kırmızı koşular; makbuz geçici bir yola yönlendiriliyor (`H22`).
_THROWAWAY_RECEIPT = tempfile.mkstemp(suffix=".json")[1]


def run_test() -> int:
    done = subprocess.run(
        [sys.executable, "-m", "pytest", TEST, "-q", "-o", "addopts=", "-p",
         "no:cacheprovider"],
        capture_output=True,
        text=True,
        timeout=180,
        env=dict(os.environ, ORCSONAR_SUITE_RECEIPT=_THROWAWAY_RECEIPT),
    )
    return done.returncode


# Bozma/geri yükleme `_perturb`'e devredildi (`H23`): tek uygulama, geri
# yüklemeyi kendisi doğruluyor, ve yazdıktan sonra bytecode'u düşürüyor.
sys.path.insert(0, ".claude/hooks")
import _perturb  # noqa: E402


def with_patched(path: Path, text: str, body: callable) -> None:
    """Replace a tracked file's bytes, run `body`, then restore them exactly."""
    with _perturb.patched(path, text):
        body()


workflow_text = WORKFLOW.read_text(encoding="utf-8")
anchor = "      - name: mypy (informational)"
if anchor not in workflow_text:
    sys.exit("workflow'da beklenen çapa bulunamadı — kapı güncellenmeli")

# ---- 2  yeni bloke edici adım → test KIRMIZI ---------------------------
injected_blocking = workflow_text.replace(
    anchor,
    "      - name: brand new gate (blocking)\n"
    "        run: echo probe\n\n" + anchor,
    1,
)
codes: dict[str, int] = {}
with_patched(WORKFLOW, injected_blocking,
             lambda: codes.__setitem__("blocking", run_test()))
if codes["blocking"] == 0:
    problems.append(
        "yeni bir BLOKE EDİCİ adım enjekte edildi ve test yine geçti — "
        "mekanizma yalnız bugünkü adımları sayıyor"
    )
else:
    print("  2  yeni bloke edici adım → test kırmızı (mekanizma çalışıyor)")

# ---- 3  kontrol: informational adım → test YEŞİL kalmalı ---------------
injected_info = workflow_text.replace(
    anchor,
    "      - name: brand new gate (blocking)\n"
    "        continue-on-error: true\n"
    "        run: echo probe\n\n" + anchor,
    1,
)
with_patched(WORKFLOW, injected_info,
             lambda: codes.__setitem__("informational", run_test()))
if codes["informational"] != 0:
    problems.append(
        "bilgilendirici bir adım da testi kırmızıya düşürdü — 'bloke edici' "
        "ayrımı workflow'dan okunmuyor, varsayılıyor"
    )
else:
    print("  3  kontrol: continue-on-error adım → test yeşil (ayrım okunuyor)")

# ---- 4  yorum yetmiyor -------------------------------------------------
mirror_text = MIRROR.read_text(encoding="utf-8")
commented = mirror_text.replace(
    'SINGLE_COPY=".claude/hooks/check-single-copy.py"',
    '# SINGLE_COPY=".claude/hooks/check-single-copy.py"',
    1,
)
if commented == mirror_text:
    problems.append("aynadaki tek-kopya çağrısı beklenen biçimde bulunamadı")
else:
    with_patched(MIRROR, commented, lambda: codes.__setitem__("commented", run_test()))
    if codes["commented"] == 0:
        problems.append(
            "ayna çağrıyı YORUMA aldığında test yine geçti — beyan uygulanmış "
            "sayılıyor (değişmez 3)"
        )
    else:
        print("  4  çağrı yoruma alınınca → test kırmızı (beyan ≠ uygulanmış)")

# Dosyalar geri yüklendi mi? Bir kapı depoyu bozarak ölçüm yapmamalı.
if WORKFLOW.read_text(encoding="utf-8") != workflow_text:
    problems.append("workflow geri yüklenmedi — kapı depoyu bozdu")
if MIRROR.read_text(encoding="utf-8") != mirror_text:
    problems.append("H6.sh geri yüklenmedi — kapı depoyu bozdu")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo "# 5  iki yeni kapı gerçekten koşuyor"
"$PY" .claude/hooks/check-single-copy.py >/dev/null \
    || fail "tek-kopya kapısı şu an reddediyor (ayna koşsa da kırmızı olurdu)"
echo "  tek-kopya kapısı: geçti"
PYTHON="$PY" bash .claude/acceptance/H9b.sh >/dev/null \
    || fail "yol haritası sıra kapısı şu an reddediyor"
echo "  sıra kapısı: geçti"

echo
echo "GEÇTİ — CI'ın bloke edici adımlarının hepsi yerel aynada koşuyor, ve"
echo "        karşılaştırma mekanizması yeni bir kapı eklenince gerçekten"
echo "        kırmızıya düşüyor (bilgilendirici adımda düşmüyor)."
echo "        NOT: bu kapı H6.sh'ın tamamını koşmaz; onun kapısı H6."
