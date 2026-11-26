#!/usr/bin/env bash
# Kabul kriteri — H10: "her `results/*/` altında `manifest.json`".
#
# Dört ölçüm:
#   1  her koşu dizininde manifest var ve JSON olarak okunuyor
#   2  her manifest'te sekiz bölümün hepsi mevcut (bir bölümün sessizce
#      kaybolması provenance'ı daraltır ve hiçbir şey fark etmez)
#   3  manifest kuralı DAG'da ve `rule all`'da — opsiyonel olması, yazılmamaya
#      başlamasının yoludur
#   4  provenance iddiası ÖLÇÜLÜ: her manifest `head_consistency.verdict`
#      taşıyor ve bu değer üç tanımlı değerden biri
#
# ⚠️ 4'ün neden kriterin parçası olduğu: bir manifest "X commit'i bu koşuyu
# üretti" diye yazsaydı, kendisinden önce üretilmiş her koşu için yanlış ve
# hiçbir koşu için yanlışlanabilir olmayan bir iddia kurardı. Bu yüzden
# modül üretici commit'i İDDİA ETMİYOR; denetlenebilir bir sınır veriyor.
# Kapı o sınırın var olduğunu ölçer, içeriğini zorlamaz.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

fail() { echo "GEÇMEDİ — $1"; exit 1; }

PY=""
for cand in "${PYTHON:-}" python3 python; do
    [ -n "$cand" ] || continue
    if "$cand" -c "import pytest, yaml" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || fail "pytest+pyyaml içeren yorumlayıcı bulunamadı; PYTHON=... ile ver"
echo "# yorumlayıcı: $PY"

echo "# 1-2-4  her koşu dizininde tam bir manifest"
"$PY" -I - <<'INNER' || fail "manifest denetimi geçmedi"
import json
import pathlib
import sys

SECTIONS = (
    "code",
    "head_consistency",
    "config",
    "external_data",
    "environment",
    "snakemake_state",
    "stochastic_components",
    "outputs",
)
VERDICTS = {
    "head_is_a_candidate_producer",
    "head_cannot_have_produced_this_run",
    "undetermined_dirty_worktree",
}

results = pathlib.Path("results")
run_dirs = sorted(d for d in results.iterdir() if d.is_dir()) if results.is_dir() else []
if not run_dirs:
    sys.exit("results/ altında hiç koşu dizini yok — kriter ölçülemez")

problems: list[str] = []
for run_dir in run_dirs:
    path = run_dir / "manifest.json"
    if not path.is_file():
        problems.append(f"{run_dir.name}: manifest.json yok")
        continue
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"{run_dir.name}: manifest okunamadı ({exc})")
        continue
    for section in SECTIONS:
        if section not in manifest:
            problems.append(f"{run_dir.name}: '{section}' bölümü eksik")
    verdict = manifest.get("head_consistency", {}).get("verdict")
    if verdict not in VERDICTS:
        problems.append(f"{run_dir.name}: tanımsız provenance verdict'i {verdict!r}")
    if not manifest.get("outputs"):
        problems.append(f"{run_dir.name}: hiçbir çıktı hash'lenmemiş")
    print(f"  {run_dir.name:<14} {verdict}  ({len(manifest.get('outputs', {}))} çıktı)")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo "# 3  kural DAG'da ve rule all'da"
grep -q "rule run_manifest:" rules/stage7_scoring.smk \
    || fail "run_manifest kuralı yok"
grep -q "manifest.json" Snakefile \
    || fail "manifest `rule all`'da değil — opsiyonel bir provenance yazılmaz hale gelir"

echo "# 5  birim testleri"
"$PY" -m pytest tests/unit/test_run_manifest.py -q -o addopts="" -p no:cacheprovider \
    || fail "manifest testleri yeşil değil"

echo
echo "GEÇTİ — her koşu dizini provenance taşıyor, bölümleri tam, verdict'i tanımlı,"
echo "        kural DAG'da ve testlerle kapsanmış."
