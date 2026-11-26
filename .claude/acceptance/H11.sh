#!/usr/bin/env bash
# Kabul kriteri — H11: "üçü de çalışıyor".
#
# Üçü: `FileChanged` (bağlanmamış config anahtarı → uyarı), `PostToolUse`'a
# mypy, ve `Stop`'ta bloke ETMEYEN özet. Artı satırın 🆕 maddesi: durum
# satırının sayım dökümü.
#
# ⚠️ "Çalışıyor"u nasıl ölçüyorum, ve neyi ölçmediğimi neden söylüyorum:
# bir hook'un `settings.json`'da **bağlı** olması çalıştığı anlamına gelmez —
# bu projenin kendi ölçümü bunun kanıtı (`log-instructions-loaded.py` `100644`
# commit'lendi, kabuk çalıştıramadı, olay `exit 126` ile öldü ve yol haritası
# hook'u "kurulu" diye kaydediyordu). O yüzden kapı üç şeyi ayrı ayrı ölçer:
#   1  üçü de `settings.json`'da doğru olayda bağlı
#   2  üçü de çalıştırılabilir (disk VE git indeksi — commit'lenen mod o)
#   3  üçünün KOMUTU gerçek payload ile koşturulup doğru davranıyor
#   4  durum satırı dökümü her maddeyi sayıyor (birim testleri)
#
# ÖLÇMEDİĞİM: olayın Claude Code tarafından gerçekten ateşlenmesi.
# `FileChanged` ve `Stop` bu oturumun dışında ateşlenir ve yeni eklenen bir
# hook kayda geçmek için oturum yenilenmesi isteyebilir. Kapı bunu geçmiş gibi
# göstermiyor; ateşlenme `H4`'ün kapandığı gibi sonraki oturumda gözlenir.

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

echo "# 1-2  üçü de doğru olayda bağlı ve çalıştırılabilir"
"$PY" -I - <<'INNER' || fail "bağlantı/çalıştırılabilirlik denetimi geçmedi"
import json
import os
import stat
import subprocess
import sys

WANTED = {
    "FileChanged": "config-key-wired.py",
    "PostToolUse": "mypy-check-src.py",
    "Stop": "stop-summary.py",
}

settings = json.load(open(".claude/settings.json", encoding="utf-8"))
hooks = settings.get("hooks", {})
problems: list[str] = []

for event, script in WANTED.items():
    blocks = hooks.get(event) or []
    commands = [
        h.get("command", "")
        for b in blocks
        for h in (b.get("hooks") or [])
        if h.get("type") == "command"
    ]
    if not any(script in c for c in commands):
        problems.append(f"{event}: {script} bağlı değil")
        continue
    path = os.path.join(".claude", "hooks", script)
    if not os.path.isfile(path):
        problems.append(f"{script}: dosya yok")
        continue
    if not os.stat(path).st_mode & stat.S_IXUSR:
        problems.append(f"{script}: diskte çalıştırılabilir değil")
    # Commit'lenen mod git indeksinde; diskte +x olup indekste olmaması tam
    # olarak `log-instructions-loaded.py`'nin `exit 126` ile ölme biçimiydi.
    done = subprocess.run(
        ["git", "ls-files", "-s", "--", path], capture_output=True, text=True
    )
    if done.returncode == 0 and done.stdout.strip():
        mode = done.stdout.split()[0]
        if not mode.endswith("755"):
            problems.append(f"{script}: git indeksinde mod {mode}, 100755 değil")
    print(f"  {event:<14} {script}")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo "# 3  üçünün komutu gerçek payload ile doğru davranıyor"
"$PY" -I - <<'INNER' || fail "komut davranışı denetimi geçmedi"
import json
import os
import subprocess
import sys

PY = sys.executable
root = os.getcwd()
problems: list[str] = []


def run(script: str, payload: dict) -> tuple[int, str]:
    done = subprocess.run(
        [PY, os.path.join(".claude", "hooks", script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=180,
    )
    return done.returncode, done.stdout


# --- FileChanged: bir config dosyası dokunulduğunda konuşur ---------------
code, out = run(
    "config-key-wired.py",
    {
        "hook_event_name": "FileChanged",
        "tool_name": "Edit",
        "tool_input": {"file_path": os.path.join(root, "config", "config.yaml")},
    },
)
if code != 0:
    problems.append(f"config-key-wired: config dosyasında çıkış {code}")
elif "additionalContext" not in out:
    problems.append("config-key-wired: bağlanmamış anahtar var ama bağlam dönmedi")

# ...ve ilgisiz bir dosyada SESSİZ kalır. Her düzenlemede konuşan bir uyarı
# okunmaz hale gelir, yani sessizlik de ölçülmesi gereken bir davranış.
code, out = run(
    "config-key-wired.py",
    {
        "hook_event_name": "FileChanged",
        "tool_name": "Edit",
        "tool_input": {"file_path": os.path.join(root, "README.md")},
    },
)
if code != 0 or out.strip():
    problems.append(f"config-key-wired: ilgisiz dosyada konuştu ({out[:60]!r})")

# --- FileChanged betiği bağımsız kapı olarak da koşabiliyor --------------
done = subprocess.run(
    [PY, os.path.join(".claude", "hooks", "config-key-wired.py"), "--all"],
    capture_output=True,
    text=True,
    timeout=300,
)
if done.returncode not in (0, 1):
    problems.append(f"config-key-wired --all: beklenmeyen çıkış {done.returncode}")

# --- PostToolUse mypy: src dışı bir dosyada sessiz -----------------------
code, out = run(
    "mypy-check-src.py",
    {
        "hook_event_name": "PostToolUse",
        "tool_name": "Edit",
        "tool_input": {"file_path": os.path.join(root, "README.md")},
    },
)
if code != 0 or out.strip():
    problems.append("mypy-check-src: src dışı dosyada konuştu")

# --- Stop: bloke ETMEMELİ ------------------------------------------------
code, out = run("stop-summary.py", {"hook_event_name": "Stop"})
if code != 0:
    problems.append(f"stop-summary: çıkış {code} — Stop hook'u asla bloke etmemeli")
if out.strip():
    parsed = json.loads(out)
    if parsed.get("continue") is False or "decision" in parsed:
        problems.append("stop-summary: bloke edici alan döndürüyor")

for problem in problems:
    print(f"  HATA {problem}")
print(f"  {4 - len(problems)}/4 davranış ölçümü geçti")
sys.exit(1 if problems else 0)
INNER

echo "# 4  durum satırı dökümü ve config kontrolü testleri"
"$PY" -m pytest tests/hooks/test_config_keys.py tests/hooks/test_session_status.py \
    -q -o addopts="" -p no:cacheprovider \
    || fail "H11'in testleri yeşil değil"

echo
echo "GEÇTİ — üç hook doğru olayda bağlı, çalıştırılabilir (disk + indeks), komutları"
echo "        gerçek payload ile doğru davranıyor, ve durum dökümü her maddeyi sayıyor."
echo "        KAPSAM DIŞI: olayın Claude Code tarafından ateşlenmesi — sonraki oturumda"
echo '        gözlenir, H4'"'"'ün kapandığı gibi.'
