#!/usr/bin/env bash
# Kabul kriteri — B11c: "immün verdi ölçülmüş şans oranıyla raporlanıyor ve U
# sayısı ayrı alan; bileşim-eşleşmeli null denendi ve ölçümle reddedildi;
# motif listesinin her satırının provenansı yazılı".
#
# Dokuz ölçüm. 2, 3, 6, 7 ve 9 ayırt edici olanlar.
#
#   1  KOD: `ImmuneResult` üç yeni alanı taşıyor
#   2  ARİTMETİK, ayırt edici: `chance_hits` kapalı formla birebir, ÜÇ ayrı
#      uzunlukta — motif dosyasından yeniden hesaplanıyor, gömülü değil
#   3  SAYI, ayırt edici: projenin dupleks uzunluğunda 0,5642 — yol
#      haritasında ve `docs/DATA_SOURCES.md`'de alıntılanan sayı
#   4  DAVRANIŞ: `u_count` raporlanıyor ve T'yi U sayıyor
#   5  KONTROL: taranmamış dizi yeni alanlarda da bilinmiyor — yoksa
#      `B11b`'nin düzeltmesi yarım kalmış olurdu
#   6  ÖLÇÜM, ayırt edici: SATIRIN ÖNERİSİNİN ÇÜRÜTÜLMESİ yeniden üretiliyor
#      — mononükleotid karıştırma null'u gözlenenle birlikte yükseliyor
#      (oran ≈ 1), düzgün-bileşim null'u yükselmiyor. Bu ölçüm düşerse
#      bileşim-eşleşmeli null haklıydı demektir ve madde yeniden açılmalı
#   7  ÖLÇÜM, ayırt edici: rastgele dizilerin `HIGH` çıkma oranı ilan edilen
#      değerle tutuyor — verdinin kalibre OLMADIĞI iddiasının dayanağı
#   8  PROVENANS: her motif için bir satır, dört kaynaksızın kaynaksız
#      olduğu açıkça yazılı, PMID'ler ve eksik `GUCCUUCAA` notu var
#   9  SENKRON, ayırt edici: provenans tablosu motif dosyasıyla İKİ YÖNLÜ
#      örtüşüyor — dosyada olup tabloda olmayan ya da tersi, kırmızı
#
# ⚠️ `data/` yalnız OKUNUYOR (değişmez 1).

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

fail() { echo "GEÇMEDİ — $1"; exit 1; }

# shellcheck source=_lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

PY=""
for cand in "${PYTHON:-}" python3 python; do
    [ -n "$cand" ] || continue
    if "$cand" -c "import pytest, pydantic, yaml" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || fail "pytest+pydantic+pyyaml içeren yorumlayıcı bulunamadı"
echo "# yorumlayıcı: $PY"

warn_untracked src tests docs .claude || true

"$PY" - 2>/dev/null <<'INNER' || exit 1
from __future__ import annotations

import random
import re
import statistics
import sys
from pathlib import Path

from loguru import logger

logger.remove()
sys.path.insert(0, ".")

import yaml  # noqa: E402

from src.core.models import ImmuneResult  # noqa: E402
from src.stage6_execution.immune_screen import (  # noqa: E402
    _load_motifs,
    _reverse_complement_rna,
    _scan_motifs,
    _to_rna,
    screen_immune_motifs,
)

MOTIF_FILE = "data/5_Icra_Güvenlik/Immun_Motifler/immune_motifs.txt"
SOURCES = Path("docs/DATA_SOURCES.md")

problems: list[str] = []
motifs = _load_motifs(MOTIF_FILE)
if motifs is None:
    print(f"GEÇMEDİ — {MOTIF_FILE} okunamadı", file=sys.stderr)
    sys.exit(1)

# ---- 1  KOD: yeni alanlar -----------------------------------------------
missing_fields = [f for f in ("chance_hits", "u_count", "u_fraction")
                  if f not in ImmuneResult.model_fields]
if missing_fields:
    problems.append(f"`ImmuneResult` şu alanları taşımıyor: {missing_fields}")
else:
    print("  1  kod: chance_hits, u_count, u_fraction alanları var")


def closed_form(length: int) -> float:
    return sum(2 * (length - len(m) + 1) * 0.25 ** len(m)
               for m in motifs if length >= len(m))


# ---- 2  ARİTMETİK: kapalı form, üç uzunlukta ---------------------------
bad: list[str] = []
for n in (12, 20, 35):
    got = screen_immune_motifs("A" * n, MOTIF_FILE).chance_hits
    want = closed_form(n)
    if got is None or abs(got - want) > 1e-12:
        bad.append(f"n={n}: {got!r} ≠ {want:.6f}")
if bad:
    problems.append("`chance_hits` kapalı formla tutmuyor: " + "; ".join(bad))
