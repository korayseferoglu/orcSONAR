# orcSONAR — Bağımsız Kod Denetimi

> Bu denetim kodu satır satır okuyarak, testleri gerçekten çalıştırarak ve
> pipeline'ı canlı yeniden koşturarak yapıldı. README'nin iddialarına
> güvenilmedi; her önemli iddia dosya/satır veya çalıştırma çıktısıyla
> doğrulandı. Yaltaklanma yok — sadece bulgular.
>
> Denetim tarihi: 2026-07-21 · Denetlenen commit: `cdb8a9b` · Dal: `main`

---

## 1) PROJE NE YAPIYOR

**Teknik olmayan biri için:** Bir gen'i "aç" (aktive et) diye tasarlanmış küçük
bir RNA parçası (saRNA) veriyorsun; program bu RNA'nın hedeflemek istediğin gen
dışında **yanlışlıkla başka hangi genlere yapışıp** onları etkileyebileceğini
tahmin etmeye çalışıyor. Üstelik bunu seçtiğin **belirli bir hücre tipine** göre
(ör. HeLa) yapıyor, çünkü aynı RNA farklı hücrelerde farklı davranır. Çıktı: her
olası "yanlış hedef" için bir risk puanı (0–1) ve bir renk sınıfı (🟢 güvenli →
🔴 tehlikeli) içeren bir HTML/JSON rapor.

**Girdi:** gen adı (`VEGFA`), hücre hattı (`HeLa`), saRNA dizisi (20 nt).
**Çıktı:** `results/{gen}_{hücre}/final_report.{json,html}` + 25 ara JSON.

**Çözdüğü problem (iddia edilen):** Klasik BLAST/dizi-benzerliği tabanlı
off-target taramasının yerine, epigenetik + varyant + termodinamik veriyi
harmanlayan "biyofizik temelli, hücreye özgü" bir karar-destek sistemi.

### README ↔ gerçek kod farkı

| İddia | Gerçek |
|---|---|
| "24 veri kaynağını harmanlıyor" | Doğru — pipeline gerçekten 24 kaynağı çekiyor ve **çoğu gerçek, site-bazında farklılaşan sinyal üretiyor** (ATAC, histon, COSMIC, gnomAD, phyloP, SHAPE çıktıları doğrulandı). Bu boş bir iskelet değil. |
| "Hücreye özgü" | **Doğru ve çalışıyor.** VEGFA aynı dizi ile HeLa'da 0.354, K562'de 0.298 puan alıyor — hücre modifieri gerçekten farklı sonuç üretiyor. |
| "Biyofizik temelli ΔG" | **Kırık.** ΔG modülü gerçek off-target dizisini hiç kullanmıyor; her site için sabit, fiziksel olarak yanlış bir değer (+31.1 kcal/mol) üretiyor. Bkz. §3 Bulgu-1. Projenin kimlik cümlesi olan "biyofizik temelli" iddiasının en zayıf halkası. |
| "Dünyanın ilk..." (CLAUDE.md) | Doğrulanamaz pazarlama ifadesi. README'de yok, iyi; ama proje kimliğinde duruyor. |
| "not clinically validated / prototype" (README) | Dürüst ve doğru. Bu ifade README'de açıkça var — iyi. |

---

## 2) MİMARİ

```
Snakefile (DAG)  →  rules/stage{1..7}.smk  →  her rule bir src modülünün run()'ını çağırır
                                                           │
config/config.yaml (YAML)                                  ↓
                                              results/{gen}_{hücre}/stageN_*.json
```

- **Workflow motoru:** Snakemake 9. `Snakefile` 7 stage'i include eder; her
  `.smk` rule'u `run:` bloğunda ilgili Python modülünün `run()` fonksiyonunu
  çağırır (girdi JSON oku → hesapla → çıktı JSON yaz).
- **CLI:** `src/cli.py` argparse ile parametreleri alır, `snakemake`'i
  `subprocess` ile çağırır ve tqdm progress bar gösterir. CLI hesaplama yapmaz,
  sadece Snakemake'i sarar.
- **Veri modeli:** `src/core/models.py` (439 satır) — tüm ara veri Pydantic v2
  modelleri. Temiz.
- **Çekirdek:** `src/core/` — config (pydantic-settings), cache (SQLite),
  exceptions, logging (loguru). Sağlam.

