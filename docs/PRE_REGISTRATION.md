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
  ([Birmingham ve ark., *RNA* 2006](https://rnajournal.cshlp.org/content/12/7/1179.full)).
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

- Başarı eşiği: <sayı ve birimi>
- Bu eşik neden bu: <önceki ölçüm, literatür ya da güç analizi>
- Eşiğin altı: <ne sonuçlanır — bu da bir sonuçtur, değişmez 7>

## 5. Null modeli

<Gözlemi neyle karşılaştırıyorsun? Permütasyon, ampirik null, eşleştirilmiş
kontrol kümesi — ve kaç tekrar. Null yoksa hipotez test edilemez.>

Çoklu test düzeltmesi: <yöntem, örn. BH-FDR; ve q eşiği>

## 6. Örneklem ve veri

- Kapsam: <gen, hücre hattı, kaç site>
- Dışlama kuralları: <önceden, veriyi görmeden>
- Veri sürümleri: <kaynak + sürüm/accession; hepsi hg38>

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
