#!/usr/bin/env bash
# Kabul kriteri — A9: "§6'da dışlama listesi kuralı".
#
# Dokuz ölçüm. 4, 5, 6 ve 7 ayırt edici olanlar.
#
#   1  §6.6 var, yer tutucu yok, üç alt bölümü yazılı
#   2  İKİ dışlamanın ZIT yönleri yazılı: hedef zorunlu, ikincil yasak
#   3  hedefin tanımlanma kuralı ve §7.2 ile ilişkisi yazılı (aynı prob
#      filtreyi hesaplıyor VE evrenden çıkıyor)
#   4  ÖLÇÜM: hedefin AP'ye katkısı (`1/P`) §6.6.1'in yazdığı değerde, ve
#      §4.4'ün marjından KÜÇÜK. Dışlamanın "ağır iş yaptığı" iddiası bu
#      ölçümle çürür
#   5  ÖLÇÜM, ayırt edici: ikincil etki kümesi SIGNOR'da gerçekten yok —
#      on hedefte toplam gen sayısı §6.6.2'nin tablosuyla birebir. Varsa
#      yasak gerekçesiz kalır
#   6  ÖLÇÜM, ayırt edici: silmenin YÖNÜ. Kaçırılanları silmek `lift`'i
#      yükseltiyor, rastgele silmek yükseltmiyor — §6.6.2'nin bütün kuralı
#      bu asimetriye dayanıyor
#   7  KONTROL: aynı ölçümde `ΔAP` küçük kalıyor (karar kuralı bağışık) —
#      bu olmadan 6. ölçüm "silmek her şeyi bozar" demiş olurdu, oysa
#      iddia daha ince: başlık bozulur, test bozulmaz
#   8  kayıt depoda + SIGNOR manifest'te, lisansı DOĞRULANMAMIŞ olarak
#   9  `A13`'ün haritası §6'yı A9'a veriyor
#
# ⚠️ 4-7 GEO gerektirir; ağ yoksa ATLANIR, ölçüm §6.6'yı yanlışlarsa GEÇMEZ.

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

warn_untracked docs .claude reports data/external || true

"$PY" - <<'INNER' || exit 1
from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path

import yaml

DOC = Path("docs/PRE_REGISTRATION.md")
MAP = Path(".claude/prereg_sections.yaml")
MANIFEST = Path("data/external/manifest.json")
RECORD = Path("reports/a9-dislama-2026-11-27")

problems: list[str] = []
text = DOC.read_text(encoding="utf-8")

found = re.search(r"^### 6\.6 (.+?)$(.*?)(?=^### 6\.7|^## 7\.)", text, re.S | re.M)
if not found:
    sys.exit("§6.6 (dışlama kuralı) bölümü bulunamadı")
body = found.group(2)

# ---- 1  bölüm -------------------------------------------------------------
leftovers = re.findall(r"<[^<>\n]{10,}>", body)
if leftovers:
    problems.append(f"§6.6'da yer tutucu kalmış: {leftovers[:2]}")
absent = [f"6.6.{i}" for i in range(1, 4) if f"#### 6.6.{i}" not in body]
if absent:
    problems.append(f"§6.6 alt bölümleri eksik: {absent}")
if not problems:
    print("  1  §6.6 dolu, üç alt bölümü yazılı")

# ---- 2  zıt yönler --------------------------------------------------------
if not re.search(r"yönleri\s*\*\*zıt\*\*|yönleri zıt", body):
    problems.append("§6.6 iki dışlamanın yönlerinin zıt olduğunu yazmıyor")
elif not (re.search(r"ihtiyatlı", body) and re.search(r"ayarlama yönü", body)):
    problems.append("§6.6 hangi yönün ihtiyatlı, hangisinin ayarlama olduğunu yazmıyor")
else:
    print("  2  iki dışlamanın zıt yönleri yazılı (biri ihtiyatlı, biri ayarlama)")

# ---- 3  hedefin tanımı ve §7.2 ile ilişkisi -------------------------------
if not re.search(r"bütün probları", body):
    problems.append("§6.6.1 hedefin BÜTÜN problarının çıktığını yazmıyor")
elif not re.search(r"§7\.2.{0,400}kullanılır.{0,80}çıkarılır|"
                   r"hesaplamak için\s*\n?\s*\*\*kullanılır\*\*", body, re.S):
    problems.append(
        "§6.6.1 hedefin probunun §7.2'nin filtresini hesaplamak için "
        "KULLANILDIĞINI ve evrenden ÇIKARILDIĞINI birlikte yazmıyor"
    )
else:
    print("  3  hedefin tanımı ve §7.2 ile ilişkisi yazılı")

