# Araştırma — R1.3 (`_clamp(None) → 0.5`) ve R4.2 (gnomAD kanalı)

İstek: "kaynağı nedir ve nasıl en iyi çözüme ulaşılır." Bu dosya **karar
vermiyor** — ikisi de ön kayıt maddesi (`A12`), kilidi kullanıcı atar
(değişmez 6). Burada yalnız kaynak teşhisi, ölçüm ve seçeneklerin maliyeti var.

Ölçümler, aksi yazılmadıkça, **2026-11-19 tarihli taze koşudan**
(`R0`–`R2` düzeltmeleri sonrası, VEGFA/HeLa) alındı.

---

## Bölüm 0 — Önce bir uyarı: taze koşu bilimsel olarak kullanılabilir DEĞİL

> ✅ **GÜNCELLEME 2026-11-24:** bu bölümün teşhis ettiği arıza `R12a`'da kapandı. Sebep ölçüldü (`expand=1` + batch=80 Ensembl'de 120 s'de timeout), `_LOOKUP_BATCH` 20'ye indirildi, ve yeni koşu **182/182 arka plan (%100)** ile **41 site** üretti — tek 504 bile almadan. Koşu artık kendi kapsamını `stage2_seed_hits.json`'daki `background_coverage` alanına yazıyor.
> Aşağıdaki teşhis tarihsel kayıt olarak duruyor; **§1.4'ün sayıları o zayıf koşudan geldiği için düzeltildi** (bkz. oradaki DÜZELTME kutusu).

Aşağıdaki sayıların hepsi bu koşudan, ve koşunun kendisi bir bulgu üretti:

```
transcriptome_fetcher: 22 background transcripts ready (excluded: VEGFA)
seed_aligner: VEGFA — scanning 48 transcripts total (22 background + target gene)
seed_aligner: VEGFA → 4 off-target site(s)
```

**182 genin 22'si çözüldü (%12).** Sebep: Ensembl `lookup/symbol` üç batch'ten
**ikisini 504 Gateway Timeout** ile reddetti (80 + 80 kayıp, 22 geçti).

Referans koşuda 41 site var, bunda 4. Ve rapor bunu söylemiyor:

```
risk_class: SAFE   final_risk_score: 0.290911   sites: 4
"Active chromatin detected at 0 of 4 off-target sites. Overall risk: SAFE."
```

### 🔴 Bu, R0.1a'daki bir boşluk — kendi düzeltmemin

`R0.1a` **tam** kayıpta (`0 gen çözüldü`) `DataSourceError` atıyor ve Bulgu
12'yi kapattı. Ama kasıtlı olarak kısmi sonucu geçiriyor ("emekliye ayrılmış
bir sembol koşuyu durdurmamalı"). %88 kayıp o kapının altından geçiyor.

Yani araç artık **yalan söylemiyor** (sıfır siteyi SAFE diye raporlamıyor) ama
**sakatlanmış bir arama uzayından güvenli bir karar üretiyor** ve kapsamı
raporlamıyor. Bu, `R4.1`'in (kanal kapsamı tabanı) tam olarak aynı sorusunun
**arama uzayı düzeyindeki** hâli, ve aynı şekilde bir ön kayıt kararı:
*arka plan kapsamının altında koşu reddedilir* eşiği kaç olmalı.

⚠️ Dolayısıyla `B12` **kapanmadı**. Dört koşunun yeniden üretilmesi,
Ensembl'in tam cevap verdiği bir pencere gerektiriyor (ya da `D1`'in yerel
GENCODE indeksi, ki bu bağımlılığı tamamen kaldırır).

---

## Bölüm 1 — R1.3: `_clamp(None) → 0.5`

### 1.1 Kaynak: bu bir modelleme kararı değil, **kod yeniden kullanımı kazası**

`src/scoring/score_integrator.py:30-42`:

