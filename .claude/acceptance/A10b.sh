#!/usr/bin/env bash
# Kabul kriteri — A10b: "§7'de G:U ağırlığı ve gerekçesi yazılı".
#
# Dokuz ölçüm. 3, 4, 5 ve 6 ayırt edici olanlar; hiçbiri ağ istemiyor çünkü
# ölçtüğü her şey depoda — kod, config ve projenin kendi Turner tabloları.
#
#   1  §7.8 var, yer tutucu yok, iki alt bölümü yazılı
#   2  ağırlık sayıyla yazılı ve KEYFİ olduğu ilan edilmiş
#   3  KOD, ayırt edici: ağırlıklar hâlâ {+1,0 / +0,5}; biri değişmişse
#      §7.8'in bütün konusu değişmiş demektir
#   4  DAVRANIŞ, ayırt edici: seed bölgesinde G:U FİİLEN oluşmuyor —
#      `seed_aligner` gerçekten koşturulup ölçülüyor. Bu olgu olmadan
#      §7.8.1'in iki sonucu da (literatür uygulanamaz, modüle edilen şey
#      seed dışı) temelsiz kalır
#   5  VERİ, ayırt edici: Turner tablolarından G:U/WC oranının aralığı ve
#      medyanı §7.8.2'nin tablosuyla birebir, VE G:U yığın ΔG'sinin işareti
#      gerçekten değişiyor. "Hiçbir sabit temsil edemez" iddiası bu işaret
#      değişimine dayanıyor
#   6  KONTROL: Watson-Crick yığınlarının işareti DEĞİŞMİYOR — bu kontrol
#      olmadan 5. ölçüm "Turner tabloları gürültülü" demiş olurdu, oysa
#      iddia G:U'ya özgü
#   7  duyarlılık ızgarası {0, 0,5, 1} ilan edilmiş ve birincil hücre sabit
#   8  ölçümün kaydı depoda, betiğiyle
#   9  `A13`'ün haritası §7'yi A10b'ye veriyor ve `A12` ona bağlı
#
# ⚠️ Bu kapı `data/`'yı yalnız OKUYOR (değişmez 1).

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

import re
import sys
from pathlib import Path

import yaml

DOC = Path("docs/PRE_REGISTRATION.md")
MAP = Path(".claude/prereg_sections.yaml")
ROADMAP = Path("SCIENTIFIC_ROADMAP.md")
ALIGNER = Path("src/stage2_offtarget_scan/seed_aligner.py")
RECORD = Path("reports/a10b-gu-agirligi-2026-11-27")

problems: list[str] = []
text = DOC.read_text(encoding="utf-8")

found = re.search(r"^### 7\.8 (.+?)$(.*?)(?=^### 7\.9|^## 8\.)", text, re.S | re.M)
if not found:
    sys.exit("§7.8 (G:U ağırlığı) bölümü bulunamadı")
body = found.group(2)

# ---- 1  bölüm -------------------------------------------------------------
leftovers = re.findall(r"<[^<>\n]{10,}>", body)
if leftovers:
    problems.append(f"§7.8'de yer tutucu kalmış: {leftovers[:2]}")
absent = [f"7.8.{i}" for i in (1, 2) if f"#### 7.8.{i}" not in body]
if absent:
    problems.append(f"§7.8 alt bölümleri eksik: {absent}")
if not problems:
    print("  1  §7.8 dolu, iki alt bölümü yazılı")

# ---- 2  ağırlık ve keyfilik beyanı ---------------------------------------
# ⚠️ "keyfi" dizgisi §7.8'de birden çok yerde geçiyor (başlıkta da), o yüzden
# KARAR bloğunda ayrı aranıyor. İlk hali tüm bölümde arıyordu ve kendi
# kırmızı-önce denememde yakalandı: karar cümlesindeki beyanı silmek kapıyı
# geçiyordu, çünkü ikinci kopya muafiyet yaratıyordu (`A8b`'nin aynı dersi).
decision = re.search(r"\*\*Karar:(.*?)(?=####)", body, re.S)
if decision is None:
    problems.append("§7.8'in `**Karar:` bloğu bulunamadı")
