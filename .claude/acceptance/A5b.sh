#!/usr/bin/env bash
# Kabul kriteri — A5b: "§7.5'te beşinci taban ya da reddinin gerekçesi yazılı".
#
# Dokuz ölçüm. 4, 5 ve 6 ayırt edici olanlar.
#
#   1  §7.5 BEŞ tabanı ayrı ayrı tanımlıyor, ve "dördü de" dili kalmamış
#   2  beşinci taban kaynağını PMID'si ve DOI'siyle adlandırıyor
#   3  REDDEDİLEN aday, üç ölçülmüş gerekçesiyle yazılı
#   4  KAYIT, ayırt edici: dışsal tablo manifest'te, checksum'ı diskteki
#      dosyayla birebir, ve lisansın BEYAN EDİLMEDİĞİ yazılı. Lisanssız bir
#      tabloyu yeniden dağıtmamak bir karar; kayıtta durmazsa karar yok
#   5  KONTROL, ayırt edici: §7.5'in ilan ettiği kapsam sınırı GERÇEK —
#      yayınlanmış önselliğin en üst sıraları cinsiyet kromozomu genleri.
#      Bu kontrol olmadan "tek hücre hattında zayıf" bir süsleme olurdu
#   6  AĞ, ASIL ÖLÇÜM: beşinci tabanın eklenme gerekçesi, yani `GSE5291`'de
#      dördüncü tabanın HESAPLANAMADIĞI (`INTENSITY1` yok) ama beşincinin
#      hesaplanabildiği (prob→gen eşleşmesi > %50, lift > 1); artı reddin
#      gerekçesi, yani `GPL2029`'un diğer platformlarla SIFIR prob-id
#      örtüşmesi. Ağ yoksa ATLANIR, ölçüm §7.5'i yanlışlarsa GEÇMEZ (`H17`)
#   7  §4.4 beş tabanla tutarlı: bayat "dört taban" dili yok, kesişimsel
#      koşul sayısı 15
#   8  ölçümün kaydı depoda, betiğiyle
#   9  `A13`'ün haritası §7'yi A5b'ye veriyor ve `A12` ona bağlı
#
# ⚠️ Bu kapı `A6a.sh`'ı tekrar etmiyor: oradaki marj ve güç ölçümleri orada
# kalıyor. Buradaki tek örtüşme 7. ölçüm, ve o bir TUTARLILIK kontrolü.

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

import hashlib
import json
import re
import statistics
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

DOC = Path("docs/PRE_REGISTRATION.md")
MAP = Path(".claude/prereg_sections.yaml")
ROADMAP = Path("SCIENTIFIC_ROADMAP.md")
MANIFEST = Path("data/external/manifest.json")
PRIOR = Path("data/external/de_prior/DE_Prior.txt")
RECORD = Path("reports/a5b-besinci-taban-2026-11-27")

problems: list[str] = []
text = DOC.read_text(encoding="utf-8")

match = re.search(r"^### 7\.5 (.+?)$(.*?)(?=^## 8\.|^### 7\.6)", text, re.S | re.M)
if not match:
    sys.exit("§7.5 (tabanlar) bölümü bulunamadı")
heading, body = match.group(1), match.group(2)

# ---- 1  beş taban ---------------------------------------------------------
numbered = re.findall(r"^\d+\.\s+[^\n*]*?\*\*(.+?)\*\*", body, re.M)
if len(numbered) < 5:
    problems.append(f"§7.5 yalnız {len(numbered)} taban tanımlıyor: {numbered}")
else:
    print(f"  1  {len(numbered)} taban ayrı ayrı tanımlı")
if re.search(r"dördü de", heading + body):
    problems.append(
        "§7.5'te hâlâ 'dördü de' dili var — beşinci taban eklendiğinde bu "
        "cümle yanlış oldu ve sessizce kalması tam bu maddenin sebebiydi"
    )

# ---- 2  kaynak -------------------------------------------------------------
for token, what in (("30846554", "PMID"), ("10.1073/pnas.1802973116", "DOI"),
                    ("Crow", "yazar")):
    if token not in body:
        problems.append(f"beşinci tabanın {what}'si (§7.5) yazılı değil: {token}")
if not [p for p in problems if "beşinci tabanın" in p]:
    print("  2  beşinci taban kaynağını PMID + DOI ile adlandırıyor")

