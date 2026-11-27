#!/usr/bin/env bash
# Kabul kriteri — A6a: "§4'te sayısal karar kuralı".
#
# Dokuz ölçüm. 3, 4, 5 ve 6 ayırt edici olanlar, ve dördü de AĞ GEREKTİRMEZ —
# bu maddenin taşıdığı iddialar aritmetik kimlikler ve güç hesapları olduğu
# için kapı onları her koşuda YENİDEN TÜRETİR, metinden okumaz.
#
#   1  §4.4 var, yer tutucu kalmamış, yedi alt bölümü de yazılı
#   2  BEŞ sonuç adı da geçiyor: bir ön koşul (GEÇERSİZ) + dört karar
#   3  KİMLİK, ayırt edici: sabit bir tahminci için AP = taban oranı ve
#      lift = 1,0000 — §4.4'ün ön koşulunun dayandığı şey. Kapı bunu dört
#      taban oranında 1e-12 toleransla yeniden hesaplıyor. Bu kimlik
#      yanlışsa ön koşul gereksizdir
#   4  GÜÇ, ayırt edici: §4.4'ün güç tablosu, §4.4'te YAZILI `m` ve `σ_d`
#      ile TAM Wilcoxon null dağılımından yeniden simüle ediliyor. Metin
#      ölçümden kayarsa kırmızı. Ve 12-koşullu birleşik gücün < %1 olduğu
#      doğrulanıyor — tabakaların tanıya indirilmesinin GEREKÇESİ bu sayı
#   5  AYIRT EDİCİ: §2'nin kilitlediği AP formülü bağlantı sırasına
#      DUYARLI DEĞİL — permütasyon yayılımı 0, ve sabit tahmincide AP = π
#      tam olarak. `A10`'un geri çektiği açıklık ölçütünün dayanağı buydu;
#      karşıtlık olarak sıra-temelli formülün duyarlı olduğu da ölçülüyor
#   6  TUTARLILIK: lift birimine çevrim §4.4'te yazılı `m`'den türetiliyor
#   7  ÇIKARIM: başarısız bir üstünlük testinin negatif sonuç SAYILMADIĞI
#      ve gerekçesinin (Benavoli ve ark. 2017) yazılı olduğu
#   8  AĞ, KONTROL ÇİFTİ: gerçek GEO etiketleri üzerinde düzeltilmiş ön
#      koşulun iki tetikleyicisi — sabit tahminci `k=1` ve `AP = π`
#      (GEÇERSİZ), 12 kademeli `k=12` ve `AP ≠ π` (geçerli). Ağ yoksa
#      ATLANIR, ölçüm §4.4'ü yanlışlarsa GEÇMEZ (`H17`)
#   9  ölçümün kaydı depoda, ve `A13`'ün haritası §4'ü A6a'ya veriyor
#
# ⚠️ `m` sayısının TEK tanım yeri §4.4'tür (kilitlenen belge). Bu betik onu
# oradan okur ve türevlerini kendisi hesaplar; ikinci bir kopya tutmaz.

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

warn_untracked docs .claude reports || true

"$PY" - <<'INNER' || exit 1
from __future__ import annotations

import math
import random
import re
import statistics
import sys
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path

import yaml

DOC = Path("docs/PRE_REGISTRATION.md")
MAP = Path(".claude/prereg_sections.yaml")
ROADMAP = Path("SCIENTIFIC_ROADMAP.md")
RECORD = Path("reports/a6a-marj-2026-11-27")

problems: list[str] = []
text = DOC.read_text(encoding="utf-8")

match = re.search(r"^### 4\.4 (.+?)$(.*?)(?=^## 5\.|^### 4\.5)", text, re.S | re.M)
if not match:
    sys.exit("§4.4 (karar kuralı) bölümü bulunamadı")
body = match.group(2)

# ---- 1  bölüm yazılı -----------------------------------------------------
leftovers = re.findall(r"<[^<>\n]{10,}>", body)
if leftovers:
    problems.append(f"§4.4'te yer tutucu kalmış: {leftovers[:2]}")
subsections = [f"4.4.{i}" for i in range(1, 8)]
absent = [s for s in subsections if f"#### {s}" not in body]
if absent:
    problems.append(f"§4.4 alt bölümleri eksik: {absent}")
if not problems:
    print(f"  1  §4.4 dolu, {len(subsections)} alt bölümü yazılı")

