# A10b — G:U sallantısının ağırlığının ölçüm kaydı (2026-11-27)

`alignment_score` her pozisyon için {Watson-Crick **+1,0**, G:U **+0,5**,
eşleşmezlik **0**} veriyor. `A10` haritalamayı ön kaydetti ama bu sabit
skorun **içinde** ve sıralamayı değiştiriyor — bir G:U ile bir eşleşmezlik
arasındaki fark tam olarak bu sayı. Ön kayıtta hiçbir yerde
gerekçelendirilmemişti.

```bash
python3 reports/a10b-gu-agirligi-2026-11-27/olcum.py
```

| dosya | ne |
|---|---|
| `olcum.py` | iki ölçüm: seed bölgesinde G:U oluşuyor mu, ve Turner oranları |
| `olcum.json` | ikisinin de çıktısı |

Ağ gerekmiyor: ölçülen her şey depoda — kod, `config/config.yaml` ve projenin
kendi Turner tabloları. `data/` yalnız **okunuyor** (değişmez 1).

## 1. Ağırlık seed bölgesinde hiç uygulanmıyor

İndeks seed'in **tam ters komplementeri** üzerine kurulu, yani bulunan her
sitede seed'in yedi pozisyonu Watson-Crick. Sentetik bir transkriptle —
seed dışı her pozisyonu bilerek bozan bir G dolgusuyla — ölçüldü:

```
saRNA n=20, seed=CAACCAU, ters komplementer=AUGGUUG
pos=40: skor=13,5, eşleşmezlik=6, G:U(toplam)=1, seed eşleşmezliği=0, seed'de G:U=0
```

Yani sabit yalnız **seed dışı** pozisyonlara uygulanıyor. İki sonucu var:

- **Alanın G:U kanıtı bu sabiti gerekçelendiremez**, çünkü literatürün
  tartışması seed **içindeki** sallantılar üzerine. PITA'nın web aracı bile
  seed'de "tek bir G-U sallantısı" seçeneği sunuyor — alan bunu ayarlanabilir
  bir seçenek olarak görüyor, yerleşmiş bir ağırlık olarak değil.
- Sabitin fiilen derecelendirdiği şey **seed dışı eşleşme**, oysa §1'in
  hipotezi seed-aracılı susturma hakkında. O terimin mekanizmadaki rolü
  doğrulanmamış bir varsayım ve §7.8.1 bunu beyan ediyor.

## 2. 0,5 termodinamikten türetilemez

`rna.stack.dg`'nin altı 4×4 yığın tablosundan, G:U yığınlarının ΔG'si aynı
bağlamdaki Watson-Crick yığınlarının medyanına oranlandı:

| ilk çift | G:U yığın ΔG | WC medyanı | oran |
|---|---|---|---|
| A:U | −1,40 / −0,60 | −1,60 | +0,37 … +0,87 |
| C:G | −2,10 / −1,40 | −2,25 | +0,62 … +0,93 |
| G:C | −2,50 / −1,50 | −2,85 | +0,53 … +0,88 |
| G:U | −0,50 / **+1,30** | −1,75 | **−0,74** … +0,29 |
| U:A | −1,30 / −1,00 | −1,70 | +0,59 … +0,76 |
| U:G | −0,50 / **+0,30** | −1,20 | **−0,25** … +0,42 |

**Oran −0,74 … +0,93, medyan 0,56.** Asıl olgu: G:U yığın ΔG'si
**−2,50 … +1,30 kcal/mol**, yani **işaret değiştiriyor** — bazı bağlamlarda
bir G:U kararsızlaştırıcı. Watson-Crick yığınları ise istisnasız
**−3,40 … −0,60**, her zaman kararlılaştırıcı. (Bu ikinci satır kapının
kontrol ölçümü: işaret değişimi G:U'ya özgü, tabloların gürültüsü değil.)

**Sonuç:** 0,5 ölçülen aralığın içinde ve medyanına (0,56) yakın, yani
**makul** — ama hiçbir sabit, işareti bağlama göre değişen bir niceliği
temsil edemez. O yüzden 0,5 **keyfi olarak donduruldu**, gerekçesi "makul
aralıkta" olması, "doğru değer" olması değil. İlan edilmiş duyarlılık
ızgarası `{0,0, 0,5, 1,0}` her zaman raporlanır.