### Modül isimlendirme paterni (dikkat: kafa karıştırıcı)

`src/stage*` ve `src/scoring` altında **57 Python dosyası** var ve büyük kısmı
**ikili (wrapper + logic) çift** oluşturuyor:

| Snakemake glue (run() var) | Saf mantık (test edilen) |
|---|---|
| `adar_estimator.py` | `adar_risk.py` |
| `ago2_fetcher.py` | `ago2_loading.py` |
| `atac_fetcher.py` | `chromatin_access.py` |
| `ccle_reader.py` | `ccle_expression.py` |
| `hic_fetcher.py` | `hic_contacts.py` |
| `histone_fetcher.py` | `histone_marks.py` |
| `groseq_fetcher.py` | `transcription_run.py` |
| `shape_reader.py` | `shape_profile.py` |
| `rbp_fetcher.py` | `rbp_competition.py` |
| `circrna_checker.py` | `circrna_sponge.py` |
| `immune_screener.py` | `immune_screen.py` |
| `promoter_definer.py` | `promoter_region.py` |
| `score_integrator.py` | `integrator.py` |
| `risk_classifier.py` | `classifier.py` |
| + mergerlar (`*_merger.py`) | — |

Bu **ölü kod değil** — wrapper'lar Snakemake giriş noktası, logic dosyaları saf
fonksiyon. Ama isimlendirme keyfi (`adar_estimator` vs `adar_risk` neden ayrı?
`fetcher` neden bazen glue bazen gerçek okuyucu?) ve dosya sayısını iki katına
çıkarıyor. Yeni gelen biri hangi dosyanın gerçek mantığı içerdiğini bilemez.

### Veri akışı (gerçek DAG)

```
Stage 1 (sıralı):  tss_mapping → transcript_resolution → promoter_definition
Stage 2 (sıralı):  seed_alignment → mirbase_check ∥ repeat_scan → merge_offtargets
Stage 3,4,5,6 (paralel, hepsi stage2_offtargets.json'a bağlı):
    3: cosmic ∥ gnomad ∥ clinvar ∥ phylop → merge_variants
    4: atac ∥ histone ∥ groseq ∥ hic ∥ ccle → merge_epigenetic
    5: delta_g ∥ shape ∥ m6a ∥ adar ∥ g4 → merge_biophysics
    6: ago2 ∥ rbp ∥ circrna ∙ immune → merge_execution
Stage 7:  score_integration → risk_classification → generate_report
```

### Dış bağımlılıklar
- **Yerel veri (~1.5 GB):** EPDnew, FANTOM5, miRBase, COSMIC VCF (904 MB), CCLE
  (291 MB), m6A BED (65 MB), immün motifler, Turner kuralları. `data/` gitignore'da.
- **Canlı API:** Ensembl REST, NCBI E-utils, gnomAD GraphQL, UCSC.
- **Remote stream:** phyloP + ENCODE/4DN BigWig/.hic (pyBigWig + hic-straw).
- **Model yok** — bu istatistiksel/ML model değil, kurallı bir skorlama motoru.

---

## 3) OLGUNLUK DURUMU (kanıtlı)

### ✅ Gerçekten çalışan
- **Pipeline uçtan uca koşuyor ve gerçek rapor üretiyor.** `results/` altında 4
  tamamlanmış gerçek koşu var (VEGFA_HeLa, VEGFA_K562, CEBPA_HepG2, MYC_K562), her
  biri 25+ ara JSON + HTML rapor. Ben `delta_g` rule'unu canlı yeniden koşturdum,
  exit 0 (`.snakemake/log/2026-07-21T104839`).
- **Gerçek veri, gerçek farklılaşma.** `stage4_atac.json`: site başına 0.0 / 0.1027
  / 0.0595... `stage4_histones.json`: 1.14 / 0.69 / 5.92... `stage3_gnomad.json`:
  gerçek varyantlar. Bunlar sabit/sahte değil.
- **Hücre-özgüllüğü fiilen işliyor.** VEGFA: HeLa=0.354 (WARNING) vs K562=0.298
  (SAFE) — aynı dizi, farklı hücre, farklı sınıf.
- **905 birim testi geçiyor** (143 s, exit 0, elle çalıştırıldı). Sahte
  (`assert True`) test **yok** (0 adet). Testler gerçek değer doğruluyor.
