#!/usr/bin/env bash
# Kabul kriteri — H13: "ikisi de çalışıyor; ajan `Write`'ı `src/` dışına
# sınırlı; log özeti okunabiliyor".
#
# Dört ölçüm, dördü de kriterin ayrı bir yarısı:
#   1  `null-check` skill'i KOŞUYOR ve raporu `H4`'ün okuduğu alanlarla yazıyor
#      — doğru yere yanlış şekilde yazmak, `E1` satırının uyardığı sessiz
#      arıza; durum satırı "hiç koşmadı" demeye devam ederdi
#   2  `claim-check` skill'i var ve frontmatter'ı YALNIZ belgelenmiş alanlar
#      kullanıyor (tanınmayan alan Claude Code'da sessizce yok sayılır, yani
#      uydurma bir alan var olmayan bir davranış beyan eder — değişmez 3)
#   3  alt-ajan `src/` yazımı GERÇEKTEN engelleniyor, ana oturum ve uygulayıcı
#      ajan engellenmiyor
#   4  `instructions-loaded.log` özeti okunabiliyor ve hiç yüklenmeyen kuralı
#      yüksek sesle bildiriyor (birim testleri)
#
# ⚠️ 1'de null modelinin SAYISI doğrulanmıyor, varlığı ve şekli doğrulanıyor.
# Eşik ya da anlamlılık kararı `A12` ön kaydına ait; kapı bir p-değerinin
# "iyi" olmasını istemez, yalnız ölçülmüş ve okunabilir olmasını ister.

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

echo "# 1  null-check raporu var ve H4'ün okuduğu alanları taşıyor"
"$PY" -I - <<'INNER' || fail "null-check raporu denetimi geçmedi"
import json
import pathlib
import sys

sys.path.insert(0, ".claude/hooks")

import _status

report_path = pathlib.Path("reports/null_gate.json")
if not report_path.is_file():
    sys.exit(
        "reports/null_gate.json yok — skill hiç koşmadı. Koş: "
        "python .claude/skills/null-check/scripts/null_check.py"
    )
payload = json.loads(report_path.read_text(encoding="utf-8"))

problems: list[str] = []
for unit in ("transcripts", "occurrences"):
    stats = payload.get("units", {}).get(unit)
    if not isinstance(stats, dict):
        problems.append(f"'{unit}' birimi yok")
        continue
    if stats.get("null_size") != 16384:
        problems.append(f"{unit}: null 16384 değil ({stats.get('null_size')})")
    for key in ("observed", "null_mean", "percentile_of_observed", "p_empirical_ge"):
        if key not in stats:
            problems.append(f"{unit}: '{key}' yok")

# Eşik/verdict YAZILMAMALI: ön kayıt kilitlenmeden bir karar üretmek
# değişmez 7'nin ihlali.
for forbidden in ("significant", "verdict", "threshold"):
    if forbidden in payload:
        problems.append(
            f"raporda '{forbidden}' var — ön kayıt kilitlenmeden karar üretilmiş"
        )

# Durum satırı bunu gerçekten okuyabiliyor mu? "tanınan alan yok" demesi,
# doğru yere yanlış şekilde yazmanın sessiz arızasıdır.
line = _status.null_gate_text(path=str(report_path), payload=payload)
if "tanınan alan yok" in line or "ÖLÇÜLMEDİ" in line:
    problems.append(f"durum satırı raporu okuyamıyor: {line}")
else:
    print(f"  durum satırı: {line}")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo "# 2  claim-check skill'i var ve yalnız belgelenmiş frontmatter alanları kullanıyor"
"$PY" -I - <<'INNER' || fail "claim-check frontmatter denetimi geçmedi"
import pathlib
import sys

import yaml

# https://code.claude.com/docs/en/skills.md — SKILL.md frontmatter tablosu.
DOCUMENTED = {
    "name", "description", "when_to_use", "argument-hint", "arguments",
    "disable-model-invocation", "user-invocable", "allowed-tools",
    "disallowed-tools", "model", "effort", "context", "agent", "background",
    "hooks", "paths", "shell", "metadata", "license", "compatibility",
}

