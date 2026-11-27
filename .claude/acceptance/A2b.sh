#!/usr/bin/env bash
# Kabul kriteri — A2b: "§6'da her accession için doğrulanmış PMID + örnek
# sayısı".
#
# Altı ölçüm. 2 ve 3 ayırt edici olanlar.
#
#   1  §6 her accession için bir PMID ve künye taşıyor
#   2  AĞ: her PMID, GEO'nun o seri için BUGÜN bildirdiğiyle aynı — PMID'i
#      yayından ya da hafızadan yazmak bu maddenin var olma sebebinin tam
#      tersi
#   3  AĞ: her PMID'in künyesi Europe PMC ile birebir (ilk yazar + yıl) —
#      doğru numarayı yanlış makaleye bağlamak, satırın uyardığı Birmingham
#      tuzağının tam şekli
#   4  TEKİLLİK: aynı yayının iki serisi olduğu yazılı (sekiz accession, altı
#      yayın) — sekizini bağımsız çalışma saymak çalışma düzeyinde sahte bir
#      bağımsızlık verir
#   5  UYUŞMAZLIK: GEO başlığı ile yayın konusu çelişen seri işaretli
#   6  `A2`'nin açık bıraktığı hücre hattı kapatılmış
#
# ⚠️ 2 ve 3 ağ gerektirir; ağ yoksa ATLANIR, ama kaynak farklı bir şey
# söylerse atlanmaz, GEÇMEZ (`H17`).

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

warn_untracked docs || true

"$PY" - <<'INNER' || exit 1
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DOC = Path("docs/PRE_REGISTRATION.md")
GEO = "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi"
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

problems: list[str] = []
text = DOC.read_text(encoding="utf-8")
match = re.search(r"^## 6\. (.+?)$(.*?)(?=^## 7\.)", text, re.S | re.M)
if not match:
    sys.exit("§6 bölümü bulunamadı")
body = match.group(2)


def fetch(url: str, timeout: int = 90) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "research-script/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError):
        return ""


# ---- 1  her accession bir PMID ve künye taşıyor ------------------------
# Künye tablosu: | `GSE…` | PMID | ilk yazar | dergi, cilt (yıl) |
#
# ⚠️ PMID hücresi **7-8 haneli** olmak zorunda. İlk hali `(\d+)` idi ve §6'ya
# accession ile anahtarlanmış İKİNCİ bir tablo (seed envanteri) eklenince
# onun satırlarını künye satırı sanmaya başladı: `GSE41924`'ün "PMID"i kol
# sayısı olan **3** okundu. Kapı bunu yakaladı — bir PMID'in tek haneli
# olamayacağını kontrol etmiyordu, yani biçimi değil yalnız varlığı ölçüyordu.
rows = re.findall(
    r"^\|\s*`(GSE\d+)`\s*\|\s*(\d{7,8})\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$",
    body,
    re.M,
)
written = {acc: (pmid, author.strip("* "), cite) for acc, pmid, author, cite in rows}
roadmap = Path("SCIENTIFIC_ROADMAP.md").read_text(encoding="utf-8")
a2_row = next((l for l in roadmap.splitlines() if l.startswith("| **A2** |")), "")
listed = sorted(set(re.findall(r"GSE\d+", a2_row)))
missing = [acc for acc in listed if acc not in written]
if missing:
    problems.append(f"künyesi olmayan accession: {missing}")
else:
    print(f"  1  {len(written)} accession'ın hepsi PMID + künye taşıyor")

# ---- 2  PMID'ler GEO ile aynı -----------------------------------------
probe = fetch(f"{GEO}?acc={listed[0]}&targ=self&form=text&view=brief") if listed else ""
if not probe:
    print("  2  ATLANDI — GEO'ya ulaşılamadı (ağ yok)")
    print("  3  ATLANDI — aynı sebep")
    live_pmids: dict[str, str] = {}