- **Kod hijyeni iyi:** `TODO/FIXME/XXX/HACK` = **0**. `print()` sadece `cli.py`'de
  (3 kez, kullanıcı çıktısı — meşru). Tip ipuçları ve docstring'ler tutarlı.
  Graceful degradation her modülde uygulanmış (kaynak patlarsa → neutral + log).

### 🔴 Kırık / yanıltıcı

**Bulgu-1 (KRİTİK) — ΔG hesaplayıcı sahte değer üretiyor.**
`src/stage5_biophysics/delta_g_calculator.py:80-83`:
```python
comp = {"A": "U", "U": "A", "G": "C", "C": "G", "N": "N"}
target = "".join(comp.get(b, "N") for b in reversed(sarna_rna))  # ← saRNA'NIN KENDİSİ
result = calc.calculate_duplex_dg(sarna_rna, target)
```
Hedef olarak **gerçek off-target mRNA dizisi değil, saRNA'nın kendi
ters-tümleyeni** kullanılıyor. Sonuç:
1. Her off-target için **birebir aynı ΔG** hesaplanıyor (canlı koşuda MTOR, VEGFA,
   HNRNPA2B1, DICER1, TNRC6B → hepsi `delta_g: 31.1`). Ayrıştırma gücü sıfır.
2. Değer **+31.1 kcal/mol** — pozitif, yani "bağlanma yok" demek. 20-nt bir RNA
   duplex'i gerçekte ~ −30 kcal/mol olmalı. `has_mismatches: true` + `reversed()`
   hatası mükemmel duplex'i sahte mismatch'lere boğuyor.
3. Sigmoid'den geçince (`domain_scores.py:225`) `thermo_risk ≈ 0`. Biyofizik
   skorunun **%35 ağırlıklı bileşeni her sitede sabit 0**. Bu yüzden VEGFA_HeLa
   site0'da `biophysics_structure = 0.0827` (tabanda).

Kök neden: `stage2_offtargets.json` off-target'ın **dizisini saklamıyor** (sadece
koordinat + `tx_start/tx_end`). Yani ΔG doğru hesaplansa bile diziyi bulamaz.
Projenin başlık özelliği olan "biyofizik temelli ΔG" fiilen dekoratif.

**Bulgu-2 (CİDDİ) — Stage'ler aynı site için farklı koordinat tarıyor.**
Aynı off-target `MTOR:ENST00000361445` için (doğrulandı):
```
stage2 (seed hit)      : chr1:11255438-11255458   ← gerçek off-target yeri
stage5 shape           : chr1:11255438-11255458   ✔ tutarlı
stage3 cosmic / phylop : chr1:11259515-11259535   -> ~4077 bp UZAKTA
stage6 ago2            : chr1:11259515-11259535   ✗ ~4077 bp uzakta
```
Yani **varyant toksisitesi ve Ago2 yükleme, off-target'ın gerçekte olduğu yerden
~4 kb uzakta** hesaplanıyor. Domainler site'ın nerede olduğunda anlaşamıyor.
"Off-target'daki varyant riski" yanlış lokustan okunuyor.

**Bulgu-3 — Orkestrasyon katmanı tamamen test dışı.**
Toplam coverage **%64**, ama dağılım yanıltıcı: saf mantık dosyaları %95-100,
Snakemake'in **gerçekten çağırdığı** glue/merger katmanı **%0**:
```
offtarget_merger.py 0%   variant_merger.py 0%   epigenetic_merger.py 0%
biophysics_merger.py 0%  execution_merger.py 0%  delta_g_calculator.py 0%
atac_fetcher.py 0%  ago2_fetcher.py 0%  histone_fetcher.py 0%  ... (19 dosya)
cli.py 0%
```
905 test yaprak fonksiyonları doğruluyor; JSON okuyup-yazan, kaynakları birleştiren
ve sonucu üreten katman **hiç** birim testiyle örtülmemiş. Integration testi
(`test_full_pipeline.py`, 59 test) yalnızca **Stage 7**'yi (skorlama+raporlama)
sentetik JSON'larla test ediyor; Stage 1-6 merger'ları çağırmıyor. Bulgu-1 ve
Bulgu-2'nin testlerden kaçmasının sebebi tam olarak bu boşluk.