```python
_NEUTRAL = 0.5

def _clamp(value: Any) -> float:
    """Clamp upstream domain score to the [0, 1] contract of DomainScores.

    Why: stage producers (e.g. sead_aligner) emit raw alignment scores that
    can exceed 1.0; DomainScores rejects them with a Pydantic ValidationError.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return _NEUTRAL
    if v != v:  # NaN guard
        return _NEUTRAL
    return max(0.0, min(1.0, v))
```

**Fonksiyonun kendi docstring'i amacını söylüyor: bir ARALIK düzelticisi.**
`seed_aligner` 8.0-14.5 arası ham hizalama skorları üretiyor, `DomainScores`
`[0,1]` istiyor, `_clamp` arasını kapatıyor. Meşru ve gerekli.

Ama `except (TypeError, ValueError)` dalı **üç ayrı durumu** yutuyor:

| girdi | gerçek anlamı | sorun tipi |
|---|---|---|
| `None` | ölçülmedi (`B2` sentinel'i) | **eksik veri** |
| `"abc"` | bozuk veri | **bozulma** |
| `NaN` | tanımsız aritmetik | **sayısal** |

ve üçüne de **skor uzayında `0.5`** cevabını veriyor.

**Teşhis:** eksik-veri politikasını kimse seçmedi. O `0.5`, başka bir sorun
için yazılmış bir `try/except`'ten **düştü**. Bu, R1.3'ü cevaplanabilir
kılıyor: "0.5 mi olmalı?" sorusu hiç sorulmamış, dolayısıyla bir kararı
geri almıyoruz — ilk kez veriyoruz.

### 1.2 İkinci yol: `.get()` varsayılanları

`:192-196` ayrıca `_NEUTRAL`'ı `.get()` varsayılanı olarak geçiyor:

```python
seq = _clamp(sequence_scores.get(site_id, _NEUTRAL))
var = _clamp(variant_scores.get(site_id, {}).get("normalized_score", _NEUTRAL))
```

Yani `0.5`'e **iki bağımsız yol** var: site upstream dosyada hiç yok (→ `.get`
varsayılanı), ya da site var ama `normalized_score: null` (→ `.get` `None`
döner, `_clamp` yakalar). İkisi birlikte ele alınmalı; birini düzeltmek
diğerini açık bırakır.

### 1.3 `_clamp` ayrıca üçüncü bir işi de kötü yapıyor

Taze koşudan ölçüm (n=4):

| domain | min | maks | ayrık değer |
|---|---|---|---|
| `sequence_specificity` | 1.0000 | 1.0000 | **1** |
| `variant_toxicity` | 0.0000 | 0.1999 | 4 |
| `epigenetic_context` | 0.0100 | 0.5035 | 4 |
| `biophysics_structure` | 0.0000 | 0.1333 | 4 |
| `execution_safety` | 0.0000 | 0.2222 | 2 |

`sequence_specificity` dört sitede de **1.0** — çünkü ham skorlar 8.0-14.5 ve
`_clamp` hepsini tavana eziyor (rule 20'nin `C1` maddesi, taze koşuda
doğrulandı). Yani `_clamp` aynı anda:

- (a) sequence kanalını sabit 1.0'a eziyor → 0.20 ağırlık bilgi taşımıyor (`C1`)
- (b) bilinmiyeni 0.5'e çeviriyor (`R1.3`/`B3`)
- (c) bozuk veriyi 0.5 diye gizliyor

Üç iş, üç farklı doğru cevap, tek fonksiyon.

### 1.4 `0.5`'in neden özellikle yanlış olduğu — taze ölçüm

⚠️ **DÜZELTME (2026-11-24, R12a sonrası tam kapsamlı koşu).** Bu bölümün ilk
hâli %12 kapsamlı, n=4 siteli koşudan ölçülmüştü ve iddiayı **olduğundan
güçlü** gösteriyordu ("beş domainin dördü"). Kendi §0 uyarımı kendi sayıma
uygulamak zorundayım. Tam kapsamlı koşu (n=41, 182/182 arka plan):