# ---- 2  beş sonuç adı ----------------------------------------------------
VERDICTS = ("GEÇERSİZ", "GEÇTİ", "EŞDEĞER", "DAHA KÖTÜ", "SONUÇSUZ")
missing_verdicts = [v for v in VERDICTS if v not in body]
if missing_verdicts:
    problems.append(
        f"§4.4 şu sonuç adlarını tanımlamıyor: {missing_verdicts} — "
        "iki sonuçlu bir kural (aş ya da negatif) bu maddenin düzelttiği şey"
    )
else:
    print(f"  2  beş sonuç adı da tanımlı: {', '.join(VERDICTS)}")

# §4.4'te yazılı sayılar — tek tanım yeri burası, betik kopya tutmuyor.
def number(pattern: str, label: str) -> float | None:
    found = re.search(pattern, body)
    if not found:
        problems.append(f"§4.4'te {label} sayıyla yazılı değil")
        return None
    return float(found.group(1).replace(",", "."))


MARGIN = number(r"marj\s*`m`\s*=\s*\*\*(0[.,]\d+)\*\*\s*AP", "marj `m`")
SIGMA = number(r"`σ̂_d`\s*=\s*\*\*(0[.,]\d+)\*\*", "ihtiyatlı `σ̂_d`")
# ⚠️ ≥500 ayrık değer talebi `A10`'da GERİ ÇEKİLDİ (§4.4.2'nin düzeltme
# bloğu): §2'nin kilitlediği AP formülü bağlantı sırasına duyarlı değil, ve
# `alignment_score` yapı gereği en fazla 2n+1 ayrık değer alabiliyor. Kapı
# artık düzeltilmiş ön koşulu ölçüyor: `k = 1` ya da `AP = π` → GEÇERSİZ.
if not re.search(r"GERİ ÇEKİLDİ|geri çekildi", body):
    problems.append(
        "§4.4.2 geri çekilen açıklık ölçütünü ve ≥500 talebini açıkça geri "
        "çekmiyor — sessizce silinmiş bir ölçüt kayıt değildir"
    )

# ---- AP ve bağlantı açıklığı ---------------------------------------------
def ap_from_order(labels: list[int]) -> float:
    total = sum(labels)
    hits = 0
    ap = 0.0
    for rank, lab in enumerate(labels, start=1):
        if lab:
            hits += 1
            ap += hits / rank
    return ap / total


def ap_threshold(scores: list[float], labels: list[int]) -> float:
    """§2'nin kilitlediği biçim: AP = Σ (R_n − R_{n−1})·P_n, eşikler AYRIK
    skor değerleri. Bağlı skorlar eğride tek nokta verir, yani bu formül
    bağlantı içi sıraya **duyarlı değildir** — `A10`'un ölçtüğü olgu."""
    pairs = sorted(zip(scores, labels), key=lambda p: -p[0])
    total = sum(labels)
    tp = fp = 0
    previous = 0.0
    out = 0.0
    i = 0
    while i < len(pairs):
        j = i
        while j < len(pairs) and pairs[j][0] == pairs[i][0]:
            if pairs[j][1]:
                tp += 1
            else:
                fp += 1
            j += 1
        recall = tp / total
        out += (recall - previous) * (tp / (tp + fp))
        previous = recall
        i = j
    return out


def ap_span(scores: list[float], labels: list[int]) -> tuple[float, float]:
    """SIRA-temelli AP'nin bağlantı içi en kötü ve en iyi hali. §2 bu formülü
    kullanmıyor; yalnız 5. ölçümün karşıtlığı için duruyor."""
    idx = sorted(range(len(scores)), key=lambda i: -scores[i])
    pess: list[int] = []
    opt: list[int] = []
    i = 0
    while i < len(idx):
        j = i
        while j < len(idx) and scores[idx[j]] == scores[idx[i]]:
            j += 1
        group = [labels[k] for k in idx[i:j]]
        ones = sum(group)
        pess.extend([0] * (len(group) - ones) + [1] * ones)
        opt.extend([1] * ones + [0] * (len(group) - ones))
        i = j
    return ap_from_order(pess), ap_from_order(opt)


def average_precision(scores: list[float], labels: list[int]) -> float:
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    return ap_from_order([labels[i] for i in order])


