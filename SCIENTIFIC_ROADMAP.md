# orcSONAR — Bilimsel Yol Haritası

> Bu dosya bir plan değil, bir **durum makinesidir.** Yeni bir oturum açan model
> buradan başlar: §2 değişmezlerini okur, bağımlılığı karşılanmış ilk `TODO` maddesini
> bulur, **yalnız onu** yapar, kabul kriterini koşar, durumu günceller.
>
> Kanıt tabanı: `AUDIT.md` (repo içi, Bulgu-1…15),
> `/home/koray/orcSONAR-denetim/DENETIM_RAPORU.md` (10 uzman denetimi, 2026-11-16) ve
> `/home/koray/orcSONAR-denetim/PLAN_DENETIMI_FABLE.md` (plan denetimi, 2026-11-17).
> Her "neden" bir ölçüme dayanır. Yeni iddia eklenecekse ölçümü de eklenir.
>
> Durum alfabesi: `TODO` · `DOING` · `DONE` · `BLOCKED(<id>)` · `DROPPED(<gerekçe>)`

---

## 0. Hedef hakkında dürüstlük — bunu ilk oku

**Metodolojik titizlik** olarak Nature standardı bu planla ulaşılabilir. **Nature'ın
kendisi** için yeterli değil: ıslak-lab doğrulaması yok, yeni biyolojik bulgu yok,
algoritmik yenilik yok. Nature ailesine geçiş için bir ıslak-lab işbirliği + ondan çıkan
biyolojik sonuç gerekir; bu plan o işbirliğinin **ön koşulunu** üretir.

**Hedef dergi tek bir liste değil — `E3a`/`E4a` sonucunun fonksiyonu.** Bunu baştan
tabloya yazmak, sonuç kötü geldiğinde ağırlık ayarlama cazibesini ortadan kaldıran tek
yapısal önlemdir (bkz. değişmez 7):

| sonuç | uygun venue |
|---|---|
| Tabanları **net geçiyor** + çok-omik katman ölçülebilir katkı veriyor | *NAR Genomics and Bioinformatics* · *Bioinformatics* (Application Note) · *Briefings in Bioinformatics* · iyi giderse *NAR* denenebilir |
| Tabanları geçiyor, çok-omik katman katkı vermiyor (**en olası**) | *NAR GAB* · *BMC Bioinformatics* · *PLOS Computational Biology* (ablasyon/benchmark çerçevesiyle) |
| Tabanları **geçmiyor** | **negatif/benchmark makalesi** — *NAR GAB*, *F1000Research*, *PLOS ONE*. Çerçeve: *"siRNA off-target verisi saRNA tasarım araçlarını test etmek için yeniden amaçlanabilir ve mevcut yaklaşımlar şans üstüne çıkmıyor."* Bu gerçek ve atıf alan bir katkıdır — `saRNA Designer`'ın kendi README'si bunun boşluk olduğunu söylüyor |
| saRNA güvenliği çerçevesi | *Molecular Therapy – Nucleic Acids* her üç senaryoda da makul |

⚠️ *NAR* ve *Genome Biology* bu çıktı için **fazla iyimser**: ikisi de birden çok bağımsız
veri setinde yerleşik araçlara net üstünlük ve topluluk kaynağı bekliyor. Elde 2006 tarihli,
yeniden amaçlanmış, tek hücre hattı verisi var. Ve asıl hakem itirazı şu olacak:
*"saRNA aracını siRNA verisiyle doğruladınız."* Bu itiraz `A1` + `A10` ile yönetilebilir,
ama NAR düzeyinde tek başına yeterli savunma değil.

---

## 1. ÜÇ iddia, üç ayrı kritik yol

| | **İDDİA 1 — P_silence** | **İDDİA 2 — hücre-hattı özgüllüğü** | **İDDİA 3 — Impact ağırlıklandırması** |
|---|---|---|---|
| cümle | Bu dupleksin ipliği şu genleri siRNA gibi baskılar | Aynı saRNA farklı hatlarda farklı siteleri riskli bulur | Susturulması daha kötü sonuç doğuracak genler doğru önceliklendiriliyor |
| bileşen | `sequence_specificity`, `biophysics_structure`, ifade/erişilebilirlik | `cell_modifier` | `variant_toxicity`, `execution_safety` |
| birim | **gen düzeyi** | site düzeyi | gen düzeyi |
| gerçek referans | **var ve bol** — GSE5814/5769/5291 (HeLa) | **yok** — aynı saRNA'nın iki desteklenen hatta transkriptom-geniş ölçümü kamuya açık değil | **yok ve hiçbir zaman olmayacak** — log2FC susturulmayı ölçer, sonucun ağırlığını değil |
| ön koşul | `C1` + `C3` + `D1` (+ `C0`, `C0b`) | `D2` + `B6` + canlı kanallar | — |
| splice-körlüğü etkiler mi | **HAYIR** — etiket gen düzeyinde, seed uzayı cDNA'da | **EVET** | hayır |
| sonuç | **doğrulanabilir → yayının gövdesi** | **doğrulanamaz → sınırı açık yazılır** | **doğrulanamaz → açıkça etiketlenmiş tasarım kararı** |

