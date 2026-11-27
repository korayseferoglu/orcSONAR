#!/usr/bin/env bash
# Kabul kriteri — B11: "istisna yolu sayısal/kategorik risk kararı dönmüyor;
# seed dilimi `[1:8]`".
#
# Dokuz ölçüm. 2, 3, 4, 5 ve 7 ayırt edici olanlar, ve hepsi **davranış** —
# kaynakta bir dizgi aramak bu hatayı yakalamaz, çünkü hata üç ayrı hop'ta
# farklı biçimlerde duruyordu.
#
#   1  KOD: `_parse_mirbase`'in dönüş tipi `None` taşıyor ve eksik dosya
#      dalında `return None` var — okunamayan ile boş dosyayı ayıran şey
#   2  DAVRANIŞ, ayırt edici: eksik FASTA → `risk_level is None`
#   3  KONTROL, ayırt edici: okunabilir ama insan miRNA'sı olmayan FASTA →
#      `SAFE` ve `0.0`. Bu **ölçülmüş** bir yokluk ve doğru cevap o; bu
#      kontrol olmadan düzeltme "her şeyi bilinmiyor yap" olurdu
#   4  DAVRANIŞ, ayırt edici: İSTİSNA yolu (FASTA yerine bir dizin) →
#      bilinmiyor, VE seed kural 10'un dilimi. ⚠️ Eksik dosya bu yolu
#      TETİKLEMİYOR (ölçüldü), o yüzden gerçek bir istisna gerekiyor
#   5  DAVRANIŞ, ayırt edici: SONRAKİ HOP — `offtarget_merger` eksik
#      mirbase dosyasıyla `SAFE`'i geri getirmiyor. Yalnız checker'ı
#      düzeltmek zincirin çıktısını değiştirmezdi
#   6  KONTROL: modelin varsayılanı bilinmiyor
#   7  TARAMA, ayırt edici: `src/` içinde kalan her `risk_level="SAFE"`
#      fallback'i ilan edilmiş bir carve-out'a sahip olmalı, ve her
#      carve-out HÂLÂ GEREKLİ olmalı — bayat bir muafiyet sessiz bir
#      silmedir (`H9`'un kalıbı)
#   8  birim testleri yeşil
#   9  KAPSAM BEYANI: bu kanal üretimde skora girmiyor — `domain_scores.py`'ın
#      sıfır üretim çağıranı olduğu doğrulanıyor, yani satırın "etkisi
#      çıktının dürüstlüğünde" ifadesi ölçülmüş kalıyor

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

fail() { echo "GEÇMEDİ — $1"; exit 1; }

# shellcheck source=_lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

PY=""
for cand in "${PYTHON:-}" python3 python; do
    [ -n "$cand" ] || continue
    if "$cand" -c "import pytest, pydantic" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || fail "pytest+pydantic içeren yorumlayıcı bulunamadı; PYTHON=... ile ver"
echo "# yorumlayıcı: $PY"

warn_untracked src tests .claude || true

"$PY" - <<'INNER' || exit 1
from __future__ import annotations

import inspect
import json
import re
import subprocess
import sys
import tempfile
import textwrap
import typing
from pathlib import Path

sys.path.insert(0, ".")

from src.core.models import MirbaseResult  # noqa: E402
from src.stage2_offtarget_scan import mirbase_checker, offtarget_merger  # noqa: E402

problems: list[str] = []
PROBE = "UAGCUUAUCAGACUGAUGUUGA"

# ---- 1  KOD: dönüş tipi ve dal ------------------------------------------
hints = typing.get_type_hints(mirbase_checker._parse_mirbase)
returns = hints.get("return")
if type(None) not in typing.get_args(returns or int):
    problems.append(
        f"`_parse_mirbase`'in dönüş tipi `None` taşımıyor ({returns}) — "
        "okunamayan dosya ile boş dosya aynı değeri verir"
    )
else:
    source = inspect.getsource(mirbase_checker._parse_mirbase)
    if not re.search(r"if not path\.exists\(\):(?:.|\n)*?return None", source):
        problems.append(
            "eksik dosya dalı `None` dönmüyor — tip imzası beyan, dal uygulama"
        )
    else:
        print(f"  1  kod: `_parse_mirbase` → {returns}, eksik dosya dalı `None`")

# ---- 2  DAVRANIŞ: eksik FASTA bilinmiyor --------------------------------
missing = mirbase_checker.check_mirbase_overlap(PROBE, "/no/such/file.fa")
if missing.risk_level is not None or missing.max_overlap_score is not None:
    problems.append(
        f"eksik FASTA bir risk kararı döndü: risk_level={missing.risk_level!r}, "
        f"score={missing.max_overlap_score!r}"
    )
