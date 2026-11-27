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

**Dupleks başına PR-AUC'nin, ayrık seed'ler üzerinden medyanı.** Her hücre
yanında **kendi taban oranıyla** ve **`lift = PR-AUC / taban`** olarak
raporlanır.

Nasıl hesaplanacağı, belirsizlik bırakmadan:

1. Her ayrık seed heptameri için (§6.2'nin birimi), o seed'i taşıyan
   dupleksin array'inde: etiket §4.1, evren §6.3.
2. Tahmin edici o array'in evrenindeki her geni sıralar; PR-AUC o sıralama ve
   o etiket üzerinden hesaplanır (`sklearn.metrics.average_precision_score`,
   yani **AP**; kesme noktası yok, eğri altı alanı interpolasyonsuz).
3. O hücrenin **tabanı** = o array'in pozitif oranı. `lift` = PR-AUC / taban.
4. Birincil sayı: bu PR-AUC'lerin **ayrık seed'ler üzerindeki medyanı**;
   yanında medyan taban oranı ve medyan lift.

🔴 **Neden havuzlanmış DEĞİL — ölçülmüş gerekçe.** §6.3'ün evreninde, dokuz
array'de taban oranı **%2,16 … %9,26** arasında değişiyor (**4,3 kat**,
medyan **%3,57**; ölçüm 2026-11-27). Havuzlanmış bir PR-AUC'nin "şans
düzeyi" bu oranların ağırlıklı ortalaması olur, yani **tek bir sayı olarak
yorumlanamaz**: aynı PR-AUC değeri bir duplekste şans düzeyi, başkasında üç
kat üstü olabilir. Üstelik **dupleks başına pozitif sayısı alanın tahmin
ettiği niceliğin kendisidir** (siSPOTR doğrulamasını
`Spearman(POTS, gözlenen off-target sayısı)` ile yapıyor), yani array'leri
havuzlamak bağımlı değişkeni siler.

⚠️ **`lift` neden zorunlu:** etiket eşiğini gevşetmek taban oranını ve
PR-AUC'yi **birlikte** yükseltir — ölçülmüş: eşik `−1.0`'dan `−0.1`'e
gevşetilince taban ~%1'den ~%36'ya çıkıyor. Yani çıplak bir PR-AUC artışı
model iyileşmesinden de, eşik gevşemesinden de gelebilir; `lift` ikisini
ayırır. Bu, "ölü kanalı telafi etmek için eşik indirme" hamlesini (değişmez 7)
görünür tutan mekanizma.

⚠️ **Alanın olağan karşılaştırması bu değil, ve bu açıkça yazılı.** RIsearch2
(PMID 28108657) kelimesi kelimesine: *"**In the literature there seems to be
no standard method** to evaluate the overall off-target effect based on
expression estimates before and after siRNA transfection, such as to evaluate
the power of prediction methods."* Alan Spearman (siSPOTR), KS `D`
(SeedMatchR) ve top-*n*'in medyan log2FC'si (RIsearch2, MIRZA-G) kullanıyor;
hiçbiri gen-başına ikili etiketle bir AUC raporlamıyor. PR-AUC burada
**bu projenin ürünü bir sıralama olduğu için** birincil — ama §3'ün üç
ikincil metriği **zorunludur**, seçenek değil, çünkü hakemin karşılaştırma
isteyeceği yer orası.

## 3. İkincil metrikler

