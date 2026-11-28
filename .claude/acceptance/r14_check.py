#!/usr/bin/env python3
"""R14's ten measurements. Called by `R14.sh`, which documents them."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from src.stage3_variant_tox import phylop_scorer as mod  # noqa: E402

SOURCE = Path(mod.__file__).read_text(encoding="utf-8")
problems: list[str] = []


def handle(mean: float | None, coverage: float | None = None) -> MagicMock:
    """A pyBigWig mock faithful to the live file's two stats types."""
    if coverage is None:
        coverage = 1.0 if mean is not None else None
    bw = MagicMock()
    bw.stats.side_effect = lambda *a, **kw: (
        [coverage] if kw.get("type") == "coverage" else [mean]
    )
    return bw


def code_without_comments(text: str) -> str:
    """Strip comments and strings so prose cannot satisfy a code check.

    The lesson from `B10a`, where a gate matched its own explanatory comment
    twice, and from `H24` before it.
    """
    import io
    import tokenize

    kept: list[str] = []
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        kept.append(tok.string)
    return " ".join(kept)


CODE = code_without_comments(SOURCE)

# ---- 1  KOD -------------------------------------------------------------
if "_NEUTRAL_MEAN_SCORE" in CODE:
    problems.append(
        "`_NEUTRAL_MEAN_SCORE` hâlâ kodda — kapsam yokluğunda 0.0 dönen sabit"
    )
else:
    print("  1  kod: `_NEUTRAL_MEAN_SCORE` yok")

# ---- 2  değeri olmayan pencere -----------------------------------------
mean, covered = mod._get_conservation_score(handle(None), "chr1", 0, 100)
if mean is not None:
    problems.append(
        f"hizalama dışı pencere {mean!r} döndü — 0.0 bu kanalın "
        "ifade edebileceği EN DÜŞÜK riske normalize olur (değişmez 2)"
    )
elif covered != 0.0:
    problems.append(
        f"sıfır kapsanan baz `covered_fraction={covered!r}` olarak kaydedildi; "
        "bilinmeyenin sebebi kayıtta olmalı"
    )
else:
    print("  2  hizalama dışı pencere → None, kapsam 0.0")

# ---- 3  başarısız okuma ------------------------------------------------
broken = MagicMock()
broken.stats.side_effect = RuntimeError("Invalid interval bounds!")
mean, covered = mod._get_conservation_score(broken, "1", 0, 100)
if mean is not None or covered is not None:
    problems.append(
        f"başarısız okuma ({mean!r}, {covered!r}) döndü — `chr` öneki hatası ve "
        "kontig sonunu aşan aralık buraya düşüyor, ve ikisi de hiçbir şey bilmiyor"
    )
else:
    print("  3  başarısız okuma → (None, None)")

# ---- 4  KONTROL: ölçülmüş sıfır ----------------------------------------
mean, covered = mod._get_conservation_score(handle(0.0), "chr1", 0, 100)
if mean is None:
    problems.append(
        "KONTROL BAŞARISIZ: ÖLÇÜLMÜŞ bir phyloP 0.0 da None'a çevrildi. "
        "UCSC'ye göre skorun mutlak değeri nötrlük altındaki -log p-değeri, "
        "yani 0 bir sonuçtur (p = 1) — ve 2./3. ölçüm 'her zaman None dön' ile "
        "de geçerdi"
    )
elif mean != 0.0:
    problems.append(f"ölçülmüş 0.0 bozuldu: {mean!r}")
else:
    print("  4  kontrol: ÖLÇÜLMÜŞ 0.0 hayatta (p = 1, bir sonuç)")

# ---- 5  negatif ortalama -----------------------------------------------
mean, _ = mod._get_conservation_score(handle(-2.1), "chr1", 0, 100)
if mean is None or abs(mean + 2.1) > 1e-9:
    problems.append(f"negatif ortalama (hızlanmış evrim) bozuldu: {mean!r}")
else:
    print("  5  negatif ortalama hayatta (hızlanmış evrim de bir sonuç)")

# ---- 6  kısmi kapsam ---------------------------------------------------
mean, covered = mod._get_conservation_score(
    handle(0.21333333104848862, coverage=0.6), "chr1", 121_609_785, 121_609_805
)
if covered is None or abs(covered - 0.6) > 1e-9:
    problems.append(
        f"kısmi kapsam kaydedilmiyor (covered={covered!r}) — canlı dosyada "
        "sınırı kesen pencere kendisinin %60'ı üzerinden ortalama döndürüyor "
        "ve bu tam ölçümmüş gibi okunuyordu"
    )
else:
    print("  6  kısmi kapsam kaydediliyor (0.6)")

# ---- 7  bilinmeyen cache'lenmiyor --------------------------------------
from unittest.mock import patch  # noqa: E402

from src.core.models import GenomicRegion  # noqa: E402

REGION = GenomicRegion(chrom="chrX", start=50_000, end=51_000, strand=".")


def run_with(mean_value: float | None) -> MagicMock:
    cache = MagicMock()
    cache.get.return_value = None
    with patch.object(mod.pyBigWig, "open", return_value=handle(mean_value)), \
            patch.object(mod, "Cache") as MockCache:
        MockCache.return_value.__enter__ = lambda s: cache
        MockCache.return_value.__exit__ = MagicMock(return_value=False)
        mod.score_phylop([REGION], "irrelevant://url", cache_db=":memory:")
    return cache


