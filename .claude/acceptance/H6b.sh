#!/usr/bin/env bash
# Kabul kriteri — H6b: Actions'da yeşil koşu VE `main` için zorunlu kontrol.
#
# Dört ölçüm:
#   1  gh var ve giriş yapılmış (yoksa GEÇMEZ — sessizce atlamaz)
#   2  HEAD için CI koşusu var ve sonucu success
#   3  `main`'i hedefleyen aktif bir kural status check zorunlu kılıyor
#   4  zorunlu tutulan ad GERÇEKTEN var olan bir kontrol adıyla eşleşiyor
#
# 4 numarası bu maddenin bütün sebebi. GitHub boş bir liste de, var olmayan bir
# ad da kabul eder: kural "active" görünür, ayar sayfası yeşildir ve hiçbir
# merge engellenmez. Bu repoda tam olarak bu oldu — `main-2` ruleset'i aktifti
# ve `required_status_checks: []` ile hiçbir şey zorunlu tutmuyordu.
#
# ⚠️ 403 "no rule" DEĞİLDİR. Private repo + ücretsiz planda bu endpoint'ler
# okumaya kapalı ve 403 döner; kural olmadığı anlamına gelmez (değişmez 2).
# Bu betik 403'ü ayrı bir arıza olarak bildirir, "koruma yok" diye okumaz.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

fail() { echo "GEÇMEDİ — $1"; exit 1; }

# ------------------------------------------------------------------ 1  gh
GH=""
for cand in "${GH_BIN:-}" gh "$HOME/.local/bin/gh"; do
    [ -n "$cand" ] || continue
    command -v "$cand" >/dev/null 2>&1 && { GH="$cand"; break; }
    [ -x "$cand" ] && { GH="$cand"; break; }
done
[ -n "$GH" ] || fail "gh bulunamadı — bu kriter GitHub tarafını okumadan ölçülemez"
"$GH" auth status >/dev/null 2>&1 || fail "gh giriş yapılmamış (gh auth login)"

REPO="$(git config --get remote.origin.url | sed -E 's#.*github\.com[:/]##; s#\.git$##')"
[ -n "$REPO" ] || fail "origin uzak deposu okunamadı"
echo "# repo: $REPO"

api() { "$GH" api "$@" 2>&1; }

# ------------------------------------------------------- 2  HEAD için yeşil koşu
HEAD_SHA="$(git rev-parse HEAD)"
RUNS="$(api "repos/$REPO/actions/runs?head_sha=$HEAD_SHA&per_page=5")"
case "$RUNS" in *'"status":"403"'*) fail "koşu listesi 403 — ÖLÇÜLMEDİ, 'koşu yok' ile karıştırma";; esac
CONCL="$(printf '%s' "$RUNS" | python3 -I -c "
import json, sys
runs = json.load(sys.stdin).get('workflow_runs', [])
ci = [r for r in runs if r.get('name') == 'CI']
print(ci[0]['conclusion'] if ci else '')
" 2>/dev/null)"
echo "# 2  HEAD ${HEAD_SHA:0:8} için CI sonucu: ${CONCL:-koşu yok}"
case "$CONCL" in
    success) ;;
    "")     fail "HEAD için hiç CI koşusu yok — commit push edildi mi?";;
    None|null) fail "HEAD için koşu henüz bitmedi (sürüyor) — bitmesini bekle, tekrar koş";;
    *)      fail "HEAD için CI koşusu yeşil değil (sonuç: $CONCL)";;
esac

# ------------------------------------------- 3  main'de zorunlu kontrol var mı
CONTEXTS=""

RULESETS="$(api "repos/$REPO/rulesets")"
case "$RULESETS" in
    *'"status":"403"'*) fail "rulesets 403 — plan/görünürlük kısıtı, ÖLÇÜLMEDİ (kural yok DEMEK DEĞİL)";;
esac
IDS="$(api "repos/$REPO/rulesets" --jq '.[] | select(.enforcement=="active") | .id' 2>/dev/null)"
for id in $IDS; do
    TARGETS="$(api "repos/$REPO/rulesets/$id" --jq '.conditions.ref_name.include[]?' 2>/dev/null)"
    case "$TARGETS" in *"refs/heads/main"*|*"~DEFAULT_BRANCH"*) ;; *) continue;; esac
    FOUND="$(api "repos/$REPO/rulesets/$id" \
        --jq '[.rules[] | select(.type=="required_status_checks") | .parameters.required_status_checks[]?.context] | join(" ")' 2>/dev/null)"
    [ -n "$FOUND" ] && CONTEXTS="$CONTEXTS $FOUND"
done

CLASSIC="$(api "repos/$REPO/branches/main/protection" --jq '.required_status_checks.contexts[]?' 2>/dev/null)"
case "$CLASSIC" in *'"status":"40'*) CLASSIC="";; esac
[ -n "$CLASSIC" ] && CONTEXTS="$CONTEXTS $CLASSIC"

CONTEXTS="$(printf '%s' "$CONTEXTS" | tr ' ' '\n' | grep -v '^$' | sort -u | tr '\n' ' ')"
echo "# 3  main için zorunlu kontrol(ler): ${CONTEXTS:-HİÇBİRİ}"
[ -n "$CONTEXTS" ] || fail "main'i hedefleyen aktif bir kural var olabilir, ama zorunlu kontrol listesi BOŞ — hiçbir merge engellenmez"

# --------------------------------------- 4  zorunlu ad gerçek bir kontrol mü
REAL="$(api "repos/$REPO/commits/$HEAD_SHA/check-runs" --jq '.check_runs[].name' 2>/dev/null | sort -u)"
[ -n "$REAL" ] || fail "HEAD için hiç check-run okunamadı, ad eşleşmesi ÖLÇÜLMEDİ"
echo "# 4  gerçekte koşan kontroller: $(printf '%s' "$REAL" | tr '\n' ' ')"
for ctx in $CONTEXTS; do
    printf '%s\n' "$REAL" | grep -qxF "$ctx" \
        || fail "zorunlu tutulan '$ctx' gerçekte koşan bir kontrol adı değil — kural yeşil görünür, hiçbir şeyi engellemez"
done

echo
echo "GEÇTİ — HEAD için CI yeşil, main'de zorunlu kontrol var ve adı gerçek: $CONTEXTS"