| domain | maks | ortalama | `0.5` tavanın üstünde mi | sitelerin kaçı 0.5 altında |
|---|---|---|---|---|
| `variant_toxicity` | 0.6698 | 0.2282 | hayır | %95 |
| `epigenetic_context` | 0.6095 | 0.2232 | hayır | %90 |
| `biophysics_structure` | 0.2933 | 0.0704 | **evet** | %100 |
| `execution_safety` | 0.2222 | 0.1680 | **evet** | %100 |
| `sequence_specificity` | 1.0000 | 1.0000 | hayır (sabit, `C1`) | %0 |

Yani doğru ifade: `0.5`, beş domainin **ikisinin** gözlenen maksimumunun
üstünde (dördünün değil), ve **dördünün ortalamasının** belirgin şekilde
üstünde. Ölçülmemiş bir `biophysics` ya da `execution` domaini hâlâ
ölçülebilen **her** siteden riskli sıralanıyor; `variant` ve `epigenetic`
için ise `0.5` sitelerin %90-95'inden riskli — yani argüman ayakta ama
"her domain için" değil, **iki domain için kesin, diğer ikisi için
olasılıksal**.

Ve yön, merger'ların içindeki renormalizasyonun **tersi**: renormalizasyon
Bulgu 7'de aşağı yönlü sapma gösteriyor (CCLE düşünce 37/41 site güvenliye),
`_clamp` yukarı yönlü. **Aynı boru hattında iki tutarsız kestirici.**

### 1.5 Seçenekler ve maliyetleri

| | ne yapar | artı | eksi |
|---|---|---|---|
| **A** `_clamp`'i üçe böl | aralık düzeltmesi / bilinmiyor / bozulma ayrı ayrı ele alınır | her birinin doğru cevabı farklı olabilir; `C1` de açılır | üç karar gerektirir |
| **B** bilinmiyeni propagate et (`None`) | `base_score` `None`, site sıralanmaz | tek dürüst arıza yönü; araç "bilmiyorum" der | bazı siteler skorsuz kalır; `risk_classifier` zaten bunu kaldırıyor (R0.1b) |
| **C** ampirik bir noktaya imput et | `0.5` yerine ölçülmüş bir yüzdelik | dağılımla tutarlı | **sonucu gördükten sonra sayı seçmek** = `A12` ihlali riski |
| **D** `coverage` raporla, `0.5`'i tut | okuyan tabakalandırabilir | en az değişiklik | kestirici tutarsızlığı kalır |

**Teknik not:** `B` bugün ucuz, çünkü altyapısı bu oturumda kuruldu —
`risk_classifier` ve `FinalReport` artık `None`'ı taşıyor (R0.1b), dört
merger da `None` dönebiliyor (R1.2/R2). Yani `_clamp`'in `None` yolunu
kaldırmak tek satır; tüketiciler hazır.

⚠️ `C`'yi seçersek yüzdelik **`B12` tamamlanmadan ve sonuca bakılmadan**
yazılmalı. Bugünkü koşu %12 kapsamlı olduğu için ondan yüzdelik okunamaz.

---

## Bölüm 2 — R4.2: gnomAD kanalı

### 2.1 Kaynak bulundu: **kategorik bir eleme kriteri, sürekli bir risk rampasına çevrilmiş**

Kod (`gnomad_client.py:280`, doğrulandı):

```python
return max(0.0, 1.0 - max_af / _AF_COMMON_THRESHOLD)   # _AF_COMMON = 0.01
```

Rampa `[0, 0.01]` aralığında 1.0 → 0.0 iniyor ve **tam %1'de doyuyor**.
O doyma noktası bir tesadüf değil — **parmak izi.**

