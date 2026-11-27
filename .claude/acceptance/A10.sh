#!/usr/bin/env bash
# Kabul kriteri — A10: "§7'de haritalama formülü, ve ön koşulu sağladığı
# gösterilmiş".
#
# Dokuz ölçüm. 3, 4, 5 ve 6 ayırt edici olanlar, ve dördü de **kodu** okur ya
# da aritmetiği yeniden türetir — bir modelleme kararının gerekçesi prose
# değil, kaynağın yapısıdır.
#
#   1  §7.7 var, yer tutucu yok, üç alt bölümü yazılı
#   2  formül yazılı, ve reddedilen iki alternatif gerekçesiyle
#   3  KOD, ayırt edici: `alignment_score` gerçekten {+1,0 / +0,5 / 0}
#      toplamı, yani değerleri `{0, 0.5, …, n}` kümesinde. §7.7'nin bölen
#      seçimi (teorik maksimum = n) ve §4.4.2'nin geri çektiği ≥500 talebi
#      bu yapıya dayanıyor
#   4  ARİTMETİK, ayırt edici: ayrık değer TAVANI `2n+1`, ve `n`
#      `config/config.yaml`'ın `sarna_sequence`'ından okunarak §7.7'nin
#      yazdığı tavanla karşılaştırılıyor
#   5  ARİTMETİK, ayırt edici: ulaşılabilir ALT SINIR = seed_length/n, ve
#      §7.7'nin yazdığı değerle birebir. Bu sayı `_NEUTRAL = 0.5`'in neden
#      bir sıralama tersliği olduğunun dayanağı
#   6  KOD + KONTROL: bugünkü kod gerçekten `_NEUTRAL = 0.5` kullanıyor ve
#      0,5 ulaşılabilir aralığın İÇİNDE — tersliğin iddiası bu iki olguya
#      dayanıyor. Biri değişmişse madde yeniden açılmalı
#   7  §4.4.2'nin GERİ ÇEKMESİ yazılı, ve §7.7 ona işaret ediyor
#   8  ölçülmüş yokluk (0,0) ile taranmamış (bilinmiyor) AYRI, tabloyla
#   9  `A13`'ün haritası §7'yi A10'a veriyor
#
# ⚠️ Bu kapı ağ istemiyor ve pytest koşmuyor: ölçtüğü her şey depoda.

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
[ -n "$PY" ] || fail "pyyaml içeren yorumlayıcı bulunamadı; PYTHON=... ile ver"
echo "# yorumlayıcı: $PY"

warn_untracked docs .claude || true

"$PY" - <<'INNER' || exit 1
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

DOC = Path("docs/PRE_REGISTRATION.md")
MAP = Path(".claude/prereg_sections.yaml")
CONFIG = Path("config/config.yaml")
ALIGNER = Path("src/stage2_offtarget_scan/seed_aligner.py")
INTEGRATOR = Path("src/scoring/score_integrator.py")

problems: list[str] = []
text = DOC.read_text(encoding="utf-8")

found = re.search(r"^### 7\.7 (.+?)$(.*?)(?=^### 7\.8|^## 8\.)", text, re.S | re.M)
if not found:
    sys.exit("§7.7 (haritalama) bölümü bulunamadı")
body = found.group(2)

# ---- 1  bölüm -------------------------------------------------------------
leftovers = re.findall(r"<[^<>\n]{10,}>", body)
if leftovers:
    problems.append(f"§7.7'de yer tutucu kalmış: {leftovers[:2]}")
absent = [f"7.7.{i}" for i in range(1, 4) if f"#### 7.7.{i}" not in body]
if absent:
    problems.append(f"§7.7 alt bölümleri eksik: {absent}")
if not problems:
    print("  1  §7.7 dolu, üç alt bölümü yazılı")

# ---- 2  formül ve reddedilenler ------------------------------------------
if not re.search(r"sequence_specificity\s*=\s*alignment_score\s*/\s*n", body):
    problems.append("§7.7 haritalama formülünü yazmıyor")
