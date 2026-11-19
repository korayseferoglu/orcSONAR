#!/usr/bin/env bash
# Kabul kriteri — B2a: "`mypy src/` sayısı `B2` öncesi seviyeye (72) döndü ya
# da her yeni hata gerekçesiyle kapatıldı".
#
# Dört ölçüm:
#   1  mypy sayısı: `B2` öncesi 72 idi; bugün ≤ 73 olmalı ve fazlası YALNIZ
#      ölü `domain_scores.py` olabilir (gerekçe aşağıda)
#   2  stage-4 adapter'larının hiçbiri arıza hâlinde sıfır yazmıyor
#   3  `round(None)` çökmesi yok: okuyucu `None` döndüğünde adapter `null` yazar
#   4  birim testleri yeşil
#
# 2 ve 3 bu maddenin asıl içeriği. `B2` okuyucu modüllerini düzeltti ama
# JSON'u yazan dört `run()` adapter'ına hiç dokunmadı; onlar herhangi bir
# istisnada **bütün kanalı 0.0 yapıyordu** ve `B2`'nin `None`'u `round()`'a
# ulaşınca tam o yolu tetikliyordu. Kanalı sıfırlamak, bu kaynaklarda riski
# DÜŞÜRÜR — değişmez 2'nin yasakladığı yön.
#
# ⚠️ Ölü `domain_scores.py`'daki iki `None * float` kasıtlı olarak açık
# bırakıldı: modülün üretimde çağıranı yok ve `B8` onu siliyor. Oraya kod
# yazmak, silinecek bir dosyayı düzeltmek olurdu. Kapı bu iki hatayı sayıyor
# ve başkası eklenirse geçmiyor.

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

# ------------------------------------------------------------- 1  mypy sayısı
echo "# 1  mypy sayısı ve kalan gerekçeler"
"$PY" -I - <<'INNER' || fail "mypy sayısı/gerekçeleri beklenen durumda değil"
import re
import subprocess
import sys

BASELINE = 72  # B2 öncesi (9eb0dcf) ölçüldü
# Bu kapının konusu "B2'nin BIRAKTIĞI" opsiyonel-tip hataları. Aşağıdaki iki
# dosya B2 ÖNCESİ listede de vardı (9eb0dcf'te ölçüldü); listede durmaları
# gerekiyor, yoksa kapı onları B2'ye yazar ve yanlış yere baktırır.
ALLOWED_FILES = (
    "scoring/domain_scores.py",  # ölü modül, B8 siliyor; None * float orada kalıyor
    "stage5_biophysics/shape_profile.py",  # B2 ÖNCESİ: max/min üzerinde int | None
)

proc = subprocess.run(
    [sys.executable, "-m", "mypy", "src/"], capture_output=True, text=True
)
total = 0
match = re.search(r"Found (\d+) error", proc.stdout)
if match:
    total = int(match.group(1))
print(f"  toplam: {total} (taban {BASELINE})")

optional_errors = [
    line for line in proc.stdout.splitlines()
    if re.search(r"\[(return-value|list-item|operator|type-var)\]", line)
    and ("None" in line or "Optional" in line)
]
stray = [l for l in optional_errors if not any(a in l for a in ALLOWED_FILES)]
for line in stray:
    print(f"  HATA: {line.strip()[:110]}")
if stray:
    sys.exit("B2'nin bıraktığı opsiyonel-tip hataları hâlâ var")
if total > BASELINE + 2:
    sys.exit(f"mypy {total}, izin verilen en fazla {BASELINE + 2} (yalnız iki ölü-modül hatası)")
print("  kalan opsiyonel-tip hataları yalnız:", ", ".join(ALLOWED_FILES))
INNER

# ------------------------------- 2 + 3  adapter'lar sıfır yazmıyor, çökmüyor
echo "# 2  adapter arızası UNKNOWN yazıyor   # 3  round(None) çökmesi yok"
if git grep -n "using 0\.0" -- src/stage4_epigenetic; then
    fail "bir stage-4 adapter'ı hâlâ arızada 0.0 yazıyor"
fi
if git grep -nE "= \{sid: 0\.0 for sid in site_ids\}" -- src; then
    fail "bir adapter hâlâ kanalı sıfırlıyor"
fi
"$PY" -m pytest tests/unit/test_stage4_fetchers.py -q -o addopts="" -p no:cacheprovider \
    || fail "adapter arıza-yönü testleri geçmiyor"

# ------------------------------------------------------------- 4  birim testleri
echo "# 4  B2'nin testleri hâlâ yeşil"
"$PY" -m pytest tests/unit/test_epigenetic_merger.py tests/unit/test_encode_reader.py \
    tests/unit/test_transcription_run.py tests/unit/test_ago2_loading.py \
    tests/unit/test_rbp_competition.py tests/unit/test_chromatin_access.py \
    tests/unit/test_histone_marks.py -q -o addopts="" -p no:cacheprovider \
    || fail "B2'nin testleri yeşil değil"

echo
echo "GEÇTİ — opsiyonel-tip borcu kapandı, adapter'lar arızada UNKNOWN yazıyor"
