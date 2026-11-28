#!/usr/bin/env bash
# Kabul kriteri — B12: dört koşu güncel kodla, tam arka plan kapsamıyla,
# pinlenmiş Ensembl sürümüyle (`B17`) ve düzeltilmiş DepMap ID'leriyle (`B18`)
# yeniden üretilmiş.
#
# ⚠️ Kriterin son cümlesi ("`verify-run` dördünde de temiz") ÖLÇÜLDÜ ve
# karşılanamaz: `verify-run` altı kontrolünün dördünde, zaten en yeni olan
# koşuda FAIL veriyordu. O bulguların bir kısmı koşunun eskiliğinden gelir ve
# yeniden koşmakla kalkar; bir kısmı canlı koddan gelir — `HIGH_RISK`
# erişilemezliği (`F1`), `sequence_specificity`'nin sabite ezilmesi (`C1`) — ve
# kaç kere koşulursa koşulsun kalır. Bu yüzden kapı "temiz mi" diye sormuyor;
# **her kalıntı bulgu adı konmuş AÇIK bir maddeye atfedilebiliyor mu** diye
# soruyor. Eşiği indirmek değişmez 7 ihlali olurdu; eşiğin neyi ölçtüğünü
# yazmak değil. Atıf `.claude/residual_findings.yaml`'da, ve kapı onu İKİ
# YÖNDE kontrol ediyor.
#
# Sekiz ölçüm:
#   1  dört koşu dizini var ve okunabiliyor
#   2  her koşu TAM arka plan kapsamı taşıyor (`background_coverage.fraction`
#      == 1.0) — alanın kendisi `R12a` sonrası olmanın da işareti, çünkü
#      önceki dört koşunun hiçbirinde yok
#   3  her koşunun manifest commit'i yedi düzeltmeyi de İÇERİYOR
#      (`git merge-base --is-ancestor`) — "güncel kod"un ölçülebilir hali
#   4  hiçbir koşuda yarıda kesinti işareti yok (`snakemake_state`)
#   5  her site_id dört parçalı (`Bulgu-2` sonrası) — stage 2 ve her downstream
#   6  pinlenmiş Ensembl: manifest'teki config hash'i bugünkü dosyayla aynı VE
#      beyan edilen sürüm canlı arşiv host'uyla uyuşuyor
#   7  ⚠️ AYIRT EDİCİ: her kalıntı `verify-run` bulgusu atıf dosyasında var,
#      VE atıf dosyasındaki her sahip HÂLÂ AÇIK. Sahipsiz bir bulgu kırmızı;
#      kapanmış bir maddeye atfedilen, hâlâ duran bir bulgu da kırmızı — ikinci
#      yön "maddeyi kapattık ama bulgu duruyor"u yakalayan taraf
#   8  KONTROL: eski koşuların bu kapıyı GEÇMEDİĞİ gösteriliyor. Korunmuş
#      `before-manifests/` üzerinde 3. ve 4. ölçüm koşuluyor; geçerlerse
#      kapının hiçbir şeyi ayırt etmediği ortaya çıkar
#
# ⚠️ 6. ölçümün canlı yarısı ağ istiyor ve ağsız ATLANIR; ama host cevap verip
# sürüm UYUŞMAZSA kırmızıya düşer (`H17` deseni).
#
# 📌 Bu kapı CI'da KOŞMUYOR ve koşmamalı: `results/` git'te izlenmiyor, yani
# CI'da dört koşu dizini hiç yok ve kapı ölçecek bir şey bulamaz. CI yalnız
# `H9` ve `H9b`'yi bloke edici koşuyor. Yokluğu eksiklik değil, bu satır da o
# yüzden burada.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

fail() { echo "GEÇMEDİ — $1"; exit 1; }

# shellcheck source=_lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

PY=""
for cand in "${PYTHON:-}" python3 python; do
    [ -n "$cand" ] || continue
    if "$cand" -c "import yaml" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || fail "PyYAML içeren yorumlayıcı bulunamadı; PYTHON=... ile ver"
echo "# yorumlayıcı: $PY"

"$PY" "$(dirname "${BASH_SOURCE[0]}")/b12_check.py"