else:
    rejected = {
        "min-max": r"min-max",
        "yüzdelik": r"yüzdelik",
        "koşuya bağımlılık gerekçesi": r"koşunun \*\*kendi dağılımının\*\*|"
                                       r"kendi dağılımının",
        "GENCODE sonucu": r"GENCODE",
    }
    missing = [k for k, pat in rejected.items() if not re.search(pat, body)]
    if missing:
        problems.append(f"§7.7.1 reddedilen alternatifleri gerekçelendirmiyor: {missing}")
    else:
        print("  2  formül yazılı; min-max ve yüzdelik gerekçesiyle reddedilmiş")

# ---- n ve seed_length config'ten -----------------------------------------
config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
sarna = str(config.get("sarna_sequence", ""))
seed_length = int(config.get("seed_length", 0))
N = len(sarna)
if N == 0 or seed_length == 0:
    problems.append("config/config.yaml'dan sarna_sequence/seed_length okunamadı")

# ---- 3  KOD: alignment_score'un yapısı -----------------------------------
aligner = ALIGNER.read_text(encoding="utf-8") if ALIGNER.exists() else ""
if not aligner:
    problems.append(f"{ALIGNER} okunamadı")
else:
    increments = set(re.findall(r"score \+= (\d\.\d)", aligner))
    if increments != {"1.0", "0.5"}:
        problems.append(
            f"`alignment_score`'un artışları değişmiş: {sorted(increments)} — "
            "§7.7'nin bölen seçimi ve §4.4.2'nin geri çekmesi {1.0, 0.5} "
            "yapısına dayanıyor, madde yeniden açılmalı"
        )
    elif "reverse_complement(seed)" not in aligner:
        problems.append(
            "indeks artık `reverse_complement(seed)` üzerine kurulu değil — "
            "§7.7.2'nin alt sınır argümanı (seed kesin eşleşir) buna dayanıyor"
        )
    else:
        print("  3  kod: artışlar {+1.0, +0.5}, indeks tam seed komplementeri")

# ---- 4  ARİTMETİK: ayrık değer tavanı ------------------------------------
if N:
    ceiling = 2 * N + 1
    written = re.search(r"2n\+1\s*=\s*\*{0,2}(\d+)\*{0,2}", body)
    if written is None:
        problems.append("§7.7.2 ayrık değer tavanını `2n+1 = N` biçiminde yazmıyor")
    elif int(written.group(1)) != ceiling:
        problems.append(
            f"§7.7.2 tavanı {written.group(1)} diyor, config'in n={N}'i "
            f"{ceiling} veriyor"
        )
    else:
        print(f"  4  ayrık değer tavanı 2n+1 = {ceiling} (n={N}, config'ten)")

# ---- 5  ARİTMETİK: ulaşılabilir alt sınır --------------------------------
if N and seed_length:
    floor_value = seed_length / N
    written = re.search(r"\*\*(0[.,]\d+)\*\*\s*=\s*(\d+)/(\d+)", body)
    if written is None:
        problems.append(
            "§7.7.2 ulaşılabilir alt sınırı `**0,xx** = a/b` biçiminde yazmıyor"
        )
    else:
        claimed = float(written.group(1).replace(",", "."))
        if abs(claimed - floor_value) > 1e-9:
            problems.append(
                f"§7.7.2 alt sınırı {claimed} diyor, config "
                f"{seed_length}/{N} = {floor_value} veriyor"
            )
        elif (int(written.group(2)), int(written.group(3))) != (seed_length, N):
            problems.append(
                f"§7.7.2'nin kesri {written.group(2)}/{written.group(3)}, "
                f"config {seed_length}/{N} diyor"
            )
        else:
            print(f"  5  ulaşılabilir alt sınır {floor_value} = "
                  f"{seed_length}/{N} (config'ten)")