**İddia 3 neden ayrı:** gerçek referans (log2FC) yalnız *susturulmayı* ölçüyor.
`variant_toxicity` (0.15) + `execution_safety` (0.20) = nominal ağırlığın **~%35'i**,
etiketin **tanım gereği göremediği** bir boyutu ölçüyor — bir onkogenin susturulma
olasılığı, o onkogende kaç COSMIC mutasyonu olduğundan bağımsızdır. Bu bileşenler
*kusursuz çalışsa bile* PR-AUC'yi **düşürürler**. Ayrıştırılmazsa `E3a` pozitif çıksa
neyin işe yaradığı belirsiz, negatif çıksa negatiflik bir hatanın değil **kategori
karışıklığının** sonucu olur — ve değişmez 7 bir kaçış deliğine dönüşür. Bkz. `A7`.

**İddia 1'in kritik yolu kasıtlı olarak koordinatsızdır.** Doğrulandı: seed arama uzayı
ve ona bağlı her şey (`gene`, `transcript_id`, `tx_start`, `tx_end`, `mismatches`,
`alignment_score`) cDNA koordinat sisteminde hesaplanıyor; `GenomicRegion`
`seed_aligner.py:105-112`'de türetilip bir daha okunmuyor. Bu yüzden `E3a` ekzon
yürüyüşünü (`D2`) **beklemez**.

---

## 2. DEĞİŞMEZLER — hiçbir madde bunları ihlal edemez

1. **`data/` salt-okunur** (elle küratörlü referans verisi). Makine-indirilen veri
   `data/external/` altına gider, manifest'li. **`results/` elle düzenlenmez; yalnız
   Snakemake yazar.** Sonucu elle düzenlemek veri uydurmaktır.
2. **Arıza yönü kuralı:** veri yokluğu asla riski düşürmez. Yeni bir fallback açık bir
   *bilinmiyor* tipi döner, sayı dönmez. Sessiz `except: pass` yazılmaz.
   *Ölçüm: üç bağımsız fallback de "güvenli" yönüne arızalanıyordu —
   `_NEUTRAL_SIGNAL = 0.0`, ago2 URL yok → `0.0`, `mirbase_checker.py` istisna → `"SAFE"`.*
3. **Beyan = uygulanmış değil.** `git grep` ile üretim çağıranını göster, yoksa ekleme.
   *Ölçüm: `mypy strict=true` (araç kurulu değildi), `max_mismatches: 12` (atıl),
   `_NEUTRAL = 0.5` (hiç okunmuyor), h3k27me3 (9 config tanımı / 0 referans),
   `--json` (belgeliydi, çalışmıyordu).*
4. **Commit'lenmemiş = yok.**
   *Ölçüm: h3k27me3 "wired ✅" hafızası hiçbir commit'te yoktu; `verify-run` check 6
   aylarca commit'siz bekledi.*
5. **Test önce kırmızı olmalı.** Hatayı yakalayan test, düzeltmeden önce başarısız
   olduğu **gösterilmeden** merge edilmez. `fix-done` bu kanıtı sorar.
   *Ölçüm: 917 test yeşil geçerken bilinen üç hatanın üçünü de yakalamıyordu.*
6. **Ön kayıt kilitlidir.** `docs/PRE_REGISTRATION.md` `A6`'da commit'lendikten sonra
   düzenlenmez — bir hook da bunu engeller (`A2.6`). Değişiklik gerekiyorsa
   `docs/PRE_REGISTRATION_v2.md` açılır ve **ikisi de** yayında raporlanır.
7. **Negatif sonuç kabul edilir ve bir yayın yolu vardır** (§0 tablosu, üçüncü satır).
   Ağırlık, eşik veya sabit ayarlayarak pozitif sonuç aramak bu planın ihlalidir.
   **Özellikle:** ölü kanalları telafi etmek için eşik indirmek de bu kategoridedir.
8. **Her madde tek iştir.** Geçerken başka bir bulgu düzeltilmez.

---

## 3. MADDELER

### FAZ A — Ön kayıt (kod yazılmaz, 2-3 gün)

> `biostatistician` ajanı **burada** devreye girer, Faz E'de değil — en pahalı hatalar
> ön kayıt anında yapılır ve ön kayıt kilitlidir.

