#!/usr/bin/env bash
# Kabul kriteri — B2: hiçbir fallback yolu sayısal risk değeri dönmüyor.
#
# Beş ölçüm:
#   1  eski sabit tamamen gitti (`_NEUTRAL_SIGNAL` üretimde yok)
#   2  okuma arızası sayı değil BİLİNMİYOR dönüyor; "kontig var, sinyal yok"
#      ise ölçülmüş 0.0 olarak KALIYOR (gerçek bilgi atılmıyor)
#   3  model varsayılanları artık 0.0/0.5 değil — bir alan doldurulmazsa
#      bilinmiyor olur, sessizce "sinyal yok" olmaz
#   4  iki merger'da da bilinmeyen kanal, ölçülmüş sıfırdan DAHA RİSKLİ
#   5  birim testleri yeşil
#
# 2'nin ikinci yarısı kritik: her şeyi bilinmiyor yapan bir düzeltme, gerçek
# ölçümleri de çöpe atar. Yön testi tek başına yetmez, bu yüzden ikisi birlikte.

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

# ------------------------------------------------- 1  eski sabit gitti mi
echo "# 1  _NEUTRAL_SIGNAL üretimde yok"
if git grep -n "_NEUTRAL_SIGNAL" -- src | grep -v "^src/stage4_epigenetic/encode_reader.py:[0-9]*:#"; then
    fail "_NEUTRAL_SIGNAL hâlâ üretim kodunda (yorum satırı dışında)"
fi

# --------------------------------------- 2 + 3 + 4  davranış ölçümleri
echo "# 2  arıza bilinmiyor, ölçülmüş sıfır korunuyor   # 3  model varsayılanları   # 4  merger yönü"
"$PY" -I - <<'INNER' || fail "B2 davranış ölçümleri geçmedi"
import sys
sys.path.insert(0, ".")
from unittest.mock import MagicMock

from src.core.models import Ago2Result, EpigeneticScore, GROseqResult, RBPResult
from src.stage4_epigenetic.encode_reader import UNKNOWN_SIGNAL, _bigwig_mean
from src.stage4_epigenetic.epigenetic_merger import _compute_normalized
from src.stage6_execution.execution_merger import _normalize as _execution_normalize

problems = []

if UNKNOWN_SIGNAL is not None:
    problems.append(f"UNKNOWN_SIGNAL sayısal: {UNKNOWN_SIGNAL!r}")

# --- 2  okuma arızası -> bilinmiyor
bw = MagicMock()
bw.stats.side_effect = RuntimeError("boom")
if _bigwig_mean(bw, "chr6", 0, 100) is not None:
    problems.append("okuma istisnası sayı döndü")

bw = MagicMock()
bw.stats.return_value = [None]
bw.chroms.return_value = {"6": 1_000_000}  # "chr" öneki uyuşmuyor
if _bigwig_mean(bw, "chr6", 0, 100) is not None:
    problems.append("dosyada olmayan kontig sayı döndü")

# --- 2b  gerçek ölçüm ATILMAMALI
bw = MagicMock()
bw.stats.return_value = [None]
bw.chroms.return_value = {"chr6": 1_000_000}
if _bigwig_mean(bw, "chr6", 0, 100) != 0.0:
    problems.append("kontig var ve sessiz: ölçülmüş 0.0 korunmadı")

bw = MagicMock()
bw.stats.return_value = [3.5]
if _bigwig_mean(bw, "chr6", 0, 100) != 3.5:
    problems.append("gerçek sinyal bozuldu")

# --- 3  model varsayılanları
defaults = {
    "EpigeneticScore.atac_signal": EpigeneticScore().atac_signal,
    "EpigeneticScore.hic_contact": EpigeneticScore().hic_contact,
    "EpigeneticScore.normalized_score": EpigeneticScore().normalized_score,
    "GROseqResult.combined_signal": GROseqResult(
        region={"chrom": "chr1", "start": 1, "end": 2, "strand": "+"}
    ).combined_signal,
    "Ago2Result.loading_score": Ago2Result(
        region={"chrom": "chr1", "start": 1, "end": 2, "strand": "+"}, cell_line="HeLa"
    ).loading_score,
    "RBPResult.competition_score": RBPResult(
        region={"chrom": "chr1", "start": 1, "end": 2, "strand": "+"}, cell_line="HeLa"
    ).competition_score,
}
for name, value in defaults.items():
    if value is not None:
        problems.append(f"{name} varsayılanı sayısal: {value!r}")

# --- 4  merger yönü
half = {"atac": 25.0, "h3k4me3": 10.0, "h3k27ac": 10.0, "groseq": 5.0, "hic": 0.5, "ccle": 4.0}
for channel in half:
    unknown = _compute_normalized(**{**half, channel: None})
    zero = _compute_normalized(**{**half, channel: 0.0})
    if not (unknown is not None and unknown > zero):
        problems.append(f"epigenetik {channel}: bilinmiyor ({unknown}) sıfırdan ({zero}) riskli değil")
if _compute_normalized(**dict.fromkeys(half)) is not None:
    problems.append("hiçbir kanal ölçülmemişken epigenetik skor üretildi")

exec_unknown = _execution_normalize(None, 0.5, False, 0.5)
exec_zero = _execution_normalize(0.0, 0.5, False, 0.5)
if not (exec_unknown is not None and exec_unknown > exec_zero):
    problems.append(f"ago2: bilinmiyor ({exec_unknown}) sıfırdan ({exec_zero}) riskli değil")
if _execution_normalize(None, None, False, 0.5) is None:
    problems.append("ölçülen kanal varken execution skoru üretilmedi")

for problem in problems:
    print(f"  HATA: {problem}")
sys.exit(1 if problems else 0)
INNER

# ------------------------------------------------------------- 5  birim testleri
echo "# 5  birim testleri"
"$PY" -m pytest tests/unit/test_epigenetic_merger.py tests/unit/test_encode_reader.py \
    tests/unit/test_chromatin_access.py tests/unit/test_histone_marks.py \
    tests/unit/test_transcription_run.py tests/unit/test_ago2_loading.py \
    tests/unit/test_rbp_competition.py -q -o addopts="" -p no:cacheprovider \
    || fail "B2'nin testleri yeşil değil"

echo
echo "GEÇTİ — arıza bilinmiyor dönüyor, ölçülmüş sıfır korunuyor, bilinmiyor riski düşürmüyor"