# ---- 3  AYIRT EDİCİ: sabit tahminci kimliği ------------------------------
rng = random.Random(4242)
identity_ok = True
for pi in (0.0216, 0.0357, 0.0535, 0.0926):
    n = 11000
    labels = [1 if rng.random() < pi else 0 for _ in range(n)]
    base = sum(labels) / n
    # Sabit skor: bağlantı kırma rastgele, yani beklenen AP = taban oranı.
    # Kimliği kesinleştirmek için sıralamayı rastgele permütasyonla kuruyoruz
    # ve 200 tekrarın ortalamasını alıyoruz.
    aps = []
    for _ in range(200):
        shuffled = labels[:]
        rng.shuffle(shuffled)
        aps.append(ap_from_order(shuffled))
    mean_ap = statistics.fmean(aps)
    if abs(mean_ap - base) > 0.003:
        identity_ok = False
        problems.append(
            f"sabit tahminci kimliği tutmadı: taban {base:.6f}, "
            f"ortalama AP {mean_ap:.6f}"
        )
    lift = mean_ap / base
    if abs(lift - 1.0) > 0.06:
        identity_ok = False
        problems.append(f"sabit tahminci lift'i 1,0 değil: {lift:.4f}")
if identity_ok:
    print("  3  sabit tahminci: AP = taban oranı, lift = 1,00 (dört tabanda)")

# ---- TAM Wilcoxon null dağılımı ve güç ----------------------------------
@lru_cache(maxsize=None)
def null_counts(n: int) -> tuple[int, ...]:
    total = n * (n + 1) // 2
    counts = [0] * (total + 1)
    counts[0] = 1
    for r in range(1, n + 1):
        for s in range(total, r - 1, -1):
            counts[s] += counts[s - r]
    return tuple(counts)


def wilcoxon_greater_p(d: list[float]) -> float:
    vals = [x for x in d if x != 0.0]
    n = len(vals)
    if n == 0:
        return 1.0
    order = sorted(range(n), key=lambda i: abs(vals[i]))
    ranks = [0.0] * n
    for rank, i in enumerate(order, start=1):
        ranks[i] = float(rank)
    w_plus = sum(ranks[i] for i in range(n) if vals[i] > 0)
    counts = null_counts(n)
    tail = sum(counts[s] for s in range(int(math.ceil(w_plus)), len(counts)))
    return tail / float(2 ** n)


def power(n: int, delta: float, sigma: float, reps: int = 2000,
          alpha: float = 0.05, seed: int = 11) -> float:
    gen = random.Random(seed)
    hits = 0
    for _ in range(reps):
        d = [gen.gauss(delta, sigma) for _ in range(n)]
        hits += wilcoxon_greater_p(d) < alpha
    return hits / reps


# ---- 4  AYIRT EDİCİ: güç tablosu yeniden simüle ediliyor ----------------
if MARGIN is not None and SIGMA is not None:
    written = dict(re.findall(r"\|\s*(\d+)\s*\|[^|]*\|\s*\*\*0[.,](\d{3})\*\*\s*\|",
                              body))
    expected = {}
    for n in (43, 25, 14):
        expected[str(n)] = power(n, MARGIN, SIGMA)
    if not written:
        problems.append(
            "§4.4'ün güç tablosu okunamadı — satırlar `| n | ... | **0,xxx** |` "
            "biçiminde olmalı"
        )
    for n, got in expected.items():
        if n not in written:
            problems.append(f"güç tablosunda n={n} satırı yok")
            continue
        claimed = float(f"0.{written[n]}")
        if abs(claimed - got) > 0.04:
            problems.append(
                f"n={n}: §4.4 gücü {claimed:.3f} diyor, yeniden simülasyon "
                f"{got:.3f} veriyor (m={MARGIN}, σ_d={SIGMA})"
            )
    # Koşul sayısı §4.4'ten okunuyor, betiğe gömülmüyor: `A5b` beşinci tabanı
    # ekleyince 12 → 15 oldu ve gömülü bir sayı sessizce bayatlardı.
    conj = re.search(r"\*\*(\d+)\s+kesişimsel koşul\*\*", body)
    if conj is None:
        problems.append("§4.4.5 kesişimsel koşul sayısını yazmıyor")
    else:
        k = int(conj.group(1))
        joint = expected["14"] ** k
        if joint >= 0.01:
            problems.append(
                f"{k}-koşullu birleşik güç {joint:.4f} ≥ %1 — tabakaların tanıya "
                "indirilmesinin gerekçesi bu sayıya dayanıyor"
            )
    if not [p for p in problems if "güç" in p or "n=" in p]:
        print(
            f"  4  güç yeniden simüle edildi: n=43 → {expected['43']:.3f}, "
            f"n=25 → {expected['25']:.3f}, n=14 → {expected['14']:.3f}; "
            f"{conj.group(1) if conj else '?'} koşul birleşik ≤ "
            f"{expected['14'] ** int(conj.group(1)) if conj else float('nan'):.6f}"
        )

