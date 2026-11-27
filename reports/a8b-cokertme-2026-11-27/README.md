# A8b — prob→gen çökertmesinin ölçüm kaydı (2026-11-27)

`A8` biterken bulunan boşluk: §6.3 birimin **gen** olduğunu söylüyor, §2 "her
**geni** sıralar" diyor, ama §4.1'in etiketi ve §6.4'ün filtresi **prob**
düzeyinde. Aradaki adım yazılı değildi. Bu dizin o adımın masum olmadığını
ölçüyor.

```bash
python3 reports/a8b-cokertme-2026-11-27/olcum.py
```

| dosya | ne |
|---|---|
| `olcum.py` | dört çökertme kuralı, dokuz array, üç platform |
| `olcum.json` | array başına prob/gen sayıları, çelişki sayıları, kural başına pozitif ve taban oranı |
| `geo-onbellek/` | ham GEO array ve platform tabloları — **izlenmiyor** |

## Boşluk ne kadar büyük

| ölçüm | değer |
|---|---|
| birden fazla prob taşıyan sembol oranı | **%13,9-20,5** (tek sembolde en çok 15 prob) |
| pozitif içeren çok-problu genlerde **etiket çelişkisi** | **%59-84** |
| sembole eşleşmeyen ve gen evreninden düşen prob | **%8,5-17,2** |

Yani problar aynı gen için sık sık **farklı** şey söylüyor, ve hangisini
dinlediğin pozitif kümesini değiştiriyor.

## Dört kuralın ölçülmüş yönü

| kural | medyan taban | `maxmean`'e göre pozitif | etikete bakıyor mu |
|---|---|---|---|
| `any` | 0,0604 | **+5,4%** | evet (OR) |
| `best-p` | 0,0603 | **+5,4%** | **evet, doğrudan** |
| **`maxmean`** (birincil) | **0,0577** | — | **hayır** |
| `all` | 0,0519 | **−9,6%** | evet (AND) |

Taban oranı `lift`'in bölenidir, yani kuralı sonucu gördükten sonra seçmek
doğrudan metriği seçmektir. Seçilen kural en çok ya da en az pozitif üreten
değil, **kararı etiketten bağımsız veren** kural: `maxmean` seçim
istatistiğinde (mock kanalı yoğunluğu, yoksa `LOGINTENSITY`) etiketi hiç
kullanmıyor.

📌 `best-p` ("en anlamlı probu al") masum görünüyor ama ölçüm onun `any` ile
**neredeyse birebir aynı** sonucu verdiğini gösteriyor — yani sessizce
pozitif kümesini maksimize ediyor. §6.5.1 onu bu yüzden açıkça yasaklıyor.

## Kaynak ve sınırları

Yöntem Miller ve ark.'nın `collapseRows`'undaki `MaxMean`
(**BMC Bioinformatics 2011;12:322, PMID 21816037**). Atfın söyleyebileceği şey
sınırlı ve §6.5.1 üç sınırı da yazıyor:

1. Makale **diferansiyel ifade analizini hiç ele almıyor** — önerisi
   çalışmalar-arası tutarlılık ve koekspresyon üzerine.
2. Kendi çekinceleri: *"the optimal collapsing strategy depends on the
   analysis goal"*; varsayılanlar *"often, but not always, the best
   parameters to use"*; tam kanda *"should not be used in this situation"*.
3. Eşitlik kuralı **değiştirildi**: `collapseRows` rastgele seçiyor, bu ön
   kayıt **en küçük prob kimliğini** seçiyor — ön kayıtlı bir evren rastgele
   kurulamaz.

## Skor tarafı

Site → gen **maksimum**, `toplam` değil. `toplam`/`sayı` site sayısında
monotondur ve site sayısı tam olarak §7.5'in 1. tabanı (3′UTR 7mer-m8 sayısı)
ile 3. tabanı (uzunluk) — toplamla çökertmek modeli aşması gereken tabanın
kısmen kendisi yapardı. `toplam` ilan edilmiş duyarlılık analizi olarak
raporlanır.