# ---- 3  reddedilen aday ----------------------------------------------------
rejected = re.search(r"REDDEDİLEN ADAY(.*?)(?=^📌 \*\*Dördüncüyü)", body, re.S | re.M)
if rejected is None:
    problems.append("§7.5 reddedilen adayı başlıkla yazmıyor")
else:
    reasons = {
        "sıfır örtüşme": r"sıfır\*{0,2}\s*prob-id örtüşmesi|prob-id örtüşmesi var",
        "lift düşüşü": r"2,18'den\s*\*\*1,46\*\*",
        "ileriye dönük yok": r"İleriye dönük|ileriye dönük",
        "tanı olarak raporlanır": r"taban olarak değil tanı olarak|tanı olarak",
    }
    missing = [k for k, pat in reasons.items() if not re.search(pat, rejected.group(1))]
    if missing:
        problems.append(f"reddin gerekçeleri eksik: {missing}")
    else:
        print("  3  reddedilen aday üç ölçülmüş gerekçeyle + tanı olarak yazılı")

# ---- 4  AYIRT EDİCİ: manifest kaydı ---------------------------------------
try:
    artifacts = json.loads(MANIFEST.read_text(encoding="utf-8"))["artifacts"]
except (OSError, ValueError, KeyError) as exc:
    problems.append(f"{MANIFEST} okunamadı: {exc}")
    artifacts = []
entry = next((a for a in artifacts if "de_prior" in str(a.get("name", ""))), None)
if entry is None:
    problems.append(
        "manifest'te `de_prior` kaydı yok — dışsal bir tabloya dayanan bir "
        "taban, kaydı olmadan yeniden üretilemez (değişmez 1)"
    )
else:
    if "A5b" not in (entry.get("used_by") or []):
        problems.append("manifest kaydı `used_by` içinde A5b'yi saymıyor")
    licence = str(entry.get("licence", ""))
    if not re.search(r"NOT STATED|beyan edilmemiş", licence, re.I):
        problems.append(
            "manifest lisansın BEYAN EDİLMEDİĞİNİ yazmıyor — yeniden "
            "dağıtmama kararı kayıtta durmuyorsa karar değildir"
        )
    if PRIOR.exists():
        digest = hashlib.sha256(PRIOR.read_bytes()).hexdigest()
        if digest != entry.get("sha256"):
            problems.append(
                f"checksum tutmuyor: diskte {digest[:16]}…, "
                f"manifest'te {str(entry.get('sha256'))[:16]}…"
            )
        elif PRIOR.stat().st_size != entry.get("bytes"):
            problems.append("manifest'teki boyut diskteki dosyayla tutmuyor")
        else:
            print(f"  4  manifest kaydı diskteki dosyayla birebir "
                  f"({entry['bytes']} bayt, sha256 {digest[:12]}…)")
    else:
        print(f"  4  manifest kaydı var; {PRIOR} indirilmemiş (kontrol atlandı)")

# ---- 5  KONTROL: ilan edilen kapsam sınırı gerçek -------------------------
DECLARED_TOP = ("XIST", "DDX3Y", "EIF1AY", "KDM5D", "USP9Y")
for gene in DECLARED_TOP:
    if gene not in body:
        problems.append(f"§7.5 kapsam sınırını örneklerken {gene}'i saymıyor")
if PRIOR.exists():
    rows = PRIOR.read_text(encoding="utf-8").splitlines()
    header = rows[0].split("\t")
    want = ["Gene_Order", "Gene_EntrezID", "N_HitLists", "DE_Prior_Rank",
            "Gene_Name"]
    if header != want:
        problems.append(f"DE_Prior.txt kolonları beklenenden farklı: {header}")
    else:
        top = [r.split("\t")[4] for r in rows[1:6]]
        if top != list(DECLARED_TOP):
            problems.append(
                f"§7.5 en üst sıraları {list(DECLARED_TOP)} diye ilan ediyor, "
                f"tablo {top} veriyor — ilan edilen kapsam sınırı yanlış"
            )
        else:
            print(f"  5  kontrol: tablonun ilk beşi gerçekten {top} — "
                  "cinsiyet kromozomu ağırlığı süsleme değil")
else:
    print("  5  ATLANDI — DE_Prior.txt indirilmemiş")