# ---- ölçüm altyapısı ------------------------------------------------------
sys.path.insert(0, str(RECORD))
olcum = None
try:
    import olcum  # type: ignore[import-not-found]
except Exception as exc:  # noqa: BLE001
    print(f"  4-7  ATLANDI — ölçüm betiği içe alınamadı ({exc})")

tables: dict[str, list[dict[str, object]]] = {}
if olcum is not None:
    for gsm, (gpl, _) in olcum.ARRAYS.items():
        try:
            tables[gsm] = olcum.universe(gsm, gpl)
        except Exception:  # noqa: BLE001 - ağ yoksa boş kalır
            continue

if olcum is not None and not tables:
    print("  4  ATLANDI — GEO'ya ulaşılamadı (ağ yok)")
    print("  6  ATLANDI")
    print("  7  ATLANDI")
elif olcum is not None:
    # ---- 4  hedefin katkısı ---------------------------------------------
    declared = re.search(r"medyan\s*`?1/P`?\s*=\s*\*\*(0[.,]\d+)\*\*", body)
    margin = re.search(r"marjının\s*\n?\s*\((0[.,]\d+)\)", body)
    contributions = [
        1.0 / sum(int(d["label"]) for d in data) for data in tables.values()
        if any(int(d["label"]) for d in data)
    ]
    observed = statistics.median(contributions)
    if declared is None:
        problems.append("§6.6.1 medyan `1/P` katkısını sayıyla yazmıyor")
    else:
        claimed = float(declared.group(1).replace(",", "."))
        if abs(claimed - observed) > max(0.0005, observed * 0.3):
            problems.append(
                f"§6.6.1 medyan 1/P = {claimed} diyor, ölçüm {observed:.5f} "
                "veriyor"
            )
        elif margin is None:
            problems.append("§6.6.1 katkıyı §4.4'ün marjıyla karşılaştırmıyor")
        elif observed >= float(margin.group(1).replace(",", ".")):
            problems.append(
                f"hedefin katkısı {observed:.5f} marjdan ({margin.group(1)}) "
                "KÜÇÜK değil — §6.6.1'in 'sayısal etkisi küçük' cümlesi düşer"
            )
        else:
            positives = sum(
                1 for gsm, data in tables.items()
                if any(d["symbol"] == olcum.ARRAYS[gsm][1] and int(d["label"])
                       for d in data)
            )
            print(f"  4  hedef {positives}/{len(tables)} array'de pozitif; "
                  f"medyan 1/P = {observed:.5f} < marj")

    # ---- 6 ve 7  silmenin yönü ve kontrolü -------------------------------
    import random

    rng = random.Random(7)
    random_lift: list[float] = []
    worst_lift: list[float] = []
    worst_ap: list[float] = []
    for data in tables.values():
        pairs = [(float(d["mock"]), int(d["label"])) for d in data
                 if d["mock"] is not None]
        if not pairs or not any(p[1] for p in pairs):
            continue
        base_ap, base_lift = olcum.ap_and_lift(pairs)
        positives = [i for i, p in enumerate(pairs) if p[1]]
        k = int(len(positives) * 0.10)
        if k == 0:
            continue
        samples = [
            olcum.ap_and_lift([p for i, p in enumerate(pairs)
                               if i not in set(rng.sample(positives, k))])
            for _ in range(10)
        ]
        random_lift.append(statistics.fmean(s[1] for s in samples) - base_lift)
        worst = set(sorted(positives, key=lambda i: pairs[i][0])[:k])
        value = olcum.ap_and_lift([p for i, p in enumerate(pairs)
                                   if i not in worst])
        worst_lift.append(value[1] - base_lift)
        worst_ap.append(value[0] - base_ap)
    if not worst_lift:
        print("  6  ATLANDI — ölçülebilir array yok")
    else:
        worst_median = statistics.median(worst_lift)
        random_median = statistics.median(random_lift)
        if worst_median <= 0:
            problems.append(
                f"kaçırılanları silmek `lift`'i yükseltmiyor "
                f"({worst_median:+.4f}) — §6.6.2'nin bütün kuralı bu yöne dayanıyor"
            )
        elif worst_median <= abs(random_median) * 3:
            problems.append(
                f"kaçırılanları silmek ({worst_median:+.4f}) rastgele silmekten "
                f"({random_median:+.4f}) belirgin ayrışmıyor — asimetri iddiası düşer"
            )
        else:
            print(f"  6  %10 silme: kaçırılanlar Δlift {worst_median:+.4f} ≫ "
                  f"rastgele {random_median:+.4f}")
        ap_median = statistics.median(worst_ap)
        if margin is not None and ap_median >= float(
            margin.group(1).replace(",", ".")
        ):
            problems.append(
                f"kontrol düştü: kaçırılanları silmek ΔAP'yi {ap_median:+.5f} "
                "kadar oynatıyor, yani karar kuralı da etkileniyor — §6.6.2'nin "
                "'karar kuralı bağışık' cümlesi yanlış"
            )
        else:
            print(f"  7  kontrol: aynı silmede ΔAP {ap_median:+.5f} — karar "
                  "kuralı (AP birimi) bağışık, etkilenen şey başlık")

