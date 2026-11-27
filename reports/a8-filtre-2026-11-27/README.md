# A8 — tespit edilebilirlik filtresinin ölçüm kaydı (2026-11-27)

Ön kayıt §6.4'teki her sayı burada ölçüldü. Bir evren tanımı, eşiği ölçülmeden
yazılırsa sonradan ayarlanabilir bir parametredir.

```bash
python3 reports/a8-filtre-2026-11-27/olcum.py
```

| dosya | ne |
|---|---|
| `olcum.py` | ölçümün tamamı: filtrenin bedeli, eşik ızgarası, `QUALITY` sapması |
| `olcum.json` | array başına n/taban/atılan pozitif, ızgara, ve lift sapmaları |
| `geo-onbellek/` | ham GEO array tabloları — **izlenmiyor** (`.gitignore`) |

Dokuz array, üç seri: `GSE5814` (3), `GSE5769` (3), `GSE5291` (3). Etiket §4.1
(`PVALUE < 0.01` ve `VALUE < 0`).

## Üç bulgu

**1. Filtre bedava değil.** `LOGINTENSITY ≥ −1` evreni medyan **23.441 →
11.009** proba indiriyor, taban oranını **0,0284 → 0,0543**'e çıkarıyor, ve
**pozitiflerin %8,7'sini atıyor** (aralık %4,6-12,8). Atılan pozitifler
PR-AUC'nin tavanını düşürür; sebebi model kalitesi değil evren tanımıdır, ve
bu ayrım ancak önceden yazılırsa korunur.

**2. Daha gevşek bir eşik neredeyse hiç pozitif atmıyor** — `−1,25`'te kayıp
%2,3, `−1,5`'te %0,3. `−1` yine de birincil, çünkü kaynak makalelerin kendi
filtresi ve karşılaştırılabilirlik §4.1'in gerekçesiyle aynı. Izgaranın
tamamı §6.4.3'te ilan edildi; seçimi denetlenebilir yapan şey ikisinin bir
arada olması.

**3. `GSE5291`'in eksik `QUALITY` kolonu zararsız, ve bu ÖLÇÜLDÜ.** Kolonu
olan altı array'de kolon yok sayılarak modelden bağımsız bir tahmin edicinin
(mock kanalı) lift'i yeniden hesaplandı: medyan sapma **−0,79%**, en büyüğü
**−4,88%**, dördünde **tam sıfır**. İşaret **negatif** — yani kolonu olmayan
seri lift'i *aşağı* yönde sapıyor, avantaj kazanmıyor. Kural bu yüzden
"kolonun yokluğu bilinmeyen kalitedir, kötü kalite değil" olarak yazıldı
(değişmez 2'nin yönü).

## Reddedilen seçenek: CCLE tabanlı evren

Yol haritası satırı evreni *"CCLE elde"* tarif ediyordu. Reddedildi — ama
**ulaşılamadığı için değil**: HeLa'nın DepMap 24Q2'de RNA profili var
(`ACH-001086` → `PR-pI7d1A`, unstranded, BROAD; otoritesi
`data/external/depmap/OmicsProfiles_24Q2.csv`, manifest'te checksum'ıyla, 215
KB — indekslediği 460 MB'lık ifade matrisi değil).

Sebep bir **yapı** sebebi: etiket array üzerinde tanımlı, o yüzden evren de
array üzerinde tanımlı olmalı. Dışsal bir evren array'in hiç ölçmediği
genleri içeri alır (etiketlenemez, yani garantili negatif → tabanı düşürür,
`lift`'i şişirir: modeli iyi gösteren yön) ve array'in ölçüp aşağı çağırdığı
genleri dışarı atar (gerçek pozitifleri siler). §6.4.1 bu iki yönü ayrı ayrı
yazıyor, ve CCLE'nin **tahmin edicinin girdisi** olarak kullanılmasına engel
olmadığını da: eşleşmek zorunda olan şey evren ile etiket.