Terapötik siRNA pratiğinde popülasyon AF'si şöyle kullanılıyor: patent
başvurularında tarif edilen iş akışı, seed'i miRBase'e karşı tarıyor,
2-uyumsuzluklu off-target sayıyor, **sonra hedef bölgeleri dbSNP'ye karşı
eliyor** — ve eşik şudur: *"target sites with no SNPs at MAF ≥ 1%"*
(TSLP, ANGPTL7 ve ANGPTL4 başvurularında aynı kalıp).

Yani yerleşik kullanım **ikili bir eleme**: MAF ≥ %1 ise site **listeden
çıkar**. orcSONAR o ikili kuralı `[0, 0.01]` üzerinde lineer bir rampaya
dönüştürmüş. Bunun iki ölçülebilir sonucu var ve ikisi de gözlendi:

1. **Dinamik aralık tamamen bilgisiz bantta.** AF %1 ile AF %50 **aynı**
   skoru (0.0) alıyor; AF %0.1 ile %0.5 ise skoru 0.4 oynatıyor — oysa ikisi
   de tek bir ailede görülebilecek frekanslar.
2. **Bağlanma ekseninde büyüklük ~100 kat yanlış.** Hâlâ guide'a uyan
   kromozom oranı tam olarak `1 − AF`'dir: AF = 0.01'de doğru çarpan
   **0.99**, kod **0.00** uyguluyor. Ölçülen örnek
   (`results/VEGFA_HeLa/stage3_gnomad.json`, MTOR sitesi):
   `max_af = 0.006846` → skor `0.31537`, yani **%0.68'lik bir alel siteyi
   %68 "güvenli"ye taşıyor.**

**İşaret doğru, biçim yanlış.** Yerleşik pratik de "polimorfik site daha az
önemli" diyor — `bio-reviewer`'ın `B4`'ün işaretini onaylaması buna uyuyor.
Yanlış olan, kategorik bir konvansiyonun graded bir risk ağırlığı gibi
kullanılması.

### 2.2 İki ek kusur (bağımsız olarak doğrulandı)

- **`ref`/`alt` okunmuyor.** `gnomad_client.py:251-252`'de parse ediliyor,
  `_calculate_polymorphism_score` hiç bakmıyor. Alt aleli guide'a **uyan** bir
  varyant, referansta olmayan bir off-target *yaratır*; kod onu risk-azaltıcı
  sayar. Bilinmeyen bir site alt kümesinde kanal ters yöne bakıyor.
- **Pozisyon ağırlığı yok.** `max` 20-nt footprint'in tamamından alınıyor
  (`:279`), yani pozisyon-19'daki SNP ile seed içindeki (2-8) SNP aynı puanı
  alıyor — oysa seed dışı uyumsuzluklar tolere edilir.

### 2.3 "Veri yok → korunmuş" — ve artık ölçülebilir

`:277-278` boş pencereyi `1.0` sayıyor. Referans koşuda `variant_count`
ortalaması **10.44**, medyan 6, **0/41 boş pencere** — yani çağrılabilir bir
20-mer bu yoğunlukta boş dönmüyor; **boş = çağrılamadı.**

🔎 **Araştırıldı:** gnomAD GraphQL'de `coverage` alanı **var** —
`dataset`, `chrom`, `start`, `stop` alıyor ve pozisyon başına
`mean`/`median`/`over_1`…`over_100` döndürüyor. Yani "varyant yok" ile
"çağrılamadı" ayrımı **sorgulanabilir**; kod sadece sormuyor.
⚠️ Bu şema üçüncü-parti dokümanlardan doğrulandı, resmî gnomAD
dokümantasyonundan değil — uygulanacaksa önce canlı bir sorguyla sınanmalı.

### 2.4 Seçenekler ve maliyetleri

