#!/usr/bin/env bash
# Kabul kriteri — H17: "`data/` yolu kullanan her test veri kapısını taşıyor,
# ve bunu bir kapı ölçüyor".
#
# ⚠️ **Önce yanlış enstrüman denendi ve atıldı.** İlk tasarım `ast` ile
# `tests/` içinde `data/` dizgisi arayıp `skipif` işareti olmayanı işaretliyordu.
# Ölçüm: **10 test, 6 dosyada** — ve hepsi yanlış pozitifti. O testler `data/`
# yolunu *okumuyor*, bir iddiada **anıyor** (`test_file_write_guard` hook'un o
# yolu engellediğini sınıyor; `test_the_literal_cache_path_appears_only_in_core_config`
# bir literali grepliyor). Anmayı okumaktan ayırmak statik olarak güvenilir
# değil, ve gürültülü bir kapı kapatılır (`H9`'un satırı aynı şeyi söylüyor).
#
# Doğru ölçüm ampirik ve tek yönlü değil: **`data/` olmadan takımı koş.** Bir
# test veri olmadan *atlıyorsa* kapısı var; *patlıyorsa* yok. `C3`'ün hatası
# tam böyle bulundu. Burada tahmin yok, davranış var.
#
# Üç ölçüm:
#   1  izlenen ağaç `data/` olmadan kurulur (CI'ın gördüğü ağacın aynısı)
#   2  takım orada koşar ve **hiçbir test başarısız olmaz** (atlama serbest)
#   3  izlenmeyen `tests/**` dosyası varsa kapı GEÇMEZ — `git ls-files` yalnız
#      indeksi görür, yani izlenmeyen bir test bu ölçümün dışında kalır ve
#      yerel-yeşil/CI-kırmızı tuzağı aynen tekrarlar (`H18`)

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

fail() { echo "GEÇMEDİ — $1"; exit 1; }

PY=""
for cand in "${PYTHON:-}" python3 python; do
    [ -n "$cand" ] || continue
    if "$cand" -c "import pytest" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || fail "pytest içeren yorumlayıcı bulunamadı; PYTHON=... ile ver"
echo "# yorumlayıcı: $PY"

echo "# 3  izlenmeyen test dosyası var mı"
UNTRACKED="$(git ls-files --others --exclude-standard -- tests | head -20)"
if [ -n "$UNTRACKED" ]; then
    echo "$UNTRACKED" | sed 's/^/  izlenmeyen: /'
    fail "izlenmeyen test dosyası var; bu ölçüm yalnız commit'lenmiş ağacı görür (H18) — git add + commit et"
fi
DIRTY="$(git status --porcelain -- tests src config rules Snakefile | head -20)"
if [ -n "$DIRTY" ]; then
    echo "$DIRTY" | sed 's/^/  commit'"'"'siz: /'
    fail "commit'siz değişiklik var; klon HEAD'i ölçer, yani çalışma ağacın ölçülmemiş kalır (H18)"
fi
echo "  yok"

WORK="$(mktemp -d)"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

echo "# 1  data/ olmadan temiz klon kuruluyor"
# Tarball DEĞİL, klon. `ci.yml`'in kendi yorumu bunu ölçmüş: `tests/hooks`
# dosya modlarını **git indeksinden** okuyor, ve bir `git archive` tarball'ına
# karşı 8 test patlıyor, temiz klona karşı geçiyor. İlk deneme tarball'dı ve
# tam o artefaktı üretti (13 başarısızlık), yani yöntem ölçmek istediği şeyi
# değil kendi eksiğini ölçüyordu.
git clone --quiet --no-hardlinks --shared . "$WORK/repo" \
    || fail "klon kurulamadı"
WORK="$WORK/repo"
# `data/external/` izlenen (manifest + README) ve kasıtlı; geri kalan data/
# depoda yok, tam CI'daki durum.
if [ -d "$WORK/data" ]; then
    LEFT="$(find "$WORK/data" -mindepth 1 -maxdepth 1 -not -name external | head -5)"
    [ -z "$LEFT" ] || fail "beklenmeyen data/ içeriği kopyalandı: $LEFT"
fi
echo "  $(find "$WORK" -name 'test_*.py' | wc -l) test dosyası · data/ altında yalnız external"

echo "# 2  takım data/ olmadan koşuyor, hiçbir test patlamıyor"
set +e
# `cd` into the clone is load-bearing. Several tests build data paths
# RELATIVE (`os.path.isfile("data/4_.../rna.stack.dg")`), so running pytest
# from the real repository resolved them against the real `data/` and the
# suite reported 1226 passed and **0 skipped** — green for exactly the
# wrong reason, which is the failure class this item is about. In the clone
# the data-dependent tests must SKIP, and measurement 2b checks that they do.
OUT="$(cd "$WORK" && "$PY" -m pytest -q -rs -o addopts="" -p no:cacheprovider tests 2>&1)"
CODE=$?
set -e
echo "$OUT" | tail -3 | sed 's/^/  /'
if echo "$OUT" | grep -qE "^[0-9]+ failed|[0-9]+ failed,"; then
    echo "$OUT" | grep -E "^FAILED" | head -10 | sed 's/^/  HATA /'
    fail "data/ olmadan test(ler) patlıyor — veri kapısı eksik"
fi
[ "$CODE" -eq 0 ] || fail "pytest çıkışı $CODE (toplama hatası olabilir)"

# 2b  Atlama SAYISI sıfır olamaz. `data/` yoksa veri-bağımlı testler atlamak
# ZORUNDA; sıfır atlama, klonun `data/`'yı bir şekilde bulduğu anlamına gelir
# ve kapı o zaman hiçbir şey ölçmemiş olur (bu tam olarak bir kez oldu).
SKIPPED="$(printf '%s' "$OUT" | grep -oE '[0-9]+ skipped' | head -1 | cut -d' ' -f1)"
if [ -z "${SKIPPED:-}" ] || [ "$SKIPPED" -eq 0 ]; then
    fail "hiç test atlanmadı — data/ bulunmuş olmalı, bu ölçüm geçersiz"
fi
echo "  $SKIPPED test atladı (veri yok, kapıları çalıştı)"

echo
echo "GEÇTİ — izlenen ağaç data/ olmadan kurulup koşuldu; her veri-bağımlı test"
echo "        atladı, hiçbiri patlamadı. Ölçüm tahmin değil davranış."
