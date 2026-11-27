#!/usr/bin/env bash
# Kabul kriteri — H24: "dedektör AST üzerinden çalışıyor; docstring'de
# 'shuffle' geçen modül yanlış-pozitif vermiyor VE `default_rng()` kullanan
# sentetik modül yakalanıyor".
#
# Dokuz ölçüm. 2, 3, 4, 5 ve 6 ayırt edici olanlar, ve ikisi İKİ AYRI YÖNÜ
# ölçüyor: yanlış-pozitif (canlı yaşanan) ve yanlış-NEGATİF (tehlikeli olan).
#
#   1  KOD: metinsel grep gitti, `ast.parse` geldi
#   2  DAVRANIŞ, ayırt edici: docstring'i "shuffling"/"random" diyen ama
#      örnekleme YAPMAYAN modül işaretlenmiyor — `B11c`'de tam takımı
#      kırmızıya düşüren şekil
#   3  DAVRANIŞ, ayırt edici (TEHLİKELİ YÖN): `default_rng()` iki biçimde de
#      yakalanıyor (`np.random.default_rng()` ve çıplak `default_rng()`).
#      Eski desen ikisini de GÖRMÜYORDU, yani manifest "rastgelelik yok"
#      diye yanlış-YEŞİL verebilirdi
#   4  DAVRANIŞ, ayırt edici: takma adlı modül yakalanıyor
#      (`import random as rnd`) — isme bakan bir kontrolün en kolay kaçağı
#   5  KONTROL, ayırt edici: alan nesnesinin `.sample(` metodu
#      işaretlenmiyor. Bu olmadan 3. ve 4. ölçüm "her şeyi işaretle" ile de
#      geçerdi, ki o eski hatanın kendisi
#   6  KOD + DAVRANIŞ, ayırt edici: dedektör kendi dosyasını MUAF TUTMUYOR
#      ve kendi kaynağında bir şey bulmuyor — eski probe kendini greplediği
#      için carve-out'a mecburdu
#   7  DAVRANIŞ: ayrıştırılamayan dosya raporlanıyor, atlanmıyor
#      (değişmez 2: okunamayan bilinmiyor, temiz değil)
#   8  CANLI: boru hattı rastgelelik bildirmiyor VE taranan dosya sayısı
#      anlamlı — boş bir listede "rastgelelik yok" bir ölçüm değil
#   9  DETERMİNİZM: bulgular sıralı, yani aynı ağaç iki koşuda birebir aynı
#      provenansı veriyor
#
# ⚠️ Ağ istemiyor.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

fail() { echo "GEÇMEDİ — $1"; exit 1; }

# shellcheck source=_lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

PY=""
for cand in "${PYTHON:-}" python3 python; do
    [ -n "$cand" ] || continue
    if "$cand" -c "import pytest" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || fail "pytest içeren yorumlayıcı bulunamadı; PYTHON=... ile ver"
echo "# yorumlayıcı: $PY"

warn_untracked src tests .claude || true

"$PY" - <<'INNER' || exit 1
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")

from src.core.run_manifest import (  # noqa: E402
    randomness_findings,
    stochastic_components,
)

MODULE = Path("src/core/run_manifest.py")
problems: list[str] = []
source = MODULE.read_text(encoding="utf-8")


def write(directory: Path, body: str, name: str = "probe.py") -> Path:
    target = directory / name
    target.write_text(body, encoding="utf-8")
    return target


# ---- 1  KOD: grep gitti, AST geldi --------------------------------------
if "ast.parse" not in source:
    problems.append("`run_manifest` artık `ast.parse` kullanmıyor")
elif re.search(r'"grep",\s*\n?\s*"-lE"', source):
    problems.append(
        "metinsel `git grep -lE` probe'u hâlâ duruyor — AST'ye geçiş yarım"
    )
else:
    print("  1  kod: metinsel grep yok, `ast.parse` var")

