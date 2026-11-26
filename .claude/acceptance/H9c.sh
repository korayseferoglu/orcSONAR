#!/usr/bin/env bash
# Kabul kriteri — H9c: "carve-out sayısı 0; kapı carve-out'suz yeşil".
#
# Kriterin "0"ı `H9c`'ye ATFEDİLEN carve-out'lar için. Satır bunu baştan
# söylüyordu: `src/scoring/domain_scores.py` + `tests/unit/test_scoring.py`
# kopyaları `B8`'e (ölü modülün silinmesi), `delta_g_calculator.py` kopyası
# `B13`'e bağlı — onlar o maddeler kapanınca kendiliğinden gider ve bu
# maddenin işi değil. Kapsam daraltması sonradan değil, iş başlamadan
# yazılmıştı; değişmez 7'nin yasakladığı şey sonucu görüp kriteri gevşetmek.
#
# Dört ölçüm:
#   1  `H9c`'ye bağlı carve-out YOK
#   2  kalan her carve-out hâlâ AÇIK bir maddeyi gösteriyor
#   3  tek-kopya kapısı temiz (doğrulanmış kopyaların değer denetimi dahil)
#   4  doğrulanmış-kopya mekanizması kırmızı olabiliyor (birim testleri)
#
# 4 olmadan 3 anlamsız: her sayıyı "doğrulanmış kopya" ilan edip hiçbirini
# karşılaştırmayan bir kayıt da yeşil verir.

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

echo "# 1-2  carve-out muhasebesi"
"$PY" -I - <<'INNER' || fail "carve-out muhasebesi geçmedi"
import sys

import yaml

sys.path.insert(0, ".claude/hooks")

import _status

registry = yaml.safe_load(open(".claude/authority.yaml", encoding="utf-8"))
items = {
    i.id.lower(): i.status
    for i in _status.parse_roadmap(
        open("SCIENTIFIC_ROADMAP.md", encoding="utf-8").read()
    )
}

mine: list[str] = []
stale: list[str] = []
remaining: list[str] = []
for fact in registry["facts"]:
    for carve in fact.get("carve_outs") or []:
        target = str(carve["roadmap"])
        label = f"{target} ({carve['path']})"
        if target.lower() == "h9c":
            mine.append(label)
            continue
        remaining.append(label)
        status = items.get(target.lower())
        if status is None or _status.is_done(status):
            stale.append(f"{label} — durum: {status!r}")

for line in mine:
    print(f"  HATA H9c'ye bağlı carve-out kaldı: {line}")
for line in stale:
    print(f"  HATA carve-out açık olmayan bir maddeyi gösteriyor: {line}")

print(f"  H9c'ye bağlı: {len(mine)} · başka maddelere bağlı (meşru): {len(remaining)}")
for line in sorted(remaining):
    print(f"    devredildi → {line}")
sys.exit(1 if (mine or stale) else 0)
INNER

echo "# 3  tek-kopya kapısı temiz"
"$PY" .claude/hooks/check-single-copy.py >/dev/null || fail "tek-kopya kapısı temiz değil"

echo "# 4  doğrulanmış-kopya mekanizması kırmızı olabiliyor"
"$PY" -m pytest tests/hooks/test_single_copy.py -q -o addopts="" -p no:cacheprovider \
    -k "VerifiedCopies or Resolvers" \
    || fail "doğrulanmış-kopya testleri yeşil değil"

echo
echo "GEÇTİ — H9c'ye bağlı hiçbir carve-out kalmadı; kalanlar açık maddelere"
echo "        devredildi, kapı temiz, ve değer denetimi testle kanıtlı."
