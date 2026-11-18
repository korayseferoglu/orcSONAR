#!/usr/bin/env bash
# Kabul kriteri — B0: "yeni sürüm eski anahtarları kullanmıyor (test)".
#
# Dört ölçüm:
#   1  sürüm girdiyle birlikte yazılıyor; sürüm yükseltilince HIT -> MISS,
#      eskimiş satır siliniyor, diğer kaynaklar etkilenmiyor
#   2  sürümleme öncesi yazılmış satırlar servis edilmiyor (göç)
#   3  CANLI cache'teki her önek kayıt defterinde var  (salt-okunur)
#   4  birim testleri yeşil
#
# 3 bu kapının en değerli adımı: ilk yazdığım drift testi regex'le tarıyordu ve
# geçiyordu — oysa canlı veritabanında `hic_contact` önekiyle 83 satır vardı ve
# defterde yoktu. Boşluğu test değil VERİ yakaladı. Bu adım defteri gerçeğe
# karşı doğruluyor.
#
# ⚠️ Canlı cache `data/` altında ve salt-okunur açılıyor (değişmez 1). Davranış
# ölçümleri geçici bir veritabanında yapılıyor, hiçbir yan etki yok.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

fail() { echo "GEÇMEDİ — $1"; exit 1; }

PY=""
for cand in "${PYTHON:-}" python3 python; do
    [ -n "$cand" ] || continue
    if "$cand" -c "import pytest" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || fail "pytest içeren yorumlayıcı bulunamadı; PYTHON=... ile ver"
echo "# yorumlayıcı: $PY"

# ------------------------------------------------- 1 + 2  davranış (geçici db)
echo "# 1  sürüm yükseltme: HIT -> MISS   # 2  sürümleme öncesi satırlar"
"$PY" -I - <<'INNER' || fail "geçersizleme davranışı ölçümü geçmedi"
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
from src.core.cache import Cache, current_version, source_of  # noqa: E402

problems = []
tmp = Path(tempfile.mkdtemp())

# --- 1  sürüm yükseltildiğinde eski cevap servis edilmiyor
db = str(tmp / "a.db")
with Cache(db) as cache:
    cache.set("clinvar:chr1:100:200", {"variants": []})
    cache.set("rmsk:chr1:100:200", {"entries": []})
    if cache.get("clinvar:chr1:100:200") != {"variants": []}:
        problems.append("normal HIT çalışmıyor")

Cache.SCHEMA_VERSIONS["clinvar"] = current_version("clinvar") + 1
with Cache(db) as cache:
    if cache.get("clinvar:chr1:100:200") is not None:
        problems.append("sürüm yükseltildiği hâlde eski cevap servis edildi")
    if cache.get("rmsk:chr1:100:200") != {"entries": []}:
        problems.append("bir kaynağın yükseltmesi başka kaynağı bozdu")

left = sqlite3.connect(db).execute("SELECT key FROM cache").fetchall()
if ("clinvar:chr1:100:200",) in left:
    problems.append("eskimiş satır silinmedi, yalnız atlandı")

# --- 2  sürümleme öncesi veritabanı: göç + servis edilmeme
old = str(tmp / "b.db")
conn = sqlite3.connect(old)
conn.execute("CREATE TABLE cache (key TEXT PRIMARY KEY, value TEXT NOT NULL, expires_at REAL NOT NULL)")
conn.execute("INSERT INTO cache VALUES ('phylop:chr1:1:2', '{\"score\": 0.0}', 1e11)")
conn.commit()
conn.close()
with Cache(old) as cache:
    if cache.get("phylop:chr1:1:2") is not None:
        problems.append("sürümleme öncesi satır servis edildi")

for problem in problems:
    print(f"  HATA: {problem}")
sys.exit(1 if problems else 0)
INNER

# ----------------------------------------- 3  canlı cache öneklerini doğrula
echo "# 3  canlı cache önekleri (salt-okunur)"
"$PY" -I - <<'INNER' || fail "canlı cache'te kayıtsız önek var"
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, ".")
from src.core.cache import Cache, source_of  # noqa: E402
from src.core.config import load_config  # noqa: E402

try:
    db = Path(load_config("config/config.yaml").data_paths.cache_db)
except Exception as exc:  # noqa: BLE001
    sys.exit(f"HATA: config okunamadı: {exc}")

if not db.is_file():
    # Gerçek bir yokluk, arıza değil: temiz klonda `data/` yok. Sessizce
    # atlanmıyor, açıkça bildiriliyor.
    print(f"  ATLANDI: {db} yok (temiz klon / CI) — defter gerçeğe karşı doğrulanamadı")
    sys.exit(0)

conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
prefixes = {source_of(key) for (key,) in conn.execute("SELECT key FROM cache")}
rows = conn.execute("SELECT count(*) FROM cache").fetchone()[0]
conn.close()

print(f"  {rows} satır, {len(prefixes)} önek: {', '.join(sorted(prefixes))}")
missing = sorted(p for p in prefixes if p not in Cache.SCHEMA_VERSIONS)
if missing:
    sys.exit(f"HATA: canlı cache'te kayıtsız önek(ler): {missing}")
INNER

# ------------------------------------------------------------- 4  birim testleri
echo "# 4  birim testleri"
"$PY" -m pytest tests/unit/test_cache_versioning.py tests/unit/test_cache.py \
    -q -o addopts="" -p no:cacheprovider || fail "B0'ın testleri yeşil değil"

echo
echo "GEÇTİ — sürüm yükseltmesi eski anahtarları kullanmıyor, defter gerçeğe uyuyor"