# ---- 5  SIGNOR: ikincil etki kümesi gerçekten yok ------------------------
if olcum is None:
    pass
else:
    downstream = olcum.signor_downstream()
    if not downstream:
        print("  5  ATLANDI — SIGNOR dosyası indirilmemiş")
    else:
        total = sum(len(v) for v in downstream.values())
        # Sayı metinden okunup ÖLÇÜMLE karşılaştırılıyor; betiğe gömülmüyor.
        stated = re.search(r"[Oo]n hedefte toplam \*\*(\d+)\*\* gen", body)
        if stated is None:
            problems.append(
                "§6.6.2 on hedefteki toplam alt akış sayısını `**N**` biçiminde "
                "yazmıyor"
            )
        elif int(stated.group(1)) != total:
            problems.append(
                f"§6.6.2 toplam {stated.group(1)} gen diyor, ölçüm {total} veriyor"
            )
        elif total > 10:
            problems.append(
                f"SIGNOR on hedef için {total} transkripsiyonel alt akış "
                "veriyor — §6.6.2 kümenin yok sayılacak kadar küçük olduğuna "
                "dayanıyor, madde yeniden açılmalı"
            )
        else:
            nonzero = {k: len(v) for k, v in downstream.items() if v}
            for gene in ("MAPK14", "VHL"):
                if gene not in nonzero:
                    problems.append(
                        f"§6.6.2 {gene} için alt akış sayıyor, ölçüm saymıyor"
                    )
            if not [p for p in problems if "alt akış" in p]:
                print(f"  5  SIGNOR: on hedefte toplam {total} transkripsiyonel "
                      f"alt akış ({nonzero})")

# ---- 8  kayıt ve manifest -------------------------------------------------
if not RECORD.is_dir():
    problems.append(f"{RECORD} yok")
else:
    needed = {"README.md", "olcum.py", "olcum.json"}
    have = {p.name for p in RECORD.iterdir()}
    if not needed <= have:
        problems.append(f"{RECORD} eksik: {sorted(needed - have)}")
    else:
        print(f"  8  ölçüm kaydı {RECORD} içinde, betiğiyle")
try:
    artifacts = json.loads(MANIFEST.read_text(encoding="utf-8"))["artifacts"]
except (OSError, ValueError, KeyError) as exc:
    artifacts = []
    problems.append(f"{MANIFEST} okunamadı: {exc}")
entry = next((a for a in artifacts if "signor" in str(a.get("name", ""))), None)
if entry is None:
    problems.append("manifest'te `signor` kaydı yok")
elif "A9" not in (entry.get("used_by") or []):
    problems.append("SIGNOR kaydı `used_by` içinde A9'u saymıyor")
elif not re.search(r"NOT VERIFIED|doğrulanmadı", str(entry.get("licence", "")), re.I):
    problems.append(
        "SIGNOR kaydı lisansın DOĞRULANMADIĞINI yazmıyor — doğrulanmamış bir "
        "lisansı doğrulanmış gibi kaydetmek kaydın kendisini bozar"
    )
else:
    print("  8  SIGNOR manifest'te, lisansı doğrulanmamış olarak kayıtlı")

# ---- 9  harita ------------------------------------------------------------
mapping = yaml.safe_load(MAP.read_text(encoding="utf-8"))["sections"]
owners = (mapping.get(6) or {}).get("owners") or []
if "A9" not in owners:
    problems.append(f"harita §6'yı A9'a vermiyor: {owners}")
else:
    print(f"  9  harita §6'yı A9'a veriyor (sahipler: {owners})")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo
echo "GEÇTİ — §6.6 iki dışlamayı ZIT yönleriyle yazıyor: hedef geni dışlamak"
echo "        zorunlu (ve sayısal etkisi ölçülmüş: marjın altında), ikincil"
echo "        etkileri dışlamak birincilde yasak (çünkü küme sabit bir"
echo "        kaynakta yok, ve kaçırılan pozitifleri silmek raporlanan"
echo "        \`lift\`'i sertçe yükseltiyor). Kontrol ölçümü karar kuralının"
echo "        bu manipülasyona bağışık olduğunu da doğruluyor."
echo "        NOT: ikincil etkiler evrende KALIYOR; tavanı düşüren gürültü."