unknown_cache = run_with(None)
if unknown_cache.set.call_count:
    problems.append(
        f"bilinmeyen cache'lendi ({unknown_cache.set.call_args_list}) — TTL bir "
        "hafta, yani tek bir kötü okuma sebebi geçtikten sonra bir hafta daha "
        "cevap verir (B2'de karara bağlandı)"
    )
else:
    print("  7  bilinmeyen cache'lenmiyor")

measured_cache = run_with(2.0)
if measured_cache.set.call_count != 1:
    problems.append(
        f"KONTROL BAŞARISIZ: ölçüm de cache'lenmiyor "
        f"({measured_cache.set.call_count} çağrı) — 7. ölçüm 'hiç cache'leme' "
        "ile de geçerdi"
    )
else:
    print("  7b kontrol: ölçüm cache'leniyor")

# ---- 8  ölü sabit ölü kalıyor ------------------------------------------
readers = []
for path in sorted(ROOT.glob("src/**/*.py")):
    text = path.read_text(encoding="utf-8")
    body = code_without_comments(text)
    hits = body.count("_NEUTRAL_CONSERVATION_SCORE")
    definition = 1 if re.search(r"^_NEUTRAL_CONSERVATION_SCORE", text, re.M) else 0
    if hits > definition:
        readers.append(f"{path.relative_to(ROOT)} ({hits} geçiş)")
if readers:
    problems.append(
        f"ölü `_NEUTRAL_CONSERVATION_SCORE` üretimde OKUNUYOR: {readers} — "
        "skor uzayında bir 0.5 sentineli geri gelmiş"
    )
else:
    print("  8  ölü `_NEUTRAL_CONSERVATION_SCORE` okunmuyor (kanıt olarak duruyor)")

# ---- 9  downstream -----------------------------------------------------
from src.stage3_variant_tox.variant_merger import _normalize  # noqa: E402

try:
    both = _normalize(
        cosmic={"mutation_count": 10, "tier1_count": 0},
        gnomad={"polymorphism_score": 0.4},
        clinvar={"pathogenic_count": 0, "likely_pathogenic_count": 0},
        phylop={"conservation_score": 0.8},
    )
    without = _normalize(
        cosmic={"mutation_count": 10, "tier1_count": 0},
        gnomad={"polymorphism_score": 0.4},
        clinvar={"pathogenic_count": 0, "likely_pathogenic_count": 0},
        phylop={"conservation_score": None},
    )
except TypeError as exc:
    print(f"  9  ATLANDI — `_normalize` imzası değişmiş ({exc})")
else:
    if without is None:
        problems.append("None phyloP kanalı tüm skoru None yaptı; dışlanması gerekir")
    elif both == without:
        problems.append(
            f"phyloP kanalını kaldırmak skoru değiştirmedi ({both}) — kanal "
            "dışlanıp ağırlıklar yeniden normalize edilmiyor olabilir"
        )
    else:
        print(f"  9  downstream: None kanal dışlanıp yeniden normalize ediliyor "
              f"({both} → {without})")

# ---- 10  CANLI ---------------------------------------------------------
import yaml  # noqa: E402

url = yaml.safe_load(
    (ROOT / "config/config.yaml").read_text(encoding="utf-8")
)["phylop_bigwig_url"]
try:
    import pyBigWig

    bw = pyBigWig.open(url)
except Exception as exc:  # noqa: BLE001 - ağ yokluğu ölçüm değil
    print(f"  10 ATLANDI — canlı dosya açılamadı ({type(exc).__name__})")
else:
    try:
        normal = bw.stats("chr1", 11_255_438, 11_255_458, type="mean")
        gap = bw.stats("chr1", 121_800_000, 121_800_020, type="mean")
        normal_value = normal[0] if normal else None
        gap_value = gap[0] if gap else None
        prefix_raises = False
        try:
            bw.stats("1", 11_255_438, 11_255_458, type="mean")
        except Exception:  # noqa: BLE001
            prefix_raises = True
        if normal_value is None:
            problems.append(
                "canlı dosya normal bir pencerede de değer vermedi — bütün "
                "kararın dayandığı ölçüm çürüdü"
            )
        elif gap_value is not None:
            problems.append(
                f"canlı dosya sentromerik pencerede {gap_value!r} verdi; ölçüm "
                "None bekliyordu — dosya değiştiyse R14'ün gerekçesi yeniden "
                "ölçülmeli"
            )
        elif not prefix_raises:
            problems.append(
                "`chr` öneksiz kontig adı artık istisna fırlatmıyor — 3. "
                "ölçümün gerekçesi değişti"
            )
        else:
            print(f"  10 canlı doğrulandı: normal pencere {normal_value:.4f}, "
                  "sentromerik pencere None, öneksiz ad istisna fırlatıyor")
    finally:
        bw.close()

for problem in problems:
    print(f"  HATA {problem}")
if problems:
    print("\nGEÇMEDİ — yukarıdaki ölçümler")
    sys.exit(1)
print("\nGEÇTİ — hizalama yokluğu ile ölçülmüş nötrlük artık ayrı: biri `None`,")
print("        diğeri gerçek bir 0.0 (p = 1). Kısmi kapsam kaydediliyor,")
print("        bilinmeyen cache'lenmiyor, ve kontrol ölçümleri 'her zaman")
print("        None dön' ile 'hiç cache'leme'yi dışlıyor.")