| id | iş | bağımlılık | kabul kriteri | durum |
|---|---|---|---|---|
| **A1** | Mekanizma kararı: modellenen şey **saRNA dupleksinin her iki ipliğinin** siRNA-benzeri seed off-target'ı. ⚠️ "guide ipliğinin" demek PR-AUC tavanını düşürür — etiketteki pasajer-iplik pozitifleri tanım gereği görülemez (bkz. `C0b`). | — | `docs/PRE_REGISTRATION.md` §1 mekanizmayı tek cümlede söylüyor | TODO |
| **A2** | Gerçek referans setini kilitle: **GSE5814** (68 örnek, HeLa, seed pozisyon mutantları — en güçlü), GSE5769, GSE5291, GSE41924, GSE44256/44105, GSE278438/9. | A1 | §2'de accession + n + tasarım | TODO |
| **A2b** | **Her accession'ın kimliğini, yayınını ve tasarımını NCBI'dan doğrula — kilitlemeden önce.** Ön kayıt kilitli olduğu için yanlış accession geri alınamaz. *Yapıldı: GSE5814 = Jackson ve ark. 2006, PMID **16682560**, "Widespread siRNA off-target transcript silencing mediated by seed region sequence complementarity". (Birmingham 2006 Nat Methods 3:199 **başka** bir veri setidir.)* | A2 | her accession için doğrulanmış PMID + örnek sayısı | TODO |
| **A3** | Etiket tanımı: gen düzeyinde belirgin aşağı regülasyon, eşik önceden sabit (öneri `log2FC ≤ −0.3`). | A2b | §3'te eşik sayı olarak | TODO |
| **A4** | Metrik: **PR-AUC** (birincil) + ROC-AUC + ECDF/KS. ⚠️ Bu literatürde ROC-AUC standart değil — siSPOTR Spearman, SeedMatchR KS kullanıyor; tek metrik olarak AUC "olağan karşılaştırma" sayılmaz. CV: leave-one-siRNA-out. | A3 | §4'te metrik + CV şeması | TODO |
| **A5** | **Tabanlar — üçü de 3'UTR tanımlı:** (i) 3'UTR 7mer-m8 varlığı/sayısı, (ii) siSPOTR POTS, (iii) **transkript / 3'UTR uzunluğu tek başına**. ⚠️ (iii) kritik: denetim hit ile cDNA uzunluğu arasında **r = 0.349** buldu; uzun ve yüksek ifadeli transkriptler hem daha çok seed eşleşmesi hem daha güvenilir DE çağrısı alır. | A4 | §5'te üç taban tanımlı, bölge açıkça yazılı | TODO |
| **A6a** | **Kabul kriteri:** orcSONAR'ın PR-AUC'si her üç tabanı da leave-one-siRNA-out CV'de **ve uzunluk tabakaları içinde** aşmalı. Aşmazsa sonuç **negatif olarak** raporlanır (§0, üçüncü satır). | A5 | §6'da sayısal eşik | TODO |
| **A7** | **Skoru iki açık bileşene ayır — planın en önemli bilimsel kazancı.** `P_silence` = f(sequence_specificity, biophysics_structure, ifade/erişilebilirlik) → **doğrulanabilir**. `Impact` = g(variant_toxicity, execution_safety) → **gerçek referansı yok**, önceliklendirme katmanı olarak açıkça etiketlenir. ⚠️ **İki ayrı sütun olarak raporlanır.** Birleşik tek skor istenirse birleştirme kuralı ayrı bir ön kayıt maddesidir ve gerekçesi yazılır — çarpımsal form (`P × Impact`) kanıtsız bir etkileşim modeli varsayar. | A1 | §7'de ayrışma ve her bileşenin doğrulanabilirlik durumu yazılı | TODO |
| **A8** | **Detectability filtresi:** değerlendirme evreni "HeLa'da ölçülebilir düzeyde ifade edilen genler" (CCLE elde). İfade edilmeyen gen aşağı regüle olamaz; ön kayıtta olmazsa PR-AUC yapay şişer ve sonradan eklemek ihlal olur. | A3 | §8'de filtre tanımı + eşik | TODO |
| **A9** | **On-target ve ikincil etki dışlaması:** hedef genin kendisi ve bilinen doğrudan alt akışı pozitif sayılamaz. | A3 | §9'da dışlama listesi kuralı | TODO |
| **A10** | **`_clamp` yerine gelecek haritalamayı ön kayda yaz.** `alignment_score`'u [0,1]'e **nasıl** haritalayacağın bir modelleme kararıdır (min-max? teorik maksimuma bölme? yüzdelik?) ve sonucu gördükten sonra değiştirilemez. Bugünkü `_clamp` bir hata; yerine gelecek şey bir **karar**. | A4 | §10'da haritalama formülü | TODO |
| **A11** | **RNAa'nın yeri:** promoter/RNAa arama uzayı ikinci bir çıktı sütunu olarak **raporlanır ama doğrulanmaz** — her saRNA için promoter penceresine seed eşleşmesi hesaplanır, `validated: false` etiketiyle sunulur. `promoter_region.py` zaten var, iplik-farkında ve doğru, yalnız hiç okunmuyor. Maliyet ~0; projenin kimliğini korur, doğrulanmamış iddia üretmez. | A1 | §11'de yazılı | TODO |
| **A12** | Ön kaydı commit'le, hash'ini not et. Bundan sonraki her analiz bu hash'e atıf yapar. **Bu commit'ten sonra dosya kilitlidir** (`A2.6` hook'u). | A6a, A7–A11 | `git log -1 --format=%H docs/PRE_REGISTRATION.md` | TODO |

---

### FAZ B-HIZLI — doğruluk değişmezleri (2 gün, `E3a`'dan önce)

> Lokus-bağımlı kanalların onarımı buraya **girmez** — onlar `D2`'den sonra bir kez
> yapılır (B-sonra). Burada yalnız "yeni sayı üretmeden önce düzeltilmesi gereken"
> doğruluk değişmezleri var.

| id | iş | bağımlılık | kabul kriteri | durum |
|---|---|---|---|---|
| **B0** | **Cache'e `schema_version` + geçersizleme. ÖNCE BU.** `clinvar:%` anahtarları koordinat tabanlı; `B1` düzeltilse bile eski boş sonuç **30 gün** servis edilir ve düzeltmenin işe yaramadığı sanılır. | — | yeni sürüm eski anahtarları kullanmıyor (test) | TODO |
| **B1** | **ClinVar'ı canlandır** — `clinvar_client.py:134-138` literal `+AND+` gönderiyor, `requests` `%2B`'ye kodluyor. Canlı A/B: kodun biçimi **0**, doğrusu aynı pencerede **121 patojenik**. 15 dakika / 2 karakter. | B0 | >0 patojenik varyant; regresyon testi | TODO |
| **B2** | **Fallback'i *bilinmiyor* tipine çevir.** `_NEUTRAL_SIGNAL = 0.0` → açık sentinel. ⚠️ Sentinel'i 0.5 yapmak **yetmez**: sabit ham-sinyal uzayında, 0.5 sözleşmesi skor uzayında (AUDIT.md Bulgu-10). | — | hiçbir fallback yolu sayısal risk değeri dönmüyor | TODO |
| **B4** | **gnomAD işaretini düzelt** — üretici "korunmuş = 1.0 = yüksek risk", tüketici `variant_merger.py:36-38` `1.0 - skor` ile tersliyor. | — | işaret testi: korunmuş > polimorfik | TODO |
| **B10a** | **İki gerçek mypy hatasını düzelt** (geri kalan 72 değil): `shape_profile.py:300-301` `max()`/`min()` çağrısı `int \| None` üzerinde ve üstündeki `type: ignore[arg-type]` mypy'nin bildirdiği kodu bile kapsamıyor; `transcriptome_fetcher.py:258-267` `None` koordinatı `TranscriptInfo`'ya verebiliyor → ValidationError → `seed_aligner`'ın **sessiz düşürme** yoluna gidiyor. ⚠️ İkincisi `D1`'de 250k transkriptle **ölçeklenerek** sessiz kayıp üretir. | — | iki hata kapandı, regresyon testi var | TODO |
| **B11** | **CI kur** — `pytest` + `ruff check src/` bloke edici; `mypy` **bilgilendirici (non-blocking)**; null kapısı (`E1`) eklendiğinde bloke edici. ⚠️ `B10`'a bağlı **değil**. | B10a | CI yeşil ve zorunlu | TODO |

---

### FAZ C — İddia 1'in ölçtüğü kanalları çalışır hale getir (1-1,5 hafta)

| id | iş | bağımlılık | kabul kriteri | durum |
|---|---|---|---|---|
| **C1** | **`_clamp`'i düzelt — gün 1-2.** Ham seed skorları 41 sitede **12 ayrık değer** taşıyor (8.0, 8.5 … 14.5) ve sabit `1.0`'a eziliyor. Bu, bugün projede **koordinat hatasından etkilenmeyen, site bazında gerçekten farklılaşan ve gerçek referansla doğrudan karşılaştırılabilir tek kanal** — ve İddia 1'in ölçtüğü şeyin ta kendisi. Haritalama `A10`'dan gelir. | A10 | `sequence_specificity` 41/41 sabit değil; `A10`'daki formül uygulandı | TODO |
| **C0** | **3'UTR / CDS / 5'UTR bölge anotasyonu.** Her siteye `region_class ∈ {5utr, cds, 3utr}`. ⚠️ **Doğrulandı: bölge farkındalığı bugün sıfır** (`grep -riE "utr\|cds_start" src/` → gerçek isabet yok). Tabanların hepsi literatürde 3'UTR tanımlı; bu olmadan `E3a` savunulamaz. GENCODE GTF `CDS`/`UTR` özelliklerini zaten taşıyor → `D0` indirildiğinde neredeyse bedava (Faz D tasarrufunun **üçüncü yüzü**). | D0 | her sitede `region_class` var | TODO |
| **C0b** | **İki ipliği de tara.** Her siteye `strand_origin ∈ {guide, passenger}`. ⚠️ **Doğrulandı: `seed_aligner.py:198` yalnız `reverse_complement(seed)` indeksliyor.** GSE5814 gibi bir sette pasajer-iplik off-target'ları **etikette mevcut**; tek iplik tarayan tahminci onları tanım gereği göremez → PR-AUC tavanı 1'in altında ve sebebi skor kalitesi değil. Maliyet: `run_seed_scan`'i ikinci dizi ile bir kez daha çağırmak. | — | her sitede `strand_origin`; iki iplik de taranıyor | TODO |
| **C3** | **ΔG'yi PAKET olarak düzelt** — hizalama + hedef + eşik **birlikte**. `delta_g_calculator.py:79-82` fazladan `reversed()` yüzünden 18/20 "mismatch" → 41/41 site aynı **+31.10**. Hizalamayı tek başına düzeltirsen **−43.80** çıkar ve `≤ −30` eşiğiyle tüm siteler 1.0'a fırlar. ⚠️ **`C2`'ye bağlı DEĞİL ve Faz D'yi beklemiyor:** `tx_start`/`tx_end` payload'da mevcut (`"tx_start": 7093, "tx_end": 7113`), hedef dizi cache'li cDNA'dan dilimlenebilir. Temiz varyant: stage 2 ayrıca 20-nt `target_window` emit etsin (~3 satır). Tamamen dizi-hesaplı → `E3a`'ya dahil. | — | ΔG negatif, siteler arası varyans > 0, hiçbir site 1.0'a saplanmıyor | TODO |
| **C4** | **Çift sayımı kaldır** — epigenetik ve execution sinyalleri hem `base_score`'a hem `cell_modifier`'a giriyor. `apply_cell_modifier()` `scoring_weights`'i hiç okumuyor; `0.40/0.40/0.20` ve `0.30 + 1.40×` hardcoded. `A7` ayrışmasının doğal sonucu. | A7 | `config.yaml` ağırlığını değiştirmek skoru öngörülen oranda değiştiriyor | TODO |

---

### FAZ D — GENCODE geçişi (5-7 hafta)

> **Tasarruf kararı:** Bulgu-6 (183 gen), Bulgu-8 (splice-körlüğü) ve `C0` (bölge
> anotasyonu) **aynı işin üç yüzü** — GENCODE GTF ekzon bloklarını *ve* CDS/UTR
> özelliklerini zaten taşıyor.
> **Ama tek commit değil, iki checkpoint:** `D1` bittiğinde ana ağaca merge edilebilir
> bir durak olmalı (indeks çalışıyor, koordinatlar hâlâ eski ve işaretli). Aksi halde
> İddia 1 gereksiz yere `D2`/`D4`'ü bekler. `isolation: worktree` önerilir.

| id | iş | bağımlılık | kabul kriteri | durum |
|---|---|---|---|---|
| **D0** | GENCODE sürümünü seç ve indir (GTF + transkript FASTA) → **`data/external/`** (bkz. değişmez 1; `data/` sandbox'ı bu dizini dışarıda bırakır). | — | sürüm + checksum `docs/DATA_SOURCES.md`'de | TODO |
| **D1** | **Yerel seed indeksi** (~250k transkript) — **checkpoint 1, merge edilebilir.** Mevcut `_BACKGROUND_GENES` 183 gen (iki docstring "~250 genes" diyor, o da yanlış). Geçerlilik itirazının kökü: 41 hit'in geldiği 29 genin **tamamı** listeden; zenginleşme biyolojiden değil **transkript uzunluğundan** (r = 0.349, medyan cDNA 5.326 vs 2.828 nt). | D0 | 183-gen listesi kodda yok; tarama tam transkriptom üzerinde | TODO |
| **D2** | **Ekzon yapısı + cDNA→genomik yürüyüş** — checkpoint 2. *Ölçüm: medyan sapma **30.732 bp**, maks 182.707 (EGFR), 39/41 site >1 kb; "doğru" çıkan 2 site retained-intron izoformu.* Pencereler sistematik olarak **intron içine** düşüyor → korunmasız, mutasyon-seyrek, kapalı kromatin → **risk sistematik olarak küçümseniyor.** | D1 | ekzon-farkında koordinatlar; `D3` sayıları tutuyor | TODO |
| **D3** | **Yeniden koş ve doğrula.** Beklenen: COSMIC 31→**350**, phyloP ort. 0.027→**0.418**, phyloP>2 site 0→**16**, m6A 0→**10**. | D2, D5 | ölçülen değerler bu mertebelerde | TODO |
| **D5** | **Toplu/yerel anotasyon mimarisi — planın eksik maliyeti.** Site-başına uzak sorgu → yerel, indeksli, önceden materyalize edilmiş anotasyon deposu (BigWig aralık çıkarımı tek seferde; COSMIC/gnomAD/ClinVar bölgesel dökümü yerel tabix/parquet; interval-tree aralık sorgusu). ⚠️ **Aritmetik:** 4⁷ = 16.384 nt'de bir rastgele 7-mer → ~450 Mb GENCODE cDNA'da **~24.000 site/koşu**. Yalnız gnomAD (1 req/s) tek koşuda **6,7 saat**; `E3b` için 100-150 siRNA → **2-4 milyon site-anotasyonu**. **Bu madde olmadan `E3b` koşamaz.** | D1 | tam koşu site-başına uzak sorgu yapmıyor; 24k site < 1 saat | TODO |
| **D4** | **Eşikleri yeniden kalibre et.** `max_mismatches: 12` şu an **hiçbir adayı elemiyor** (≤12→41, ≤8→28, ≤6→7, ≤4→0, ≤3→0); modül docstring'i "max 3" diyor, 3 olsaydı çıktı boş olurdu. (Not: `core/config.py:82` varsayılanı 3 ama `rules/stage2_offtarget.smk:16` configfile'dan 12 alıyor — iki paralel config yolu.) | D3 | eşik gerekçesi + hassasiyet analizi | TODO |
| **C2** | **Satürasyon sabitlerini veriden türet.** ⚠️ **`D3`'ten ÖNCE YAPILAMAZ.** Faz D'den önceki dağılımlar **intron içinden** ölçülmüştür; sabitleri onlardan türetmek **koordinat hatasını kalibrasyona gömer** ve `D3`'ün doğrulamasını kendi kendini doğrulayan hale getirir — değişmez 7 ihlali. *(`hic_contact` CEBPA_HepG2'de 16.226× SAT.)* | D3 | satüre site oranı hiçbir ham sinyalde >%50 değil | TODO |