else:
    print(f"  2  chance_hits kapalı formla birebir (n=12/20/35: "
          f"{closed_form(12):.4f}/{closed_form(20):.4f}/{closed_form(35):.4f})")

# ---- 3  SAYI: projenin dupleks uzunluğu --------------------------------
config = yaml.safe_load(Path("config/config.yaml").read_text(encoding="utf-8"))
duplex = len(str(config["sarna_sequence"]))
observed = closed_form(duplex)
declared = re.search(r"~?0[.,]56\d*", SOURCES.read_text(encoding="utf-8"))
if abs(observed - 0.5642) > 5e-4:
    problems.append(
        f"dupleks uzunluğunda ({duplex}) beklenen hit {observed:.4f}, "
        "ilan edilen 0,5642 değil — motif listesi ya da uzunluk değişmiş"
    )
elif declared is None:
    problems.append(
        "`docs/DATA_SOURCES.md` şans oranını (~0,56) anmıyor — sayı yalnız "
        "kodda kalırsa okuyucu verdiyi neye karşı okuyacağını bilmez"
    )
else:
    print(f"  3  n={duplex} için beklenen hit {observed:.4f}, belgede anılıyor")

# ---- 4  DAVRANIŞ: u_count ----------------------------------------------
rna = screen_immune_motifs("UUUUAAAACCCCGGGG", MOTIF_FILE)
dna = screen_immune_motifs("TTTTAAAACCCCGGGG", MOTIF_FILE)
if rna.u_count != 4 or dna.u_count != 4:
    problems.append(f"u_count yanlış: RNA {rna.u_count!r}, DNA {dna.u_count!r}")
elif rna.u_fraction is None or abs(rna.u_fraction - 0.25) > 1e-12:
    problems.append(f"u_fraction yanlış: {rna.u_fraction!r}")
else:
    print("  4  u_count/u_fraction raporlanıyor ve T'yi U sayıyor")

# ---- 5  KONTROL: taranmamış dizi ---------------------------------------
unknown = screen_immune_motifs("GCUUUUGC", "/no/such/dir/motifs.txt")
if (unknown.chance_hits, unknown.u_count, unknown.u_fraction) != (None, None, None):
    problems.append(
        f"taranmamış dizi yeni alanlarda değer taşıyor: "
        f"{unknown.chance_hits!r}/{unknown.u_count!r}/{unknown.u_fraction!r} — "
        "`B11b`'nin düzeltmesi yarım kalır"
    )
else:
    print("  5  kontrol: taranmamış dizi yeni alanlarda da bilinmiyor")

# ---- hit sayacı (null ölçümleri için) ----------------------------------
def hits(sequence: str) -> int:
    rna_seq = _to_rna(sequence)
    return (len(_scan_motifs(rna_seq, motifs))
            + len(_scan_motifs(_reverse_complement_rna(rna_seq), motifs)))


rng = random.Random(11)

# ---- 6  ÖLÇÜM: satırın önerisinin çürütülmesi --------------------------
ratios: list[float] = []
for u_fraction in (0.4, 0.6, 0.8):
    for _ in range(8):
        count = int(duplex * u_fraction)
        seq = ["U"] * count + [rng.choice("ACG") for _ in range(duplex - count)]
        rng.shuffle(seq)
        sequence = "".join(seq)
        seen = hits(sequence)
        chars = list(sequence)
        shuffled = []
        for _ in range(60):
            rng.shuffle(chars)
            shuffled.append(hits("".join(chars)))
        null_mean = statistics.fmean(shuffled)
        if null_mean > 0:
            ratios.append(seen / null_mean)
if not ratios:
    problems.append("çürütme ölçümü kurulamadı")
else:
    median_ratio = statistics.median(ratios)
    if abs(median_ratio - 1.0) > 0.35:
        problems.append(
            f"mononükleotid karıştırma null'u gözlenenden ayrışıyor (oran "
            f"{median_ratio:.2f}) — bileşim-eşleşmeli null haklıydı demektir "
            "ve bu maddenin çürütmesi yeniden açılmalı"
        )
    else:
        uniform = statistics.fmean(
            hits("".join(rng.choice("ACGU") for _ in range(duplex)))
            for _ in range(300)
        )
        if uniform > 1.5:
            problems.append(
                f"düzgün-bileşim null'u da yüksek ({uniform:.2f}) — iki null "
                "ayırt edilemiyor, 6. ölçüm boş"
            )
        else:
            print(f"  6  çürütme yeniden üretildi: karıştırma null'u / gözlenen "
                  f"= {median_ratio:.2f} (≈1, sinyali yok ediyor), düzgün-bileşim "
                  f"null'u {uniform:.2f} (yükselmiyor)")

