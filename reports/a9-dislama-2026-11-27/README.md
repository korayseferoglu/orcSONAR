# A9 — on-target ve ikincil etki dışlamasının ölçüm kaydı (2026-11-27)

İki dışlama konuşuluyor ve **yönleri zıt**. Bu dizin ikisinin de yönünü ve
büyüklüğünü ölçüyor.

```bash
python3 reports/a9-dislama-2026-11-27/olcum.py
```

| dosya | ne |
|---|---|
| `olcum.py` | üç ölçüm: hedef genin kendisi, SIGNOR'daki alt akış, silmenin yönü |
| `olcum.json` | array başına hedef probu/etiketi/`log2FC`'si, SIGNOR alt akış listeleri, silme yönleri |
| `geo-onbellek/` | ham GEO array ve platform tabloları — **izlenmiyor** |

## 1. Hedef genin kendisi: dışlanması zorunlu, etkisi küçük

On array'de ölçüldü: hedef **7'sinde pozitif**, `log2FC` **−1,13 … −4,00**.
İki array'de hedefin **probu hiç yok** (`Luc` insan geni değil; diğerinde prob
§6.4'ün evrenine girmiyor). Bir array'de (`GSM134317`, `PIK3CA`) on-target
**pozitif değil** (`log2FC +0,002`) — §7.2'nin *"hedef-üstü susturma > %85"*
filtresi o kolu zaten dışlıyor.

Büyüklük: birinci sıradaki bir gerçek pozitifin AP'ye katkısı `1/P`, medyan
**0,00165** — §4.4'ün marjının (0,020) yaklaşık **on ikide biri**. Yani
dışlama **yapı** gereği zorunlu, sayısal etkisi küçük. Kayıtta durmasının
sebebi: sonradan "dışlama ağır iş yaptı" denmesini engellemek.

## 2. "Bilinen doğrudan alt akış" bir küme olarak YOK

SIGNOR'un **31.020** insan nedensel ilişkisi transkripsiyonel mekanizmaya
süzüldüğünde, bu setin on hedef geni için:

| hedef | transkripsiyonel alt akış |
|---|---|
| `MAPK14` | **4** — `CCND1`, `COL1A1`, `HBB`, `JUNB` |
| `VHL` | **1** — `SPARC` |
| `PLK1`, `PIK3CA`, `PIK3CB`, `SOS1`, `PRKCE`, `MPHOSPH1`, `SOD1`, `GAPDH` | **0** |

**Toplam beş gen.** ⚠️ Bu veritabanı hakkında bir cümle, biyoloji hakkında
değil: `VHL`'nin gerçek programı HIF üzerinden yürür ve SIGNOR onu taşımıyor.
İkincil etkiler **var**; sabit bir kaynaktan **sayılamıyor**. Sayılamayan bir
kümeyi dışlamak listeyi *bizim kürasyonumuz* yapar — bir serbest parametre.

## 3. Silmenin yönü — ve ilk simülasyonum yanlış modeli ölçüyordu

Pozitifleri **rastgele** silmek AP'yi *düşürüyor* ve `lift`'i neredeyse hiç
oynatmıyor. Ama elle küratörlenmiş bir "ikincil etki" listesi rastgele
değildir: tahmin edicinin **kaçırdığı** pozitiflerle korelasyonludur.

| silinen pozitif | rastgele ΔAP | rastgele Δlift | kaçırılanlar ΔAP | **kaçırılanlar Δlift** |
|---|---|---|---|---|
| %2 | −0,0015 | +0,0008 | +0,0002 | **+0,024** |
| %5 | −0,0037 | +0,0025 | +0,0004 | **+0,062** |
| %10 | −0,0076 | +0,0018 | +0,0007 | **+0,134** |
| %20 | −0,0155 | +0,0059 | +0,0006 | **+0,300** |

Asimetri burada: böyle bir liste **AP'yi neredeyse hiç** değiştirmezken
**raporlanan `lift`'i** sertçe yükseltiyor. §4.4'ün karar kuralı AP biriminde
olduğu için bağışık; §2'nin zorunlu kıldığı `lift` değil. §6.6.2'nin yasağı
tam o başlık sayısını koruyor.
