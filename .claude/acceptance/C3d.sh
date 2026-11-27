#!/usr/bin/env bash
# Kabul kriteri — C3d: "eşikler üç kopyanın hepsinden silinmiş; ham ΔG hâlâ
# üretiliyor; türetilmiş skor ön kayıt olmadan sayı üretmiyor ve skoru
# değiştiremiyor; üç literatür bulgusu kodda atıflı".
#
# Altı ölçüm. 3 ve 4 ayırt edici olanlar.
#
#   1  SİLİNDİ: config, model, Snakemake kuralı ve İKİ modül — eşik yok
#   2  ÖLÇÜM KORUNDU: hesaplayıcı hâlâ negatif, site başına DEĞİŞEN ham ΔG
#      üretiyor (gerçek Turner verisiyle koşuluyor) ve `risk_score` null
#   3  ÇEKİMSER: ΔG skoru DEĞİŞTİREMİYOR — −43,8 ile −7,1 ile null aynı
#      sonucu veriyor. Kanalı "kaldırdım" demek ile gerçekten etkisiz olması
#      ayrı şeyler
#   4  KONTROL: ölçülmüş bir kanal hâlâ skorluyor — 3. ölçümün boş olmadığını
#      gösteren şey; her şeyi null döndüren bir merger de 3'ü geçerdi
#   5  GEREKÇE YAZILI: silinen sabitin geri gelmesini engelleyen tek şey,
#      silinme sebebinin silindiği yerde durması (PMID'ler)
#   6  birim testleri yeşil
#
# ⚠️ Bu kapı ΔG'nin DOĞRU ölçüldüğünü yeniden ölçmez — o `C3`'ün işi ve
# `tests/unit/test_thermodynamics.py`'de duruyor. Burada ölçülen tek şey,
# gerekçesiz bir eşiğin yerine sessizce başka bir sayı KONMADIĞI.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

fail() { echo "GEÇMEDİ — $1"; exit 1; }

# shellcheck source=_lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

PY=""
for cand in "${PYTHON:-}" python3 python; do
    [ -n "$cand" ] || continue
    if "$cand" -c "import pytest, yaml, pydantic" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || fail "pytest+pyyaml+pydantic içeren yorumlayıcı bulunamadı"
echo "# yorumlayıcı: $PY"

warn_untracked src tests config rules || true

echo "# 1-5  silme, ölçüm, çekimserlik, kontrol ve gerekçe"
"$PY" - <<'INNER' || exit 1
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")

import yaml

problems: list[str] = []

CALC = Path("src/stage5_biophysics/delta_g_calculator.py")
MERGER = Path("src/stage5_biophysics/biophysics_merger.py")

# ---- 1  üç kopyanın hepsi silindi --------------------------------------
raw = yaml.safe_load(Path("config/config.yaml").read_text(encoding="utf-8"))
for key in ("delta_g_strong", "delta_g_moderate"):
    if key in raw:
        problems.append(f"config.yaml hâlâ {key} tanımlıyor")

from src.core.config import OrcSonarConfig  # noqa: E402

for key in ("delta_g_strong", "delta_g_moderate"):
    if key in OrcSonarConfig.model_fields:
        problems.append(f"OrcSonarConfig hâlâ {key} alanını taşıyor")

smk = Path("rules/stage5_biophysics.smk").read_text(encoding="utf-8")
for token in ("dg_strong", "dg_moderate", "delta_g_strong", "delta_g_moderate"):
    if token in smk:
        problems.append(f"Snakemake kuralı hâlâ {token} geçiriyor")

calc_text = CALC.read_text(encoding="utf-8")
merger_text = MERGER.read_text(encoding="utf-8")
for token in ("_dg_to_risk_score", "_DG_STRONG", "_DG_MODERATE", "_DG_NEUTRAL"):
    if token in calc_text:
        problems.append(f"delta_g_calculator hâlâ {token} içeriyor")
for token in ("_delta_g_risk", "_DG_REFERENCE", "_DG_STRONG"):
    if token in merger_text:
        problems.append(f"biophysics_merger hâlâ {token} içeriyor")
if not problems:
    print("  1  config, model, kural ve iki modül: eşik yok")

# ---- 2  ham ölçüm korundu (gerçek Turner verisiyle) --------------------
TURNER = Path("data/4_Biyofizik_Yapısal/Turner_Rules")
if not (TURNER / "rna.stack.dg").is_file():
    print("  2  ATLANDI — Turner veri dosyaları yok")
