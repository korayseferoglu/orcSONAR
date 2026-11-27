#!/usr/bin/env bash
# Kabul kriteri — B17: "her uzak dizi çağrısının sürümü kayıtlı; önbellek
# anahtarı sürüm taşıyor; aynı sürümle iki koşu birebir aynı".
#
# Yedi ölçüm. 2, 5 ve 6 ayırt edici olanlar.
#
#   1  PİN: config bir arşiv host'u ve bir sürüm beyan ediyor, ikisi tutarlı
#   2  ANAHTAR: üretimde Ensembl önbellek anahtarı kuran HİÇBİR yer sürümü
#      atlamıyor (kaynak taranarak ölçülüyor, iddia edilmiyor) — bir çağrı
#      yerinin kendi anahtar metnini yazması, iki kopyanın kaymaya başladığı
#      yerdir (`H9`)
#   3  MANİFEST: `run_manifest` sürümü ve doğrulanıp doğrulanmadığını kaydediyor
#   4  KONTROL: uyuşmazlık RET (istisna), ulaşılamama ise "doğrulanmadı" —
#      geçici bir ağ hatası değişmiş bir sürüm gibi görünmemeli, ama sessizce
#      de geçmemeli
#   5  AĞ: pinlenmiş host TAM OLARAK beyan edilen sürümü veriyor, ve bu işin
#      başladığı ölçüm yeniden üretiliyor (`ENST00000372067` = 3535 nt)
#   6  AĞ: aynı sürümle iki ardışık çekim, arada önbellek TEMİZLENEREK,
#      BİREBİR aynı — kriterin üçüncü şıkkı
#   7  birim testleri yeşil
#
# ⚠️ 5 ve 6 ağ gerektirir ve ağ yoksa ATLANIR — ama host YANLIŞ sürüm verirse
# atlanmaz, GEÇMEZ. Atlamak ile geçmek aynı şey değil (`H17`).

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

fail() { echo "GEÇMEDİ — $1"; exit 1; }

# shellcheck source=_lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

PY=""
for cand in "${PYTHON:-}" python3 python; do
    [ -n "$cand" ] || continue
    if "$cand" -c "import pytest, yaml, requests, pydantic" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || fail "pytest+pyyaml+requests+pydantic içeren yorumlayıcı bulunamadı"
echo "# yorumlayıcı: $PY"

warn_untracked src tests config || true

echo "# 1-6  pin, anahtar, manifest, kontrol ve iki ağ ölçümü"
"$PY" - <<'INNER' || exit 1
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")

import yaml

from src.core import ensembl_release as er

problems: list[str] = []

# ---- 1  pin -------------------------------------------------------------
raw = yaml.safe_load(Path("config/config.yaml").read_text(encoding="utf-8"))
base_url = raw.get("ensembl_base_url", "")
declared = raw.get("ensembl_release")
if not er.host_is_archived(base_url):
    problems.append(f"ensembl_base_url pinli bir arşiv host'u değil: {base_url!r}")
if not isinstance(declared, int):
    problems.append(f"ensembl_release bir tamsayı değil: {declared!r}")
else:
    print(f"  1  pin: {base_url} · beyan edilen sürüm {declared}")

from src.core.config import OrcSonarConfig  # noqa: E402

if OrcSonarConfig.model_fields["ensembl_base_url"].default != base_url:
    problems.append("config.yaml ile model varsayılanı farklı host söylüyor")
if OrcSonarConfig.model_fields["ensembl_release"].default != declared:
    problems.append("config.yaml ile model varsayılanı farklı sürüm söylüyor")

# ---- 2  üretimde sürümsüz anahtar yok -----------------------------------
PRODUCTION = (
    "src/stage1_genomic_map/transcript_resolver.py",
    "src/stage1_genomic_map/tss_mapper.py",
    "src/stage2_offtarget_scan/transcriptome_fetcher.py",
)
offenders: list[str] = []
for rel in PRODUCTION:
    text = Path(rel).read_text(encoding="utf-8")
    for match in re.finditer(r'f?"(seq|bg|ensembl):[^"]*"', text):
        literal = match.group(0)
        if "{release}" in literal or "cache_key(" in literal:
            continue
        # `cache_key("seq", release, …)` passes the prefix as a bare string;
        # that is the sanctioned shape, so only a key that carries more than
        # the prefix is an offender.
        if literal.count(":") >= 1 and not re.fullmatch(r'"(seq|bg|ensembl):"', literal):
            offenders.append(f"{rel}: {literal}")
if offenders:
    problems.append("sürümsüz Ensembl anahtarı: " + "; ".join(offenders))
else:
    print(f"  2  {len(PRODUCTION)} üretim dosyasında sürümsüz Ensembl anahtarı yok")

# ---- 3  manifest --------------------------------------------------------
from src.core.run_manifest import data_sources  # noqa: E402