---

### FAZ B-SONRA — lokus-bağımlı kanallar (Faz D sonrası)

> Bunlar `D2`'den önce onarılırsa, lokuslar değişince hepsi yeniden koşulup yeniden
> yorumlanmak zorunda kalır. Doğru lokusların olduğu ilk anda bir kez yapılır.

| id | iş | bağımlılık | kabul kriteri | durum |
|---|---|---|---|---|
| **B3** | **`provenance` + `coverage` her siteye.** Skorun kaçta kaçı gerçek ölçümden geliyor; `coverage` eşiğin altındaysa **skor üretmeyi reddet.** Bilimsel aleti prototipten ayıran şey budur. Ayrıca `/verify-run` check 4'ün ham `0.0`'ı "ölü kaynak" ile "gerçekten sessiz lokus"tan ayırabilmesi buna bağlı. | B2, D3 | her sitede `provenance` + `coverage`; eşik altı `null` skor + gerekçe | TODO |
| **B5** | **Hi-C anchor'ı promotere bağla** — `hic_fetcher.py:44-47` `regions[0]` kullanıyor (köşegen bin). `promoter_region` tüm repoda hiç okunmuyor. *VEGFA_HeLa'da `hic_contact` 41 sitenin 34'ünde `0.0`.* | D3 | anchor `promoter_region`; temaslar köşegen dışı | TODO |
| **B6** | **`cell_modifier`'ı site-başına yap** — `epigenetic_merger.py:137-147` tüm sitelerin ortalamasını üretiyor, `risk_classifier.py:73` aynı sözlüğü herkese veriyor → koşu başına **tek sabit çarpan** (`final/base` 6. haneye kadar sabit; Spearman(base,final) = 1.000000 4/4 koşuda). Monoton sabit çarpan sıralamayı değiştiremez. | D3 | aynı koşuda ≥2 farklı çarpan; Spearman < 1.0 | TODO |
| **B8** | **Ölü `domain_scores.py`'ı sil.** ⚠️ **Önce 44 testin davranışsal niyetini üretim yoluna aktar** — o testler projedeki tek yerde yazılı niyeti taşıyor (H3K27me3 yönü, RBP işareti, satürasyon sabitleri). Değişmez 5 gereği yeni testlerin önce kırmızı olduğu gösterilir, sonra modül silinir. | D3 | `git grep domain_scores src/` boş; niyet testleri üretim yoluna karşı yeşil | TODO |
| **B9** | **AGO2 accession'larını düzelt** — K562 ENCFF426YFB = shRNA-KD RNA-seq, HepG2 ENCFF097LEQ = ChIP-seq; **ikisi de eCLIP değil**. HeLa'da zaten `null` (8 hattın 6'sında null). | D3 | accession'lar gerçekten AGO2 eCLIP | TODO |
| **B10** | mypy strict'i sıfıra indir (72 hata, 39'u eksik generic), sonra CI'da bloke ediciye çevir. | B11 | `mypy src/` 0 hata | TODO |
| **G0** | **API yanıtlarını dondur** — tüm uzak kaynakların versiyonlu snapshot'ı + checksum. ⚠️ **`G-VI` bugünkü haliyle yapısal olarak geçilemez:** Stage 7 tekrarlanabilir olsa da Stage 2-6 canlı API'lere bağlı. | D5 | taze makinede aynı snapshot ile aynı sayılar | TODO |
| **H1** | **Run manifest** — her koşu çıktısına git SHA, config hash, kaynak sürümleri, seed'ler. *Dört mevcut koşunun "eski iki-parçalı site_id" formatında olduğu elle keşfedildi; manifest bunu otomatik yapardı.* | — | her `results/*/` altında `manifest.json` | TODO |