else:
    from src.stage5_biophysics.delta_g_calculator import run as dg_run

    guide = "GCAACCAUAGCCUCGGCCGC"
    comp = {"A": "U", "U": "A", "G": "C", "C": "G"}
    perfect = "".join(comp[b] for b in reversed(guide))
    mutated = perfect[:-4] + "".join(comp[b] for b in perfect[-4:])
    sites = [
        {
            "gene": f"G{i}",
            "transcript_id": f"ENST0000000000{i}",
            "region": {"chrom": "chr1", "start": 100 + i, "end": 120 + i, "strand": "+"},
            "seed_match_type": "perfect",
            "mismatches": 0,
            "alignment_score": 10.0,
            "tx_start": 0,
            "tx_end": 20,
            "target_window": window,
            "site_id": f"G{i}:ENST0000000000{i}:chr1:{100 + i}",
        }
        for i, window in enumerate((perfect, mutated))
    ]
    with tempfile.TemporaryDirectory() as tmp:
        tmpd = Path(tmp)
        off = tmpd / "offtargets.json"
        off.write_text(json.dumps({"offtarget_sites": sites}), encoding="utf-8")
        out = tmpd / "deltag.json"
        dg_run(
            sarna_sequence=guide,
            offtargets_path=str(off),
            turner_dir=str(TURNER),
            output_path=str(out),
            log_path=str(tmpd / "dg.log"),
        )
        results = json.loads(out.read_text(encoding="utf-8"))["deltag_results"]
    dgs = [r["delta_g"] for r in results.values()]
    risks = [r["risk_score"] for r in results.values()]
    if not dgs or any(d is None or d >= 0 for d in dgs):
        problems.append(f"ham ΔG kayboldu ya da negatif değil: {dgs}")
    elif len(set(dgs)) < 2:
        problems.append(f"ΔG site başına değişmiyor: {dgs}")
    elif any(r is not None for r in risks):
        problems.append(f"türetilmiş skor hâlâ sayı üretiyor: {risks}")
    else:
        print(f"  2  ham ΔG korundu ve değişiyor: {dgs} · risk_score {risks}")

# ---- 3 ve 4  çekimserlik ve kontrolü -----------------------------------
from src.stage5_biophysics.biophysics_merger import _normalize  # noqa: E402

base = {"shape_acc": 0.4, "m6a_score": 0.6, "adar_score": None, "g4_risk": None}
variants = {
    "ΔG=-43.8": _normalize(delta_g=-43.8, **base),
    "ΔG=-7.1": _normalize(delta_g=-7.1, **base),
    "ΔG=None": _normalize(delta_g=None, **base),
}
if len(set(variants.values())) != 1:
    problems.append(f"ΔG skoru hâlâ değiştiriyor: {variants}")
else:
    print(f"  3  ΔG skoru değiştiremiyor: üçü de {next(iter(variants.values()))}")

only_dg = _normalize(
    delta_g=-30.0, shape_acc=None, m6a_score=None, adar_score=None, g4_risk=None
)
if only_dg is not None:
    problems.append(f"yalnız ΔG varken skor {only_dg} üretildi, bilinmiyor olmalı")
only_shape = _normalize(
    delta_g=-30.0, shape_acc=0.8, m6a_score=None, adar_score=None, g4_risk=None
)
if only_shape != 0.8:
    problems.append(
        f"ölçülmüş kanal skorlamıyor: {only_shape} (beklenen 0.8) — 3. ölçüm boş"
    )
else:
    print("  4  kontrol: ölçülmüş kanal hâlâ skorluyor (0.8), renormalizasyon sağlam")

# ---- 5  gerekçe silindiği yerde yazılı ---------------------------------
WANT = {
    "delta_g_calculator": (CALC, calc_text, ("26657993", "discontinuous", "A10")),
    "biophysics_merger": (MERGER, merger_text, ("28108657", "C3e")),
}
for label, (path, text, tokens) in WANT.items():
    missing = [token for token in tokens if token not in text]
    if missing:
        problems.append(f"{label} gerekçeyi taşımıyor, eksik: {missing}")
if not any("gerekçeyi" in p for p in problems):
    print("  5  gerekçe ve PMID'ler silinen sabitlerin yerinde yazılı")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo "# 6  birim testleri"
ORCSONAR_SUITE_RECEIPT="$(mktemp -u)" "$PY" -m pytest \
    tests/unit/test_delta_g_thresholds_removed.py \
    tests/unit/test_thermodynamics.py tests/unit/test_stage5_fetchers.py \
    -q -o addopts="" -p no:cacheprovider \
    || fail "C3d birim testleri yeşil değil"

echo
echo "GEÇTİ — üç eşik kopyası da silindi, yerine sayı KONMADI; ham per-site ΔG"
echo "        korundu ve skoru değiştiremiyor; gerekçe PMID'leriyle silindiği"
echo "        yerde yazılı."
echo "        NOT: per-site ölçütün KURULMASI C3e'de, işareti A10'un ön kaydında."