# ---- 6  KOD + KONTROL: _NEUTRAL tersliği ---------------------------------
integrator = INTEGRATOR.read_text(encoding="utf-8") if INTEGRATOR.exists() else ""
neutral = re.search(r"_NEUTRAL\s*=\s*([\d.]+)", integrator)
if not integrator:
    problems.append(f"{INTEGRATOR} okunamadı")
elif neutral is None:
    problems.append(
        "`score_integrator` artık `_NEUTRAL` tanımlamıyor — §7.7.2'nin "
        "sıralama tersliği iddiası bu sabite dayanıyor, madde yeniden açılmalı"
    )
elif N and seed_length:
    value = float(neutral.group(1))
    floor_value = seed_length / N
    if not floor_value < value < 1.0:
        problems.append(
            f"`_NEUTRAL = {value}` ulaşılabilir aralığın "
            f"[{floor_value}, 1,0) İÇİNDE değil — terslik iddiası düşer"
        )
    elif "_NEUTRAL" not in body and "0,5" not in body:
        problems.append("§7.7.2 bugünkü fallback değerini anmıyor")
    else:
        print(f"  6  kod: _NEUTRAL = {value}, ulaşılabilir aralığın "
              f"[{floor_value}, 1,0) içinde → terslik gerçek")

# ---- 7  geri çekme -------------------------------------------------------
section442 = re.search(r"#### 4\.4\.2(.*?)(?=#### 4\.4\.3)", text, re.S)
if section442 is None:
    problems.append("§4.4.2 bulunamadı")
else:
    chunk = section442.group(1)
    if not re.search(r"GERİ ÇEKİLDİ|geri çekildi", chunk):
        problems.append(
            "§4.4.2 geri çekmeyi yazmıyor — sessizce değiştirilmiş bir ölçüt "
            "kayıt değildir"
        )
    elif not re.search(r"k > 1|`k = 1`", chunk):
        problems.append("§4.4.2 düzeltilmiş ön koşulu (`k`) yazmıyor")
    elif not re.search(r"§4\.4\.2", body):
        problems.append("§7.7 geri çekmeye işaret etmiyor")
    else:
        print("  7  §4.4.2'nin geri çekmesi yazılı ve §7.7 ona işaret ediyor")

# ---- 8  ölçülmüş yokluk vs taranmamış ------------------------------------
if not (re.search(r"ölçülmüş yokluk", body) and re.search(r"taranmadı", body)):
    problems.append(
        "§7.7.2 'ölçülmüş yokluk (0,0)' ile 'taranmadı (bilinmiyor)' ayrımını "
        "yazmıyor — değişmez 2 ile çelişmemesinin tek sebebi bu ayrım"
    )
elif not re.search(r"\|\s*\*\*0,0\*\*\s*\|", body):
    problems.append("§7.7.2 ayrımı bir tabloda sayıyla vermiyor")
else:
    print("  8  ölçülmüş yokluk (0,0) ile taranmamış (bilinmiyor) ayrı")

# ---- 9  harita -----------------------------------------------------------
mapping = yaml.safe_load(MAP.read_text(encoding="utf-8"))["sections"]
owners = (mapping.get(7) or {}).get("owners") or []
if "A10" not in owners:
    problems.append(f"harita §7'yi A10'a vermiyor: {owners}")
else:
    print(f"  9  harita §7'yi A10'a veriyor (sahipler: {owners})")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo
echo "GEÇTİ — §7.7 haritalamayı teorik maksimuma bölme olarak sabitliyor;"
echo "        koşuya bağımlı iki alternatif gerekçesiyle reddedilmiş; ayrık"
echo "        değer tavanı ve ulaşılabilir alt sınır config'ten YENİDEN"
echo "        türetiliyor; ve aday olmayan genin değeri (0,0) ile bugünkü"
echo "        fallback'in (0,5) yarattığı sıralama tersliği kodda doğrulanıyor."
echo "        NOT: haritalamanın UYGULANMASI \`C1\`, fallback'in düzeltilmesi"
echo "        \`B3\`; bu kapı ikisini de ölçmez."