**Bulgu-4 — Sıkışık dinamik aralık.**
4 gerçek koşunun hepsi 0.298–0.408 bandında (SAFE/WARNING); hiçbiri
HIGH_RISK/DANGEROUS'a ulaşmıyor. Sebepler: (a) ölü ΔG pillar'ı biyofiziği tabana
çekiyor, (b) çok sayıda kaynağın neutral'a düşmesi ortalamayı 0.3-0.4'e sıkıştırıyor.
Sınıflandırıcının üst iki sınıfı pratikte hiç tetiklenmiyor.

**Bulgu-5 (tasarım riski) — Sessiz neutral maskeleme.**
Her modül hata → `0.5`/`0.0` neutral + `logger.warning` yapıyor (graceful
degradation, `grep` ile ~30 nokta). İyi niyet ama tehlikeli: **her kaynak
tamamen patlasa bile** pipeline çöker gibi görünmez, makul-görünen ~0.5 skorlar
üretir. Rapor, kaç domainin gerçek veri kaç domainin fallback olduğunu kullanıcıya
göstermiyor. Güvenilirlik sinyali yok.

### Ölçümler
- `src/` toplam ~10.5k satır, en büyük dosya `transcript_resolver.py` (540).
  Anormal şişkin dosya yok.
- Kod tekrarı: §2'deki 15+ wrapper/logic çifti (mimari seçim, ölü değil ama fazla).
- Loglama: loguru, tutarlı. Config: YAML + pydantic-settings, temiz. Hata yönetimi:
  her yerde try/except + neutral (Bulgu-5 uyarısıyla).

---

## 4) YAYINA HAZIRLIK BOŞLUKLARI

| Öğe | Durum |
|---|---|
| LICENSE | ✅ MIT var. Bağımlılıklar (pandas/BSD, pysam/MIT, snakemake/MIT, loguru/MIT...) MIT ile uyumlu. **Ama:** veri kaynakları öyle değil — **COSMIC akademik/ticari-olmayan lisanslı** ve kayıt ister; CCLE/DepMap kendi şartlarına tabi. Kod MIT olsa da "klonla-çalıştır" pratikte bu lisanslara takılır. Veri commit edilmediği için redistribüsyon ihlali **yok** (iyi). |
| README | ✅ Kapsamlı (24 KB), dürüst limitasyon bölümü var. |
| CONTRIBUTING | ❌ Yok. |
| CHANGELOG | ❌ Yok. |
| Tek komutla kurulum | ❌ **Hayır.** `pip install -e .` var ama: (a) `pyBigWig` pip wheel'ı libcurl'süz — remote BigWig için **kaynaktan derleme + sistem dev-header'ları** gerekiyor (README:180-192 kabul ediyor). (b) **~1.5 GB yerel veri** gitignore'da, **indirme script'i yok**, sadece `docs/DATA_SOURCES.md`. COSMIC/CCLE elle, kayıtla indirilecek. |
| Bağımlılık sabitleme | ✅ `pyproject.toml`'da exact pin (`pandas==3.0.2`, `snakemake==9.19.0`...). İyi pratik, ama pinler agresif/sıradışı; taze makinede hepsi çözülür mü test edilmeli. |
| Sızmış sır/anahtar | ✅ **Yok.** Tüm tracked dosyalar tarandı; `.env`/token/key yok. `.gitignore` sırları dışlıyor. |
| Olmaması gereken veri/çıktı | ✅ Temiz. `data/`, `results/`, `logs/`, `.snakemake/` gitignore'da; git'te 0 veri dosyası. (Not: çalışma dizininde `.coverage` ve `orcsonar.egg-info/` duruyor ama tracked değil.) |
| **Sıfırdan klonla-çalıştır** | ❌ **Mümkün değil.** Taze klon: (1) `data/` boş → 7 zorunlu dosya elle indirilecek (biri lisans-kapılı 904 MB COSMIC), (2) pyBigWig kaynaktan derlenecek, (3) sonra Snakemake çalışır. "Quick start" README'de var ama önkoşul veri edinimi saatler sürer ve otomatik değil. |

---

## 5) DÜRÜST DEĞERLENDİRME

### Olgunluk puanı: **5 / 10**

