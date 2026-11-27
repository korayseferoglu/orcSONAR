# Ön kayıt — orcSONAR

> **değişmez 6: bu dosya commit'lendikten sonra DÜZENLENMEZ.**
> Değişiklik gerekiyorsa `docs/PRE_REGISTRATION_v2.md` açılır ve yayında
> **ikisi de** raporlanır. Bir metriği ya da eşiği sonucu gördükten sonra
> değiştirmek bu projenin en sinsi ihlali olur — üç ay sonra kimsenin
> farketmeyeceği bir commit.

Tarih: 2026-11-27 · Yol haritası maddesi: A12 · Commit: <bu dosyayı kilitleyen sha>

## 1. Hipotez

**Modellenen mekanizma, bir saRNA dupleksinin *her iki ipliğinin* 5′ ucundan
2–8. pozisyondaki seed'ine 3′UTR'sinde komplementerlik taşıyan transkriptlerin
siRNA-benzeri, seed-aracılı aşağı regülasyonudur.**

Hipotez, işaretli ve yanlışlanabilir hali: **bir transkriptin 3′UTR'sinde
saRNA'nın iki ipliğinden herhangi birinin seed'ine komplementer eşleşme sayısı
arttıkça, o transkriptin ölçülebilir aşağı regülasyon olasılığı artar.** Azalma
yönünde bir ilişki ya da ilişkisizlik, hipotezin reddi sayılır.

### Neden "her iki iplik" — ve bu kararın maliyeti

Bu bir kolaylık değil, tavan kararı. Referans setindeki pozitifler pasajer
ipliğin yol açtığı susturmaları da içeriyorsa, yalnız guide ipliğini modelleyen
bir tahminci onları **tanım gereği göremez** ve PR-AUC tavanı 1'in altına iner;
düşük skorun sebebi model kalitesi değil, kapsam olur. Bugünkü kod tek iplik
tarıyor (`seed_aligner.py` yalnız `reverse_complement(seed)` indeksliyor) —
yol haritası `C0b` bu boşluğu kapatan madde, ve bu ön kayıt onu **gereklilik**
olarak sabitler.

Dayanak, ve sınırı:

