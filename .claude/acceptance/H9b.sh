#!/usr/bin/env bash
# Kabul kriteri — H9b: dosya sırası ile satır-içi her sıralama beyanı uyuşuyor.
#
# Yol haritasında sıra TEK bir mekanizmayla okunur: `_status.ready_items`
# "bağımlılığı karşılanmış ilk TODO"yu **dosya sırasına** göre seçer. Bir
# satırın prose'u buna aykırı bir sıra beyan ederse, "ne hangi sırayla"
# gerçeği aynı otorite dosyasının içinde iki kez ve çelişkili yazılmış olur:
# biri makineyle, biri insanla okunan. 2026-11-26'da tam bu oldu — `H7`'nin
# satırı `H9`'u işaret ederken `next-fix` `H7` diyordu.
#
# Ölçüm: bir satırın prose'unda ok ile bağlanmış her `a` → `b` madde çifti
# için, dosya sırası ZATEN `a`'yı `b`'den önce koymalı. Koymuyorsa beyan
# makinenin göremediği bir sıra iddiasıdır ve kapı kırmızıdır.
#
# ⚠️ Bilerek YAPILMAYAN şey: çifti bağımlılık hücresine çevirmek. "a önce
# gelsin" ile "b, a'ya bağımlı" aynı şey değildir — `H7` sıralaması bir
# öncelik yargısıydı, teknik bir zorunluluk değil, ve onu bağımlılık olarak
# yazmak `H7`'yi `H11` bitene kadar erişilemez göstererek yol haritasına
# yanlış bir kenar eklerdi. Sıra konumla ifade edilir; bağımlılık hücresi
# yalnız gerçek zorunluluklar için.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

fail() { echo "GEÇMEDİ — $1"; exit 1; }

PY=""
for cand in "${PYTHON:-}" python3 python; do
    [ -n "$cand" ] || continue
    if "$cand" -c "import sys" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || fail "yorumlayıcı bulunamadı; PYTHON=... ile ver"
echo "# yorumlayıcı: $PY"

"$PY" -I - <<'INNER' || exit 1
import re
import sys

sys.path.insert(0, ".claude/hooks")

import _status

text = open("SCIENTIFIC_ROADMAP.md", encoding="utf-8").read()
items = _status.parse_roadmap(text)
position = {item.id: index for index, item in enumerate(items)}

# `\`A\` → \`B\`` ya da `\`A\` -> B`. Ok şart: virgülle ayrılmış bir liste
# sıra beyan etmez, "şu maddeler" der.
PAIR = re.compile(r"`([A-Za-z]+[0-9]+[a-z]?)`\s*(?:→|->)\s*`?([A-Za-z]+[0-9]+[a-z]?)`?")

def contradictions(work: str, pos: dict[str, int]) -> tuple[list[str], int]:
    """Ordering claims in `work` that `pos` does not already satisfy."""
    found: list[str] = []
    seen = 0
    for match in PAIR.finditer(work):
        first, second = match.group(1), match.group(2)
        if first not in pos or second not in pos:
            continue
        seen += 1
        if pos[first] >= pos[second]:
            found.append(
                f"prose '{match.group(0)}' diyor, ama dosya sırası "
                f"{second} ({pos[second]}) satırını {first} "
                f"({pos[first]}) satırından ÖNCE koyuyor"
            )
    return found, seen


# Kapının kendisi kırmızı olabiliyor mu? Bugün yol haritasında yalnız BİR
# sıralama beyanı var; regex bozulsa kapı sessizce sıfır şey denetleyip
# "GEÇTİ" yazardı — `.claude/acceptance/README.md`'deki `exit 0` tuzağı.
# O yüzden dedektör her koşuda bilinen-kötü bir örnek üzerinde sınanıyor.
probe, probe_seen = contradictions("`Z9` → `Z1`", {"Z1": 0, "Z9": 1})
if probe_seen != 1 or len(probe) != 1:
    sys.exit(
        "GEÇMEDİ — dedektör bilinen-kötü örneği yakalamadı; kapı ölçüm "
        f"yapmıyor (görülen={probe_seen}, bulunan={len(probe)})"
    )
print("# dedektör öz-sınaması: bilinen-kötü çift yakalandı")

problems: list[str] = []
checked = 0
for item in items:
    found, seen = contradictions(item.work, position)
    checked += seen
    problems.extend(f"{item.id}: {f}" for f in found)

for problem in problems:
    print(f"  HATA {problem}")

print()
print(f"# {checked} sıralama beyanı denetlendi, {len(items)} madde")
if problems:
    print()
    print(
        f"GEÇMEDİ — {len(problems)} beyan dosya sırasıyla çelişiyor; sıra iki "
        "yerde yazılı ve biri makinenin görmediği yerde"
    )
    sys.exit(1)
print("GEÇTİ — satır-içi her sıralama beyanı dosya sırasıyla uyumlu")
INNER