Dördü de **zorunlu** — raporlanmaması bir seçim değil, eksiklik. Hiçbiri
birincil ile yer değiştiremez (§4.3'ün kuralı buraya da geçerli).

1. **Spearman ρ**, dupleks düzeyinde: tahmin edilen off-target potansiyeli ile
   **gözlenen off-target sayısı** arasında, ayrık seed'ler üzerinden.
   siSPOTR'ın (PMID 22941647) doğrulama biçimi, ve §2'nin işaret ettiği
   nokta: dupleks başına pozitif sayısı alanın asıl bağımlı değişkeni.
2. **Tek-yanlı Kolmogorov–Smirnov `D`**, seed-eşleşmeli genlerin log2FC
   dağılımı ile eşleşmeyenlerin dağılımı arasında. SeedMatchR'ın
   (PMID 38192001) biçimi. ⚠️ **`D` bir etki büyüklüğü olarak raporlanır,
   p-değeri olarak DEĞİL:** TargetScan'in uyarısı (PMID 26267216) — n ≈ 18.000
   mRNA'da KS p-değerleri *"highly significant p values for very slight
   differences"* veriyor, yani p burada bilgi taşımıyor.
3. **Top-*n* tahminlerin medyan log2FC'si**, `1 ≤ n ≤ 300` eğrisi olarak.
   RIsearch2 ve MIRZA-G'nin (PMID 25628353) biçimi; eşiksiz olduğu için
   §4.1'in etiket kararından bağımsız bir okuma verir.
4. **ROC-AUC**, dupleks başına. ⚠️ Raporlanır ama **karşılaştırma ölçütü
   değildir**: bu sınıf dengesizliğinde (taban %2-9) ROC-AUC iyimser, ve
   literatürde standart değil. Buraya yazılmasının tek sebebi, yazılmazsa
   sonradan "daha iyi görünen metrik" olarak eklenebilmesi.

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

### 4.4 Karar kuralı — bir geçerlilik ön koşulu ve dört sonuç

🔴 **Yol haritası `A6a` satırı bu kuralı İKİ sonuçlu yazıyordu** — *"PR-AUC
her üç tabanı da aşmalı; aşmazsa sonuç negatif olarak raporlanır"* — ve o
hali hem çıkarım olarak geçersiz hem de bu projenin bugünkü kodunda
**yanlış bir negatif üretmeye açık**. İkisi de ölçüldü; düzeltilmiş hali
aşağıda, ve nerede neden saptığı her alt bölümde yazılı.

#### 4.4.1 Marj `m` — ölçülmüş, modelden bağımsız, modeli görmeden sabitlendi

Marj, "aşmak" ile "aşmış görünmek"i ayıran sayı. Değeri **modelin hiçbir
çıktısı görülmeden**, yalnız referans setinin etiketleri ve **dizi bilgisi
taşımayan** iki tahmin edici üzerinden ölçüldü:

- **B4** = `log10(INTENSITY1)`, §7.5'in dördüncü tabanı (mock kanalı ifadesi),
- **VAR** = aynı probun mock yoğunluğunun **diğer array'lerdeki yayılımı**
  (genin ifade oynaklığı) — etiketten de, diziden de bağımsız.

İkisi de aynı ucuzlukta ve aynı ölçüde bilgisiz. 20 ayrık seed heptamerinde
(her seed için bir array; `GSE5814` + `GSE5769`, §6.2'nin birimi) eşleşmiş
AP farkı:

| nicelik | ölçüm |
|---|---|
| medyan \|AP(B4) − AP(VAR)\| | **0,0162** |
| sd(AP(B4) − AP(VAR)) | 0,0209 |
| iki **rastgele** sıralama arasındaki sd — saf örnekleme tabanı | 0,0028 |
| medyan taban oranı **0,0540** | 20 array; §2'nin ölçtüğü %2,16-%9,26 aralığında |

Karar: marj `m` = **0,020** AP — ölçülen 0,0162'nin ikinci ondalığa yukarı
yuvarlanmış hali. Gerekçe tek cümlede: **iki rastgele ucuz kovaryat arasındaki
tipik farktan küçük bir üstünlük, hangi ucuz tabanı seçtiğinizin gürültüsü
içindedir** ve hiçbir şey göstermez. Medyan taban oranında bu, lift
biriminde **0,37**'ye karşılık geliyor.

⚠️ **Yuvarlamanın yönü ilan edilmiştir.** Yukarı yuvarlamak `GEÇTİ` çıtasını
**yükseltir** ve eşdeğerlik iddiasını **kolaylaştırır**. Değişmez 7'nin
yasakladığı yön pozitif sonuç aramaktır; bu yuvarlama o yönün tersine
çalıştığı için serbest, ve ters yönde bir yuvarlama (aşağı) **yapılmayacaktır**.

İhtiyatlı `σ̂_d` = **0,0395** — modelden bağımsız çiftlerin ölçülen en
büyük sd'si. Güç hesapları (§4.4.6) bu değerle yapılıyor; daha küçük bir
`σ̂_d` seçmek gücü kâğıt üzerinde şişirmek olurdu.

🔬 **Aynı ölçümün yan ürünü, ve `A5b` olarak açık bırakıldı:** hiçbir dizi
bilgisi kullanmayan **üçüncü** bir ucuz tahmin edici — probun diğer
array'lerdeki medyan \|VALUE\|'su, yani "bu prob genel olarak ne kadar oynar" —
20 seed'in **20'sinde de** B4'ü aşıyor ve medyan lift'i **2,19** (B4'ün medyan
lift'i yalnız **1,18**, ve 20 seed'in 16'sında rastgelenin üstünde). Yani
§7.5'in taban envanterinin dışında, ondan **iki kat güçlü** ve tamamen
dizi-bağımsız bir çıta ölçüldü. Bu bölüm onu taban **yapmıyor** (tabanlar
§7.5'in, yani `A5`'in işi; değişmez 8); yol haritasına `A5b` olarak yazıldı ve
`A12` ona bağlandı, çünkü kilitten sonra eklenemez.

#### 4.4.2 Geçerlilik ön koşulu: **GEÇERSİZ** (yozlaşmış sıralama)

🔴 **Bu ön koşul, iki sonuçlu kuralın bu projede ürettiği yanlış negatifi
kapatıyor, ve gerekçesi bir aritmetik kimlik.** Sabit bir tahminci için
ortalama kesinlik **taban oranına eşittir**, yani

```
AP = π   ve   lift = 1,0000   (her taban oranında, tam olarak)
```

Bu bir ölçüm değil, kimlik: sıralamayı skor değil **bağlantı kırma** belirler.
Dolayısıyla sabit bir skorla koşulan bir değerlendirme `lift = 1,00` verir, ve
iki sonuçlu bir kural bunu **"negatif sonuç"** diye raporlar — oysa doğru
cümle *"enstrüman sıralama üretmedi"*. Değişmez 7 negatif sonucu yayın yolu
olan bir sonuç yaptığı için bu, sessizce yayınlanabilecek bir yanlıştır.

⚠️ **Ve bugün tam bu durumdayız.** `.claude/rules/20-skor-degismezleri.md`
ölçülmüş olgu olarak şunu yazıyor: §1'in mekanizmasını ölçen kanal
(`sequence_specificity`) **41/41 sitede 1.0**, çünkü `_clamp` 12 ayrık ham
değeri eziyor. Yani bu ön koşul yazılmadan kilitlenen bir ön kayıt, *ölçüm
yapmayan* bir planı kilitlemiş olurdu — `pre-register` skill'inin kelimesi
kelimesine uyardığı şey.

**Ön koşul, sayıyla.** Bir tahmin ediciye §2'nin metriği uygulanabilmesi için,
değerlendirilen **her** array'de bağlantı grupları içindeki sıralama
belirsizliğinin AP'yi oynatabileceği aralık marjın yarısını geçmemeli:

```
AP_en_iyi − AP_en_kötü  ≤  m/2 = 0,010
```

(`AP_en_kötü`: her bağlantı grubunun içinde pozitifler **sona**;
`AP_en_iyi`: başa.) Ön koşul **iki ayrı yerde** uygulanır:

1. **Değerlendirilen sıralama** (nihai risk skoru) için — sağlanmazsa sonuç
   `GEÇERSİZ`, ve §9'un negatif sonuç yolu **kullanılmaz**.
2. **Sıfırdan farklı ağırlıkla skora giren her kanal** için ayrı ayrı. Sabit
   bir kanal nominal ağırlığını taşımaya devam ederse ağırlıklı toplamın
   yorumu yanlışlaşır; özellikle §1'in hipotezi seed-aracılı susturma
   hakkında olduğu için, `sequence_specificity` sabitken alınan bir `GEÇTİ`
   **hipoteze atfedilemez**. Böyle bir kanalın ya çözünürlüğü düzeltilir
   (`C1`) ya da ağırlığı **ilan edilerek sıfırlanır** ve §2'nin metriği onsuz
   yeniden hesaplanır. Üçüncü bir seçenek yok.

🔬 **Ölçülmüş çözünürlük talebi — `C1` ve `A10` için bir sayı.** Aynı 20
array'de, mock yoğunluğu kovaryatı `k` kademeye nicelenerek bağlantı açıklığı
ölçüldü:

| kademe | medyan açıklık | en kötü array | m/2 = 0,010 altında? |
|---|---|---|---|
| 1 (sabit) | 0,9725 | 0,9881 | hayır |
| 12 (bugünkü ham seed skoru) | 0,0316 | 0,0518 | **hayır** |
| 50 | 0,0073 | 0,0199 | hayır |
| 100 | 0,0040 | 0,0155 | hayır |
| 250 | 0,0017 | 0,0106 | hayır |
| 500 | 0,0009 | 0,0060 | **evet** |

Yani `_clamp`'i kaldırmak **yetmez**: `_clamp` öncesindeki 12 ayrık değer de
bu ön koşulu geçmiyor, ve açıklığı (0,0518) marjın **iki buçuk katı**.
`A10`'un ön kaydedeceği haritalama ve `C1`'in uygulaması, değerlendirme
evreninde ≥ **500** ayrık değer üretmek zorunda. Bu sayı ölçülmüştür, bir
tercih değildir; `C1`'in bugünkü kabul kriteri ("41/41 sabit değil") bu
eşiğin çok altındaydı ve yol haritasında düzeltildi.

#### 4.4.3 Kontrast ve test

Her ayrık seed heptameri `i` ve her taban `b` için eşleşmiş fark:

```
d_i^b  =  AP_model(i) − AP_b(i)
```

⚠️ **`AP_model` HANGİ skor üzerinde hesaplanır:** yalnız **`P_silence`**
üzerinde (§7.6). Karar kuralı `Impact` kolonundan **hiçbir girdi almaz**, çünkü
`Impact` bu referans setinde doğrulanamıyor (§10.1, `validated: false`) ve
doğrulanamayan bir kolonu geçme koşuluna sokmak, ölçülmemiş bir niceliği
sonucun belirleyicisi yapardı. Birleşik bir skor da kullanılmaz; §7.6
birleştirmeyi ayrı bir ön kayıt maddesine bırakıyor.

- **Test:** tek-yanlı **eşleşmiş Wilcoxon işaretli sıra** testi, `d_i^b − m`
  üzerinde, `α = 0,05`. Yani sınanan şey "sıfırdan büyük" değil,
  **"marjdan büyük"** — eşik testin içinde, sonradan bakılan bir sayı değil.
  Birim seed olduğu için test §7.1'in foldlarıyla aynı birimde; sınıflandırıcı
  karşılaştırmasında eşleşmiş sıralı test Demšar 2006'nın önerdiği ölçüt.
  `n ≤ 25` için null dağılımı **tam** hesaplanır (normal yaklaşım bu örneklem
  büyüklüğünde yetersiz).
- **Çoklu taban için α DÜZELTİLMEZ, ve bu bir ihmal değil.** Gereklilik
  **kesişimsel**: beş tabanın **hepsi** aşılmalı. Böyle bir kural bir
  kesişim-birleşim testidir ve boyutu `α`'yı **aşamaz** (Berger 1982), yani
  düzeltme gereksiz. Ters yönü de yazılı: FDA'nın 2022 çok-uç-noktalı
  kılavuzu kelimesi kelimesine *"increasing α for each co-primary endpoint is
  not acceptable"* diyor — yani eş-birincil uç noktalarda α'yı **büyütmek**
  yasak, ve bu bölüm onu yapmıyor.
- **Güven aralığı:** medyan `d` için **BCa bootstrap**, 10.000 yeniden
  örnekleme, birim **seed** (array içi yeniden örnekleme gen düzeyinde
  kümelenmiş bootstrap). Aralık her tabanda raporlanır, sonuç ne olursa olsun.

#### 4.4.4 Dört sonuç

Ön koşul (§4.4.2) sağlanmazsa tek sonuç **`GEÇERSİZ`**'dir ve aşağıdakilerin
hiçbiri okunmaz. Sağlanırsa, **her taban için** aralık hesaplanır ve verdi
şöyle okunur:

| sonuç | koşul | ne iddia edilir |
|---|---|---|
| **`GEÇTİ`** | beş tabanın **hepsinde** `d − m` için tek-yanlı Wilcoxon `p < 0,05` | orcSONAR her ucuz tabanı pratik olarak anlamlı bir farkla aşıyor |
| **`EŞDEĞER`** | en az bir tabanda iki-yanlı %95 GA tamamen `(−m, +m)` içinde | o tabana karşı **pratik eşdeğerlik** — pozitif, yayınlanabilir bir iddia |
| **`DAHA KÖTÜ`** | en az bir tabanda GA tamamen `−m`'in altında | orcSONAR o ucuz tabandan kötü |
| **`SONUÇSUZ`** | kalan her şey (GA bir sınırı kesiyor) | **hiçbir yönde iddia yok**; ulaşılan GA genişliği raporlanır |

**Öncelik, belirsizlik bırakmadan.** `GEÇTİ` beş tabanın **hepsini** ister;
biri bile sağlanmazsa `GEÇTİ` yoktur. Kalan durumda birden fazla sonuç aynı
anda uygulanabilir (bir tabanda `DAHA KÖTÜ`, başkasında `EŞDEĞER`), ve o zaman
raporlanan verdi **en olumsuz uygulanabilir** olandır:
`DAHA KÖTÜ` > `EŞDEĞER` > `SONUÇSUZ` > `GEÇTİ`. Sonuç ne olursa olsun dört
tabanın **beşinin** aralığı da raporlanır; verdi bir özet, veri değil.

🔴 **`EŞDEĞER` ve `SONUÇSUZ`'un ayrı olması bu bölümün asıl düzeltmesi.**
Başarısız bir üstünlük testi negatif sonuç **üretmez**: Benavoli, Corani,
Demšar & Zaffalon 2017 (*JMLR* 18(77)) kelimesi kelimesine *"NHST cannot
provide evidence in favour of the null hypothesis… When NHST does not reject
the null hypothesis, no conclusion can be made."* Negatif bir sonucun
söylenebilir hale gelmesi için **eşdeğerlik** (pratik eşdeğerlik bölgesi,
*rope*) yönünde bir test gerekir, ve o testin eşiği de `m`. `A6a` satırının
"aşmazsa negatif raporla" cümlesi bu ayrımı yapmıyordu; §9'un (`A15`)
yayın yolu **`EŞDEĞER` ve `DAHA KÖTÜ`** içindir, `SONUÇSUZ` için değildir —
`SONUÇSUZ` bir sonuç değil, yetersiz bilgidir ve öyle raporlanır.

#### 4.4.5 Tabakalar: raporlanan tanı + bağlayıcı yön koşulu

`A6a` satırı birincil metriğin **uzunluk tabakaları içinde de** her tabanı
aşmasını istiyordu. 5 taban × 3 tabaka = **15 kesişimsel koşul** (`A5b`
beşinci tabanı ekledi, §7.5), ve bunun gücü ölçüldü: tabaka içi
`n ≈ 43/3 ≈ 14`'te tek testin gücü **0,538**, on beş koşulun birleşik gücü
(bağımsızlık varsayımıyla, yani bir **alt sınır**) **0,0001**. Testler pozitif korele olduğu için gerçek değer bundan yüksek, ama
iki mertebe yüksek değil. **Gücü %0,06 olan bir geçme koşulunu sonucu
belirleyen şey model değil örneklem büyüklüğüdür** — ve böyle bir koşul
konulursa sonuç neredeyse kesin olarak `SONUÇSUZ` çıkar, yani kural
yanlışlanamaz hale gelir.

O yüzden tabakalar şöyle bağlanıyor:

- **Raporlanır:** birincil metrik, beş tabanın hepsine karşı, uzunluk ve
  ifade-şiddeti tabakalarının her birinde, güven aralıklarıyla (§7.4'ün
  zorunluluğu aynen duruyor).
- **Bağlayıcı olan koşul YÖN:** hiçbir tabakada, hiçbir tabana karşı
  medyan `d`'nin **nokta tahmini negatif olamaz**. Negatifse verdi
  `SONUÇSUZ`'a düşer ve o tabaka **adıyla** raporlanır — havuzlanmış bir
  kazanımın bir tabakadaki kayıptan geldiği durumu yakalayan şey bu.
- ⚠️ **Bu, `A6a` satırının istediğinden ZAYIF, ve sebebi yazılı:** ölçülmüş
  güç, kolaylık değil. Tabaka-içi testleri geçme koşulu yapmak için gereken
  örneklem bu veri setinde yok (§6.2'nin envanteri ≈43 seed), ve bunu
  kilitten sonra farketmek sapma günlüğü maddesi olurdu.

#### 4.4.6 Güç, önceden ilan edilmiş

Tek-yanlı eşleşmiş Wilcoxon, `α = 0,05`, gerçek fark `δ = m = 0,020`,
`σ̂_d = 0,0395`, tam null dağılımı, 4000 tekrar:

| n | ne | güç |
|---|---|---|
| 43 | tüm seed'ler, tabanlar 1-3 ve 5 (§6.2) | **0,935** |
| 25 | dördüncü taban (`GSE5291` hesaplanamıyor, §7.5) | **0,779** |
| 14 | tabaka içi (≈43/3) | **0,538** |

- Beş tabanın **birleşik** gücü, bağımsızlık varsayımıyla (alt sınır):
  `0,935⁵ ≈ 0,71`. ⚠️ Beşinci tabanı eklemek bu alt sınırı 0,76'dan 0,71'e
  indiriyor; maliyet ilan edilmiştir ve taban **yine de eklendi**, çünkü
  çıtayı yükseltmemek değişmez 7'nin yasakladığı yöndür (`A5b`). Testler aynı model ve aynı seed'ler üzerinde olduğu için
  pozitif korele, yani gerçek değer bunun üstünde.
- ⚠️ **Dördüncü taban yetersiz güçlüdür ve bu ilan edilmiştir:** 0,779 < 0,80.
  Çözüm olarak marj **büyütülmeyecek** — marjı `σ̂_d`'yi gördükten sonra
  büyütmek gücü kâğıt üzerinde düzeltir ve eşdeğerlik iddiasını kolaylaştırır,
  yani değişmez 7'nin yasakladığı hamlenin eşdeğerlik yönündeki hali. Yoğunluğu
  başka serilerden ithal etmek de §7.5'te zaten reddedildi. Dördüncü tabanın
  sonucu **ulaşılan gücüyle birlikte** raporlanır.
- ⚠️ `σ̂_d` 20 seed üzerinden kestirildi, 43 üzerinden değil; nokta
  kestirimdir ve güç tablosu ona koşulludur. Bu da ilan edilmiştir.

#### 4.4.7 Bu bölümün ölçümünün kaydı

Marj, `σ̂_d`, çözünürlük tablosu ve güç tablosunun hepsi
**`reports/a6a-marj-2026-11-27/`** altında: ölçüm betiği, çıktı JSON'ları ve
hangi 20 array'in hangi seed'i temsil ettiği. `A12`'nin kilidi bu dizine atıf
yapar; kapı (`.claude/acceptance/A6a.sh`) güç tablosunu **her koşuda tam
Wilcoxon null dağılımından yeniden simüle eder** ve bu bölümdeki sayılardan
saparsa kırmızıya düşer, yani metin ölçümden sessizce ayrılamaz.

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

### 6.2b Analiz birimi: array mı, replikat çifti mi — ölçülmüş cevap

Kaynak makalelerin kendi birimi **array değil**: Jackson 2006b kelimesi
kelimesine *"Transcript regulation was calculated as the **error-weighted
mean log 10 ratio** for each transcript across the **fluor-reversed
pair**."* Bu birimin GEO yatağından **ne kadarının geri kurulabildiği**
ölçüldü (2026-11-27), çünkü analiz birimi `A12`'den sonra değiştirilemez:

| seri | array | ayrık kol | tam `a`/`b` çifti taşıyan | durum |
|---|---|---|---|---|
| `GSE5291` | 18 | 18 | — | ✅ **Her GSM zaten çift-ortalaması.** Metadata açıkça söylüyor: `!Sample_label_ch1 = Cy3/Cy5 (fluor-reversed pair)`. Birim = GSM = siRNA |
| `GSE5814` | 68 | 30 | **19** | kısmi |
| `GSE5769` | 61 | 50 | **11**, artı **1 yarım çift** | kısmi |

Üç ölçülmüş sonuç ve üçü de bağlayıcı:

1. ✅ **Replikat yapısı geri kurulabiliyor:** `GSE5814` ve `GSE5769`'un
   başlıklarındaki `a`/`b` eki kolları eşleştirmeye yetiyor.
2. ⚠️ **Ama `a`/`b`'nin boya-çevrimi OLDUĞU kayıtlı değil.** İki serinin
   **bütün** örnekleri `ch1 = Cy3, ch2 = Cy5` diyor; `GSE5291` gibi açık bir
   *"fluor-reversed pair"* ifadesi yok. Makaleler birimlerini çevrimli çift
   üzerinden tanımladığına göre `a`/`b` en olası eşleşme — ama bu bir
   **çıkarım**, ölçüm değil, ve burada öyle etiketli.
3. 🔴 **Makalelerin tam birimi kolların AZINLIĞI için mevcut:** `GSE5814`'ün
   30 kolundan 19'u, `GSE5769`'un 50 kolundan 11'i. Geri kalan kollar **tek
   array** tahmini verir. `E0` bu kolları **işaretlemek** zorunda, sessizce
   çift gibi ortalamamak; ve `GSE5769`'daki **yarım çift** ayrıca
   raporlanacak, tam çift sayılmayacak.

📌 Yani §2'nin "dupleks başına" hücresi, çifti olan kollarda çift-ortalaması,
olmayanlarda tek array üzerinden hesaplanır, **ve hangisinin hangisi olduğu
raporda görünür**. Bu bir zayıflık ve örtülmüyor: tek-array hücreleri daha
gürültülü, yani §2'nin medyanı onların bulunduğu yerde daha oynak.

### 6.3 Kapsam, dışlama ve sürümler

- **Kapsam:** değerlendirme evreni, HeLa'da ölçülebilir düzeyde eksprese
  edilen genler (filtre tanımı ve eşiği `A8`'de); birim **gen**, site
  değil (koordinat körlüğü İddia 1'i etkilemez — `.claude/rules/10-koordinatlar.md`).
- **Dışlama kuralları (veriyi görmeden):** §6.2'nin üç kol tipi; hedef genin
  kendisi ve bilinen doğrudan alt akışı (`A9`); HeLa'da eksprese edilmeyen
  genler (`A8`).
- ⚠️ **İfade filtresinin kendisi hakkında bir beyan:** Jackson'ın yayınlanmış filtresi *"expressed at significant levels (log 10 intensity ≥ −1, ∼1 copy/cell)"* ve o eşik `LOGINTENSITY` üzerinde tanımlı — ki GEO'nun tanımıyla **iki kanalın ortalaması**, yani aşağı regüle olmuş bir gende kısmen **etiketin fonksiyonu**. Filtre buna rağmen **kaynak makalelerin kendi filtresi olduğu için** korunuyor (karşılaştırılabilirlik §4.1'in gerekçesiyle aynı), ama bağımlılık burada yazılı ve etkisi **ihtiyatlı yönde**: ortalama düşeceği için filtre aşağı regüle olmuş genleri daha kolay **dışlar**, yani pozitifleri azaltır, uydurmaz. ⚠️ Tabanlarda aynı tercih **yapılmıyor**: §7.5'in dördüncü tabanı mock kanalını (`INTENSITY1`) kullanıyor, çünkü bir tabanın etiket bilgisi taşıması onu taban olmaktan çıkarır.
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

Burada yazılmayan bir analiz keşifseldir ve yayında öyle etiketlenir (§10).

### 7.1 Çapraz doğrulama — birim **ayrık seed heptameri**

**Leave-one-seed-out.** Her fold bir ayrık 2-8 seed heptameri; §6.2'nin
envanterine göre **≈43 fold**, 39'u 2006'nın üç serisinden.

🔴 **Neden kol ya da dupleks düzeyinde DEĞİL — sızıntı.** `GSE5814`'ün 19
pozisyon mutantı tek bir ebeveynin birer nükleotid farklı halleri, ve seed
2-8 olduğu için **1. ve 9-19. pozisyon mutantları yabani-tip seed'i aynen
taşır**. Kol düzeyinde bir fold, tutulan kolun seed'ini eğitimde bırakır ve
dizi-tabanlı bir tahmin edici o fold'da **aynı öngörüyü** üretir — yani
performans ölçülmez, hatırlanır. Bu bizim çıkarımımız değil, alanın yaptığı:
siSPOTR `GSE5814`'ü kendi eğitim setinden **tam bu sebeple** çıkardı
(*"77 of the experiments tested siRNAs with the same seed sequence"*), MIRZA-G
ise yalnız o serinin ayrık-seed kollarını kullandı.

Kural, tek cümlede: **aynı seed heptamerini taşıyan hiçbir kol eğitim ve test
bölümlerinde birlikte bulunamaz.** §6.2'nin dışladığı üç kol tipi (kimyasal
varyantlar, havuzlar, seed'i değişmeyen mutantlar) hiçbir fold'da pozitif
örnek olarak sayılmaz.

### 7.2 Değerlendirme kümesinin devralınan iki filtresi

siSPOTR'ın ve RIsearch2'nin ortak kullandığı iki filtre **ön kayıtlı olarak**
devralınıyor, çünkü ikisi de sonucu gördükten sonra eklenirse ayarlama olur:

- **İplik yanlılığı:** guide ipliğin baskın yüklendiği dupleksler. ⚠️ Bu
  filtre `A1`'in "her iki iplik" kararıyla gerilim içinde ve gerilim burada
  **yazılı**: filtre yalnız *ölçüm gürültüsünü* azaltmak için var, modelin
  kapsamını daraltmak için değil; pasajer-baskın dupleksler **dışlanmaz**,
  ayrı bir alt küme olarak raporlanır (§10).
- **Hedef-üstü susturma > %85:** dupleksin kendi hedefini gerçekten
  susturduğu array'ler. Hedefin kendi probundan hesaplanır. ⚠️ Bir dupleksin
  hedef probu array'de yoksa o dupleks **dışlanır ve sayısı raporlanır** —
  sessizce düşmez.

### 7.3 Birincil ve ikincil kümelerin ayrımı

- **Birincil küme: 2006'nın üç Rosetta serisi** (`GSE5814`, `GSE5769`,
  `GSE5291`). Tek ölçek, tek hata modeli, prob-başına `PVALUE`, ve §4.1'in
  ölçütü doğrudan hesaplanabilir.
- **İlan edilmiş dış replikasyon: beş modern seri** (`GSE41924`, `GSE44256`,
  `GSE44105`, `GSE278438`, `GSE278439`). **Seri başına** raporlanır,
  birincil metriğe **havuzlanmaz**.
- **Gerekçe, ve maliyeti:** MAQC-I (PMID 16964229) log-oran **sıralamalarının**
  platformlar arası karşılaştırılabilir olduğunu, **büyüklüklerinin**
  olmadığını buluyor (*"which can lead to over- or underestimates of log
  ratios and fold changes"*; sıralama korelasyonu minimum R = 0,69). SEQC
  (PMID 25150838) aynı yönde: *"relative expression are accurate and
  reproducible … In contrast, RNA-seq and microarrays **do not provide
  accurate absolute measurements**"*. Beş modern seri ≈43 seed'in yalnız
  ~4'ünü (%9) getiriyor ama karşılaştırılabilirlik riskinin tamamını
  taşıyor. ⚠️ **Bu ayrımın tartışılabilir olduğu da yazılı:** 2025 tarihli,
  dört platformlu bir replikasyonun tek platformdaki 39 seed'den daha
  inandırıcı olduğu savunulabilir; o yüzden dışlanmıyor, **ayrı
  raporlanıyor**.

### 7.4 Zorunlu tabakalar

`A4`'ün bağladığı iki zorunluluk:

- Birincil metrik **hem uzunluk hem ifade-şiddeti tabakaları içinde**
  raporlanır. Gerekçe ölçülmüş: pozitiflerin medyan `LOGINTENSITY`'si
  **−0,08 … −0,36**, tüm probların medyanı **−0,78 … −1,12** — yani
  pozitiflik tespit edilebilirlikle korelasyonlu, ve uzunluk/ifade ile
  korelasyonlu **herhangi** bir tahmin edici tek başına şans üstü skorlar.
  Bu, denetimin bulduğu hit-sayısı ↔ cDNA uzunluğu `r = 0,349`
  korelasyonunun mekanizması.
- ⚠️ **Tabakalama yeterli değil, ve bu da yazılı:** TargetScan aynı
  karıştırıcıyı *tam bu derlemede* ölçtü ve 3′UTR uzunluğu ile AU içeriğinin
  mikroarray kat-değişimiyle korelasyonunun **yayın-özgü bir yönde**
  olduğunu buldu (*"the extent and direction of the correlation … differed
  when comparing to datasets from other publications"*); çözümleri
  **yayın başına PLSR çıkarımı** oldu. Bu projede PLSR **uygulanmıyor**;
  bunun yerine tabaka içi raporlama yapılıyor ve **bu sınır burada
  beyan ediliyor**, sonradan "biz de PLSR yapmalıydık" demek bir sapma
  günlüğü maddesi olur, sessiz bir düzeltme değil.

### 7.5 Tabanlar — beşi de, ve ilk dördü 3′UTR tanımlı

orcSONAR'ın **her birini** aşması gerekiyor; biri aşılmazsa verdi §4.4'ün
tablosundan okunur. Beşi de §6.3'ün evreninde, §4.1'in etiketiyle, §7.1'in
foldlarıyla hesaplanır ve §2'nin metriğiyle raporlanır — yani tabanlar modelle
**aynı** koşuda ölçülür, literatürden **performans** alıntılanmaz. ⚠️ Beşinci
tabanın *tablosu* dışsaldır (yayınlanmış bir gen listesi), ama o tablonun bu
sette ürettiği **AP yine burada ölçülür**; aradaki fark §4.4.1'in marjının
dayandığı ayrımın aynısı.

⚠️ **Bölge:** 1-3 numaralı tabanlar 3′UTR tanımlıdır. Dördüncüsü (mock kanalı
yoğunluğu) ve beşincisi (yayınlanmış genel-DE önselliği) **gen düzeyindedir**
ve bölge tanımı taşımaz — çünkü ikisi de bir dizi özelliği değil, genin
ölçülme/oynama eğilimi. Bu ayrım burada yazılı, çünkü "hepsi 3′UTR tanımlı"
cümlesi dördüncü taban eklendiğinde zaten doğru olmaktan çıkmıştı.

1. **3′UTR 7mer-m8 varlığı / sayısı.** Genin 3′UTR'sinde seed'in 7mer-m8
   eşleşmesi var mı, kaç tane. Alanın en çıplak tahmin edicisi; bunu aşmayan
   bir model hiçbir şey eklemiyor demektir.
2. **siSPOTR POTS** (PMID 22941647). 3′UTR heptamer frekans tablosundan
   türetilen yayınlanmış skor. Tabloyu kurmak ayrı bir iş (`E0b`).
   ⚠️ POTS'un eşiği `GSE5291` + `GSE5769` üzerinde türetilmiş (§4.3'ün ilan
   ettiği döngüsellik), yani POTS bu iki seride **avantajlı** bir taban;
   aşılması gereken çıta bu yüzden daha yüksek, ve bu *lehimize* değil.
3. **Transkript / 3′UTR uzunluğu, tek başına.** Hiçbir dizi bilgisi yok,
   yalnız uzunluk. Denetim hit sayısı ile cDNA uzunluğu arasında
   **r = 0,349** buldu: uzun transkriptler hem daha çok seed eşleşmesi hem
   daha güvenilir DE çağrısı alır.
4. 🆕 **Mock kanalının ham yoğunluğu — `log10(INTENSITY1)`, tek başına.**
   Hiçbir dizi bilgisi yok, yalnız genin o array'in **mock** kanalında ne
   kadar eksprese olduğu. **Bu dördüncü taban bu satırın kendi
   gerekçesinden ve bir ölçümden doğdu:** yol haritası `A5` satırı
   karıştırıcıyı *"uzun **ve yüksek ifadeli** transkriptler"* diye tarif
   ediyordu ama yalnız uzunluğu taban yapıyordu. Ölçüm (2026-11-27)
   ifadenin en az o kadar güçlü olduğunu gösteriyor: mock kanalında
   **pozitiflerin medyanı −0,014 … −0,134, tüm probların medyanı −0,766 …
   −1,109** — yani **0,75-1,09 birim** fark. Yalnız ifadeye göre sıralayan
   bir tahmin edici şans üstü skorlar, ve bu taban olmadan orcSONAR'ın skoru
   *"tespit edilebilirliği öğrendi"* ile ayırt edilemez.

   🔴 **Bu tanım DÜZELTİLDİ ve ilk hali döngüseldi.** İlk yazım kovaryatı
   `LOGINTENSITY` olarak veriyordu; GEO'nun kendi tanımı
   `#LOGINTENSITY = Corrected **average** log intensity of channels`, yani
   **iki kanalın ortalaması** — ve aşağı regüle olmuş bir genin işlem kanalı
   düşük olduğu için o ortalama **etiketin bir fonksiyonu**. Etiket bilgisi
   taşıyan bir taban, tabanı değil kendisini ölçer. Mock kanalı
   `#INTENSITY1 = Raw Cy3 intensity (CH1)`, ve `GSE5814`/`GSE5769`'da ch1 =
   mock (§4.2). Ölçüm mock kanalında **yeniden yapıldı** ve fark duruyor;
   zaten döngüsellik gözlenen yönün **tersine** itiyordu (aşağı regülasyon
   ortalamayı düşürür), yani gerçek fark en az bu kadar.

   🔴 **Ve bu taban `GSE5291`'de HESAPLANAMIYOR.** O serinin tablosu yalnız
   `VALUE`, `LOGINTENSITY`, `PVALUE`, `MLRATIOERROR` taşıyor — **kanal-başına
   yoğunluk yok** (ölçüldü). `GSE5291` ≈43 seed'in **18'ini** veren en güçlü
   seri olduğu için bu önemli: dördüncü taban **hesaplanabildiği foldlarda**
   değerlendirilir ve hangi foldları kapsadığı **raporlanır**.
   ⚠️ Alternatif — mock yoğunluğunu `GSE5814`/`GSE5769`'dan ortak prob kümesi
   üzerinden **ithal etmek** — **benimsenmedi**: seriler arası bir varsayım
   ekler ve MAQC'nin büyüklük uyarısı (§7.3) tam buna karşı. Benimsenmediği
   burada yazılı, çünkü sonradan yapılırsa sessiz bir genişleme olur.

5. 🆕 **Yayınlanmış genel-DE önselliği — Crow ve ark. 2019'un `DE prior`'ı.**
   Genin, **birbirinden bağımsız deneylerde** diferansiyel eksprese çıkma
   eğilimi; hiçbir dizi bilgisi yok, bu projenin verisinden hiçbir şey yok.
   Kaynak: Megan Crow, Nathaniel Lim, Sara Ballouz, Paul Pavlidis, Jesse
   Gillis, *"Predictability of human differential gene expression"*,
   **PNAS 2019;116(13):6491-6500, PMID 30846554, DOI 10.1073/pnas.1802973116**;
   tablo `DE_Prior.txt` (19.172 gen, Entrez anahtarlı, `DE_Prior_Rank` ∈ (0,1]),
   `data/external/de_prior/` altında checksum'ıyla.

   🔴 **Bu tabanın eklenmesinin sebebi `A6a`'nın kendi ölçümü, ve literatür
   onu teyit etti.** Marjı ölçerken dizi bilgisi kullanmayan bir "genel
   oynaklık" kovaryatının §7.5'in dördüncü tabanını 20 seed'in 20'sinde de
   aştığı görüldü. Crow ve ark. aynı kovaryatı 635 veri setinde ölçmüş ve
   kelimesi kelimesine şunu buluyor: `DE prior` tek başına bir çalışmanın DE
   listesini **"mean AUROC, 0.83 ± 0.1"** ile geri getiriyor, ve
   *"a large fraction of DE hit lists are nonspecific"*. Daha önemlisi,
   §7.5'in 1-4 numaralı tabanlarının **tam olarak zayıf sınıfta** olduğunu
   söylüyor: GC içeriği, gen uzunluğu, doku ifadesi, mutabilite ve
   koekspresyon derecesi için *"None of these properties is nearly as
   predictive as the DE prior (mean across all categories, 0.55"*. Yani
   §7.5'in dört tabanı 0,55 sınıfındandı ve 0,83 sınıfı listede **yoktu**.

   🔬 **Bu sette ölçüldü (2026-11-27, modelden bağımsız):** 20 ayrık seed'de
   medyan lift **1,2708**, dördüncü tabanı 20 seed'in **14'ünde** aşıyor, ve
   eşleşmiş fark medyanı **+0,0063** (tek-yanlı tam Wilcoxon `p = 0,041`
   sıfıra karşı, ama `§4.4`'ün marjına karşı `p = 0,995`). ⚠️ Yani **bu sette
   yayınlanmış önsellik dördüncü tabandan pratik olarak daha güçlü DEĞİL**, ve
   bu beklenen bir uyumsuzluk: önsellik GPL570 derlemesinde, ağırlıkla
   cinsiyet karşılaştırmalarıyla kurulmuş (en üst sıraları `XIST`, `DDX3Y`,
   `EIF1AY`, `KDM5D`, `USP9Y`), tek bir hücre hattında ise o genler hiç
   oynamıyor. Bu sayı **sonucu görmeden** yazıldı; tabanın zayıf olduğunu
   sonradan keşfetmek bir sapma maddesi olurdu.

   📌 **Eşleşmeyen problar medyan rankla doldurulur, son sıraya atılmaz.**
   Prob→gen eşleşmesi platforma göre **%66,1-87,4** (ölçüldü); eşleşmeyeni son
   sıraya atmak tabanı *zayıflatır*, yani çıtayı düşürür — değişmez 7'nin
   yasakladığı yön. Doldurma yönü bu yüzden tabanın lehine seçildi ve burada
   ilan edildi.

   ✅ **Buna rağmen eklenmesinin iki ölçülmüş sebebi var.** (i) Dördüncü
   tabandan **farklı bir alternatif açıklamayı** kapatıyor: Crow'un kendi
   ölçümü ifade düzeyini 0,55'te, önselliği 0,83'te buluyor, ve bu sette de
   iki sıralama birbirinin yerine geçmiyor (önsellik 14/20'de üstün, 6/20'de
   değil). (ii) **`GSE5291`'de hesaplanabiliyor, dördüncü taban ise değil.**
   `GSE5291` 18 ayrık seed'le kilitlenen setin en güçlü serisi; tablosunda
   kanal-başına yoğunluk **yok** ama platformu `GPL3992`, yani prob→gen
   eşlemesi aynen çalışıyor (ölçüldü: 5 array'de eşleşme %68,1-68,6, medyan
   lift **1,33**). Yani beşinci taban **n ≈ 43**'ü kapsıyor, dördüncüsü
   **n ≈ 25**'i.

🔴 **REDDEDİLEN ADAY, gerekçesiyle: "bu prob genel olarak ne kadar oynar".**
`A6a`'nın ölçümünde en güçlü ucuz tahmin edici bu çıktı — probun **bu setteki
diğer array'lerdeki** medyan `\|VALUE\|`'su, medyan lift **2,18** (20/20'de
dördüncü tabanın üstünde; `A6a`'nın ayrı betiği 2,19 ölçtü, yani sayı iki
bağımsız uygulamada tekrarlandı). Taban yapılmadı, ve üç sebebin **üçü de ölçüm**:

- **Gücünün yarısı paylaşılan koşuldan geliyordu.** Yalnız **diğer seriden**
  hesaplandığında medyan lift 2,18'den **1,46**'ya düşüyor. Aradaki fark aynı
  serinin paylaşılan mock hibridizasyonları ve aynı platformun teknik ortak
  varyansı. Leke-sız hali hâlâ dördüncü tabanı aşıyor (12 hesaplanabilir
  array'de 12/12, eşleşmiş fark medyanı **+0,0230**, `p = 0,0002`) — yani
  sorun gerçek olmaması değil, **tanımının keyfi olması**.
- **Tanımı küme üzerinde tek biçimli DEĞİL.** `GPL2029` ile `GPL3991`/`GPL3992`
  arasında **sıfır** prob-id örtüşmesi var (ölçüldü: 0; aynı ölçümde
  `GPL3991 ∩ GPL3992` = **4.895**, yani %37,9). Yani `GSE5814`'ün sekiz `GPL2029` array'i için
  seriler-arası bir tanım **hiç hesaplanamıyor**. "Hangi diğer array'ler
  besler" sorusu böylece serbest bir parametre olur, ve `A12`'den sonra
  ayarlanabilir bir parametre değişmez 7'nin yasakladığı şeyin ta kendisi.
- **İleriye dönük bir tahmin için mevcut değil:** yeni bir dupleks için aynı
  platformda bir transfeksiyon derlemesi gerektiriyor. Yayınlanmış önsellik
  (5 numaralı taban) tam bu boşluğu dışsal ve sabit bir tabloyla kapatıyor.

📌 **Ama raporlanması ZORUNLU, taban olarak değil tanı olarak.** Seriler-arası
hali, hesaplanabildiği foldlarda, kapsamıyla birlikte raporlanır. Sebebi tek
cümlede: dizi bilgisi kullanmayan bir derleme kovaryatı off-target'ları ifade
düzeyinden daha iyi sıralıyorsa, okuyucunun bunu bilmesi gerekir — ve bu
cümle `A12`'den sonra yazılamaz.

📌 **Dördüncüyü eklemek çıtayı YÜKSELTİYOR**, yani değişmez 7'nin yasakladığı
yönün tersi: bir tabanı sonradan *çıkarmak* ihlal olurdu, eklemek ihtiyattır.
`A5`'in satırı "üçü de" diyordu; dördüncüsü o satırın kendi cümlesinin
tamamlanması, ve bu fark burada yazılı çünkü `A12`'den sonra görünmez olurdu.

### 7.6 Skorun ayrışması — `P_silence` ve `Impact`, iki ayrı kolon

Bu planın en önemli yapısal kararı, ve sebebi tek cümlede: **referans seti bir
transkriptin düşüp düşmediğini ölçüyor, düşmesinin ne kadar kötü olduğunu
ölçmüyor.** O yüzden skorun doğrulanabilir yarısı ile doğrulanamayan yarısı
**aynı sayıya karışamaz**.

- **`P_silence`** — bir off-target transkriptin susturulma olasılığı.
  §2'nin birincil metriği **bunu** sıralar. §4.1'in etiketi tam olarak bunun
  gözlenmiş halidir, yani doğrulanabilir.
- **`Impact`** — susturma gerçekleşirse sonucunun ciddiyeti. Bu referans
  setinde **gözlenmiş karşılığı yok**. §10.1'de keşifsel olarak, `validated:
  false` ile duruyor.

🔴 **Yol haritası `A7` satırının kanal ataması KODDAN düzeltildi.** Satır
`Impact = g(variant_toxicity, execution_safety)` diyordu. Ama
`src/stage6_execution/execution_merger.py` dört girdiden üçünü *susturmanın
gerçekleşip gerçekleşmediği* üzerine kuruyor, ve `_normalize`'ın kendi
docstring'i bunu kelimesi kelimesine söylüyor: *"Higher score = more execution
risk (**more silencing activity expected**)"*. Girdi girdi:

| girdi | ne ölçüyor | hangi tarafa ait |
|---|---|---|
| `ago2_loading` | guide ipliğin Ago2'ye yüklenmesi | **`P_silence`** |
| `rbp_competition` | sitenin RBP'lerce kapatılması (ters çevrilmiş) | **`P_silence`** |
| `circrna_overlap` | circRNA sünger etkisi | **`P_silence`** |
| immün motifler | TLR aktivasyonu | `Impact` |

Yani `execution_safety`'yi bütün olarak `Impact`'a koymak, kendi sözleşmesine
göre bir **olasılık** kanalını **sonuç** tarafına yazmak olurdu. Ayrışmanın
bağlayıcı hali:

```
P_silence = f(sequence_specificity, biophysics_structure, epigenetic_context,
              ago2_loading, rbp_competition, circrna_overlap)
Impact    = g(variant_toxicity, immün motifler)
```

⚠️ **Ve bu, `Impact`'ın bugün site-başına içeriği olmadığını ortaya çıkarıyor.**
`execution_merger.py:152` immün sonucu `offtarget_immune.get(site_id,
sarna_immune)` ile okuyor — yani bir site için kayıt yoksa **saRNA düzeyindeki
tek değer** düşüyor. Dolayısıyla `Impact`'ın iki kanalından biri geniş ölçüde
**site-değişmez**, diğeri (`variant_toxicity`) ise aşağıda çürütülmüş bir vekil
üzerinde duruyor. Sonuç: `Impact` kolonu §4.4.2'nin geçerlilik ön koşuluna
**ayrıca** tabidir ve onu geçmesi beklenmemektedir; geçmezse `Impact` **sayı
olarak değil, bilinmiyor olarak** raporlanır (değişmez 2).

🔴 **`variant_toxicity`'nin bugünkü vekili çürütüldü, ve bu ön kayda yazılı.**
`cosmic_scanner.py` site başına kb başına COSMIC mutasyon yoğunluğu kullanıyor.
Lawrence ve ark. 2013 (PMID 23770567) naif mutasyon frekansının gen uzunluğu,
ifade düzeyi ve replikasyon zamanlamasıyla sürüklendiğini gösteriyor — naif
listelerindeki 450 genin 101'i **koku reseptörü**. Martincorena ve ark. 2017
(PMID 29056346) kodlayan mutasyonların **~%99'unun tolere edildiğini**
buluyor. Yani mutasyon yoğunluğu ile fonksiyonel önem arasındaki ilişki ters
değil, **yok**. Bu vekille hesaplanmış bir `Impact` kolonu bir ölçüm değildir
ve öyle etiketlenir.

📌 **İki kolon birleştirilmez.** Tek bir skor isteniyorsa birleştirme kuralı
**ayrı bir ön kayıt maddesidir** ve gerekçesi yazılır; özellikle çarpımsal form
(`P_silence × Impact`) kanıtsız bir etkileşim modeli varsayar — iki kat daha
olası bir susturmanın iki kat daha kötü olduğunu söyler, ki bunun hiçbir
dayanağı yok. Bu ön kayıt **iki kolonu** bağlar.

⚠️ **Arka plan kümesi `Impact` için yanlı, ölçüldü.** Bugünkü arka plan
kümesinin (boyutunun otoritesi `transcriptome_fetcher.py`'ın
`_BACKGROUND_GENES` tanımı) **tamamı** DepMap evreninde, yani etiket kapsamı
tam; ama **%40'ı** DepMap ortak-esansiyeli — küme kanser ve housekeeping
genleri etrafında elle küratörlendiği için taban orandan çok yukarıda. Bu kümede hesaplanan her
`Impact` AUROC'u **şişkindir** ve Bulgu-6 göçünden sonra yeniden
hesaplanmalıdır. Bu cümle burada, çünkü `A12`'den sonra "şişkin olduğunu
biliyorduk" demek bir sapma maddesi olur.


## 8. Durdurma kuralı

<Analiz ne zaman biter? "Sonuç anlamlı olana kadar koşturmak" bir kural
değil, ihlaldir.>

## 9. Negatif sonuç

<Hipotez doğrulanmazsa ne rapor edilecek ve nereye. Değişmez 7: negatif sonuç
kabul edilir ve bir yayın yolu vardır. Ağırlık, eşik ya da sabit ayarlayarak
pozitif sonuç aramak ihlaldir — ölü kanalları telafi etmek için eşik
indirmek de bu kategoridedir.>

## 10. Keşifsel (ön kayıt dışı)

Buraya yazılan hiçbir şey §2'nin birincil metriğine **taşınamaz**; §4.3'ün
kuralı buraya da geçerli. Her madde `validated:` bayrağıyla duruyor, çünkü
"keşifsel" kelimesi tek başına bir okuyucuya neyin ölçülmüş neyin
ölçülmemiş olduğunu söylemiyor.

### 10.1 `Impact` kolonu — `validated: false`

```yaml
impact_column:
  validated: false
  per_site: false        # immün kanal saRNA düzeyine düşüyor (§7.6)
  reason_not_validated: "bu referans setinde gözlenmiş karşılığı yok"
```

§7.6'nın ayırdığı doğrulanamayan yarı. **Dört ayrı sebeple** doğrulanamaz, ve
dördü de ölçülmüş ya da kaynaklı:

1. **Referans seti onu ölçmüyor.** §6.1'in sekiz accession'ı bir transkriptin
   düşüp düşmediğini ölçüyor; düşmenin sonucunu değil. ⚠️ Daha önceki bir
   ifade *"`Impact`'ın hiçbir gerçek referansı yok"* diyordu; o iddia
   2026-11-27'de ölçülüp **geri çekildi**. Doğru ifade: *siRNA off-target
   mikroarray'lerinde yok.* Susturmanın sonucunu ölçen veri **var**: DepMap
   CRISPR gene effect (24Q2, figshare DOI
   `10.25452/figshare.plus.25880521.v1`) ve DEMETER2 RNAi (figshare DOI
   `10.6084/m9.figshare.6025238.v6`). DEMETER2 bu projeye üç sebeple daha iyi
   oturuyor: HeLa onun içinde var (DepMap CRISPR'ın taranmış modellerinde
   **yok**), seed tanımı bu projeyle birebir aynı (McFarland ve ark. 2018,
   PMID 30389920, antisense ipliğin 1-7 ve 2-8'i), ve hücre-hattı başına seed
   etki matrisi yayınlanmış (≈15.386 7-mer × 712 hat).
2. **Yön uyuşmuyor.** DepMap, DEMETER2, LOEUF, pLI, CEG2 ve pHaplo'nun
   **hepsi kaybın** sonucunu ölçer. Bu bir *aktive edici* RNA aracı; off-target
   *aktivasyon* için eşleşen metrik **pTriplo** (Collins ve ark. 2022,
   PMID 35917817; `pTriplo ≥ 0,94` → 1.559 gen). Tek bir `Impact` kolonu iki
   yönü birlikte temsil **edemez**, ve hangi yönün raporlandığı yazılmak
   zorunda.
3. **Arıza yönü yanlış.** Bir fitness taraması ölümsüzleşmiş bir hatta ~3
   haftalık çoğalmayı ölçer. `gene effect ≈ 0` *"bu testte fitness kaybı
   yok"* demektir, **"güvenli" demez** — bir risk aracında bu, değişmez 2'nin
   yasakladığı yönde bir arızadır.
4. **Precedent yok.** Beş Europe PMC ve iki web sorgusunda, öngörülen
   off-target'ları gen esansiyelliğiyle ağırlıklandıran **tek bir yayın**
   bulunamadı. Sektör bunun yerine seed'i doğrudan bir **toksisite** bitiş
   noktasına bağlıyor (GalNAc-siRNA hepatotoksisitesi: Janas ve ark. 2018,
   PMID 29459660; Schlegel ve ark. 2022, PMID 35736224). Dolayısıyla
   esansiyellikle ağırlıklandırma burada **keşifsel** olarak durur ve sahip
   olmadığı bir precedent'e atıf **yapamaz**.

📌 **Ne yapılacağı, şimdiden bağlı:** `Impact` kolonu raporlanır, `validated:
false` etiketiyle ve yukarıdaki dört sebebin özetiyle. Esansiyellikle
ağırlıklandırma denenirse **yalnız keşifsel** olarak raporlanır, pTriplo
kolonuyla **birlikte**, ve hiçbir koşulda §2'nin birincil metriğine girmez.
`A6a`'nın karar kuralı `Impact`'tan hiçbir girdi almaz.

### 10.2 Diğer keşifsel analizler

<`A11`'in maddesi: pasajer-baskın dupleks alt kümesi (§7.2), ve ön kayıt
dışında kalan diğer okumalar.>

## Sapma günlüğü

Bu dosya kilitlendikten sonra plandan her sapma buraya **değil**,
`docs/PRE_REGISTRATION_v2.md`'ye yazılır. Bu bölüm kasıtlı olarak boştur.