- Seed-aracılı, transkriptom ölçeğinde off-target susturma HeLa mikroarray'inde
  kurulmuş bir olgu: seed'e komplementer diziler bakımından zenginleşme var, ve
  **seed mutasyona uğratılınca yeni seed'e uyan yeni bir off-target imzası**
  doğuyor — yani ilişki nedensel yönde sınanmış
  ([**Jackson** ve ark., *RNA* 12(7):1179-1187, 2006, **PMID 16682560**](https://rnajournal.cshlp.org/content/12/7/1179.full)),
  ve bu çalışmanın verisi §6'da kilitlenen `GSE5814`'ün kendisi — yani
  mekanizma kararı ile değerlendirme seti aynı deneyden geliyor.
  Bağımsız bir ikinci dayanak, **farklı** bir çalışma:
  [Birmingham ve ark., *Nat Methods* 3(3):199-204, 2006, PMID 16489337](https://pubmed.ncbi.nlm.nih.gov/16489337/)
  — *"3′ UTR seed matches, but not overall identity, are associated with RNAi
  off-targets"*.
  ⚠️ **Bu satır 2026-11-27'de düzeltildi:** ilk hali bu iddiayı *"Birmingham
  ve ark., RNA 2006"* diye yazıp Jackson'ın makalesine link veriyordu. Künye
  ölçüldü: o URL `RNA` 12(7):1179'dur ve **Jackson**'dır; Birmingham *Nat
  Methods*'tadır; `RNA` 12(7)'nin diğer makalesi Fedorov ve ark. 1188-1196
  (PMID 16682561), **başka** bir iddia (toksik fenotip). Üçü karıştırılması
  kolay ve `A2b` satırı tam bu tuzağa karşı yazılmıştı; PMID'ler bu yüzden
  artık metnin içinde.
- Seed'in tanımı literatürde zaten **iplik-agnostik**: "her iki siRNA ipliğinin
  5′ ucundan 2–8. pozisyonu"
  ([Chemical modification of the siRNA seed region, *ACS Omega* 2017](https://pubs.acs.org/doi/full/10.1021/acsomega.7b00291)).
- Pasajer-iplik off-target'ı mikroarray'de **gözlenmiş** ve fosforotiyoat
  modifikasyonuyla güçlenmiş (aynı kaynak). ⚠️ **Ama kanıt ince:** bu tek bir
  çalışma, ve alanın çoğu "off-target" terimini kasıtlı olarak yalnız guide
  ipliğine indiriyor. Yani "her iki iplik" kararı **ihtiyatlı** olduğu için
  seçildi (kapsamı daraltmak tavanı düşürür, genişletmek düşürmez), bir pasajer
  katkısının büyük olduğu iddiasına dayandığı için değil.
- saRNA (RNAa) tarafında nicel bir off-target eşiği yok; alan mismatch sayımıyla
  tarıyor (bkz. yol haritası `C3`'ün literatür notu). Bu yüzden mekanizma siRNA
  literatüründen ödünç alınıyor ve bu **açıkça** bir dış-geçerlilik varsayımı:
  saRNA dupleksinin RISC'e yüklenen ipliği, siRNA gibi seed-aracılı susturma
  yapar. §10'da keşifsel olarak işaretli.

## 2. Birincil metrik

<Tek metrik. Birden fazla yazmak, sonradan geçeni seçmek demektir.>

Nasıl hesaplanacağı: <formül ya da fonksiyon adı, belirsizlik bırakmadan>

## 3. İkincil metrikler

<Varsa listele. Birincil olanla yer değiştiremezler.>

## 4. Eşikler ve karar kuralı

### 4.1 Etiket tanımı — bir genin "off-target" sayılması

**Birincil etiket:** `PVALUE < 0.01` **ve** `VALUE < 0`, §6.3'ün ifade
evreninde, her array için ayrı ayrı.

**Neden bu, ve neden bir kat-değişim eşiği DEĞİL.** Kaynak makalelerin üçü de
tam bunu kullanıyor ve kat-değişime **hiç** kesim koymuyor. Jackson ve ark.
2006a (PMID 16682560) yöntem bölümünde kelimesi kelimesine: *"Data shown are
signature genes that display a difference in expression level (p < 0.01)
relative to mock-transfected cells. **No cuts were placed on fold change in
expression.**"* Aynı cümle 2006b'de (PMID 16682562) de var; Schwarz ve ark.
(PMID 16965178) *"(p < 0.01, in one or two experiments…)"* diyor. Testin
kendisi Rosetta Resolver prob-başına hata modeli (Hughes ve ark. 2001,
PMID 11283592) ve **GEO kaydında `PVALUE` kolonu olarak zaten geliyor** — yani
bu projenin ~161 array'inin 147'si için sahip olacağı **tek** gen-başına hata
modeli. Bir çıplak kat-değişim eşiği onu çöpe atıp yerine ayarlanması gereken
bir serbest parametre koyardı.

🔬 **Ve ölçüm kararı serbest parametresiz hale getiriyor.** Altı array'de
(üç seri, üç platform) `{p<0.01 ve aşağı}` ile
`{p<0.01 ve log2FC ≤ −0.3}` **birebir aynı prob kümesini** veriyor
(640/640, 307/307, 367/367, 575/575, 509/509, 280/280), çünkü `p<0.01`'e
ulaşan **en zayıf** düşüş zaten **−0.382 … −0.394 log2** aralığında. Yani
`p<0.01` kat-değişim eşiğini *ima ediyor*; ikisini birlikte yazmak hem
kaynak makalelerin ölçütünü hem siSPOTR'ın eşiğini hem MAQC'nin
"kat-değişim + sıkı olmayan bir P" doktrinini **ayarlama yapmadan**
karşılıyor. ⚠️ Bu denklik 6 array'de ölçüldü, ~161'inde değil; `E0` ölçeğe
çıktığında bozulursa birincil ölçüt kararı **yeniden açılır** ve bu satır onu
şimdiden söylüyor.

### 4.2 Ölçek, yön ve dönüşüm — sayıdan önce gelen şey

🔴 **Eşik yazmadan önce ölçeği yazmak zorunlu, çünkü bu sette iki farklı
"−0.3" var ve ikisi farklı log tabanında.** siSPOTR'ın `−0.3`'ü **log2**
(1,23 kat); Anderson 2008'in (PMID 18367722) `−0.3`'ü **log10**, ve o
kelimesi kelimesine *"down-regulated by **twofold or more** (log ratio more
negative than −0.3)"* diyor.

Ölçülmüş olgular (GEO kayıtlarından, 2026-11-27):

- `GSE5814`, `GSE5769`: `#VALUE = Corrected (normalized) **Log10** Ratio of
  channels (CH2/CH1)`
- `GSE5291`: `#VALUE = MLRATIO: Averaged **log10** ratio
  [log10(CHANNEL1/CHANNEL2), error weighted]`
- Dönüşüm sabiti: **`log2FC = VALUE × 3.321928`**
- Yön: `GSE5814`/`GSE5769` ch1=mock, ch2=işlem; `GSE5291` **ch1=işlem,
  ch2=mock** *ve* oranı ters. **İki ters çevirme birbirini götürüyor**, üçü de
  `log10(işlem/mock)`, yani negatif = aşağı regülasyon. ⚠️ Yönü **yalnız**
  `VALUE` dizgisinden ya da **yalnız** `characteristics` alanından okuyan biri
  `GSE5291`'in işaretini ters çevirir — **iki alan birlikte** okunmak zorunda.

**Sayısal örnek, karışmasın diye:** `VALUE = −0.1150` →
`log2FC = −0.1150 × 3.321928 = −0.3820` → kat değişimi `2^−0.382 = 0.767`,
yani **%23 azalma**. Aynı `−0.3` sayısı dönüştürülmeden uygulanırsa
`log10 = −0.3` → `2 kat azalma` okunur. Ölçülen maliyet: aynı array'de
280 pozitif yerine **8** pozitif (35 kat), başka bir array'de 640 yerine 80.

### 4.3 Duyarlılık ızgarası — ilan edilmiş, ve birincil asla yeniden atanmaz

Tam ızgara **her zaman raporlanır**: log2FC ≤
`{−0.1, −0.2, −0.3, −0.4, −0.5, −0.75, −1.0}`, artı BH `q < 0.05`.
**Birincil hücre §4.1'dir ve ızgara görüldükten sonra yeniden atanmaz.**

⚠️ Bunun neden kuralla yazıldığı ölçülmüş: eşiği `−1.0`'dan `−0.1`'e
gevşetmek pozitif oranını ~%1'den ~%36'ya çıkarır ve **PR-AUC'yi mekanik
olarak yükseltir**. Bu, "ölü bir kanalı telafi etmek için eşik indirmek"
hamlesinin tam kendisi (değişmez 7), ve görünür kalmasının yolu her PR-AUC'nin
**kendi taban oranıyla ve `lift = PR-AUC / taban` olarak** raporlanması —
bu da ön kayıtlı bir zorunluluktur.

📌 **İlan edilmiş döngüsellik:** siSPOTR'ın `−0.3`'ü 0,05-log2 aralıklarını
tarayıp seed-vs-arka plan ayrımını maksimize eden aralığı **seçerek**
türetilmiş, ve eğitim verisi **`GSE5291` ve `GSE5769`** — yani bu projenin
kilitlediği setin ikisi. Dolayısıyla `−0.3` bu proje için **bağımsız bir eşik
değil**; ızgarada ilan edilmiş bir hücre olarak durur, gerekçe olarak değil.

### 4.4 Karar kuralı

Başarı eşiği `A6a`'da sayıyla yazılı (aynı bölüm). Eşiğin altı kalırsa sonuç
**negatif olarak** raporlanır; planı §9'da (`A15`).

## 5. Null modeli

<Gözlemi neyle karşılaştırıyorsun? Permütasyon, ampirik null, eşleştirilmiş
kontrol kümesi — ve kaç tekrar. Null yoksa hipotez test edilemez.>

Çoklu test düzeltmesi: <yöntem, örn. BH-FDR; ve q eşiği>

## 6. Örneklem ve veri

### 6.1 Gerçek referans seti — kilitlenen accession'lar

Aşağıdaki her sayı **2026-11-27'de GEO SOFT kayıtlarından sayıldı**, yayından
ya da yol haritasından alıntılanmadı. Sebebi somut: yol haritası `GSE5814`'ü
*"68 örnek, HeLa"* diye tarif ediyordu; ölçüm 67 HeLa **artı bir HT29**
örneği ve **üç ayrı platform** gösterdi. Kilitlenen bir belgeye alıntı
girmez.

| accession | örnek | platform(lar) | hücre hattı | PMID | tasarım |
|---|---|---|---|---|---|
| `GSE5814` | 68 | GPL3992 (47), GPL2029 (20), GPL3991 (1) | 67 HeLa + 1 HT29 | 16682560 | **Ana set.** `193-MAPK14` guide'ının **1-19. pozisyonlarında tek nükleotid mutantları** (pozisyon başına bir kol) + mutasyonsuz hali; ayrıca `Luc`, `PLK1-319`, `1721-PLK-772` |
| `GSE5769` | 61 | GPL3992 (38), GPL3991 (23) | 61 HeLa | 16682562 | **Yedi ayrı ebeveyn dizi** (`PIK3CA-2629`, `MPHOSPH1-2692`, `SOS1-1582`, `PRKCE-1295`, `VHL-2651`, `VHL-2652`, `193-MAPK14`), her biri **modifiye edilmemiş** ve **AS_pos2_modified** halinde, `a`/`b` tekrarıyla |
| `GSE5291` | 18 | GPL3992 | 18 HeLa | 16965178 | `SOD1` tek-nükleotid ayrımı (tek nükleotidle farklılaşan dizi çiftleri) |
| `GSE41924` | 3 | GPL6947 | HeLa (⚠️ örnek *başlıklarında* yok; `source_name = "HeLa cells"` ve `characteristics = "cell line: HeLa cervical cancer cell line"` alanlarından doğrulandı — `A2b`) | 24145823 | `GAPDH` siRNA + negatif kontrol + mock transfeksiyon |
| `GSE44256` | 4 | GPL9115 (**RNA-seq**) | HeLa-d1EGFP | 23475073 | `EGFP` siRNA + `EGFP100`/`EGFPFL` **pro-siRNA** + NC |
| `GSE44105` | 6 | GPL6244 | HeLa-d1EGFP | 23475073 | `LMNA` siRNA + `LMNA` pro-siRNA, iki tekrar + NC |
| `GSE278438` | 7 | GPL20844 | 7 HeLa | 41467115 | `siVIM-270`, DNA/FA/MOE kimyaları |
| `GSE278439` | 4 | GPL20844 | 4 HeLa | 41467115 | `siVIM-270`, Fluoro/OMe kimyaları |

Toplam **171 örnek**. Ama genelleme birimi örnek değil **dupleks dizisi**, ve
ikisi arasındaki fark bu setin en önemli özelliği (§6.2).

### 6.1b Yayın kimlikleri — sekiz accession, **altı** yayın

Her PMID iki kez çözüldü: numara GEO'nun kendi kaydından, künye Europe
PMC'den. Gerekçe, bu satırın kendi uyarısı: `GSE5814`'ün yayını Jackson ve
ark. 2006 ***RNA***'dır, ve Birmingham ve ark. 2006 ***Nat Methods*** 3:199
**başka bir veri setidir** — yerine atıf vermek kolay, `A12`'den sonra geri
alınamaz.

| accession | PMID | ilk yazar | dergi, cilt (yıl) |
|---|---|---|---|
| `GSE5814` | 16682560 | Jackson AL | *RNA* 12 (2006) |
| `GSE5769` | 16682562 | Jackson AL | *RNA* 12 (2006) |
| `GSE5291` | 16965178 | **Schwarz DS** | *PLoS Genetics* 2 (2006) |
| `GSE41924` | 24145823 | Jiang Z | *RNA* 19 (2013) |
| `GSE44256` | 23475073 | Huang L | *Nature Biotechnology* 31 (2013) |
| `GSE44105` | 23475073 | Huang L | *Nature Biotechnology* 31 (2013) |
| `GSE278438` | 41467115 | An S | *Mol Ther Nucleic Acids* 36 (2025) |
| `GSE278439` | 41467115 | An S | *Mol Ther Nucleic Acids* 36 (2025) |

İki şey buradan okunuyor ve ikisi de analizi bağlıyor:

- **Sekiz accession, altı yayın.** `GSE44256`+`GSE44105` tek bir yayının iki
  serisi; `GSE278438`+`GSE278439` de öyle. Yani bunlar bağımsız çalışma değil,
  aynı laboratuvarın aynı deney setinin parçaları — çalışma düzeyinde bir
  rastgele etki ya da ağırlıklandırma düşünülürse birim **yayın** olmalı, seri
  değil. `GSE5814` ve `GSE5769` de aynı grubun (Jackson/Rosetta) iki ardışık
  makalesi.
- ⚠️ **`GSE41924`'ün GEO başlığı ile yayın konusu uyuşmuyor.** Seri
  *"Global analysis of off-target genes by GAPDH siRNA"* diyor; bağlı yayın
  ise *"Rational design of **microRNA-siRNA chimeras** for multifunctional
  target suppression"*. Yani bu üç örnek, düz bir siRNA off-target
  çalışmasının değil, bir **kimera** tasarım çalışmasının yan verisi. Bu
  madde onu **dışlamıyor** (n=3 ve tek dupleks olduğu için ağırlığı zaten
  yok), ama *sanki bağımsız bir off-target çalışmasıymış gibi* sayılmasını
  engellemek için burada yazılı.

### 6.2 Bağımsız birim **seed heptameri**: ~43, ve üç kol tipi tabandan dışlanıyor

⚠️ **Bu bölümün ilk hali birimi yanlış seçmişti ve 2026-11-27'de düzeltildi.**
"Ayrık ebeveyn dizi"yi **hedef gen etiketine** göre saymış ve ~14 bulmuştu; o
sayı `GSE5291`'i **iki** dizi sanıyordu. Doğru birim hedef gen değil, modelin
tahmin ettiği şey: **2-8 seed heptameri**.

Ölçülen envanter:

| seri | kol | ayrık seed heptameri | neden |
|---|---|---|---|
| `GSE5814` | 19 pozisyon mutantı + WT + 3 başka reaktif | **~8** (+3) | seed 2-8 olduğu için **1. ve 9-19. pozisyon mutantları yabani-tip seed'i AYNEN taşır**; yalnız 2-8'deki yedi mutant yeni seed üretir. Bu aritmetik, atıf değil |
| `GSE5769` | 61 array | **~8** | yedi ebeveyn dizi + `MAPK14-193`; `AS_pos2_modified` kolları ve doz/zaman serisi **diziyi değiştirmiyor**, kimyayı değiştiriyor |
| `GSE5291` | 18 array | **18** | SNP **18 ayrı pozisyona** yerleştirilmiş, yani 18 ayrı dizi ve 18 ayrı seed (örnek başlıkları: *"SOD1 SNP at position 1…19"*). **Bu, kilitlenen setin en güçlü serisi** |
| `GSE41924` | 3 | 1 | tek `GAPDH` siRNA'sı |
| `GSE44256` | 4 | 1 | tek tanımlı `EGFP` siRNA'sı; pro-siRNA kolları havuz |
| `GSE44105` | 6 | 1 | tek `LMNA` siRNA'sı |
| `GSE278438`+`GSE278439` | 11 | **1** | hepsi `siVIM-270`, yalnız kimyası değişiyor |

**Toplam ≈ 43 ayrık seed**, ve bunun **39'u 2006'nın üç serisinden**. 171
örnek bunların kolları, tekrarları ve kimyasal varyantları. ⚠️ `GSE5814` ve
`GSE5769`'un tam sayıları dizileri elde edilince `E0`'da kesinleşecek
(yayınların ek dosyalarında); yukarıdaki *"~8"*ler yapıdan türetilmiş alt
sınırlar, ölçülmüş sayılar değil — **bu belirsizlik burada yazılı, çünkü
`A12`'den sonra düzeltilemez.**

📌 **Sonuç, ve `A4`'ün CV şemasını bağlıyor: CV birimi ayrık seed
heptameridir.** Kol düzeyinde ya da dupleks düzeyinde fold kurmak aynı seed'i
foldlar arasında sızdırır. Bu bizim çıkarımımız değil, alanın yaptığı:
**siSPOTR `GSE5814`'ü tam bu sebeple kendi eğitim setinden çıkardı**
(*"77 of the experiments tested siRNAs with the same seed sequence"*), ve
MIRZA-G yalnız o serinin ayrık-seed kollarını kullandı.

Üç kol tipi, ölçülmüş gerekçeyle, **birincil değerlendirmenin dışında**:

1. **Tek nükleotid mutant kardeşleri — sızıntı.** `GSE5814`'ün 19 kolu *tek
   bir* ebeveynin (`193-MAPK14`) birer nükleotid farklı halleri. Kol düzeyinde
   leave-one-out yapmak, tutulan kolun dizisinin **19'da 18'ini** eğitimde
   bırakır. Bu yüzden CV birimi **ebeveyn dizi**, kol değil (şema §7'de).
   ⚠️ Bu kolların *2-8 dışındaki* pozisyonlardaki mutantları aynı seed'i
   taşır ve dupleksin 3' yarısını değiştirir — yani kendi başına değerli bir
   soru, ama birincil metrik için fold değil (§10).
2. **Aynı diziyi taşıyan kimyasal varyantlar — tavan.** `GSE5769`'un
   `AS_pos2_modified` kolları ve `GSE278438`/`GSE278439`'un tüm kimyaları,
   modifiye edilmemiş kardeşiyle **aynı seed dizisini** taşır. Dizi-tabanlı
   bir tahmin edici ikisine **birebir aynı** öngörüyü verir, ölçülen sonuç ise
   farklıdır; bu kollar fold olamaz ve birincil metrikte ulaşılabilir tavanı
   **düşürür**. (Bir termodinamik ölçüt için ise tam tersine en bilgili
   kollardır — §10.)
3. **pro-siRNA / esiRNA havuzları — tek seed yok.** `GSE44256` ve
   `GSE44105`'in pro-siRNA kolları enzimatik olarak üretilmiş heterojen
   havuzlar; tanımı gereği tek bir 2-8 seed'i yoktur, dolayısıyla bu modelin
   öngörebileceği bir nesne değildir.

### 6.3 Kapsam, dışlama ve sürümler

- **Kapsam:** değerlendirme evreni, HeLa'da ölçülebilir düzeyde eksprese
  edilen genler (filtre tanımı ve eşiği aşağıda, `A8`); birim **gen**, site
  değil (koordinat körlüğü İddia 1'i etkilemez — `.claude/rules/10-koordinatlar.md`).
- **Dışlama kuralları (veriyi görmeden):** §6.2'nin üç kol tipi; hedef genin
  kendisi ve bilinen doğrudan alt akışı (`A9`); HeLa'da eksprese edilmeyen
  genler (`A8`).
- **Veri sürümleri:** annotasyon **Ensembl 115**, pinlenmiş arşiv host'undan
  (`src/core/ensembl_release.py` otorite; sürüm her koşunun manifest'inde ve
  her önbellek anahtarında). İfade verisi DepMap 24Q2'ye eşlenmiş CCLE
  (`config/ccle_depmap_ids.yaml`, otoritesi `data/external/depmap/`). Tüm
  genomik koordinatlar hg38.
- ⚠️ **Dış geçerlilik, tekrar:** bu accession'ların hepsi **siRNA**.
  saRNA/RNAa'ya özgü bir referans seti bu büyüklükte yok (üç veri seti, toplam
  üç dupleks — `E7`), ve onlar birincil metriğe girmez, ayrı bir dış kontrol
  olarak raporlanır.

## 7. Analiz planı

<Hangi adımlar, hangi sırayla. Burada yazılmayan bir analiz keşifseldir ve
yayında öyle etiketlenir.>

## 8. Durdurma kuralı

<Analiz ne zaman biter? "Sonuç anlamlı olana kadar koşturmak" bir kural
değil, ihlaldir.>

## 9. Negatif sonuç

<Hipotez doğrulanmazsa ne rapor edilecek ve nereye. Değişmez 7: negatif sonuç
kabul edilir ve bir yayın yolu vardır. Ağırlık, eşik ya da sabit ayarlayarak
pozitif sonuç aramak ihlaldir — ölü kanalları telafi etmek için eşik
indirmek de bu kategoridedir.>

## 10. Keşifsel (ön kayıt dışı)

<Yapmayı düşündüğün ama teste sokmadığın şeyler. Buraya yazmak serbest;
sonradan buradan birincil metriğe taşımak değil.>

## Sapma günlüğü

Bu dosya kilitlendikten sonra plandan her sapma buraya **değil**,
`docs/PRE_REGISTRATION_v2.md`'ye yazılır. Bu bölüm kasıtlı olarak boştur.
