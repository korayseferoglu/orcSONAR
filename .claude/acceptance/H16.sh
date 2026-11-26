#!/usr/bin/env bash
# Kabul kriteri — H16: "workflow sabit imaj + Node 24 action'ları kullanıyor;
# test kayan etiketi reddediyor".
#
# Dört ölçüm:
#   1  koşu imajı kayan etiket DEĞİL
#   2  her `uses:` değişmez bir commit SHA'sına pinli, ve sürümü yorumda yazılı
#   3  pinlenen action'lar Node 24 hedefliyor (deprecation anotasyonunun sebebi)
#   4  testler bunu kilitliyor (kayan etiket geri gelirse kırmızı)
#
# ⚠️ 3 **ağ gerektirir** ve ağ yoksa GEÇMEZ, sessizce atlamaz: "pinlediğim
# sürüm Node 24'tü" iddiası doğrulanmadan geçerse, bu maddenin tamamı bir
# beyana döner (değişmez 3). Ağsız ortamda kapı bunu açıkça söyleyerek düşer.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

fail() { echo "GEÇMEDİ — $1"; exit 1; }

PY=""
for cand in "${PYTHON:-}" python3 python; do
    [ -n "$cand" ] || continue
    if "$cand" -c "import pytest, yaml" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || fail "pytest+pyyaml içeren yorumlayıcı bulunamadı; PYTHON=... ile ver"
echo "# yorumlayıcı: $PY"

echo "# 1-2  sabit imaj ve SHA-pinli action'lar"
"$PY" -I - <<'INNER' || fail "pin denetimi geçmedi"
import re
import sys

import yaml

wf = yaml.safe_load(open(".github/workflows/ci.yml", encoding="utf-8"))
text = open(".github/workflows/ci.yml", encoding="utf-8").read()
problems: list[str] = []

runs_on = wf["jobs"]["gate"]["runs-on"]
if runs_on.endswith("-latest"):
    problems.append(f"runs-on: {runs_on} kayan etiket")
else:
    print(f"  koşu imajı: {runs_on}")

uses = re.findall(r"uses:\s*(\S+)", text)
if not uses:
    problems.append("hiç `uses:` yok — workflow beklenen şekilde değil")
for entry in uses:
    ref = entry.split("@", 1)[1] if "@" in entry else ""
    if not re.fullmatch(r"[0-9a-f]{40}", ref):
        problems.append(f"SHA-pinli değil: {entry}")
    else:
        print(f"  pin: {entry[:28]}…@{ref[:8]}")
for line in text.splitlines():
    if "uses:" in line and "@" in line and "#" not in line.split("@", 1)[1]:
        problems.append(f"sürüm yorumu yok: {line.strip()}")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo "# 3  pinlenen action'lar Node 24 hedefliyor (ağ gerekir)"
"$PY" -I - <<'INNER' || fail "Node sürümü doğrulanamadı — ağ yoksa bu madde bir beyandır"
import base64
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request

text = open(".github/workflows/ci.yml", encoding="utf-8").read()
pins = re.findall(r"uses:\s*([\w.-]+/[\w.-]+)@([0-9a-f]{40})", text)
if not pins:
    sys.exit("pin bulunamadı")

problems: list[str] = []
for repo, sha in pins:
    url = f"https://api.github.com/repos/{repo}/contents/action.yml?ref={sha}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
            payload = json.load(resp)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        sys.exit(f"{repo}: action.yml okunamadı ({exc}) — ağ yoksa kapı geçmez")
    body = base64.b64decode(payload["content"]).decode("utf-8", "replace")
    match = re.search(r"using:\s*'?\"?(node\d+)", body)
    if not match:
        problems.append(f"{repo}: runs.using okunamadı")
    elif match.group(1) != "node24":
        problems.append(f"{repo}: {match.group(1)} — Node 24 değil")
    else:
        print(f"  {repo}: node24")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo "# 4  testler kayan etiketi reddediyor"
"$PY" -m pytest tests/hooks/test_ci_workflow.py -q -o addopts="" -p no:cacheprovider \
    || fail "CI workflow testleri yeşil değil"

echo
echo "GEÇTİ — imaj sabit, action'lar SHA-pinli ve sürümleri yorumda, pinler Node 24,"
echo "        ve testler kayan etiketin geri gelmesini engelliyor."
