#!/usr/bin/env bash
# Kabul kriteri — A13: "her A maddesinin kriteri şablonda gerçekten var olan
# bölümü adlandırıyor; şablonun her bölümünün sahibi var; `A12` hepsine bağlı".
#
# Beş ölçüm. 2, 3 ve 4 ayırt edici olanlar — ve üçü de bu maddenin ilk
# yazdığım testinin NEDEN yanlış sebeple geçtiğini kapatıyor.
#
#   1  bugünkü durum yeşil (harita ↔ şablon ↔ yol haritası, iki yönde)
#   2  SAHİPSİZ BÖLÜM yakalanıyor: haritadaki bir bölümün sahibi silinince
#      kırmızı. §8 ve §9'un hiç sahibi olmaması bu maddenin sebebiydi.
#   3  SAYI ÖRTÜŞMESİ YETMİYOR: bir maddenin kriteri haritadaki bölümünden
#      BAŞKA bir sayıya çevrilince kırmızı. İlk testim yalnız "her numara bir
#      kriterde geçiyor mu" diye sorup GEÇMİŞTİ — çünkü `A8` §8'i, `A9` §9'u
#      rakam uyuştuğu için sahipleniyordu, oysa `A8` tespit filtresi, §8
#      durdurma kuralı. *Sayı saymak anlamsal uyum ölçmez.*
#   4  VAR OLMAYAN BÖLÜM yakalanıyor: şablonda olmayan bir § numarası kırmızı
#      (`A11` tam bunu yapıyordu: §11).
#   5  KİLİT BEKLİYOR: `A12`'nin bağımlılık grafiği her bölüm sahibine
#      geçişli olarak ulaşıyor — eksik bir kenar `next-fix`'in `A12`'yi erken
#      önermesine de yol açardı.
#
# ⚠️ 2-4 ölçümleri dosyaların KOPYASI üzerinde değil, dosyanın kendisinde
# geçici değişiklikle yapılır ve baytlar birebir geri yüklenir; betik bunu
# ayrıca doğrular. Bir kapı ölçüm yapmak için depoyu bozmamalı.

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

warn_untracked .claude docs tests || true

echo "# 1  bugünkü durum: harita, şablon ve yol haritası uyumlu"
ORCSONAR_SUITE_RECEIPT="$(mktemp -u)" "$PY" -m pytest \
    tests/hooks/test_prereg_sections.py -q -o addopts="" -p no:cacheprovider \
    >/dev/null || fail "eşleme testi bugünkü durumda bile kırmızı"
echo "  geçti"

echo "# 2-5  üç bozma denemesi ve kilit grafiği"
"$PY" - <<'INNER' || exit 1
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

MAP = Path(".claude/prereg_sections.yaml")
ROADMAP = Path("SCIENTIFIC_ROADMAP.md")
TESTS = "tests/hooks/test_prereg_sections.py"

problems: list[str] = []


# Bu çağrılar testleri KASTEN kırmızıya düşürüyor (mekanizmanın çalıştığını
# göstermenin başka yolu yok). Makbuz geçici bir yola yönlendirilmek zorunda,
# yoksa o kırmızı gerçek makbuzun "son koşu" alanında kalır ve `H7` sonraki
# commit'i reddeder — ölçüldü, `H22`.
_THROWAWAY_RECEIPT = tempfile.mkstemp(suffix=".json")[1]


