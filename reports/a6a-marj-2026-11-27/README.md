# A6a — ön kaydın karar kuralının ölçüm kaydı (2026-11-27)

`docs/PRE_REGISTRATION.md` §4.4'teki **her sayı** burada ölçüldü. Dizinin
varlık sebebi tek cümlede: ön kayıt kilitlendikten sonra o sayıların nereden
geldiğini kimse yeniden türetemez, ve türetilemeyen bir eşik ayarlanabilir bir
eşiktir.

```bash
python3 reports/a6a-marj-2026-11-27/olcum.py
```

| dosya | ne |
|---|---|
| `olcum.py` | ölçümün tamamı; GEO'dan indirir, önbelleğe alır, dört tabloyu üretir |
| `marj.json` | 20 array × 5 tahmin edicinin AP'si, ve yedi çiftin eşleşmiş fark istatistikleri |
| `cozunurluk.json` | kademe sayısına göre bağlantı açıklığı (medyan ve en kötü array) |
| `geo-onbellek/` | ham GEO SOFT metinleri — **izlenmiyor** (`.gitignore`), tanım gereği yeniden indirilebilir ve ~40 MB |

## Neden bu ölçüm modelden bağımsız

Marjı modelin çıktısını gördükten sonra sabitlemek değişmez 6'nın ihlalidir, ve
`A12` kilidinden sonra farkedilmesi imkânsıza yakındır. O yüzden ölçüm yalnız
**hiçbir dizi bilgisi taşımayan** tahmin ediciler üzerinde yapıldı:

- `B4` — `log10(INTENSITY1)`, mock kanalı yoğunluğu (§7.5'in dördüncü tabanı),
- `VAR` — aynı probun mock yoğunluğunun diğer array'lerdeki yayılımı; hem
  diziden hem etiketten bağımsız,
- `VOL` — probun diğer array'lerdeki medyan `|VALUE|`'su, yani genel
  oynaklık; diziden bağımsız, ama **diğer seed'lerin** sonuçlarını kullanıyor,
- `R1`, `R2` — iki bağımsız rastgele sıralama; saf örnekleme tabanı.

orcSONAR'ın hiçbir çıktısı okunmadı, ve bu dizinde orcSONAR'ın bir skoru yok.

## Birim ve etiket

Birim §6.2'nin **ayrık 2-8 seed heptameri**; her seed için bir array seçildi ve
kol başlıkları GEO'dan doğrulandı. `GSE5814`'ün 1. ve 9-19. pozisyon mutantları
yabani-tip seed'i aynen taşıdıkları için listede **yok** — §7.1'in sızıntı
kuralı. `GSE5291` kanal-başına yoğunluk yayınlamadığı için bu ölçümde yer
almıyor (§7.5'in ikinci düzeltmesi), yani 20 seed, 43 değil; `σ̂_d` bu 20
üzerinden kestirildi ve §4.4.6 bunu ilan ediyor.

Etiket §4.1 (`PVALUE < 0.01` ve `VALUE < 0`), evren §6.3 (Jackson'ın
yayınlanmış filtresi `LOGINTENSITY ≥ −1`, artı `QUALITY == 1`).

## Ne bulundu

1. İki eşit ucuzlukta, etiketten ve diziden bağımsız tahmin edici arasındaki
   **tipik AP farkı 0,0162** — §4.4.1'in marjı buradan geliyor. İki rastgele
   sıralama arasındaki sd ise yalnız 0,0028, yani marj (0,020) saf örnekleme
   gürültüsünün **7,1 katı** — marjı sınırlayan şey örnekleme hatası değil,
   "hangi ucuz kovaryatı seçtiğiniz" belirsizliği.
2. Sabit bir tahminci için AP'nin taban oranına eşit olduğu (kimlik) sayıyla
   doğrulandı, ve bağlantı açıklığı **0,9725** — yani sıralamayı skor değil
   bağlantı kırma belirliyor. §4.4.2'nin ön koşulu bunun üzerine kuruldu.
3. **12 ayrık değer yetmiyor.** `_clamp` kaldırılsa bile bugünkü ham seed
   skorunun açıklığı 0,0518, marjın iki buçuk katı. Açıklığın m/2'nin altına
   indiği ilk kademe **500**.
4. Dizi bilgisi kullanmayan üçüncü bir tahmin edici (`VOL`) 20 seed'in
   20'sinde de `B4`'ü aşıyor, medyan lift **2,19**'a karşı **1,18**. §7.5'in
   taban envanterinde yok; yol haritasına `A5b` olarak yazıldı.