# ---- 7  ÖLÇÜM: rastgele dizide HIGH oranı ------------------------------
levels = [
    screen_immune_motifs(
        "".join(rng.choice("ACGU") for _ in range(duplex)), MOTIF_FILE
    ).risk_level
    for _ in range(1000)
]
high_rate = levels.count("HIGH") / len(levels)
non_safe = 1 - levels.count("SAFE") / len(levels)
if not 0.08 <= high_rate <= 0.18:
    problems.append(
        f"rastgele dizide HIGH oranı %{high_rate * 100:.1f} — ilan edilen "
        "%12,7'den uzak, motif listesi ya da sınıflandırıcı değişmiş"
    )
else:
    print(f"  7  rastgele {duplex}-mer: HIGH %{high_rate * 100:.1f}, "
          f"SAFE-dışı %{non_safe * 100:.1f} (verdi kalibre DEĞİL)")

# ---- 8 ve 9  PROVENANS ve senkron --------------------------------------
text = SOURCES.read_text(encoding="utf-8")
block = re.search(r"\*\*Provenance, per line\*\*(.*?)(?=^---|\Z)", text, re.S | re.M)
if block is None:
    problems.append("`docs/DATA_SOURCES.md` motif provenans tablosunu taşımıyor")
else:
    body = block.group(1)
    rows = dict(re.findall(r"^\|\s*`([ACGU]+)`\s*\|\s*([^|]+?)\s*\|", body, re.M))
    in_file = set(motifs)
    in_table = set(rows)
    if in_file != in_table:
        problems.append(
            f"provenans tablosu motif dosyasıyla örtüşmüyor — dosyada fazla: "
            f"{sorted(in_file - in_table)}, tabloda fazla: "
            f"{sorted(in_table - in_file)}"
        )
    else:
        # ⚠️ Bir SAYI değil, tam KÜME kontrol ediliyor. İlk hali "en az dört
        # satır kaynaksız" diyordu ve kendi kırmızı-önce denememde yakalandı:
        # `UUUU`'ya uydurma bir kaynak yazmak sayıyı 5'ten 4'e indiriyor ve
        # kapıyı geçiyordu. Kaynaklı tek motif ÖLÇÜLDÜ ve `UGUGU`.
        SOURCED = {"UGUGU"}
        claims_pmid = {m for m, src in rows.items() if re.search(r"PMID", src)}
        unsourced = {m for m, src in rows.items() if re.search(r"none", src, re.I)}
        if claims_pmid != SOURCED:
            problems.append(
                f"PMID iddia eden motifler {sorted(claims_pmid)}, ölçülen küme "
                f"{sorted(SOURCED)} — kaynağı olmayan bir satıra kaynak yazmak "
                "bu maddenin tam tersi"
            )
        elif unsourced | claims_pmid != set(rows):
            problems.append(
                f"ne PMID iddia eden ne kaynaksız diyen satır(lar) var: "
                f"{sorted(set(rows) - unsourced - claims_pmid)} — her satır ya "
                "kaynaklanır ya kaynaksız olduğunu söyler"
            )
        else:
            for pmid, what in (("15778705", "Judge (UGUGU)"),
                               ("19630977", "Goodchild (U sayısı)"),
                               ("21749297", "Jurk (model eksik)"),
                               ("15723075", "Hornung (eksik motif)")):
                if pmid not in body:
                    problems.append(f"provenans {what} PMID'sini taşımıyor: {pmid}")
            if "GUCCUUCAA" not in body:
                problems.append("provenans eksik motif `GUCCUUCAA`'yı anmıyor")
            if not [p for p in problems if "provenans" in p]:
                print(f"  8  provenans: {len(rows)} satır, {len(unsourced)} tanesi "
                      "açıkça kaynaksız, dört PMID ve eksik motif notu var")
                print(f"  9  senkron: tablo ile motif dosyası iki yönlü örtüşüyor "
                      f"({sorted(in_file)})")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo "# birim testleri"
ORCSONAR_SUITE_RECEIPT="$(mktemp -u)" "$PY" -m pytest \
    tests/unit/test_immune_screen.py -q -o addopts="" -p no:cacheprovider \
    || fail "B11c birim testleri yeşil değil"

echo
echo "GEÇTİ — immün verdi artık ölçülmüş şans oranıyla (analitik, simülasyonsuz)"
echo "        ve literatürün kendi korelatı olan U sayısıyla birlikte"
echo "        raporlanıyor; satırın önerdiği bileşim-eşleşmeli null DENENDİ ve"
echo "        çürütmesi her koşuda yeniden üretiliyor; motif listesinin her"
echo "        satırının provenansı yazılı ve tabloyla dosya iki yönlü senkron."
echo "        NOT: eksik motifi (\`GUCCUUCAA\`) EKLEMEK \`data/\`'yı değiştirir,"
echo "        değişmez 1 kapsamında ve ayrı bir karar."