**Neden 5:** Bu boş bir vaporware değil — gerçek bir pipeline, gerçek veriyi
çekiyor, 24 kaynağı entegre ediyor, hücreye-özgü farklılaşan çıktı üretiyor,
905 gerçek test geçiyor, kod hijyeni (tip/docstring/log/TODO=0) üstün. Bu, puanı
2-3'ten 5'e çıkaran şey. **Neden 5'in üstü değil:** Projenin kimlik iddiası olan
"biyofizik ΔG" fiilen kırık (Bulgu-1), domainler site koordinatında anlaşamıyor
(Bulgu-2), ve bu iki kusuru yakalaması gereken orkestrasyon katmanı %0 test edilmiş
(Bulgu-3). Bilimsel çekirdek doğrulanmamış; puanın büyük kısmı mühendislik
disiplininden geliyor, biyolojik doğruluktan değil.

### Bu proje şu an: **ALFA**
Prototipten ileri (çalışan pipeline + testler + CI-hazır yapı var), ama beta değil:
temel bir hesaplama pillar'ı bozuk, orkestrasyon test edilmemiş, klonla-çalıştır
mümkün değil, hiçbir çıktı biyolojik olarak valide edilmemiş.

### Bunu yayınlarsam beni en çok utandıracak 5 şey

1. **"Biyofizik temelli" diyen projenin ΔG'si sahte.** Biraz bilen biri
   `stage5_deltag.json`'a bakıp her satırda aynı `+31.1`i görür ve tüm biyofizik
   katmanının dekoratif olduğunu 30 saniyede anlar. (`delta_g_calculator.py:80-83`)
2. **Varyant/Ago2 yanlış koordinatı tarıyor** — off-target'tan 4 kb uzağı. Bir
   reviewer JSON'ları çapraz-okuyunca site'ın "nerede olduğu" konusunda
   stage'lerin çeliştiğini görür. (Bulgu-2)
3. **"905 test geçiyor" rozeti ile %0 test edilmiş orkestrasyon** yan yana. Testler
   kolay kısmı (saf fonksiyonlar) örtüyor, gerçekten çağrılan glue'yu değil.
4. **README "Quick start" diyor ama kimse çalıştıramaz** — 1.5 GB lisans-kapılı
   veri + kaynaktan pyBigWig derlemesi, indirme script'i yok.
5. **Tüm gerçek çıktılar 0.30–0.41'e sıkışmış**, hep WARNING/SAFE. Bir kullanıcı
   "bu araç hiçbir şeyi HIGH_RISK bulmuyor" derse haklı olur; dinamik aralık ölü.

### Alternatiflere göre ayırt edici yanı

**Kavramsal olarak gerçek ve ilginç.** Bu alandaki mevcut off-target araçları
(BLAST, siRNA için TargetScan/miRanda/RNAhybrid, CRISPR için Cas-OFFinder/CRISPOR)
ya saf dizi-benzerliği ya da tek-katman termodinamik yapar. **Hücreye-özgü
epigenetik + varyant + biyofizik + RISC-execution'ı tek risk skorunda birleştiren
ve saRNA'ya (siRNA/CRISPR değil) odaklanan** açık bir araç bildiğim kadarıyla yok.
Fikir ve entegrasyon iskeleti gerçekten ayırt edici.

**Ama ayırt edicilik henüz bilimsel değil, mimari.** Hiçbir çıktı deneysel veriyle
karşılaştırılmadı; ΔG pillar'ı kırık; skorlar valide edilmedi. Yani "yeni bir yöntem
öneriyor" diyebilirsin, "yeni bir yöntem **kanıtlıyor**" diyemezsin. Rakiplerin
karşısındaki üstünlüğü şu an bir **hipotez**, ürün değil.

---

## Yayın öncesi öncelikli iş listesi (etkiye göre)

1. **ΔG'yi düzelt veya dürüstçe devre dışı bırak.** Off-target dizisini
   `stage2_offtargets.json`'a ekle; `delta_g_calculator`'da gerçek diziyi kullan;
   `reversed()`/işaret hatasını düzelt. Düzeltilemeyecekse README'de "ΔG şu an
   deneysel/devre dışı" de — sahte +31.1 üretmekten iyidir.
2. **Koordinat tutarsızlığını çöz (Bulgu-2).** Tüm domainler aynı off-target
   region'ını kullanmalı; stage3/6'nın neden 4 kb kaydığını bul.