# ---- 6  AĞ: eklenme ve reddin gerekçeleri yeniden ölçülüyor ---------------
GEO = "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi"


def geo(acc: str) -> list[str] | None:
    url = f"{GEO}?acc={acc}&targ=self&form=text&view=full"
    req = urllib.request.Request(url, headers={"User-Agent": "research-script/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=240) as resp:
            return resp.read().decode("utf-8", "replace").splitlines()
    except (urllib.error.URLError, TimeoutError):
        return None


def rows_of(lines: list[str], kind: str) -> tuple[list[str], list[list[str]]]:
    start = lines.index(f"!{kind}_table_begin")
    end = lines.index(f"!{kind}_table_end")
    return lines[start + 1].split("\t"), [
        line.split("\t") for line in lines[start + 2 : end]
    ]


probe_a = geo("GSM133689")   # GSE5814, GPL2029
if probe_a is None:
    print("  6  ATLANDI — GEO'ya ulaşılamadı (ağ yok)")
else:
    probe_b = geo("GSM134317")   # GSE5769, GPL3991
    gse5291 = geo("GSM119707")   # GSE5291, GPL3992
    gpl = geo("GPL3992")
    if any(x is None for x in (probe_b, gse5291, gpl)):
        problems.append("GEO'ya ilk istek geçti ama hepsi geçmedi")
    else:
        head_a, rows_a = rows_of(probe_a, "sample")
        head_b, rows_b = rows_of(probe_b, "sample")
        ids_a = {r[0].strip() for r in rows_a if r}
        ids_b = {r[0].strip() for r in rows_b if r}
        shared = len(ids_a & ids_b)
        if shared != 0:
            problems.append(
                f"GPL2029 ile GPL3991 {shared} prob-id paylaşıyor — reddin "
                "'tek biçimli tanımlanamıyor' gerekçesi bu ölçüme dayanıyor"
            )
        else:
            print(f"  6  GPL2029 ∩ GPL3991 = 0 prob-id "
                  f"({len(ids_a)} vs {len(ids_b)}) — rejeksiyonun gerekçesi ayakta")

        head_s, rows_s = rows_of(gse5291, "sample")
        if "INTENSITY1" in head_s:
            problems.append(
                "GSE5291'in tablosunda INTENSITY1 VAR — dördüncü tabanın orada "
                "hesaplanamadığı iddiası (§7.5) yanlış"
            )
        head_p, rows_p = rows_of(gpl, "platform")
        pcol = {name: i for i, name in enumerate(head_p)}
        pmap: dict[str, tuple[str, str]] = {}
        for parts in rows_p:
            if len(parts) < len(head_p):
                parts = parts + [""] * (len(head_p) - len(parts))
            pmap[parts[pcol["ID"]].strip()] = (
                parts[pcol.get("GeneID", 0)].strip() if "GeneID" in pcol else "",
                parts[pcol.get("ORF", pcol.get("GeneSymbol", 0))].strip(),
            )
        by_entrez: dict[str, float] = {}
        by_symbol: dict[str, float] = {}
        if PRIOR.exists():
            for line in PRIOR.read_text(encoding="utf-8").splitlines()[1:]:
                parts = line.split("\t")
                if len(parts) < 5:
                    continue
                try:
                    rank = float(parts[3])
                except ValueError:
                    continue
                by_entrez[parts[1].strip()] = rank
                by_symbol[parts[4].strip().upper()] = rank
        if not by_entrez:
            print("  6  önsellik tablosu yok — GSE5291 lift ölçümü atlandı")
        else:
            scol = {name: i for i, name in enumerate(head_s)}
            labels: list[int] = []
            known: list[float | None] = []
            for parts in rows_s:
                if len(parts) != len(head_s):
                    continue
                try:
                    value = float(parts[scol["VALUE"]])
                    pval = float(parts[scol["PVALUE"]])
                    logint = float(parts[scol["LOGINTENSITY"]])
                except (KeyError, ValueError):
                    continue
                if logint < -1.0:
                    continue
                labels.append(1 if (pval < 0.01 and value < 0) else 0)
                entrez, symbol = pmap.get(parts[scol["ID_REF"]].strip(), ("", ""))
                rank = by_entrez.get(entrez)
                if rank is None and symbol:
                    rank = by_symbol.get(symbol.upper())
                known.append(rank)
            hits = [x for x in known if x is not None]
            cover = len(hits) / len(known) if known else 0.0
            if cover <= 0.50:
                problems.append(
                    f"GSE5291'de prob→gen eşleşmesi yalnız {cover:.1%} — "
                    "beşinci tabanın 'n ≈ 43'ü kapsıyor' gerekçesi düşüyor"
                )
            else:
                median = statistics.median(hits)
                scores = [x if x is not None else median for x in known]
                order = sorted(range(len(scores)), key=lambda i: -scores[i])
                total = sum(labels)
                seen = 0
                value = 0.0
                for rank, i in enumerate(order, start=1):
                    if labels[i]:
                        seen += 1
                        value += seen / rank
                average_precision = value / total
                base = total / len(labels)
                lift = average_precision / base
                if lift <= 1.0:
                    problems.append(
                        f"GSE5291'de beşinci tabanın lift'i {lift:.3f} ≤ 1 — "
                        "şans üstü olduğu iddiası desteklenmiyor"
                    )
                else:
                    print(f"  6  GSE5291/GSM119707: INTENSITY1 yok (4. taban "
                          f"hesaplanamaz), 5. taban eşleşme {cover:.1%}, "
                          f"lift {lift:.3f}")

# ---- 7  §4.4 tutarlılığı ---------------------------------------------------
section44 = re.search(r"^### 4\.4 (.+?)$(.*?)(?=^## 5\.)", text, re.S | re.M)
if section44 is None:
    problems.append("§4.4 bulunamadı")
else:
    rule = section44.group(2)
    stale = re.findall(r"dört taban|dördünün|4 taban ×", rule)
    if stale:
        problems.append(
            f"§4.4'te bayat 'dört taban' dili kalmış: {stale[:3]} — beşinci "
            "taban eklenince karar kuralı onu saymak zorunda"
        )
    conj = re.search(r"\*\*(\d+)\s+kesişimsel koşul\*\*", rule)
    if conj is None or int(conj.group(1)) != 5 * 3:
        problems.append(
            f"§4.4.5 kesişimsel koşul sayısı 15 olmalı, "
            f"{conj.group(1) if conj else 'yok'} yazıyor"
        )
    if not [p for p in problems if "§4.4" in p]:
        print("  7  §4.4 beş tabanla tutarlı (15 kesişimsel koşul)")

# ---- 8  kayıt --------------------------------------------------------------
if not RECORD.is_dir():
    problems.append(f"{RECORD} yok — kararın ölçümü depoda kayıtlı değil")
else:
    needed = {"README.md", "olcum.py", "olcum.json"}
    have = {p.name for p in RECORD.iterdir()}
    if not needed <= have:
        problems.append(f"{RECORD} eksik: {sorted(needed - have)}")
    else:
        print(f"  8  ölçüm kaydı {RECORD} içinde, betiğiyle")

# ---- 9  harita ve kilit ----------------------------------------------------
mapping = yaml.safe_load(MAP.read_text(encoding="utf-8"))["sections"]
owners = (mapping.get(7) or {}).get("owners") or []
if "A5b" not in owners:
    problems.append(f"harita §7'yi A5b'ye vermiyor: {owners}")
else:
    print(f"  9  harita §7'yi A5b'ye veriyor (sahipler: {owners})")

sys.path.insert(0, ".claude/hooks")
import _status  # noqa: E402

items = {i.id: i for i in _status.parse_roadmap(ROADMAP.read_text(encoding="utf-8"))}
if "A5b" not in (items.get("A12").deps if items.get("A12") else []):
    problems.append(
        "A12 A5b'ye bağlı değil — kilit açılırsa beşinci taban bir daha "
        "eklenemez"
    )
else:
    print("  9  A12 A5b'ye bağlı")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo
echo "GEÇTİ — §7.5 beş tabanı ayrı ayrı tanımlıyor, beşincisi yayınlanmış ve"
echo "        dışsal (PMID 30846554, manifest'te checksum'ıyla, lisansı beyan"
echo "        edilmemiş olarak kayıtlı), küme-içi aday üç ölçülmüş gerekçeyle"
echo "        reddedilip tanı olarak bağlanmış, ve §4.4 beş tabanla tutarlı."
echo "        NOT: 3′UTR heptamer tablosunun KURULMASI E0b, bu kapı onu ölçmez."
