#!/usr/bin/env bash
# Kabul kriteri — H5: "üçü de çalışıyor; fix-done geçmeyen maddeyi reddediyor".
#
# Dört ölçüm, hepsi gerçekten koşuyor:
#   1  next-fix    gerçek yol haritasında sıradaki maddeyi çözüyor
#   2  pre-register ön kayıt kilidini bildiriyor, hiçbir şey yazmadan
#   3  fix-done    GEÇMEYEN bir maddeyi reddediyor (kriterin asıl cümlesi)
#   4  üç betiğin birim testleri yeşil
#
# 3 numarası tek başına kritik: bir kapının yalnız "evet" diyebildiği
# durumda H5 yapılmamış sayılır (değişmez 3).

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

SKILLS=".claude/skills"
NEXT_FIX="$SKILLS/next-fix/scripts/next_fix.py"
FIX_DONE="$SKILLS/fix-done/scripts/fix_done.py"
PRE_REGISTER="$SKILLS/pre-register/scripts/pre_register.py"

fail() { echo "GEÇMEDİ — $1"; exit 1; }

# pytest'i olan bir yorumlayıcı bul; bulunamazsa GEÇME (sessizce atlama).
PY=""
for cand in "${PYTHON:-}" python3 python; do
    [ -n "$cand" ] || continue
    if "$cand" -c "import pytest" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || fail "pytest içeren yorumlayıcı bulunamadı; PYTHON=... ile ver (.claude/acceptance/README.md)"

echo "# yorumlayıcı: $PY"

# ---------------------------------------------------------------- 1  next-fix
echo "# 1  next-fix"
"$PY" -I "$NEXT_FIX" --json >/dev/null 2>&1 || fail "next-fix gerçek yol haritasında çalışmıyor"

# ----------------------------------------------------------- 2  pre-register
echo "# 2  pre-register --check"
"$PY" -I "$PRE_REGISTER" --check >/dev/null 2>&1 || fail "pre-register --check çalışmıyor"
[ -f docs/PRE_REGISTRATION.md ] && fail "--check dosya yazmış olmamalı (A12 henüz TODO)"

# --------------------------------------------------- 3  fix-done bir maddeyi reddediyor
echo "# 3  fix-done geçmeyen maddeyi reddediyor"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cat >"$TMP/ROADMAP.md" <<'EOF'
### FAZ 9 — Kabul testi fazı

| **Z1** | kapısı geçmeyen iş | — | kabul betiği kırmızı | TODO |
EOF
mkdir -p "$TMP/acceptance"
printf '#!/usr/bin/env bash\necho "kasten kirmizi"\nexit 1\n' >"$TMP/acceptance/Z1.sh"
chmod +x "$TMP/acceptance/Z1.sh"

"$PY" -I "$FIX_DONE" Z1 --roadmap "$TMP/ROADMAP.md" --acceptance-dir "$TMP/acceptance" \
    --red-first "kabul testi: bu madde kasten kırmızı" >"$TMP/out.txt" 2>&1
code=$?
[ "$code" -eq 1 ] || fail "geçmeyen madde reddedilmedi (çıkış $code, beklenen 1)"
grep -q "REDDEDİLDİ" "$TMP/out.txt" || fail "red gerekçesi basılmadı"
grep -q "kasten kirmizi" "$TMP/out.txt" || fail "kapının kendi çıktısı gösterilmedi"

# Kanıtsız kapanış da reddedilmeli (değişmez 5).
"$PY" -I "$FIX_DONE" Z1 --roadmap "$TMP/ROADMAP.md" --acceptance-dir "$TMP/acceptance" \
    >/dev/null 2>&1
[ $? -eq 1 ] || fail "kırmızı-önce kanıtı olmadan kapanış reddedilmedi"

# ------------------------------------------------------------------ 4  testler
echo "# 4  birim testleri"
"$PY" -m pytest tests/hooks/test_next_fix.py tests/hooks/test_fix_done.py \
    tests/hooks/test_pre_register.py -q -o addopts="" || fail "üç skill'in testleri yeşil değil"

echo "GEÇTİ — üçü de çalışıyor ve fix-done geçmeyen maddeyi reddediyor"