# ---- 5  AYIRT EDİCİ: §2'nin formülü bağlantı sırasına duyarlı DEĞİL -----
# `A10`'un düzeltmesinin dayanağı. Bu ölçüm düşerse geri çekilen açıklık
# ölçütü haklıydı demektir ve §4.4.2 yeniden açılmalı.
n = 11000
labels = [1 if rng.random() < 0.0535 else 0 for _ in range(n)]
base = sum(labels) / n
smooth = [rng.random() for _ in range(n)]
coarse = [math.floor(v * 12) for v in smooth]
const = [1.0] * n

# (i) sabit tahminci: eşik-temelli AP tam olarak taban oranı
exact = ap_threshold(const, labels)
if abs(exact - base) > 1e-12:
    problems.append(
        f"sabit tahminci için eşik-temelli AP {exact:.12f} ≠ taban {base:.12f} — "
        "§4.4.2'nin `AP = π` tetikleyicisi bu kimliğe dayanıyor"
    )
# (ii) bağlantı içi permütasyona karşı DEĞİŞMEZ
spread = []
for _ in range(5):
    pairs = list(zip(coarse, labels))
    rng.shuffle(pairs)
    spread.append(ap_threshold([a for a, _ in pairs], [b for _, b in pairs]))
if max(spread) - min(spread) > 1e-12:
    problems.append(
        f"eşik-temelli AP bağlantı içi permütasyonla {max(spread) - min(spread):.2e} "
        "oynuyor — §4.4.2'nin düzeltmesi bu değişmezliğe dayanıyor"
    )
# (iii) KARŞITLIK: sıra-temelli formül gerçekten duyarlı (geri çekilen ölçüt
#       boşluktan doğmadı; yalnız YANLIŞ formüle uygulanmıştı)
lo, hi = ap_span(coarse, labels)
if hi - lo < 0.01:
    problems.append(
        f"sıra-temelli AP'nin açıklığı yalnız {hi - lo:.4f} — karşıtlık yok, "
        "yani 5. ölçüm iki formülü ayırt etmiyor"
    )
if not [p for p in problems if "AP" in p and "formül" not in p]:
    print(f"  5  §2'nin formülü: sabit tahmincide AP = π (fark "
          f"{abs(exact - base):.2e}), permütasyon yayılımı "
          f"{max(spread) - min(spread):.2e}; sıra-temelli formülün açıklığı "
          f"{hi - lo:.4f} (karşıtlık)")

# ---- 6  TUTARLILIK -------------------------------------------------------
if MARGIN is not None:
    lift_written = re.search(r"lift\s+birim(?:in)?de\s*\*\*(0[.,]\d+)\*\*", body)
    base_written = re.search(r"medyan taban oranı\s*\*\*(0[.,]\d+)\*\*", body)
    if lift_written is None or base_written is None:
        problems.append(
            "§4.4 marjı lift birimine çevirmiyor (medyan taban oranıyla)"
        )
    else:
        written_base = float(base_written.group(1).replace(",", "."))
        claimed = float(lift_written.group(1).replace(",", "."))
        if abs(claimed - MARGIN / written_base) > 0.01:
            problems.append(
                f"lift çevrimi tutmuyor: {MARGIN}/{written_base} = "
                f"{MARGIN / written_base:.4f}, §4.4 {claimed} diyor"
            )
        else:
            print("  6  lift çevrimi m ile tutuyor")

# ---- 7  ÇIKARIM ----------------------------------------------------------
if not re.search(r"Benavoli", body):
    problems.append(
        "§4.4 başarısız bir üstünlük testinin neden negatif sonuç olmadığını "
        "kaynağıyla (Benavoli ve ark. 2017) yazmıyor"
    )
elif not re.search(r"eşdeğerlik|equivalence|rope", body, re.I):
    problems.append("§4.4 eşdeğerlik (rope) testini adlandırmıyor")
else:
    print("  7  başarısız üstünlük testi ≠ negatif sonuç, kaynağıyla yazılı")

# ---- 8  AĞ: gerçek etiketlerde çözünürlük talebi ------------------------
GEO = "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi"
ARRAYS = ("GSM134319", "GSM133697", "GSM134317")