| | ne yapar | maliyet | not |
|---|---|---|---|
| **A** Anotasyona indir | `max_af` raporda kalır, skora girmez | **en küçük**, yeni veri yok | kanalın 0.03 ağırlığı serbest kalır; `C4` ağırlıkları zaten yeniden ele alacak |
| **B** Kategorik elemeye dön | MAF ≥ %1 olan site **listeden çıkar** | küçük; eşik zaten kodda | **yerleşik pratikle birebir aynı**; ama *site listesini* değiştirir, yani değerlendirme evrenini — ön kayda yazılmalı |
| **C** Gen düzeyi kısıt metriği | LOEUF/pLI/pTriplo ile değiştir | **en büyük**: yeni veri kaynağı | gen-anahtarlı → Bulgu-8/`D2`'den **etkilenmez**; docstring'in iddia ettiği şeyi gerçekten ölçer |
| **D** Rampayı düzelt, kanalı tut | `1 − AF` + pozisyon ağırlığı + `ref`/`alt` | orta-büyük | lokus yanlış olduğu sürece kazancı ölçülemez (aşağı) |

### 2.5 Hepsinin üstündeki kısıt: lokus yanlış

`.claude/rules/10-koordinatlar.md`: türetilen genomik koordinatın **medyan
sapması 30.732 bp**, 41 sitenin 39'u >1 kb. gnomAD o koordinattan okuyor.

Yani `D2` bitene kadar bu kanalın **hiçbir** değeri yorumlanamaz — `B4` yanlış
yerden okunan bir sayının işaretini düzeltti. Bu, `D`'yi (rampayı düzeltmek)
şimdilik ölçülemez kılıyor ve `A`/`B`'yi cazip yapıyor: ikisi de `D2`'yi
beklemeden uygulanabilir ve ikisi de yanlış bir sayıyı skordan çıkarır.

`C`'nin özel avantajı tam burada: gen kimliği, splice-körlüğünden
**etkilenmeyen** tek alan (`site_id` alan 0; rule 10 bunu açıkça yazıyor).

---

## Bölüm 3 — Bu araştırmanın kendi sınırları

- Taze koşu **n = 4 site** ve **%12 arka plan kapsamı**. Bölüm 1.4'ün domain
  maksimumları bu yüzden zayıf; yön güçlü, büyüklük değil. `B12` tamamlanınca
  yeniden ölçülmeli.
- gnomAD `coverage` şeması resmî dokümandan doğrulanmadı (§2.3).
- Patent iş akışları **hakemli yöntem değil**; yerleşik pratiğin kanıtı
  sayılabilir, doğruluğunun kanıtı sayılamaz. Hakemli, MAF-duyarlı bir
  off-target aracı bulunamadı — bu da kanalın özgün ve gerekçelenmemiş bir
  kurgu olduğu yönünde bir kanıt.
- Hiçbir şey uygulanmadı. İkisi de `A12` maddesi.

### Kaynaklar

- gnomAD API koordinat tabanı ve `coverage` alanı:
  [ToolUniverse gnomAD araçları](https://zitniklab.hms.harvard.edu/ToolUniverse/tools/gnomad_tools.html) ·
  [gnomAD API tasarım notu](https://rhshah.github.io/vFlank/0.6.0/research/gnomad-api/) ·
  [gnomAD GraphQL sorgu referansı](https://cdn.jsdelivr.net/npm/@saibolla/ada@0.1.3/skills/gnomad-database/references/graphql_queries.md)
- Terapötik siRNA iş akışında MAF ≥ %1 elemesi:
  [TSLP başvurusu](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11452738) ·
  [ANGPTL7](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12378556) ·
  [ANGPTL4](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11377658)
- Seed baskınlığı ve seed-dışı belirleyiciler:
  [PLoS Comp Biol / RNAi ekran analizi](https://pmc.ncbi.nlm.nih.gov/articles/PMC4117740/) ·
  [siRNA non-seed bölgesi](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4676691/) ·
  [SeedSeq](https://onlinelibrary.wiley.com/doi/10.1155/2013/905429)