with tempfile.TemporaryDirectory() as tmp:
    work = Path(tmp)
    quote = chr(34) * 3

    # ---- 2  YANLIŞ-POZİTİF yönü: düzyazı ------------------------------
    prose = write(work, (
        "def chance_hits(motifs, length):\n"
        "    " + quote + "A permuted null tracks the observation.\n"
        "\n"
        "    Shuffling the sequence preserves its uridine content, so the\n"
        "    shuffled null cancels the signal. A random 20-mer scores 0.56,\n"
        "    and np.random.sample( would be the wrong tool here.\n"
        "    " + quote + "\n"
        "    # random.shuffle would also be wrong; secrets. too\n"
        "    return sum(2 * (length - len(m) + 1) * 0.25 ** len(m) for m in motifs)\n"
    ), "prose.py")
    found = randomness_findings([prose])
    if found:
        problems.append(
            f"docstring/yorum rastgelelik sayıldı: {found} — `B11c`'de tam "
            "takımı kırmızıya düşüren şekil hâlâ açık"
        )
    else:
        print("  2  düzyazı (docstring + yorum) işaretlenmiyor")

    # ---- 3  YANLIŞ-NEGATİF yönü: default_rng -------------------------
    attribute_form = write(work, (
        "import numpy as np\n"
        "\n"
        "\n"
        "def draw(n):\n"
        "    rng = np.random.default_rng()\n"
        "    return rng.normal(size=n)\n"
    ), "attr.py")
    bare_form = write(work, (
        "from numpy.random import default_rng\n"
        "\n"
        "RNG = default_rng(7)\n"
    ), "bare.py")
    # ⚠️ Üçüncü biçim kapıyı yazarken ÖLÇÜLEREK eklendi: ilk iki biçim
    # `numpy` kurallarıyla da yakalanıyor, o yüzden `_STOCHASTIC_NAMES`'ten
    # `default_rng`'yi çıkarmak kapıyı GEÇİYORDU. Yerel bir yeniden-ihraç
    # yalnız o kümeyle yakalanıyor.
    reexport_form = write(work, (
        "from mylib.helpers import default_rng\n"
        "\n"
        "RNG = default_rng(7)\n"
    ), "reexport.py")
    # Ve dördüncüsü takma ad ÇÖZÜMLEMESİNİ yalıtıyor: `import numpy as np`
    # kendisi bulgu değil, yani takma ad izlenmezse çağrı görünmez olur.
    alias_only_form = write(work, (
        "import numpy as np\n"
        "\n"
        "\n"
        "def pick(items):\n"
        "    return np.random.choice(items)\n"
    ), "aliasonly.py")
    missed = [
        name for name, path in (("np.random.default_rng()", attribute_form),
                                ("bare default_rng()", bare_form),
                                ("locally re-exported default_rng()", reexport_form),
                                ("np.random.choice via alias", alias_only_form))
        if not randomness_findings([path])
    ]
    alias_findings = randomness_findings([alias_only_form])
    if alias_findings and any("import" in f["construct"] for f in alias_findings):
        problems.append(
            "takma ad vakası import kaydıyla yakalanıyor, çağrı çözümlemesiyle "
            "değil — ölçüm takma ad takibini yalıtmıyor"
        )
    if missed:
        problems.append(
            f"örnekleme KAÇIRILDI: {missed} — eski desenin göremediği biçim, "
            "ve manifest bu durumda yanlış-YEŞİL verir"
        )
    else:
        print("  3  tehlikeli yön kapalı: default_rng üç biçimde de yakalanıyor "
              "(numpy attribute, numpy.random import, yerel yeniden-ihraç) ve "
              "takma ad çözümlemesi çağrıdan yakalıyor")

    # ---- 4  takma ad --------------------------------------------------
    aliased = write(work, (
        "import random as rnd\n"
        "\n"
        "\n"
        "def pick(items):\n"
        "    return rnd.choice(items)\n"
    ), "alias.py")
    if not randomness_findings([aliased]):
        problems.append("`import random as rnd` yakalanmıyor — isme bakan bir kaçak")
    else:
        print("  4  takma adlı modül yakalanıyor")

    # ---- 5  KONTROL: alan metodu --------------------------------------
    domain = write(work, (
        "def read(curve, points):\n"
        "    return curve.sample(points)\n"
    ), "domain.py")
    label = write(work, (
        'random_label = "control"\n'
        "\n"
        "\n"
        "def label():\n"
        "    return random_label\n"
    ), "label.py")
    noise = [
        name for name, path in (("curve.sample(...)", domain),
                                ("random_label değişkeni", label))
        if randomness_findings([path])
    ]
    if noise:
        problems.append(
            f"sıradan kod rastgelelik sayıldı: {noise} — 3. ve 4. ölçüm 'her "
            "şeyi işaretle' ile de geçerdi"
        )
    else:
        print("  5  kontrol: `.sample(` metodu ve `random_label` işaretlenmiyor")

    # ---- 7  ayrıştırılamayan dosya ------------------------------------
    broken = write(work, "def broken(\n", "broken.py")
    broken_findings = randomness_findings([broken])
    if not broken_findings:
        problems.append(
            "ayrıştırılamayan dosya 'rastgelelik yok' olarak okundu — "
            "yanlış-yeşil (değişmez 2)"
        )
    elif not any("unparseable" in f["construct"] for f in broken_findings):
        problems.append(f"ayrıştırma hatası bildirilmiyor: {broken_findings}")
    else:
        print("  7  ayrıştırılamayan dosya raporlanıyor, atlanmıyor")

    # ---- 9  DETERMİNİZM ----------------------------------------------
    one = randomness_findings([bare_form, attribute_form, aliased])
    two = randomness_findings([aliased, attribute_form, bare_form])
    if one != two:
        problems.append(
            "bulgular girdi sırasına bağlı — aynı ağaç iki koşuda farklı "
            "provenans verir"
        )
    else:
        print(f"  9  determinizm: {len(one)} bulgu, girdi sırasından bağımsız")