---

### FAZ E — Doğrulama

| id | iş | bağımlılık | kabul kriteri | durum |
|---|---|---|---|---|
| **E1** | **Null kapısını kalıcı hale getir** — 16.384 7-mer ampirik null. *Ölçüm: gözlenen 42 hit vs beklenen 52.7 (%47.4 yüzdelik, ortalamanın **altında**); BH-FDR sonrası **0/41** anlamlı.* | B11 | CI'da koşuyor, p-değeri raporlanıyor | TODO |
| **E2** | **Scrambled saRNA negatif kontrolü** — aynı boru hattı rastgele dizilerle. Veri gerektirmeyen en ucuz adım. | E1 | skor dağılımı karşılaştırması | TODO |
| **E0** | **GEO veri mühendisliği** — 6 seriyi indir, normalize et, prob→Ensembl gen eşlemesi, replikatlar, log2FC matrisi. ⚠️ Plan bunu "accession kilitle" sanıyordu; gerçekte **3-5 günlük ayrı iş** ve `E3a`'nın gerçek ön koşulu. | A12 | log2FC matrisi + eşleme raporu | TODO |
| **E0b** | **siSPOTR POTS tabanını uygula** — 3'UTR seed frekans tablosu. Taban kendiliğinden gelmiyor, kurulması gereken bir araç. | C0 | POTS skoru hesaplanıyor, referans değerlerle doğrulandı | TODO |
| **E3a** | **ANA DENEY — seed katmanı, gen düzeyi, koordinatsız.** Girdi: `P_silence` bileşenleri (`sequence_specificity` + ΔG + `region_class` + `strand_origin`). Tabanlar: üçü de (`A5`). CV: leave-one-siRNA-out. ⚠️ Tamamen dizi-hesaplı — **hiçbir API çağrısı yok**, `D5`'i beklemez. | A12, C1, C3, C0, C0b, D1, E0, E0b, E1 | `A6a` kriteri karşılandı **veya** negatif sonuç açıkça raporlandı | TODO |
| **E4a** | **ABLASYON (seed + ΔG).** Hangi bileşen ne kadar katkı veriyor? ⚠️ Bu, yayının **asıl bilimsel çekirdeği.** *Ölçüm: nominal 1.00 ağırlığın %35'inden azı gerçek bilgi taşıyor.* Varyans payı tablosu bu maddenin kabul kriterinin parçası. | E3a | bileşen bazlı katkı + varyans payı tablosu | TODO |
| **E3b** | **Tam bileşik skor** (`P_silence` + `Impact`, tüm kanallar canlı, doğru lokuslar). | E3a, D4, C4, D5 | raporlandı; `Impact` sütunu `validated: false` | TODO |
| **E4b** | **Tam ablasyon** — çok-omik katman seed katmanının üstüne bilgi ekliyor mu? | E3b | domain bazlı katkı tablosu | TODO |
| **B7** | **ADAR + H3K27me3 kanallarını bağla.** ⚠️ **`E4b`'den sonra.** Hiçbir mevcut kanalın bilgi taşıdığı gösterilmemişken yeni kanal eklemek ölü ağırlığa ölü ağırlık eklemektir. Kabul kriteri: `E4b` tablosunda epigenetik domain sıfırdan farklı katkı gösterdi. Yön kararı `A1`'e bağlı. | E4b | `stage4_histones.json`'da `h3k27me3_signals` | TODO |
| **E5** | **Ortogonal kanıt — AGO2 eCLIP** (K562 ENCSR048YXG, HeLa E-MTAB-12944). HepG2 için AGO2 eCLIP yok. | D3, B9 | zenginleşme testi | TODO |