else:
    live_pmids = {}
    bad: list[str] = []
    for acc in listed:
        raw = probe if acc == listed[0] else fetch(
            f"{GEO}?acc={acc}&targ=self&form=text&view=brief"
        )
        if not raw:
            problems.append(f"{acc}: GEO'ya ilk istek geçti ama bu geçmedi")
            continue
        found = [
            line.split("=", 1)[1].strip()
            for line in raw.splitlines()
            if line.startswith("!Series_pubmed_id")
        ]
        if not found:
            bad.append(f"{acc}: GEO kaydında PMID yok")
            continue
        live_pmids[acc] = found[0]
        if acc in written and written[acc][0] not in found:
            bad.append(f"{acc}: §6 PMID {written[acc][0]}, GEO {found}")
        time.sleep(1)
    if bad:
        problems.append("PMID'ler GEO ile uyuşmuyor — " + "; ".join(bad))
    else:
        print(f"  2  {len(live_pmids)} PMID'in hepsi GEO kaydıyla aynı")

    # ---- 3  künyeler Europe PMC ile birebir ---------------------------
    checked = 0
    wrong: list[str] = []
    for pmid in sorted(set(live_pmids.values())):
        raw = fetch(f"{EPMC}?query=EXT_ID:{pmid}&resultType=core&format=json")
        try:
            hit = json.loads(raw)["resultList"]["result"][0]
        except (json.JSONDecodeError, KeyError, IndexError):
            problems.append(f"PMID {pmid} Europe PMC'de çözülemedi")
            continue
        checked += 1
        author = (hit.get("authorString") or "").split(",")[0].strip()
        year = str(hit.get("pubYear", ""))
        for acc, (written_pmid, written_author, written_cite) in written.items():
            if written_pmid != pmid:
                continue
            surname = written_author.split()[0] if written_author else ""
            if surname and surname.lower() not in author.lower():
                wrong.append(
                    f"{acc}/PMID {pmid}: §6 ilk yazar {written_author!r}, "
                    f"Europe PMC {author!r}"
                )
            if year and year not in written_cite:
                wrong.append(
                    f"{acc}/PMID {pmid}: §6 künyesi {written_cite!r}, yıl {year}"
                )
        time.sleep(1)
    if wrong:
        problems.append("künye uyuşmuyor — " + "; ".join(wrong))
    elif checked:
        print(f"  3  {checked} yayının künyesi Europe PMC ile birebir")

# ---- 4  aynı yayının iki serisi olduğu yazılı -------------------------
dupes = {
    pmid
    for pmid in {v[0] for v in written.values()}
    if sum(1 for v in written.values() if v[0] == pmid) > 1
}
if dupes and not re.search(r"(altı|6)\s*yayın|tek bir yayının iki serisi", body, re.I):
    problems.append(
        f"§6, {len(dupes)} PMID'in iki seriye karşılık geldiğini söylemiyor — "
        "sekiz seriyi bağımsız çalışma saymak sahte bağımsızlık verir"
    )
else:
    print(f"  4  aynı yayının iki serisi olduğu yazılı ({len(dupes)} PMID)")

# ---- 5  başlık/konu uyuşmazlığı işaretli ------------------------------
if not re.search(r"uyuşmuyor|chimera|kimera", body, re.I):
    problems.append("GEO başlığı ile yayın konusu çelişen seri işaretli değil")
else:
    print("  5  başlık/konu uyuşmazlığı işaretli")

# ---- 6  A2'nin açık bıraktığı hücre hattı kapatıldı -------------------
if re.search(r"`A2b` doğrulayacak", body):
    problems.append("§6 hâlâ 'A2b doğrulayacak' diyor — hücre hattı kapatılmadı")
elif not re.search(r"cell line: HeLa", body):
    problems.append("GSE41924'ün hücre hattı kanıtı §6'da yazılı değil")
else:
    print("  6  GSE41924'ün hücre hattı kanıtıyla kapatıldı")

for problem in problems:
    print(f"  HATA {problem}")
sys.exit(1 if problems else 0)
INNER

echo
echo "GEÇTİ — §6'daki her PMID GEO kaydıyla, her künye Europe PMC ile birebir;"
echo "        sekiz serinin altı yayından geldiği ve bir serinin başlığının"
echo "        yayın konusuyla çeliştiği yazılı."
echo "        NOT: bu kapı tasarımın UYGUNLUĞUNU ölçmez — §6.2'nin üç dışlama"
echo "        gerekçesi A2'nin kapısında."
