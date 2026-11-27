#!/usr/bin/env bash
# Kabul kriteri — H20: "bir kabul betiği koşmak sonraki commit'i reddettirmiyor;
# sınır belgelenmiş".
#
# Altı ölçüm. Birincisi kriterin kendisi ve **gerçek bir pytest koşuyor** —
# çünkü makbuzu ezen şey tam olarak o: yazıcı (`tests/conftest.py`). Sentetik
# bir makbuzla "korunuyor" demek yazıcıyı hiç ölçmezdi.
#
#   1  YAZICI: daraltılmış gerçek bir pytest koşusu, önceki tam-takım kanıtını
#      KORUYOR (`last_whole_suite` yerinde, `whole_suite` false)
#   2  KAPI: o makbuzla commit'e İZİN veriyor               ← kriterin kendisi
#   3  REGRESYON: eski biçimli (kanıtsız) kısmi makbuz hâlâ REDDEDİLİYOR —
#      düzeltme kapıyı gevşetmedi, kanıtın tanımını düzeltti
#   4  BAYAT tam-takım kanıtı hâlâ REDDEDİLİYOR (tazelik kanıt üzerinde ölçülüyor)
#   5  SINIR BELGELİ: `pytest && git commit` kendi mesajıyla reddediliyor,
#      "BAYAT" demiyor
#   6  birim testleri yeşil
#
# ⚠️ 3 ve 4 olmadan 1-2 anlamsız: her makbuzu kabul eden bir kapı da ikisini
# "geçer". H19'un dersi tam buydu — ölçmek istediği ayrımı yapamayan bir kapının
# yeşil olması hiçbir şey söylemez.

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

warn_untracked tests .claude || true

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
RECEIPT="$WORK/receipt.json"

echo "# 1  yazıcı: daraltılmış koşu tam-takım kanıtını koruyor (gerçek pytest)"
# Kanıt GELECEKTE: depodaki hiçbir dosya ondan yeni olamaz, böylece 2. ölçüm
# tazelik aritmetiğine değil kanıtın korunmasına bakar.
"$PY" -I - "$RECEIPT" <<'INNER' || fail "sentetik tam-takım makbuzu yazılamadı"
import json
import sys
import time

with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(
        {
            "at": time.time() + 3600,
            "exitstatus": 0,
            "whole_suite": True,
            "args": ["tests"],
            "collected": 1246,
            "failed": 0,
        },
        handle,
    )
INNER

# Gerçek, daraltılmış bir pytest. Bu çağrı eskiden makbuzu ezerdi.
ORCSONAR_SUITE_RECEIPT="$RECEIPT" "$PY" -m pytest tests/hooks/test_suite_receipt.py \
    -q -o addopts="" -p no:cacheprovider >/dev/null 2>&1 \
    || fail "daraltılmış pytest koşusu kırmızı"

"$PY" -I - "$RECEIPT" <<'INNER' || exit 1
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    receipt = json.load(handle)

problems = []
if receipt.get("whole_suite") is not False:
    problems.append(f"üst kayıt tam takım sanıyor: whole_suite={receipt.get('whole_suite')}")
evidence = receipt.get("last_whole_suite")
if not isinstance(evidence, dict):
    problems.append("last_whole_suite KAYBOLDU — yazıcı kanıtı eziyor (H20'nin hatası)")
elif evidence.get("collected") != 1246:
    problems.append(f"kanıt değişti: collected={evidence.get('collected')}")
else:
    print(f"  kanıt korundu: collected={evidence['collected']}, at={evidence['at']:.0f}")
    print(f"  son koşu      : collected={receipt.get('collected')}, whole_suite=False")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo "# 2-5  kapının dört kararı"
"$PY" -I - "$RECEIPT" <<'INNER' || exit 1
import json
import os
import subprocess
import sys
import tempfile
import time

HOOK = os.path.join(".claude", "hooks", "block-stale-commit.py")
problems: list[str] = []


def ask(receipt_path: str, command: str) -> str:
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    done = subprocess.run(
        [sys.executable, HOOK],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=60,
        env=dict(os.environ, ORCSONAR_SUITE_RECEIPT=receipt_path),
    )
    return done.stdout + done.stderr


def check(label, path, command, *, expect_block, expect_text=None, forbid_text=None):
    out = ask(path, command)
    blocked = "BLOCKED" in out
    if blocked != expect_block:
        problems.append(
            f"{label}: {'engellendi' if blocked else 'izin verildi'} "
            f"(beklenen {'engellendi' if expect_block else 'izin'})"
        )
        return
    if expect_text and expect_text not in out:
        problems.append(f"{label}: gerekçe yanlış, '{expect_text}' yok")
        return
    if forbid_text and forbid_text in out:
        problems.append(f"{label}: yanıltıcı gerekçe, '{forbid_text}' var")
        return
    print(f"  {label:<40} {'RET' if blocked else 'İZİN'}")


def crafted(receipt: dict) -> str:
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump(receipt, handle)
    handle.close()
    return handle.name


COMMIT = "git" + " commit -m probe"
now = time.time() + 3600

# 2  kriterin kendisi: 1. ölçümün bıraktığı gerçek makbuz
check("2 kabul betiği sonrası commit", sys.argv[1], COMMIT, expect_block=False)

# 3  regresyon: eski biçim, kanıt yok
check(
    "3 kanıtsız kısmi makbuz",
    crafted({"at": now, "exitstatus": 0, "whole_suite": False, "collected": 17}),
    COMMIT,
    expect_block=True,
    expect_text="tam takım HİÇ koşmadı",
)

# 4  bayat kanıt
check(
    "4 bayat tam-takım kanıtı",
    crafted(
        {
            "at": now,
            "exitstatus": 0,
            "whole_suite": False,
            "collected": 17,
            "last_whole_suite": {"at": 1.0, "exitstatus": 0, "collected": 1246},
        }
    ),
    COMMIT,
    expect_block=True,
    expect_text="BAYAT",
)

# 5  sınır: zincir komutu kendi mesajını alıyor
check(
    "5 pytest && git commit zinciri",
    sys.argv[1],
    "pytest -q && " + COMMIT,
    expect_block=True,
    expect_text="tek bir komut olarak çalışmaz",
    forbid_text="BAYAT",
)

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo "# 6  birim testleri"
ORCSONAR_SUITE_RECEIPT="$WORK/throwaway.json" "$PY" -m pytest \
    tests/hooks/test_suite_receipt.py tests/hooks/test_commit_gate.py \
    -q -o addopts="" -p no:cacheprovider \
    || fail "H20 birim testleri yeşil değil"

echo
echo "GEÇTİ — daraltılmış bir koşu tam-takım kanıtını ezmiyor, o yüzden bir kabul"
echo "        betiği koşmak sonraki commit'i reddettirmiyor; kanıtsız ve bayat"
echo "        makbuz hâlâ reddediliyor; zincir komutunun sınırı kapının kendi"
echo "        mesajında yazılı."
echo "        NOT: bu betik kendi makbuzunu geçici bir yola yazar, gerçek"
echo "        reports/last-suite.json'a dokunmaz."