---

### FAZ F — Kalibrasyon ve dürüst sınırlar (2 hafta)

| id | iş | bağımlılık | kabul kriteri | durum |
|---|---|---|---|---|
| **F1** | **Risk sınıfı eşiklerini `E3b`'nin eğrisinden türet.** ⚠️ **`B2` ve `D2` bitmeden kalibre etme** — aksi halde ölü kanalları telafi etmek için eşik indirmiş olursun, ki bu değişmez 7'nin ihlali ve bir risk aracında en tehlikeli hamledir. *Düzeltilmiş ölçüm: gözlenen çarpan 0.707–0.809; HIGH_RISK için gereken base 0.741–0.848, base tavanı 0.836 (biyofizik bugünkü tavanıyla) → **HIGH_RISK erişilebilir ama ulaşılmamış**; DANGEROUS için 1.05 gerekiyor → **erişilemez**. Erişilememenin kök nedeni `_ATAC_SAT` değil (SAT'ı 50× düşürmek eşiği yalnız 0.789→0.728 indiriyor), **`_NEUTRAL_SIGNAL = 0.0` + intronik lokuslar**.* | E3b, B2, D2 | eşikler veriden; her sınıf erişilebilir | TODO |
| **F3** | **Belirsizlik raporlama** — `B3`'ün `coverage` alanı üstüne güven/tahmin aralığı. | B3, E3b | her tahmin yanında belirsizlik | TODO |
| **F4** | **`docs/METHODS.md`** — hakem okuyacak düzeyde. `docs/` şu an yalnız `DATA_SOURCES.md` içeriyor. | F1 | her aşama, sabit ve eşik gerekçeli | TODO |
| **F5** | **`docs/LIMITATIONS.md`** — İddia 2 ve İddia 3'ün doğrulanamadığı, hangi veriyle doğrulanabileceği, hangi kaynakların ölü/vekil olduğu. §5 tablosu buraya taşınır. | F4 | her satır ölçümlü | TODO |

---

### FAZ G — Yayın

| id | iş | bağımlılık | durum |
|---|---|---|---|
| **G1** | Preprint (bioRxiv), ön kayıt hash'ine atıfla; venue §0'ın koşullu tablosundan | F5 | TODO |
| **G2** | Zenodo DOI + tam tekrarlanabilirlik paketi (`G0` snapshot'ları, sürümler, checksum'lar, seed'ler) | G1 | TODO |
| **G3** | Dergi gönderimi | G2 | TODO |
| **E6** | *(madde değil)* GSE42024 (MCF7/HIC-1) — n=3v3, tek saRNA. **Metrik iddiası olmayan tek paragraf + tek şekil olarak Tartışma'ya.** Ayrı yol haritası maddesi değil; hakeme "asıl mekanizmayı neden doğrulamadınız" sorusunu davet ediyor. | G1 | — |

---

## 4. ÜÇ AYLIK MİNİMUM SAVUNULABİLİR YAYIN

Tam kapsam **4,5-6 ay**. Üç ayda savunulabilir bir preprint ancak kapsamı keserek:

```
İÇERİDE:   A (tamamı) → B-hızlı → C1, C3, C0, C0b → D0, D1
           → E0, E0b, E1, E2, E3a, E4a → F4, F5, G1

DIŞARIDA (ikinci yayın):
           D2, D3, D4, D5, C2, B-sonra (B3/B5/B6/B8/B9/B10/G0),
           E3b, E4b, E5, B7, F1, F3, İddia 2'nin tamamı
```

Bu kapsam **tek bir yanlışlanabilir iddiayı** (İddia 1) gerçekten kapatır.
Kapsam kesilmezse üç ayda **hiçbir** iddia kapanmaz.

**Prensip: en ucuz yanlışlama önce.** Gerçek referansa karşı ilk sayı **3. haftada**
alınabilir. Seed katmanı 3'UTR tabanlarını geçmiyorsa, 24 kanalı onarmak için
harcanacak haftalar zaten yanlış yatırımdı — ve bunu baştan öğrenirsin.

---

## 5. "BİLİMSEL" TANIMI — dokuz kapı

Hepsi geçilmeli; sekizi geçip biri kalırsa proje bilimsel **değildir**, kısmi puan yok.

| kapı | soru | nasıl ölçülür | şu an |
|---|---|---|---|
| G-I | Yanlışlanabilir, ön kayıtlı iddia var mı? | `docs/PRE_REGISTRATION.md` commit'li, metrik + eşik sayı olarak | ✗ |
| G-II | Gerçek referansa karşı test edildi mi? | `E3a` koşmuş, sonuç raporlanmış (pozitif **veya** negatif) | ✗ |
| G-III | Tabanı geçiyor mu **yoksa geçmediğini söylüyor mu**? | `E4a`/`E4b` ablasyon tablosu | ✗ |
| G-IV | Bilmediğini biliyor mu? | `B3` `coverage` + `F3`; eşik altı skor **üretilmiyor** | ✗ |
| G-V | Sabitler veriden mi — **ve doğrulanmış koordinatlardan mı**? | `C2` (`D3` sonrası) + `F1`; hiçbir sihirli sayı gerekçesiz değil | ✗ |
| G-VI | Bit düzeyinde tekrarlanabilir mi? | **`G0`** snapshot'ları + `H1` manifest; taze makinede aynı sayılar | ✗ |
| **G-VII** | **İnşa geçerliliği:** skorladığım şey, etiketin ölçtüğü şey mi? | `A7` ayrışması yapılmış; `E3a` yalnız `P_silence`'ı test ediyor | ✗ |
| **G-VIII** | **Arıza yönü:** her kanalın işaret testi var mı; veri yokluğu riski düşürüyor mu? | Her veri kanalı için işaret/monotonluk testi CI'da; "veri yok → sayı dönmüyor" testi | ✗ |
| **G-IX** | **Test edilen kod = sevk edilen kod** | 32 `run()` adaptörünün kapsaması >0; ölü modüle karşı test yok | ✗ |

> **G-VIII neden kapı:** denetimin bulduğu en tekrarlayan hata sınıfı **işaret/yön**
> hatası (gnomAD tersine, fallback güvenli yöne, Hi-C köşegene, mirbase istisnası "SAFE").
> Bu bir kerelik düzeltme değil, kalıcı bir sınıf.
> **G-IX neden kapı:** `test_h3k27me3_represses_active_histones` yeşil geçerken sıfır
> üretim etkisi var.

### Fayda ölçütü — kapı DEĞİL, ayrı

Dokuz kapı geçilince proje **bilimsel** olur; **faydalı olduğu gösterilmiş olmaz.**

> *orcSONAR, 3'UTR 7mer-m8 ve siSPOTR POTS tabanlarını leave-one-siRNA-out CV'de PR-AUC
> olarak **ve uzunluk tabakaları içinde** aşarsa **faydalıdır**; aşmazsa **bilimsel ama
> faydasızdır** ve yayın bir benchmark/negatif sonuç makalesidir (§0, üçüncü satır).*

Bu ayrım G-III'ün dürüstlüğünü korurken kendini kandırma riskini kaldırır.

---

## 6. ASLA YAZILMAYACAKLAR (kapı geçilene kadar)

| iddia | neden yazılamaz | hangi madde açar |
|---|---|---|
| "hücre hattına özgü risk tahmini" | koşu başına tek sabit çarpan; sıralamayı değiştiremiyor | `B6` (+ doğrulama için veri yok → `F5`'te sınır) |
| "saRNA **RNAa** off-target aracı" | arama uzayı promotersiz olgun mRNA (`type="cdna"`) | `A1` + `A11` (`validated: false` sütun) |
| herhangi bir **bulgu** cümlesi ("RISC makinesini riskli buldu") | 183-gen listesi × transkript uzunluğu artefaktı (r = 0.349) | `D1` + `A5`(iii) uzunluk tabanı |
| "termodinamik değerlendirme yapıyor" | 41/41 site aynı +31.10 | `C3` |
| "ClinVar / patojenik varyant entegrasyonu" | 119 site / 4 koşu → 0 varyant | `B1` |
| "graceful degradation" | fallback "güvenli" yönüne arızalanıyor | `B2` |
| "bölge-farkında seed analizi" | `region_class` yok, bölge farkındalığı **sıfır** | `C0` |
| "her iki iplik değerlendiriliyor" | yalnız `reverse_complement(seed)` indeksleniyor | `C0b` |
| herhangi bir doğruluk/performans sayısı | hiç ölçülmedi | `E3a` |

---

## 7. Yol haritası dışında, zaten yapılanlar

- **`fix(verify-run)`** — check 4 ölüydü (yalnız `0.5` nöbetçisini sayıyordu; gerçek
  nöbetçi `0.0`). Artık iki nöbetçiyi ayrı sayıyor; VEGFA_HeLa'da **7 yeni bulgu**
  (`hic_contact` %82.9, `groseq_signal` %78.0, `ago2`/`rbp` `raw_signal` %100). Yanlış
  `0.5` iddiası beş yerden temizlendi. `--json` düzeltildi. Check 6 commit'lendi.
  `AUDIT.md` worktree'ye geri alındı.
- **`chore(ruff)`** — 71 lint hatası; 6 `zip()`'e `strict=True` (hiçbiri aktif hata
  değildi, doğrulandı); 2 sessiz `except: pass` loglamaya çevrildi; mypy kuruldu ve ilk
  kez ölçüldü (72 hata → `B10a`/`B10`); ajanlara `omitClaudeMd: true`.
- **Plan denetimi (Fable 5.2, 2026-11-17)** — 30 öneri; 27'si koşulsuz, 3'ü
  değiştirilerek kabul edildi. Adjudikasyon:
  `/home/koray/orcSONAR-denetim/PLAN_REVIZYON_TASLAGI.md`.