elif not re.search(r"0,5", decision.group(1)):
    problems.append("§7.8'in karar cümlesi ağırlığı sayıyla sabitlemiyor")
elif not re.search(r"keyfi", decision.group(1)):
    problems.append(
        "§7.8'in KARAR cümlesi ağırlığın keyfi olduğunu ilan etmiyor — "
        "türetilmemiş bir sabiti türetilmiş gibi bırakmak bu maddenin tam tersi"
    )
elif not re.search(r"türetilmiş değildir, keyfidir|keyfidir", body):
    problems.append(
        "§7.8.2 sonuç cümlesinde ağırlığın termodinamikten TÜRETİLMEDİĞİNİ "
        "yazmıyor — iki beyan (karar ve sonuç) ayrı ayrı aranıyor, çünkü "
        "birini silip diğerine saklanmak muafiyet yaratır"
    )
else:
    print("  2  karar cümlesi VE sonuç cümlesi: 0,5 sabit, keyfi olduğu ilan edilmiş")

# ---- 3  KOD: ağırlıklar -------------------------------------------------
aligner = ALIGNER.read_text(encoding="utf-8") if ALIGNER.exists() else ""
if not aligner:
    problems.append(f"{ALIGNER} okunamadı")
else:
    increments = set(re.findall(r"score \+= (\d\.\d)", aligner))
    if increments != {"1.0", "0.5"}:
        problems.append(
            f"ağırlıklar değişmiş: {sorted(increments)} — §7.8'in konusu "
            "{1.0, 0.5}, madde yeniden açılmalı"
        )
    else:
        print("  3  kod: ağırlıklar hâlâ {+1.0, +0.5}")

# ---- ölçüm betiği --------------------------------------------------------
sys.path.insert(0, str(RECORD))
olcum = None
try:
    import olcum  # type: ignore[import-not-found]
except Exception as exc:  # noqa: BLE001
    print(f"  4-6  ATLANDI — ölçüm betiği içe alınamadı ({exc})")

# ---- 4  DAVRANIŞ: seed'de G:U yok ---------------------------------------
if olcum is not None:
    try:
        seed = olcum.seed_region_wobbles()
    except Exception as exc:  # noqa: BLE001
        seed = None
        problems.append(f"seed ölçümü koşmadı: {exc}")
    if seed:
        sites = seed["sites"]
        if not sites:
            problems.append(
                "indeks sentetik transkriptte hiç site bulmadı — ölçüm anlamsız"
            )
        elif any(int(s["gu_wobbles_in_seed"]) for s in sites):
            problems.append(
                "seed bölgesinde G:U BULUNDU — §7.8.1'in iki sonucu da bu "
                "yokluğa dayanıyor, madde yeniden açılmalı"
            )
        elif not any(int(s["gu_wobbles_total"]) for s in sites):
            problems.append(
                "ölçümde seed DIŞINDA da hiç G:U yok — o zaman 4. ölçüm "
                "ağırlığın nerede uygulandığını ayırt etmiyor"
            )
        else:
            site = sites[0]
            print(f"  4  davranış: seed'de G:U = {site['gu_wobbles_in_seed']}, "
                  f"seed dışında {site['gu_wobbles_total']} (skor {site['score']})")

