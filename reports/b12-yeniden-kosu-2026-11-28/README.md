# B12 — hazırlık ölçümleri (2026-11-28, madde KAPANMADI)

`B12` dört koşuyu yeniden koşmak istiyor. Bu dizin, koşuya *başlamadan önce*
alınan ölçümleri taşıyor. **Madde açık**; aşağıdakiler bir sonraki oturumun
yeniden türetmesi gerekmeyen, ölçülmüş girdiler.

## 1. Kabul kriteri bugünkü haliyle KARŞILANAMAZ

Kriter "`verify-run` dördünde de temiz" diyor. Mevcut **en yeni** koşuda
(`VEGFA_HeLa`, 2026-11-26) `verify-run` **6 kontrolün 4'ünde FAIL** veriyor:
`degeneracy`, `ranges`, `fallback`, `dynamic_range`.

Bunların bir kısmı koşunun *eskiliğinden* gelir ve yeniden koşmakla kalkar;
bir kısmı **canlı koddan** gelir ve kaç kere koşulursa koşulsun kalır —
örneğin `HIGH_RISK`/`DANGEROUS` sınıflarının erişilemezliği (`F1`, TODO) ve
`sequence_specificity`'nin sabit `1.0`'a ezilmesi (`C1`, TODO).

Yani sorulması gereken "temiz mi" değil, **"her kalıntı bulgu adı konmuş açık
bir yol haritası maddesine atfedilebiliyor mu"**. Bu ölçülebilir ve yeniden
koşunun gerçekten kurabileceği şey bu. Eşiği indirmek değişmez 7 ihlali olurdu;
eşiğin neyi ölçtüğünü yazmak değil. Kriterin düzeltilmesi `B12` kapanırken
satıra işlenmeli.

`olcum.py` bu atfı makine-okunur üretiyor: eski ve taze koşunun bulgu
**kümelerini** `(table, metric)` kimliği üzerinden diff'liyor, ve "yeniden
koşuyla kalkan" / "YENİ" / "değişmeyen" olarak ayırıyor. Eski tarafın sayıları
kayıtta *eskilik kanıtı* olarak etiketli — ölçüm olarak değil (`B12`/`B17`/`B18`
yasağı).

## 2. Eski koşular düzeltilmiş ΔG koduna girdi bile veremiyor

`C3d` (DONE) ΔG eşiklerini sildi ve `delta_g_calculator.py:83` artık stage
2'nin yaydığı `target_window`'u okuyor. Eski `stage2_offtargets.json`'da o alan
**hiç yok** (`src/core/models.py:140`'ta `None` varsayılanı). Ölçüldü: eski
site anahtarları `gene, transcript_id, region, seed_match_type, mismatches,
alignment_score, tx_start, tx_end, site_id` — `target_window` yok.

Yani eski koşulardaki ΔG yalnız yanlış değil, **düzeltilmiş kodun çalıştırılamaz
olduğu** bir girdi üzerinde üretilmiş. Yeniden koşunun `degeneracy` ve `ranges`
bulgularını ΔG tarafında kaldırması bekleniyor; kaldırmazsa bu `C3e`'ye (TODO)
ait yeni bir bulgudur, `B12`'ye değil.

## 3. Koşuların taşıması gereken commit'ler

Kriterin "güncel kod" ifadesinin ölçülebilir hali: her koşunun
`manifest.json`'daki `code.head_commit`'i aşağıdakilerin **hepsini** içermeli
(`git merge-base --is-ancestor`).

| madde | commit | tarih |
|---|---|---|
| B1 (ClinVar sorgusu) | `397978f` | 2026-11-18 |
| B2 (fallback sentineli) | `c8d7f8c` | 2026-11-18 |
| B4 (gnomAD işareti) | `9eb0dcf` | 2026-11-18 |
| R12a (arka plan kapsamı) | `a166a18` | 2026-11-24 |
| B17 (pinlenmiş Ensembl) | `f49096e` | 2026-11-27 |
| B18 (DepMap ID'leri) | `b56da0d` | 2026-11-27 |
| C3d (ΔG eşikleri silindi) | `a7b977f` | 2026-11-27 |

## 4. Kapsam nereden okunacak

"Tam arka plan kapsamı" `stage2_seed_hits.json` → `background_coverage`
(`requested`, `resolved`, `fraction`; `seed_aligner.py:444`). Mevcut dört
koşunun **hiçbirinde** bu alan yok — `R12a` onlardan sonra geldi, yani alanın
varlığı tek başına koşunun `R12a` sonrası olduğunun işareti.

Pinlenmiş host canlı doğrulandı: `sep2025.rest.ensembl.org` sürüm **115** =
`config/config.yaml`'ın beyan ettiği 115.

## 5. Yeniden koşmadan önce alınan anlık görüntü

`results/` git'te izlenmiyor, yani üzerine yazmak tek kopyayı yok eder. Dört
koşu oturum scratchpad'ine kopyalandı (2,8 MB) ve bütünlük hash'i:

```
51ac4206b7cc59093b79f713ac12b1a68185bd34762b55730543573e84fab421
```

(`find . -type f | sort | xargs sha256sum | sha256sum`). ⚠️ Scratchpad kalıcı
değil. Kalıcı kayıt gerekiyorsa dört `manifest.json` commit'lenmeli — ham
çıktılar değil, çünkü onlardan sayı alıntılamak zaten yasak.

## Durum

Deneme koşusu (`VEGFA_HeLa`, izole çıktı + izole cache) 02:27 UTC'de başladı ve
bu kayıt yazılırken stage 2'de Ensembl'den 182 geni çekiyordu — 504 yok, cache
büyüyor. Kullanım limiti nedeniyle sonucu bu oturumda ölçülemedi.