else:
    print("  2  eksik FASTA → risk_level=None, score=None")

# ---- 3  KONTROL: okunabilir ama insan yok → gerçekten SAFE -------------
with tempfile.TemporaryDirectory() as tmp:
    nonhuman = Path(tmp) / "mature.fa"
    nonhuman.write_text(textwrap.dedent("""\
        >cel-let-7-5p MIMAT0000001 Caenorhabditis elegans let-7-5p
        UGAGGUAGUAGGUUGUAUAGUU
    """), encoding="utf-8")
    measured = mirbase_checker.check_mirbase_overlap(PROBE, str(nonhuman))
if measured.risk_level != "SAFE" or measured.max_overlap_score != 0.0:
    problems.append(
        f"okunabilir ama insan miRNA'sı olmayan FASTA `SAFE`/0.0 vermiyor "
        f"({measured.risk_level!r}/{measured.max_overlap_score!r}) — düzeltme "
        "ölçülmüş yokluğu da bilinmiyor yapmış, yani 2. ölçüm boş"
    )
else:
    print("  3  kontrol: okunabilir/insan-yok FASTA → SAFE, 0.0 (ölçülmüş yokluk)")

# ---- 4  DAVRANIŞ: İSTİSNA yolu ve seed dilimi --------------------------
expected_seed = PROBE[
    mirbase_checker._SEED_START :
    mirbase_checker._SEED_START + mirbase_checker._SEED_LENGTH
]
if expected_seed == PROBE[:7]:
    problems.append("sonda dizisi iki dilimi ayırt etmiyor — ölçüm anlamsız")
else:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        a_directory = work / "not-a-fasta"
        a_directory.mkdir()
        out = work / "stage2_mirbase.json"
        mirbase_checker.run(
            sarna_sequence=PROBE,
            mirbase_fa=str(a_directory),
            output_path=str(out),
            log_path=str(work / "log.txt"),
        )
        payload = json.loads(out.read_text(encoding="utf-8"))
    if payload["risk_level"] is not None or payload["max_overlap_score"] is not None:
        problems.append(
            f"istisna yolu risk kararı yazdı: {payload['risk_level']!r}"
        )
    elif payload["sarna_seed"] == PROBE[:7]:
        problems.append(
            f"istisna yolu seed'i `[:7]` olarak yazıyor "
            f"({payload['sarna_seed']!r}), kural 10 {expected_seed!r} diyor"
        )
    elif payload["sarna_seed"] != expected_seed:
        problems.append(
            f"istisna yolunun seed'i {payload['sarna_seed']!r}, beklenen "
            f"{expected_seed!r}"
        )
    else:
        print(f"  4  istisna yolu (dizin) → bilinmiyor, seed {expected_seed!r} "
              f"(≠ {PROBE[:7]!r})")

# ---- 5  DAVRANIŞ: sonraki hop ------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    work = Path(tmp)
    seed_hits = work / "stage2_seed_hits.json"
    seed_hits.write_text(json.dumps({"sites": [], "sequence_scores": {}}),
                         encoding="utf-8")
    repeats = work / "stage2_repeats.json"
    repeats.write_text(json.dumps({"repeat_results": {}}), encoding="utf-8")
    merged = work / "stage2_offtargets.json"
    offtarget_merger.run(
        seed_hits_path=str(seed_hits),
        mirbase_path="/no/such/file.json",
        repeats_path=str(repeats),
        output_path=str(merged),
        log_path=str(work / "log.txt"),
    )
    chain = json.loads(merged.read_text(encoding="utf-8"))["mirbase_result"]
if chain["risk_level"] is not None or chain["max_overlap_score"] is not None:
    problems.append(
        f"`offtarget_merger` `SAFE`'i geri getirdi: {chain['risk_level']!r} — "
        "yalnız checker'ı düzeltmek zincirin çıktısını değiştirmezdi"
    )
else:
    print("  5  sonraki hop: merger eksik dosyada bilinmiyor yazıyor")

# ---- 6  KONTROL: modelin varsayılanı ------------------------------------
bare = MirbaseResult(sarna_seed=expected_seed)
if bare.risk_level is not None or bare.max_overlap_score is not None:
    problems.append(
        f"`MirbaseResult`'ın varsayılanı hâlâ bir risk kararı: "
        f"{bare.risk_level!r}/{bare.max_overlap_score!r}"
    )