3. **Merger + `run()` glue için testler yaz.** En az bir uçtan-uca gerçek-küçük-veri
   integration testi (Stage 1→7), sentetik-only değil.
4. **`scripts/download_data.py`** yaz; hangi kaynağın lisans/kayıt istediğini
   `DATA_SOURCES.md`'de netleştir. Küçük bir örnek veri seti ("VEGFA slice")
   ekle ki insanlar klonlayıp deneyebilsin.
5. **Rapora güven sinyali ekle:** kaç domain gerçek veri, kaç tanesi neutral
   fallback. Sessiz maskelemeyi görünür yap (Bulgu-5).
6. Wrapper/logic isimlendirmesini sadeleştir; CONTRIBUTING + CHANGELOG ekle.

---

## EK BULGULAR (2026-09-16, CLAUDE.md denetimi sırasında)

**Bulgu-6 (KRİTİK) — "Whole transcriptome" taraması aslında 183 gen.**
`src/stage2_offtarget_scan/transcriptome_fetcher.py:37` içindeki
`_BACKGROUND_GENES` elle küratörlenmiş **183 genlik** bir liste (housekeeping +
hnRNP + RISC + cell cycle + onkogen). Tüm transkriptom ~20.000 protein-kodlayan
gen. İddia üç yerde geçiyor ve üçü de yanlış:
```
CLAUDE.md "Key Design Decisions"  : "WHOLE TRANSCRIPTOME (all mRNAs)"
README.md:55, README.md:244       : "whole transcriptome"
docs/DATA_SOURCES.md:207          : aynı iddia
transcriptome_fetcher.py:133      : docstring "~250 genes"  ← o da yanlış
seed_aligner.py:311               : docstring "~250 genes"  ← o da yanlış
```
Arama uzayı 183 genle sınırlı olduğu için VEGFA_HeLa koşusunda çıkan 41
off-target'ın MTOR/DICER1/MYC gibi tanıdık isimler olması tesadüf değil.
**Yayın açısından Bulgu-1'den daha ölümcül:** bir hakem `_BACKGROUND_GENES`
listesini gördüğü anda "whole transcriptome" iddiası çöker. Ensembl REST ile
ölçeklenmez; GENCODE v44 lokal FASTA + hızlı seed indeksi gerekir. Mevcut
kriter (5-6 mismatch + G:U wobble) tam transkriptomda on binlerce hit üretir,
eşikler ROC ile yeniden kalibre edilmeli.

**Bulgu-7 (KRİTİK) — Belgelenen skorlama mimarisi kodda yok; epigenetik ve
execution çifte sayılıyor.**
CLAUDE.md "Scoring Architecture" iki katmanlı bir model tarif ediyor:
```
Final Risk = Base_Score × Cell_Modifier
Base_Score   = sequence(0.20) + variant(0.15) + biophysics(0.25)
Cell_Modifier ← epigenetic(0.20) + execution(0.20)'den türetilir
```
Gerçek kod (`src/scoring/integrator.py`):
- `integrate()` **beş domainin hepsini** `base_score` ağırlıklı toplamına
  katıyor — epigenetik ve execution dahil.
- `apply_cell_modifier()` config'deki ağırlıkları **hiç kullanmıyor**; kendi
  hardcoded katsayıları var: `0.4×atac + 0.4×expr + 0.2×exec`,
  `modifier = 0.3 + 1.4×activity`, aralık `[0.3, 1.7]`.

Sonuçlar:
1. **Çifte sayım:** epigenetik ve execution sinyali hem base_score'a hem
   modifier'a giriyor. `config.yaml`'daki `epigenetic_context: 0.20` kullanıcıya
   yalan söylüyor — gerçek etki 0.20 değil.
2. **Düzeltme (2026-09-16):** bu katsayılar *belgesiz değil* —
   `docs/DATA_SOURCES.md:239-249` `cell_activity` ve `cell_modifier`
   formüllerini, `[0.3, 1.7]` aralığını ve "eksik girdi → 0.5 → modifier 1.0"
   davranışını doğru şekilde yazıyor. Yani public doküman kodu doğru anlatıyor;
   **yanlış mimariyi anlatan tek yer CLAUDE.md.** Geriye kalan sorun daha dar
   ama hâlâ geçerli: `0.4/0.4/0.2`, `0.3`, `1.4` sayıları config'de değil koda
   gömülü ve hiçbir literatür gerekçesi yok.