# ---- 6  kendi dosyasını muaf tutmuyor -----------------------------------
if ":!src/core/run_manifest.py" in source:
    problems.append(
        "dedektör kendi dosyasını hâlâ muaf tutuyor — AST ile buna gerek yok, "
        "ve gereksiz bir muafiyet sessizce gerçek bir bulguyu gizleyebilir"
    )
else:
    self_findings = randomness_findings([MODULE])
    if self_findings:
        problems.append(f"dedektör kendi kaynağını işaretliyor: {self_findings}")
    else:
        print("  6  kendi dosyası muaf DEĞİL ve kendi kaynağında bulgu yok")

# ---- 8  CANLI ------------------------------------------------------------
claim = stochastic_components(Path("."))
if claim["present"] is not False:
    problems.append(f"boru hattı rastgelelik bildiriyor: {claim.get('findings')}")
elif int(claim.get("scanned", 0)) <= 50:
    problems.append(
        f"probe yalnız {claim.get('scanned')} dosya taradı — boş bir listede "
        "'rastgelelik yok' bir ölçüm değil"
    )
elif "ast" not in str(claim.get("evidence", "")).lower():
    problems.append("iddia nasıl kurulduğunu söylemiyor (`evidence` AST demiyor)")
else:
    print(f"  8  canlı: {claim['scanned']} dosya tarandı, rastgelelik yok, "
          "ve iddia yöntemini söylüyor")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo "# birim testleri"
ORCSONAR_SUITE_RECEIPT="$(mktemp -u)" "$PY" -m pytest \
    tests/unit/test_randomness_detector.py tests/unit/test_run_manifest.py \
    -q -o addopts="" -p no:cacheprovider || fail "H24 birim testleri yeşil değil"

echo
echo "GEÇTİ — rastgelelik dedektörü AST üzerinden çalışıyor: düzyazı"
echo "        işaretlenmiyor (canlı yaşanan yanlış-pozitif), \`default_rng()\`"
echo "        iki biçimde de yakalanıyor (eski desenin göremediği ve manifest'i"
echo "        yanlış-YEŞİL yapacak olan yön), takma ad kaçağı kapalı, ve"
echo "        kontrol ölçümü sıradan \`.sample(\` çağrısının işaretlenmediğini"
echo "        gösteriyor. Dedektör artık kendi dosyasını muaf tutmuyor."