# ---- 5 ve 6  VERİ: Turner oranları ve işaret ----------------------------
if olcum is not None:
    if not olcum.STACK.exists():
        print(f"  5-6  ATLANDI — {olcum.STACK} yok")
    else:
        ratios = olcum.wobble_ratios()
        declared = re.search(
            r"[Oo]ran aralığı (−|-)(\d+[.,]\d+) … \+?(\d+[.,]\d+), medyanı "
            r"(\d+[.,]\d+)", body
        )
        if declared is None:
            problems.append(
                "§7.8.2 oran aralığını ve medyanını yazmıyor"
            )
        else:
            def number(raw: str) -> float:
                return float(raw.replace(",", "."))

            claimed = (-number(declared.group(2)), number(declared.group(3)),
                       number(declared.group(4)))
            observed = (float(ratios["ratio_min"]), float(ratios["ratio_max"]),
                        float(ratios["ratio_median"]))
            if any(abs(a - b) > 0.02 for a, b in zip(claimed, observed)):
                problems.append(
                    f"§7.8.2 oranları {claimed} diyor, Turner tabloları "
                    f"{tuple(round(v, 4) for v in observed)} veriyor"
                )
            elif float(ratios["wobble_dg_max"]) <= 0:
                problems.append(
                    f"G:U yığın ΔG'sinin maksimumu {ratios['wobble_dg_max']} ≤ 0 "
                    "— işaret değişmiyor, yani 'hiçbir sabit temsil edemez' "
                    "iddiası düşer"
                )
            else:
                print(f"  5  Turner: oran {observed[0]:+.2f}…{observed[1]:+.2f}, "
                      f"medyan {observed[2]:.2f}; G:U ΔG "
                      f"{ratios['wobble_dg_min']:+.2f}…"
                      f"{ratios['wobble_dg_max']:+.2f} (işaret DEĞİŞİYOR)")
            # ---- 6  KONTROL ------------------------------------------------
            if float(ratios["wc_dg_max"]) >= 0:
                problems.append(
                    f"kontrol düştü: WC yığın ΔG'sinin maksimumu "
                    f"{ratios['wc_dg_max']} ≥ 0, yani işaret değişimi G:U'ya "
                    "özgü değil — 5. ölçüm 'tablolar gürültülü' demiş olurdu"
                )
            else:
                print(f"  6  kontrol: WC yığınları istisnasız negatif "
                      f"({ratios['wc_dg_min']:+.2f}…{ratios['wc_dg_max']:+.2f}) — "
                      "işaret değişimi G:U'ya özgü")

# ---- 7  duyarlılık ızgarası ---------------------------------------------
if not re.search(r"\{0,0,\s*0,5,\s*1,0\}", body):
    problems.append("§7.8 duyarlılık ızgarasını `{0,0, 0,5, 1,0}` olarak yazmıyor")
elif not re.search(r"yeniden atanmaz", body):
    problems.append("§7.8 birincil hücrenin yeniden atanmayacağını yazmıyor")
else:
    print("  7  ızgara {0, 0,5, 1} ilan edilmiş, birincil yeniden atanmaz")

# ---- 8  kayıt ------------------------------------------------------------
if not RECORD.is_dir():
    problems.append(f"{RECORD} yok")
else:
    needed = {"README.md", "olcum.py", "olcum.json"}
    have = {p.name for p in RECORD.iterdir()}
    if not needed <= have:
        problems.append(f"{RECORD} eksik: {sorted(needed - have)}")
    else:
        print(f"  8  ölçüm kaydı {RECORD} içinde, betiğiyle")

# ---- 9  harita ve kilit -------------------------------------------------
mapping = yaml.safe_load(MAP.read_text(encoding="utf-8"))["sections"]
owners = (mapping.get(7) or {}).get("owners") or []
if "A10b" not in owners:
    problems.append(f"harita §7'yi A10b'ye vermiyor: {owners}")
else:
    print(f"  9  harita §7'yi A10b'ye veriyor (sahipler: {owners})")

sys.path.insert(0, ".claude/hooks")
import _status  # noqa: E402

items = {i.id: i for i in _status.parse_roadmap(ROADMAP.read_text(encoding="utf-8"))}
a12 = items.get("A12")
if a12 is None or "A10b" not in a12.deps:
    problems.append("A12 A10b'ye bağlı değil")
else:
    print("  9  A12 A10b'ye bağlı")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo
echo "GEÇTİ — §7.8 G:U ağırlığını 0,5'te donduruyor ve KEYFİ olduğunu iki"
echo "        ölçümle ilan ediyor: ağırlık seed bölgesinde hiç uygulanmıyor"
echo "        (aligner koşturulup ölçüldü), ve Turner tablolarında G:U'nun"
echo "        katkısı işaret değiştiriyor — hiçbir sabit onu temsil edemez."
echo "        Kontrol: Watson-Crick yığınlarının işareti değişmiyor."
echo "        NOT: nearest-neighbour ΔG'ye geçmek \`C3\`/\`C3e\`'nin işi."