block = data_sources(Path("."))
ens = block.get("ensembl", {})
if ens.get("release") != declared:
    problems.append(f"manifest sürümü {ens.get('release')!r}, config {declared!r}")
if not ens.get("pinned"):
    problems.append("manifest pin'i yakalamıyor")
if "release_verified" not in ens:
    problems.append("manifest doğrulanma durumunu kaydetmiyor")
else:
    print(f"  3  manifest: release={ens.get('release')} pinned={ens.get('pinned')} "
          f"verified={ens.get('release_verified')}")

# ---- 4  kontrolün iki yönü ----------------------------------------------
try:
    er.verify(declared=115, live=116)
    problems.append("uyuşmazlık istisna atmadı")
except er.ReleaseMismatch:
    pass
er.verify(declared=115, live=None)  # ulaşılamama istisna atmamalı
if er.verified(declared=115, live=None) is not False:
    problems.append("ulaşılamama 'doğrulandı' sayılıyor")
if er.verified(declared=115, live=115) is not True:
    problems.append("eşleşme 'doğrulandı' sayılmıyor")
print("  4  uyuşmazlık RET · ulaşılamama = doğrulanmadı (sessiz geçiş değil)")

# ---- 5  AĞ: host beyan edilen sürümü veriyor ----------------------------
live = er.live_release(base_url, timeout=25.0)
if live is None:
    print("  5  ATLANDI — pinlenmiş host'a ulaşılamadı (ağ yok)")
    print("  6  ATLANDI — aynı sebep")
else:
    if live != declared:
        problems.append(
            f"PİN YANLIŞ: host {live} veriyor, config {declared} diyor"
        )
    else:
        print(f"  5a pinlenmiş host sürüm {live} veriyor")
    # Bu işin başladığı ölçüm: VEGFA transkripti 115'te 3535 nt.
    import requests

    try:
        resp = requests.get(
            f"{base_url.rstrip('/')}/sequence/id/ENST00000372067?type=cdna",
            headers={"Content-Type": "application/json"},
            timeout=60,
        )
        resp.raise_for_status()
        seq = resp.json().get("seq", "")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"pinlenmiş host'tan dizi çekilemedi: {exc}")
        seq = ""
    if seq:
        if len(seq) != 3535:
            problems.append(
                f"ENST00000372067 {len(seq)} nt geldi, sürüm {declared} için "
                f"beklenen 3535 (116'da 3537) — pin baytları belirlemiyor"
            )
        else:
            print(f"  5b ENST00000372067 = {len(seq)} nt (sürüm 116'da 3537)")

    # ---- 6  AĞ: iki çekim birebir aynı ---------------------------------
    from src.core.config import config_from_mapping
    from src.stage2_offtarget_scan.transcriptome_fetcher import _load_sequences

    ids = ["ENST00000372067", "ENST00000377970", "ENST00000230480"]
    runs = []
    for _ in range(2):
        with tempfile.TemporaryDirectory() as tmp:
            cache_db = Path(tmp) / "cache.db"   # her koşu TEMİZ önbellekle
            cfg = config_from_mapping(
                {"target_gene": "VEGFA", "cell_line": "HeLa",
                 "data_paths": {"cache_db": str(cache_db)}},
                data_paths={"cache_db": str(cache_db)},
            )
            runs.append(_load_sequences(ids, cfg))
    if not runs[0]:
        problems.append("ilk çekim boş döndü")
    elif runs[0] != runs[1]:
        differing = [k for k in runs[0] if runs[0].get(k) != runs[1].get(k)]
        problems.append(f"iki çekim farklı: {differing}")
    else:
        lens = {k: len(v) for k, v in sorted(runs[0].items())}
        print(f"  6  iki temiz-önbellek çekimi birebir aynı: {lens}")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo "# 7  birim testleri"
ORCSONAR_SUITE_RECEIPT="$(mktemp -u)" "$PY" -m pytest \
    tests/unit/test_ensembl_release.py tests/unit/test_run_manifest.py \
    tests/unit/test_transcript_resolver.py tests/unit/test_tss_mapper.py \
    tests/unit/test_transcriptome_fetcher.py \
    -q -o addopts="" -p no:cacheprovider \
    || fail "B17 birim testleri yeşil değil"

echo
echo "GEÇTİ — Ensembl sürümü pinli, her önbellek anahtarı onu taşıyor, manifest"
echo "        onu kaydediyor, uyuşmazlık koşuyu durduruyor, ve aynı sürümle iki"
echo "        temiz çekim birebir aynı."
echo "        NOT: eski karışık önbellek girdileri SİLİNMEDİ — anahtarları"
echo "        farklı olduğu için artık ulaşılamaz. results/ altındaki koşular"
echo "        hâlâ eski karışımla üretilmiş; yeniden koşum B12'de."
