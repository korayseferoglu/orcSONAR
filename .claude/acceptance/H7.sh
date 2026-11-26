#!/usr/bin/env bash
# Kabul kriteri — H7: "eski pytest ile commit reddediliyor".
#
# Kapı testi KOŞMAZ, koşulmuş olmasını ister. Satırın gerekçesi: tam takım
# ~3,7 dakika ve her commit'e bunu ekleyen bir kapı atlanır, o yüzden ölçülen
# şey **tazelik**. Satırın uyarısı da burada: düzenlemeden ÖNCE koşulmuş bir
# pytest kapıyı açmamalı, yoksa kapı "testler geçiyor" derken aslında "bir
# şeyler bir ara geçmişti" demiş olur.
#
# Beş ret yolu + bir izin yolu, hepsi sentetik makbuzlarla ölçülüyor
# (`ORCSONAR_SUITE_RECEIPT`), böylece gerçek makbuz bozulmuyor:
#   1  makbuz yok            → RET
#   2  koşu başarısızdı      → RET
#   3  koşu tam takım değildi→ RET
#   4  makbuz BAYAT          → RET   ← kriterin kendisi
#   5  taze + tam + geçmiş   → İZİN
#   6  komut algılaması kesin (birim testleri) + hook bağlı
#
# ⚠️ 6 olmadan 1-5 anlamsız: her Bash komutunu engelleyen ya da hiçbirini
# engellemeyen bir kapı da bu beş vakayı "geçer".

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

warn_untracked src tests .claude || true

echo "# 1-5  beş ret yolu ve izin yolu"
"$PY" -I - <<'INNER' || fail "makbuz davranışı denetimi geçmedi"
import json
import os
import subprocess
import sys
import tempfile
import time

HOOK = os.path.join(".claude", "hooks", "block-stale-commit.py")
COMMIT = {"tool_name": "Bash", "tool_input": {"command": "git" + " commit -m probe"}}
problems: list[str] = []


def run(receipt_path: str) -> str:
    env = dict(os.environ, ORCSONAR_SUITE_RECEIPT=receipt_path)
    done = subprocess.run(
        [sys.executable, HOOK],
        input=json.dumps(COMMIT),
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    return done.stdout + done.stderr


def check(label: str, receipt: dict | None, expect_block: bool) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "receipt.json")
        if receipt is not None:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(receipt, handle)
        out = run(path)
    blocked = "BLOCKED" in out
    if blocked != expect_block:
        problems.append(
            f"{label}: {'engellendi' if blocked else 'izin verildi'} "
            f"(beklenen {'engellendi' if expect_block else 'izin'})"
        )
    else:
        print(f"  {label:<34} {'RET' if blocked else 'İZİN'}")


now = time.time()
fresh = {"at": now, "exitstatus": 0, "whole_suite": True, "collected": 1200, "failed": 0}

check("makbuz yok", None, True)
check("koşu başarısız", {**fresh, "exitstatus": 1, "failed": 3}, True)
check("tam takım değil", {**fresh, "whole_suite": False, "collected": 15}, True)
# BAYAT: makbuz 1970'te; depodaki her dosya ondan yeni.
check("makbuz bayat", {**fresh, "at": 1.0}, True)
check("taze + tam + geçmiş", fresh, False)

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo "# 6  komut algılaması ve bağlantı"
"$PY" -I - <<'INNER' || fail "hook bağlı değil"
import json
import sys

settings = json.load(open(".claude/settings.json", encoding="utf-8"))
wired = [
    h.get("command", "")
    for b in settings["hooks"].get("PreToolUse", [])
    if b.get("matcher") == "Bash"
    for h in (b.get("hooks") or [])
    if "block-stale-commit.py" in h.get("command", "")
]
if not wired:
    sys.exit("block-stale-commit.py PreToolUse/Bash'e bağlı değil")
print(f"  bağlı: {len(wired)} adım (matcher Bash)")
INNER

"$PY" -m pytest tests/hooks/test_commit_gate.py -q -p no:cacheprovider \
    || fail "komut algılama testleri yeşil değil"

echo
echo "GEÇTİ — bayat, başarısız, kısmi ve eksik makbuz commit'i reddediyor; taze ve"
echo "        tam bir koşu izin veriyor; algılama yalnız gerçek commit'te ateşleniyor."
echo "        NOT: bu kapı pytest'i koşmaz, koşulmuş olmasını ölçer; ve Claude Code"
echo "        dışında yapılan bir commit bu kapının tamamen dışındadır."