3. Faz 3'te ağırlık öğrenmesi yapılacaksa, **parametre uzayının yarısı
   config'de değil koda gömülü** — öğrenilemez, raporlanamaz.
4. Bulgu-4'ün (tüm skorlar 0.30–0.41'e sıkışmış) muhtemel ikinci sebebi bu
   çifte sayım: aynı sinyal iki kez ortalamaya çekiyor.

Karar gerekiyor: ya kod belgeye uydurulacak (iki katmanlı model gerçekten
uygulanacak), ya belge koda uydurulacak (tek katmanlı 5-domain toplamı + ayrı
modifier olarak dürüstçe yazılacak). Faz 3 başlamadan çözülmeli.

---

## BULGU-2 — KÖK NEDEN BULUNDU (2026-09-16, `/verify-run` ilk çıktısı)

Denetimde "stage'ler aynı site için farklı koordinat tarıyor" diye tarif edilen
sorun bir koordinat hesaplama hatası değil. **Site kimlik anahtarı benzersiz
değil.**

`stage2_offtargets.json` bir **liste** yazıyor ve aynı transkript için birden
fazla seed hit kaydedebiliyor. VEGFA_HeLa'da:

```
41 seed hit  →  30 benzersiz "gene:transcript" anahtarı  →  11 DUPLİKE (%27)

MTOR:ENST00000361445  ×2
   chr1:11255438-11255458   mm=5   score=14.5   ← güçlü hit
   chr1:11259515-11259535   mm=9   score=10.0   ← zayıf hit, 4077 bp uzakta
HNRNPA2B1:ENST00000618183 ×2  (26198044 / 26197989)
DICER1:ENST00000343455    ×2  (95152261 / 95147794)
TNRC6B, ATR, ... toplam 11 anahtar
```

Stage 3-6 bu listeyi `gene:transcript` anahtarlı bir **dict**'e çeviriyor.
Anahtar çakışınca biri sessizce diğerinin üzerine yazıyor — ve **stage'ler aynı
kazananı seçmiyor**:

```
MTOR:ENST00000361445 için hangi lokus ölçülmüş:
  stage3_phylop  → 11259515   (zayıf hit)
  stage3_cosmic  → 11259515   (zayıf hit)
  stage6_ago2    → 11259515   (zayıf hit)
  stage5_shape   → 11255438   (güçlü hit)   ← diğerleriyle çelişiyor
```

Sonuç, denetimde yazılandan daha kötü:

1. **Güçlü hit (mm=5) yanlış lokustan ölçülüyor.** Varyant toksisitesi,
   korunum ve Ago2 yüklemesi 4 kb uzaktaki zayıf hit'in yerinden okunuyor.
2. `final_report.json` 41 site'ın hepsini listeliyor (site kaybı YOK), ama
   `domain_scores_per_site` dict olduğu için **11 çift, tek bir skor kaydını
   paylaşıyor**. MTOR'un iki satırı raporda birebir aynı skorları taşıyor:
   `{sequence_specificity: 1.0, variant_toxicity: 0.65, ...}` — farklı iki
   lokus, tek ölçüm.
3. Yani raporlanan 41 site'ın **11'i başka bir site'ın ölçümlerini taşıyor.**
4. `stage5_shape` denetimde "tutarlı" sayılmıştı; değil — sadece diğerlerinden
   farklı kazananı tutuyor. (`/verify-run` ayrıca DDX17:ENST00000403230'da
   3041 bp'lik ikinci bir sapma buldu.)

**Düzeltme yönü:** site kimliği `gene:transcript` değil, koordinatı da içeren
benzersiz bir anahtar olmalı (ör. `gene:transcript:chrom:start`). Alternatif:
stage 2 transkript başına en iyi hit'i seçip tekilleştirsin. Bu, Bulgu-1'den
daha ucuz bir düzeltme ve tüm domainleri aynı anda doğru lokusa oturtur.

**Nasıl bulundu:** `/verify-run` skill'inin 3. kontrolü (stage'ler arası
koordinat tutarlılığı). Bu tam olarak kontrolün var oluş sebebi.