problems: list[str] = []
for name in ("claim-check", "null-check"):
    path = pathlib.Path(".claude/skills") / name / "SKILL.md"
    if not path.is_file():
        problems.append(f"{name}: SKILL.md yok")
        continue
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        problems.append(f"{name}: frontmatter yok")
        continue
    front = yaml.safe_load(text.split("---", 2)[1])
    unknown = sorted(set(front) - DOCUMENTED)
    if unknown:
        problems.append(
            f"{name}: belgelenmemiş alan {unknown} — Claude Code tanınmayan "
            "alanı sessizce yok sayar, yani var olmayan bir davranış beyan eder"
        )
    if not front.get("description"):
        problems.append(f"{name}: description yok (skill hiç tetiklenmez)")
    print(f"  {name:<12} alanlar: {', '.join(sorted(front))}")

if pathlib.Path(".claude/skills/claim-check/SKILL.md").is_file():
    front = yaml.safe_load(
        pathlib.Path(".claude/skills/claim-check/SKILL.md")
        .read_text(encoding="utf-8")
        .split("---", 2)[1]
    )
    # Satır `context: fork` + sonnet/high istiyor; `context: fork` bir `agent`
    # olmadan hangi alt-ajanı başlatacağını bilmez.
    if front.get("context") == "fork" and not front.get("agent"):
        problems.append("claim-check: context: fork var ama agent: yok")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo "# 3  alt-ajanın src/ yazımı engelleniyor, ana oturum ve uygulayıcı serbest"
"$PY" -I - <<'INNER' || fail "ajan yazma kapsamı denetimi geçmedi"
import json
import os
import subprocess
import sys

HOOK = os.path.join(".claude", "hooks", "block-agent-src-writes.py")
SRC = os.path.join(os.getcwd(), "src", "core", "models.py")
problems: list[str] = []


def blocked(payload: dict) -> bool:
    done = subprocess.run(
        [sys.executable, HOOK], input=json.dumps(payload),
        capture_output=True, text=True, timeout=30,
    )
    return "BLOCKED" in done.stdout + done.stderr


cases = [
    ("gözlemci ajan src/ yazıyor", True,
     {"tool_name": "Write", "agent_id": "a1", "agent_type": "bio-reviewer",
      "tool_input": {"file_path": SRC}}),
    ("ana oturum src/ yazıyor", False,
     {"tool_name": "Write", "tool_input": {"file_path": SRC}}),
    ("uygulayıcı ajan src/ yazıyor", False,
     {"tool_name": "Write", "agent_id": "a1",
      "agent_type": "coordinate-engineer", "tool_input": {"file_path": SRC}}),
    ("ajan reports/ yazıyor", False,
     {"tool_name": "Write", "agent_id": "a1", "agent_type": "bio-reviewer",
      "tool_input": {"file_path": os.path.join(os.getcwd(), "reports", "x.md")}}),
]
for label, expect_block, payload in cases:
    got = blocked(payload)
    mark = "engellendi" if got else "serbest"
    if got != expect_block:
        problems.append(f"{label}: {mark} (beklenen {'engellendi' if expect_block else 'serbest'})")
    else:
        print(f"  {label:<34} {mark}")

# Hook settings.json'da gerçekten bağlı mı?
settings = json.load(open(".claude/settings.json", encoding="utf-8"))
wired = any(
    "block-agent-src-writes.py" in h.get("command", "")
    for b in settings["hooks"].get("PreToolUse", [])
    for h in (b.get("hooks") or [])
)
if not wired:
    problems.append("hook settings.json'da PreToolUse'a bağlı değil")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo "# 4  log özeti ve null modeli testleri"
"$PY" -m pytest tests/hooks/test_null_check.py tests/hooks/test_session_status.py \
    -q -o addopts="" -p no:cacheprovider \
    || fail "H13'ün testleri yeşil değil"

echo
echo "GEÇTİ — null-check koşuyor ve durum satırı raporunu okuyor; claim-check yalnız"
echo "        belgelenmiş alanlar kullanıyor; alt-ajan src/ yazımı engelli, ana oturum"
echo "        ve uygulayıcı serbest; log özeti hiç yüklenmeyen kuralı bildiriyor."