else:
    print("  6  kontrol: modelin varsayılanı bilinmiyor")

# ---- 7  TARAMA: kalan SAFE fallback'leri carve-out'lu olmalı ------------
# Her carve-out onu KALDIRACAK yol haritası maddesini adlandırmak zorunda
# (`H9`'un kalıbı), ve bayat bir carve-out kırmızıya düşer.
CARVE_OUTS: dict[str, str] = {
    "src/stage6_execution/immune_screen.py": "B11b",
    # `ImmuneResult`'ın varsayılanı da aynı satırda duruyor ve aynı madde
    # onu kaldırıyor.
    "src/core/models.py": "B11b",
}
out = subprocess.run(
    # Üç biçim: `risk_level="SAFE"` (çağrı), `risk_level: str = "SAFE"`
    # (alan varsayılanı — ilk regex bunu KAÇIRIYORDU ve carve-out bayat
    # görünüyordu), ve `"risk_level": "SAFE"` (sözlük literali).
    ["git", "grep", "-n", "-E",
     r'risk_level"?\s*(:[^=]*)?[=:]\s*"SAFE"', "--", "src"],
    capture_output=True, text=True, check=False,
)
offenders: dict[str, list[str]] = {}
for line in out.stdout.splitlines():
    path = line.split(":", 1)[0]
    offenders.setdefault(path, []).append(line.strip())
unexcused = sorted(set(offenders) - set(CARVE_OUTS))
if unexcused:
    problems.append(
        f"ilan edilmemiş `SAFE` fallback'i: {unexcused} — bir dördüncü hop "
        "sessizce geri getirilmiş olabilir"
    )
sys.path.insert(0, ".claude/hooks")
import _status  # noqa: E402

items = {i.id: i for i in _status.parse_roadmap(
    Path("SCIENTIFIC_ROADMAP.md").read_text(encoding="utf-8"))}
stale = [p for p in CARVE_OUTS if p not in offenders]
for path, item in CARVE_OUTS.items():
    if item not in items:
        problems.append(f"{path}'in carve-out'u var olmayan bir maddeyi adlandırıyor: {item}")
    elif "DONE" in items[item].status and path in offenders:
        problems.append(
            f"{item} kapandı ama {path} hâlâ `SAFE` dönüyor — carve-out "
            "kaldırılmamış"
        )
if stale:
    problems.append(
        f"bayat carve-out: {stale} artık `SAFE` dönmüyor, muafiyet kalkmalı "
        "(sessiz bir silme olmasın)"
    )
if not [p for p in problems if "carve-out" in p or "fallback" in p]:
    print(f"  7  tarama: {len(offenders)} kalan `SAFE` fallback'i, hepsi "
          f"carve-out'lu ve carve-out'lar güncel ({sorted(CARVE_OUTS.values())})")

# ---- 9  KAPSAM BEYANI: kanal üretimde skora girmiyor -------------------
callers = subprocess.run(
    ["git", "grep", "-l", "-E", r"from src\.scoring\.domain_scores|"
     r"import domain_scores\b", "--", "src", "rules", "Snakefile"],
    capture_output=True, text=True, check=False,
)
live = [p for p in callers.stdout.split() if p != "src/scoring/domain_scores.py"]
if live:
    problems.append(
        f"`domain_scores.py` artık üretimden çağrılıyor ({live}) — bu kanalın "
        "skora girmediği beyanı bayatlamış, madde yeniden açılmalı"
    )
else:
    print("  9  kapsam: `domain_scores.py`'ın sıfır üretim çağıranı var, yani "
          "bu kanalın risk seviyesi skora girmiyor (etkisi çıktının "
          "dürüstlüğünde)")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo "# 8  birim testleri"
ORCSONAR_SUITE_RECEIPT="$(mktemp -u)" "$PY" -m pytest \
    tests/unit/test_mirbase_checker.py -q -o addopts="" -p no:cacheprovider \
    || fail "B11 birim testleri yeşil değil"

echo
echo "GEÇTİ — miRBase kanalı artık veri yokluğundan risk kararı üretmiyor, ve"
echo "        bu ÜÇ hop'ta birlikte ölçülüyor: parser okunamayanı ayırıyor,"
echo "        istisna yolu bilinmiyor yazıyor ve seed'i kural 10'un dilimi,"
echo "        merger \`SAFE\`'i geri getirmiyor. Kontrol ölçümü ölçülmüş"
echo "        yokluğun hâlâ \`SAFE\` olduğunu doğruluyor; tarama kalan tek"
echo "        örneği (\`B11b\`) carve-out olarak izliyor."
