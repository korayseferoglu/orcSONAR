#!/usr/bin/env bash
# Kabul kriteri — H8: kilitli ön kayıt dosyasına edit reddediliyor.
#
# Beş ölçüm:
#   1  hook dört yazma aracına da bağlı ve git index'inde 100755
#   2  commit'lenmiş dosyaya edit  -> çıkış 2 (ve v2 yolunu adlandırıyor)
#   3  commit'lenmemiş taslağa edit -> çıkış 0 (A12 öncesi yazım serbest)
#   4  `_v2` dosyasına yazma        -> çıkış 0 (değişmez 6'nın yasal yolu)
#   5  birim testleri yeşil
#
# 2 ve 4 birlikte ölçülmek zorunda: her şeyi reddeden bir kilit, etrafından
# dolaşılan bir kilittir. Yasal yolu kapatmak kuralı güçlendirmez, delinmesini
# garanti eder.
#
# ⚠️ Bu kapı gerçek `docs/PRE_REGISTRATION.md` üzerinde ÇALIŞMAZ ve çalışmamalı:
# onu commit'lemek A12'yi yapmak olurdu, yani bilimsel bir kararı bir testin
# yan etkisi olarak almak. Geçici bir repo kurar, kilidi orada ölçer.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

HOOK="$ROOT/.claude/hooks/block-prereg-writes.py"
fail() { echo "GEÇMEDİ — $1"; exit 1; }

PY=""
for cand in "${PYTHON:-}" python3 python; do
    [ -n "$cand" ] || continue
    if "$cand" -c "import pytest" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || fail "pytest içeren yorumlayıcı bulunamadı; PYTHON=... ile ver"
echo "# yorumlayıcı: $PY"

[ -f "$HOOK" ] || fail "$HOOK yok"

# ------------------------------------------------------------- 1  bağlama
echo "# 1  settings.json bağlaması + exec biti"
MODE="$(git ls-files -s -- .claude/hooks/block-prereg-writes.py | awk '{print $1}')"
[ "$MODE" = "100755" ] || fail "hook git index'inde $MODE (100755 olmalı) — shell onu çağıramaz"
"$PY" -I -c "
import json, sys
s = json.load(open('.claude/settings.json'))
wired = [e.get('matcher','') for e in s['hooks']['PreToolUse']
         if any('block-prereg-writes.py' in h.get('command','') for h in e.get('hooks', []))]
if not wired:
    sys.exit('PreToolUse\'a bağlı değil')
for tool in ('Write', 'Edit', 'MultiEdit', 'NotebookEdit'):
    if not any(tool in m for m in wired):
        sys.exit(f'{tool} kapsanmıyor')
" || fail "settings.json bağlaması eksik"

# ---------------------------------------------- geçici repo (gerçek dosya DEĞİL)
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
REPO="$TMP/repo"
mkdir -p "$REPO/docs"
git -C "$REPO" init -q
git -C "$REPO" config user.email "t@example.com"
git -C "$REPO" config user.name "t"
printf '# on kayit\n' >"$REPO/docs/PRE_REGISTRATION.md"

probe() {  # probe <dosya> -> çıkış kodu, stderr $PROBE_ERR'de
    PROBE_ERR="$(printf '{"tool_name":"Edit","cwd":"%s","tool_input":{"file_path":"%s"}}' \
        "$REPO" "$1" | CLAUDE_PROJECT_DIR="$REPO" "$PY" -I "$HOOK" 2>&1 >/dev/null)"
    return $?
}

# ------------------------------------------- 3  commit'lenmemiş taslak serbest
echo "# 3  commit'lenmemiş taslak"
probe "$REPO/docs/PRE_REGISTRATION.md"
[ $? -eq 0 ] || fail "A12 öncesi taslağa edit engellendi — kilit henüz kapanmadı, yazım serbest olmalı"

git -C "$REPO" add -A
git -C "$REPO" commit -qm "A12"

# -------------------------------------------------- 2  commit'li dosya kilitli
echo "# 2  commit'lenmiş dosya"
probe "$REPO/docs/PRE_REGISTRATION.md"
code=$?
[ $code -eq 2 ] || fail "commit'lenmiş ön kayda edit REDDEDİLMEDİ (çıkış $code, beklenen 2) — değişmez 6 yaptırımsız"
printf '%s' "$PROBE_ERR" | grep -q "PRE_REGISTRATION_v2.md" \
    || fail "red mesajı tek yasal yolu (v2) adlandırmıyor"

# ------------------------------------------------------- 4  v2 yolu açık kalmalı
echo "# 4  v2 yolu"
probe "$REPO/docs/PRE_REGISTRATION_v2.md"
[ $? -eq 0 ] || fail "v2 engellendi — yasal yolu kapatan kilit delinir, uygulanmaz"

# ------------------------------------------------------------- 5  birim testleri
echo "# 5  birim testleri"
"$PY" -m pytest tests/hooks/test_prereg_lock.py tests/hooks/test_pre_register.py \
    -q -o addopts="" || fail "H8'in testleri yeşil değil"

echo
echo "GEÇTİ — kilitli dosyaya edit reddediliyor, v2 yolu açık, taslak serbest"
