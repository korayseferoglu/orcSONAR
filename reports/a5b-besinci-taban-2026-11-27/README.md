# A5b — beşinci taban kararının ölçüm kaydı (2026-11-27)

`A6a`'nın marj ölçümü, ön kayıt §7.5'in taban envanterinde **olmayan** bir
tahmin edicinin dördüncü tabanı 20 seed'in 20'sinde de aştığını gösterdi. Bu
dizin o bulgunun ne olduğunu ve neden §7.5'e **yayınlanmış** bir tabanın
eklenip **küme-içi** halinin reddedildiğini ölçüyor.

```bash
python3 reports/a5b-besinci-taban-2026-11-27/olcum.py
```

| dosya | ne |
|---|---|
| `olcum.py` | ölçümün tamamı: dört tahmin edici, 20 ayrık seed, artı `GSE5291` kapsam kontrolü |
| `olcum.json` | array başına AP'ler, medyan lift'ler, §4.4'ün testinin sonuçları, prob-id örtüşmeleri |
| `geo-onbellek/` | ham GEO array ve platform tabloları — **izlenmiyor** (`.gitignore`), yeniden indirilebilir |

Beşinci tabanın veri tablosu (`DE_Prior.txt`) depoda **değil**:
`data/external/de_prior/` altında, kaydı `data/external/manifest.json`'da
checksum'ıyla. Lisansı **beyan edilmemiş** (repoda `LICENSE` yok), o yüzden
yeniden dağıtılmıyor; manifest bunu açıkça yazıyor.

## Dört tahmin edici, hiçbiri dizi bilgisi kullanmıyor

| ad | ne | sızabilir mi |
|---|---|---|
| `B4` | `log10(INTENSITY1)` — §7.5'in dördüncü tabanı | hayır |
| `DEP` | Crow ve ark. 2019'un yayınlanmış `DE prior`'ı | **hayır — dışsal tablo** |
| `VOLw` | probun **bu setteki** diğer array'lerdeki medyan `\|VALUE\|`'su | evet: aynı seri, aynı mock |
| `VOLx` | aynısı, yalnız **diğer seriden** | hayır, ama tanımı tek biçimli değil |

## Ölçülenler

| nicelik | değer |
|---|---|
| medyan lift — `B4` | 1,18 |
| medyan lift — `DEP` | **1,27** (14/20'de `B4` üstünde) |
| medyan lift — `VOLw` | **2,18** (20/20'de `B4` üstünde) |
| medyan lift — `VOLx` | **1,46** (12 hesaplanabilir array'de 12/12) |
| `DEP` − `B4`, medyan fark | +0,0063 · `p(d>0) = 0,041` · `p(d>m) = 0,995` |
| `VOLx` − `B4`, medyan fark | +0,0230 · `p(d>0) = 0,0002` · `p(d>m) = 0,259` |
| prob-id örtüşmesi `GPL2029 ∩ GPL3991/3992` | **0** |
| prob-id örtüşmesi `GPL3991 ∩ GPL3992` | 4.895 (%37,9) |
| `DEP` prob→gen eşleşmesi | %66,1-87,4 |
| `GSE5291`'de `DEP` medyan lift | **1,33** (5 array) · `INTENSITY1` **yok**, `QUALITY` **yok** |

## Kararın üç ayağı

1. **Yayınlanmış önsellik taban olur.** Dışsal olduğu için kilitlenen kümeden
   sızamaz ve "hangi diğer array'ler besler" diye bir serbest parametresi yok.
   Crow ve ark. onu 635 veri setinde `mean AUROC, 0.83 ± 0.1` ölçmüş, ve
   §7.5'in 1-4 numaralı tabanlarının sınıfını da ölçmüş:
   *"None of these properties is nearly as predictive as the DE prior (mean
   across all categories, 0.55"*. Yani 0,83 sınıfı listede yoktu.
2. **Bu sette önsellik dördüncü tabandan pratik olarak güçlü değil** (medyan
   fark +0,0063, marj 0,020). Sebebi ölçülü: önselliğin en üst sıraları
   cinsiyet kromozomu genleri, tek hücre hattında oynamıyorlar. Buna rağmen
   eklendi, çünkü (i) farklı bir alternatif açıklamayı kapatıyor ve (ii)
   `GSE5291`'in 18 seed'inde **hesaplanabiliyor**, dördüncü taban ise değil.
3. **Küme-içi oynaklık taban OLMAZ, tanı olur.** Gücünün yarısı paylaşılan
   mock/platform varyansından geliyor (2,18 → 1,46), ve `GPL2029` ile diğer
   platformlar arasında **sıfır** prob-id örtüşmesi olduğu için seriler-arası
   tanımı kümenin sekiz array'inde hiç hesaplanamıyor. Tanımı keyfi olan bir
   taban `A12`'den sonra ayarlanabilir bir parametreye dönüşür.

## Geçerken ölçülen, kendi satırına yazılan

`GSE5291`'in array tablosunda **`QUALITY` kolonu yok** (ölçüldü: 5 array'in
5'inde de). Evren filtresi bunu yokluğu "kalitesiz" sayarak uygularsa serinin
tamamı silinir. `A8`'in satırına yazıldı; bu dizin onu düzeltmiyor.
