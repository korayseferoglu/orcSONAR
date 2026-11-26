#!/usr/bin/env bash
# Kabul kriteri — A1: "`docs/PRE_REGISTRATION.md` §1 mekanizmayı tek cümlede
# söylüyor".
#
# Dört ölçüm:
#   1  dosya var ve §1 bölümü mevcut
#   2  §1'de yer tutucu KALMAMIŞ — şablonun köşeli parantezleri bilerek boş
#      bırakılmış, ve doldurulmamış bir alan doldurulmuş gibi okunamaz
#   3  mekanizma cümlesi mekanizmayı söylüyor: **her iki iplik** ve seed
#      pozisyonu geçiyor. "Guide ipliğinin" demek tavanı düşürür (satırın
#      kendi uyarısı), o yüzden kapsamın yazılı olması kriterin özü.
#   4  tek cümle: ilk vurgulu ifade tek bir cümle (nokta sayısı 1)
#
# ⚠️ Kapı cümlenin DOĞRU olduğunu ölçmez — ölçemez. Mekanizmanın doğruluğu
# `E3a`'nın ampirik sorusu. Burada ölçülen şey, kararın **yazılı ve tek
# anlamlı** olduğu: ön kaydın işi sonucu belirlemek değil, sonradan
# değiştirilemez hale getirmek.

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
import pathlib
import re
import sys

path = pathlib.Path("docs/PRE_REGISTRATION.md")
if not path.is_file():
    sys.exit("docs/PRE_REGISTRATION.md yok — `pre-register` skill'i ile aç")

text = path.read_text(encoding="utf-8")
match = re.search(r"^## 1\. (.+?)$(.*?)(?=^## )", text, re.S | re.M)
if not match:
    sys.exit("§1 bölümü bulunamadı")
body = match.group(2)

problems: list[str] = []

# 2  yer tutucu kalmamış
leftovers = re.findall(r"<[^<>\n]{10,}>", body)
if leftovers:
    problems.append(f"§1'de doldurulmamış yer tutucu var: {leftovers[:2]}")

# 3  mekanizma kapsamı yazılı
if not re.search(r"her iki ipli", body):
    problems.append("§1 'her iki iplik' kapsamını söylemiyor")
if not re.search(r"2\s*[–-]\s*8", body):
    problems.append("§1 seed pozisyonunu (2–8) söylemiyor")
if "3′UTR" not in body and "3'UTR" not in body:
    problems.append("§1 3′UTR'yi söylemiyor")

# 4  mekanizma TEK cümlede
bold = re.findall(r"\*\*(.+?)\*\*", body, re.S)
mechanism = next((b for b in bold if "her iki ipli" in b), None)
if mechanism is None:
    problems.append("mekanizma cümlesi vurgulu (**…**) değil, bulunamıyor")
else:
    # Türkçe sıra sayısı ("2–8. pozisyon") nokta taşır, o yüzden rakamdan
    # sonraki nokta cümle sonu sayılmaz. İlk hali tam bu yüzden mekanizma
    # cümlesini iki cümle okudu.
    sentences = [
        s for s in re.split(r"(?<![0-9])\.(?:\s|$)", mechanism.strip()) if s.strip()
    ]
    if len(sentences) != 1:
        problems.append(
            f"mekanizma tek cümle değil ({len(sentences)} cümle): {mechanism[:70]}…"
        )
    else:
        print(f"  mekanizma cümlesi: {' '.join(mechanism.split())[:88]}…")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo
echo "GEÇTİ — §1 mekanizmayı tek cümlede söylüyor: her iki iplik, seed 2–8, 3′UTR."
echo "        NOT: kapı cümlenin doğruluğunu ölçmez; o E3a'nın ampirik sorusu."
