#!/usr/bin/env bash
# Kabul kriteri — R14: "kapsam yokluğu ile ölçülmüş düşük korunma
# ayrılabiliyor".
#
# Satır karar istiyordu ve karar ÖLÇÜLEREK verildi, iki kaynaktan:
#
#   UCSC hg38 cons100way track açıklaması, birebir: "Both phastCons and phyloP
#   treat alignment gaps and unaligned nucleotides as missing data" ve "the
#   absolute values of the scores represent -log p-values under a null
#   hypothesis of neutral evolution". Yani phyloP **0 bir ölçümdür** (p = 1,
#   nötrlükten sapma saptanmadı), ve "ölçülmedi" yerine 0.0 yazmak gerçek bir
#   sonuçtan ayırt edilemeyen bir sayı üretir.
#
#   Canlı dosya ölçümü (hg38.phyloP100way.bw, 2026-11-28): normal pencere
#   ortalama + coverage 1.0 döndürüyor; sentromerik/telomerik pencere `stats`
#   None ve 20/20 NaN döndürüyor (dosya o pozisyonları gerçekten içermiyor);
#   `chr` öneki olmayan kontig adı ve kontig sonunu aşan aralık
#   `RuntimeError: Invalid interval bounds!` fırlatıyor; sınırı kesen pencere
#   kendisinin BİR KISMI üzerinden ortalama döndürüyor
#   (chr1:121.609.785-805 → mean 0.213, coverage 0.6).
#
# ⚠️ Bu, `encode_reader`'ın kararından KASITLI olarak farklı. Orada "kontig
# var, aralıkta veri yok" gerçek bir sıfır: assay lokusu kapsadı ve hiçbir şey
# ölçmedi. phyloP'ta öyle bir durum YOK — pozisyon ya hizalama kolonuna sahip
# ve skoru var, ya ikisi de yok.
#
# On ölçüm. 2, 3, 4, 6 ve 8 ayırt edici; 4 ve 7b kontrol.
#
#   1  KOD: `_NEUTRAL_MEAN_SCORE` modülde yok
#   2  DAVRANIŞ, ayırt edici: değeri olmayan pencere → `None`, 0.0 değil
#   3  DAVRANIŞ, ayırt edici: başarısız okuma → `None`, 0.0 değil, ve kapsam
#      da bilinmiyor
#   4  KONTROL, ayırt edici: ÖLÇÜLMÜŞ bir 0.0 hayatta kalıyor. Bu olmadan
#      "her zaman None dön" 2. ve 3. ölçümü geçerdi — ve o, nötr evrimin
#      gerçek ölçümlerini silmek olurdu
#   5  DAVRANIŞ: negatif ortalama (hızlanmış evrim) hayatta kalıyor
#   6  DAVRANIŞ, ayırt edici: kısmi kapsam kaydediliyor
#   7  B2 kuralı: bilinmeyen cache'lenmiyor — 7b kontrol: ölçüm cache'leniyor
#   8  KOD, ayırt edici: ölü `_NEUTRAL_CONSERVATION_SCORE` ÜRETİMDE OKUNMUYOR.
#      Silinmedi çünkü değişmez 2'nin `epigenetic_merger._NEUTRAL` için
#      yaptığı gibi bu satırın kanıtı; kapı ölü kalmasını sağlıyor
#   9  DOWNSTREAM: `variant_merger` None phyloP kanalını dışlayıp ağırlıkları
#      yeniden normalize ediyor, sayı ikame etmiyor
#  10  CANLI (ağ): gerçek dosyada sentromerik pencere bilinmiyor, normal
#      pencere ölçüm veriyor. Ağsız ATLANIR ama dosya ÇELİŞİRSE kırmızı
#      (`H17` deseni) — bütün kararın dayandığı ölçüm bu
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

fail() { echo "GEÇMEDİ — $1"; exit 1; }

# shellcheck source=_lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

PY=""
for cand in "${PYTHON:-}" python3 python; do
    [ -n "$cand" ] || continue
    if "$cand" -c "import pytest, pyBigWig" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || fail "pytest + pyBigWig içeren yorumlayıcı bulunamadı; PYTHON=... ile ver"
echo "# yorumlayıcı: $PY"

warn_untracked src tests .claude || true

"$PY" "$(dirname "${BASH_SOURCE[0]}")/r14_check.py"