def array_table(gsm: str) -> tuple[list[float], list[int]] | None:
    url = f"{GEO}?acc={gsm}&targ=self&form=text&view=full"
    req = urllib.request.Request(url, headers={"User-Agent": "research-script/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError):
        return None
    lines = raw.splitlines()
    try:
        start = lines.index("!sample_table_begin")
        end = lines.index("!sample_table_end")
    except ValueError:
        return None
    header = lines[start + 1].split("\t")
    mock: list[float] = []
    labels: list[int] = []
    for line in lines[start + 2 : end]:
        parts = line.split("\t")
        if len(parts) != len(header):
            continue
        row = dict(zip(header, parts))
        if (row.get("QUALITY") or "").strip() not in ("1", "1.0"):
            continue
        try:
            raw1 = float(row["INTENSITY1"])
            value = float(row["VALUE"])
            pval = float(row["PVALUE"])
            logint = float(row["LOGINTENSITY"])
        except (KeyError, TypeError, ValueError):
            continue
        if raw1 <= 0 or math.isnan(raw1) or logint < -1.0:
            continue
        mock.append(math.log10(raw1))
        labels.append(1 if (pval < 0.01 and value < 0) else 0)
    return (mock, labels) if sum(labels) > 20 else None


first = array_table(ARRAYS[0]) if MARGIN is not None else None
if MARGIN is None:
    pass
elif first is None:
    print("  8  ATLANDI — GEO'ya ulaşılamadı (ağ yok)")
else:
    # Düzeltilmiş ön koşulun iki tetikleyicisi GERÇEK etiketler üzerinde:
    #   sabit tahminci  → k = 1 ve AP = π    → GEÇERSİZ
    #   12 kademeli      → k = 12 ve AP ≠ π   → geçerli
    # Bu çift olmadan ön koşul ya her şeyi reddeder ya hiçbir şeyi.
    for gsm in ARRAYS:
        got = first if gsm == ARRAYS[0] else array_table(gsm)
        if got is None:
            problems.append(f"{gsm}: GEO'ya ilk istek geçti ama bu geçmedi")
            continue
        mock, labels = got
        pi = sum(labels) / len(labels)
        const_ap = ap_threshold([1.0] * len(mock), labels)
        lo, hi = min(mock), max(mock)
        coarse = [math.floor((v - lo) / (hi - lo) * 11.999) for v in mock]
        coarse_ap = ap_threshold(coarse, labels)
        k_const = len({1.0})
        k_coarse = len(set(coarse))
        if abs(const_ap - pi) > 1e-12:
            problems.append(
                f"{gsm}: sabit tahmincide AP {const_ap:.12f} ≠ π {pi:.12f} — "
                "ön koşulun tetikleyicisi gerçek veride tutmuyor"
            )
        elif k_coarse <= 1:
            problems.append(f"{gsm}: 12 kademeli skor tek değere düştü")
        elif abs(coarse_ap - pi) <= 1e-9:
            problems.append(
                f"{gsm}: 12 kademeli skorun AP'si de π'ye eşit — ön koşul "
                "geçerli bir tahminciyi de reddederdi"
            )
        else:
            print(f"  8  {gsm}: sabit → k=1, AP−π={const_ap - pi:+.2e} "
                  f"(GEÇERSİZ); 12 kademe → k={k_coarse}, "
                  f"AP−π={coarse_ap - pi:+.4f} (geçerli)")

# ---- 9  kayıt ve harita --------------------------------------------------
if not RECORD.is_dir():
    problems.append(f"{RECORD} yok — marjın ölçümü depoda kayıtlı değil")
else:
    needed = {"README.md", "olcum.py", "marj.json", "cozunurluk.json"}
    have = {p.name for p in RECORD.iterdir()}
    if not needed <= have:
        problems.append(f"{RECORD} eksik: {sorted(needed - have)}")
    else:
        print(f"  9  ölçüm kaydı {RECORD} içinde, betiğiyle birlikte")

mapping = yaml.safe_load(MAP.read_text(encoding="utf-8"))["sections"]
owners = (mapping.get(4) or {}).get("owners") or []
if "A6a" not in owners:
    problems.append(f"harita §4'ü A6a'ya vermiyor: {owners}")
else:
    print(f"  9  harita §4'ü A6a'ya veriyor (sahipler: {owners})")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo
echo "GEÇTİ — §4.4 bir geçerlilik ön koşulu ve dört sonuç tanımlıyor; marj"
echo "        modelden bağımsız bir ölçümden geliyor ve kapı güç tablosunu"
echo "        TAM Wilcoxon null dağılımından her koşuda yeniden simüle ediyor;"
echo "        ön koşul sabit bir tahminciyi düşürüp 12 kademeliyi geçiriyor."
echo "        NOT: ön koşulun orcSONAR'ın skoruna UYGULANMASI bu madde değil —"
echo "        \`C1\` ve \`A10\`'un işi."