def run_tests() -> int:
    done = subprocess.run(
        [sys.executable, "-m", "pytest", TESTS, "-q", "-o", "addopts=",
         "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
        timeout=180,
        env=dict(os.environ, ORCSONAR_SUITE_RECEIPT=_THROWAWAY_RECEIPT),
    )
    return done.returncode


# Bozma/geri yükleme `_perturb`'e devredildi (`H23`): tek uygulama, ve geri
# yüklerken bytecode'u geçersiz kılıyor. Bu kapı `.md`/`.yaml` bozuyor, ama
# yardımcının paylaşılması `.py` bozan ilk kapının sessizce yanlış-yeşil
# vermesini engelliyor — ölçülmüş tuzak, `H23`'ün satırında.
sys.path.insert(0, ".claude/hooks")
import _perturb  # noqa: E402


def perturb(path: Path, old: str, new: str, label: str) -> int | None:
    """Temporarily replace `old` with `new`, run the tests, restore exactly."""
    try:
        with _perturb.perturbed(path, old, new):
            return run_tests()
    except ValueError as exc:
        problems.append(f"{label}: {exc}")
        return None
    except RuntimeError as exc:  # geri yükleme başarısız — depo kirli
        problems.append(f"{label}: {exc}")
        return None


# ---- 2  sahipsiz bölüm ---------------------------------------------------
code = perturb(MAP, "    owners: [A14]", "    owners: []",
               "sahipsiz bölüm")
if code == 0:
    problems.append(
        "§8'in sahibi silindi ve testler yine geçti — sahipsiz bölüm "
        "yakalanmıyor (bu maddenin sebebi tam buydu)"
    )
elif code is not None:
    print("  2  sahipsiz bölüm → kırmızı")

# ---- 3  sayı örtüşmesi yetmiyor -----------------------------------------
# A14'ün kriteri §8'i adlandırıyor; §9'a çevirince harita ile çelişiyor.
# ⚠️ Çapalar DURUM hücresini içermiyor. İlk hali `| TODO |` ile bitiyordu ve
# `A14` kapandığı anda çapa kayboldu — kapı "bozulamadı" diye düştü, yani
# kendi ölçümünü yol haritasının durum sütununa bağlamak bir bayatlama
# kaynağıydı.
code = perturb(ROADMAP, "| §8'de koşu sayısı/koşulu sayıyla yazılı |",
               "| §9'da koşu sayısı/koşulu sayıyla yazılı |",
               "yanlış bölüm")
if code == 0:
    problems.append(
        "bir kriter haritadaki bölümünden başka bir sayıya çevrildi ve testler "
        "yine geçti — sayı örtüşmesi anlamsal uyum sanılıyor"
    )
elif code is not None:
    print("  3  kriter haritadan sapınca → kırmızı")

# ---- 4  var olmayan bölüm -----------------------------------------------
code = perturb(ROADMAP, "| §9'da negatif sonucun raporlanacağı yer ve içerik yazılı |",
               "| §11'de negatif sonucun raporlanacağı yer ve içerik yazılı |",
               "var olmayan bölüm")
if code == 0:
    problems.append(
        "şablonda olmayan §11'e işaret eden bir kriter testleri geçti — "
        "`A11`'in orijinal hatası yakalanmıyor"
    )
elif code is not None:
    print("  4  var olmayan bölüm → kırmızı")

# ---- 5  kilit her sahibe geçişli olarak bağlı ---------------------------
sys.path.insert(0, ".claude/hooks")
import yaml

import _status

items = {i.id: i for i in _status.parse_roadmap(ROADMAP.read_text(encoding="utf-8"))}
mapping = yaml.safe_load(MAP.read_text(encoding="utf-8"))["sections"]


def ancestors(item_id: str, seen: set[str] | None = None) -> set[str]:
    seen = set() if seen is None else seen
    item = items.get(item_id)
    if item is None:
        return seen
    for dep in item.deps:
        if dep not in seen:
            seen.add(dep)
            ancestors(dep, seen)
    return seen


reachable = ancestors("A12")
owners = {o for e in mapping.values() for o in (e.get("owners") or [])} - {"A12", "A1"}
missing = sorted(o for o in owners if o not in reachable)
if missing:
    problems.append(f"A12 şu sahiplere bağlı değil: {missing}")
else:
    print(f"  5  A12 {len(owners)} bölüm sahibinin hepsine geçişli olarak bağlı")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo
echo "GEÇTİ — her A maddesinin kriteri şablonda var olan bölümü adlandırıyor,"
echo "        her bölümün sahibi var, A12 hepsine geçişli olarak bağlı, ve"
echo "        mekanizma üç bozma denemesinin üçünde de kırmızıya düşüyor."
echo "        NOT: bölümlerin DOLDURULMASI bu madde değil — A2…A15'in işi."
