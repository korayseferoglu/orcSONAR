#!/usr/bin/env bash
# Kabul kriteri — H9: "otorite tablosu yazılı; kapı CI'da".
#
# Kriterin iki yarısı iki ayrı şekilde arızalanır, o yüzden ayrı ayrı ölçülür:
#   1  otorite tablosu yazılı  — `00-degismezler.md`'de id kolonlu tablo, ve
#      makine-okunur `.claude/authority.yaml` ile BİREBİR aynı id kümesi
#   2  kapı koşuyor ve temiz   — hiçbir dosya otoritesi olmadığı bir kanonik
#      gerçeği ifade etmiyor; her carve-out onu kaldıracak maddeyi adlandırıyor
#   3  kapı CI'da              — iş akışı gerçekten çağırıyor ve bloke edici
#   4  kapı kırmızı olabiliyor — birim testleri, yeni bir kopyanın yakalandığı
#      durum dahil
#
# 4'ü atlamak kapıyı anlamsız yapardı: hiçbir şey taramayan bir betik de
# "GEÇTİ" yazar (`.claude/acceptance/README.md`, "exit 0 yazma tuzağı").
# Kırmızı-olabilirlik bu yüzden kriterin parçası, eklenti değil.

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

warn_untracked . || true

# ------------------------------------------------- 1  otorite tablosu yazılı
echo "# 1  otorite tablosu id kolonlu ve kayıtla aynı"
grep -q '^| id | gerçek | otorite |' .claude/rules/00-degismezler.md \
    || fail "00-degismezler.md'de id kolonlu otorite tablosu yok"
[ -f .claude/authority.yaml ] || fail ".claude/authority.yaml yok"

# ------------------------------------- 2  kapı temiz (tablo↔kayıt dahil)
# Çıkış 2 = ölçüm yapılamadı; 1 = ihlal var. İkisi de geçmez, ama ayrı yazılır
# çünkü okunamayan bir kayıt asla "temiz" diye okunmamalı.
echo "# 2  kapı temiz"
"$PY" .claude/hooks/check-single-copy.py
rc=$?
case "$rc" in
    0) : ;;
    2) fail "kapı ölçüm yapamadı (çıkış 2) — okunamayan kayıt temiz sayılmaz" ;;
    *) fail "kapı ihlal buldu (çıkış $rc)" ;;
esac

# ------------------------------------------------------------- 3  kapı CI'da
echo "# 3  kapı CI'da ve bloke edici"
WF=".github/workflows/ci.yml"
[ -f "$WF" ] || fail "$WF yok"
grep -q "check-single-copy.py" "$WF" \
    || fail "CI iş akışı tek-kopya kapısını çağırmıyor — kriterin ikinci yarısı"
"$PY" -I - <<'INNER' || fail "CI adımı bloke edici değil"
import sys

import yaml

wf = yaml.safe_load(open(".github/workflows/ci.yml", encoding="utf-8"))
steps = wf["jobs"]["gate"]["steps"]
hits = [s for s in steps if "check-single-copy.py" in str(s.get("run", ""))]
if not hits:
    sys.exit("CI'da tek-kopya adımı yok")
for step in hits:
    if step.get("continue-on-error"):
        sys.exit(f"adım bloke edici değil: {step.get('name')!r}")
    if "pip install" in str(step.get("run", "")):
        sys.exit("adım kendi başına kurulum yapıyor (test_ci_workflow bunu yasaklıyor)")
print(f"  {len(hits)} bloke edici adım")
INNER

# ------------------------------------------------- 4  kapı kırmızı olabiliyor
echo "# 4  birim testleri (yeni bir kopya yakalanıyor dahil)"
"$PY" -m pytest tests/hooks/test_single_copy.py -q -o addopts="" -p no:cacheprovider \
    || fail "tek-kopya kapısının testleri yeşil değil"

echo
echo "GEÇTİ — otorite tablosu id kolonlu ve kayıtla birebir; kapı temiz, CI'da,"
echo "        bloke edici, ve yeni bir kopyayı yakaladığı testle kanıtlı."
