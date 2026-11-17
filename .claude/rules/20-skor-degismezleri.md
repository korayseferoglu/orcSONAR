---
paths:
  - "src/scoring/**"
  - "src/stage7_*/**"
  - "src/reporting/**"
---

# Skorlama — kodda gerçekten ne oluyor

`src/scoring/integrator.py`'de uygulandığı haliyle. Beş domainin hepsi `base_score`'a
girer ve **`apply_cell_modifier` `scoring_weights`'i hiç okumaz**:

```
base_score    = 0.20·sequence_specificity + 0.15·variant_toxicity
              + 0.25·biophysics_structure + 0.20·epigenetic_context
              + 0.20·execution_safety          # config/config.yaml, toplamı 1.0
cell_activity = 0.40·atac + 0.40·expression + 0.20·execution   # hardcoded
cell_modifier = 0.30 + 1.40·cell_activity                      # [0.3, 1.7], hardcoded
final_risk    = clamp(base_score × cell_modifier, 0, 1)

risk sınıfı: [0, 0.3) SAFE · [0.3, 0.6) WARNING · [0.6, 0.8) HIGH_RISK · [0.8, 1] DANGEROUS
```

## Ağırlıklar göründükleri anlama gelmiyor

Epigenetik ve execution sinyalleri **hem** `base_score`'a **hem** `cell_modifier`'a
giriyor — çift sayım (AUDIT.md Bulgu-7). `config.yaml`'daki bir ağırlığı değiştirmek
skoru öngörülen oranda değiştirmez. Bağımsız yorumlanamazlar. Düzeltme: yol haritası `C4`.

Ayrıca `execution_score` = 0.2232 = epigenetik ortalamanın aynısı → üçlü sayım.

## `cell_modifier` koşu başına tek sabittir

`epigenetic_merger.py:137-147` `cell_context`'i **tüm sitelerin ortalaması** olarak
üretiyor; `risk_classifier.py:73` aynı sözlüğü her siteye veriyor. Sonuç: tek çarpan.

*Ölçüm: `final/base` oranı 6. haneye kadar sabit; Spearman(base, final) = 1.000000
dört koşunun dördünde.* Monoton sabit bir çarpan **sıralamayı değiştiremez** — yani
"hücre hattına özgü risk" iddiası bugün kodda matematiksel olarak yok. Düzeltme: `B6`.

Site-başına ATAC/ifade **zaten hesaplanıyor** ve ortalamaya ezilerek atılıyor.

## HIGH_RISK hakkında doğru cümle

Dört koşu da 0.298-0.408 aralığında, üst sınıflar hiç görülmüyor. Ama **nedeni önemli,
çünkü düzeltmenin yerini değiştiriyor:**

| | gereken base | tavan | sonuç |
|---|---|---|---|
| HIGH_RISK (final ≥ 0.6) | 0.741-0.848 | 0.836 (biyofizik bugünkü 0.345 tavanıyla) | **erişilebilir, ulaşılmamış** |
| DANGEROUS (final ≥ 0.8) | ≈1.05 | 0.836 | gerçekten erişilemez |

Yani HIGH_RISK *matematiksel olarak imkânsız* değil — **kanallar ölü olduğu için**
ulaşılmıyor: `_NEUTRAL_SIGNAL = 0.0` (`B2`) + intronik lokuslar (`D2`). Doygunluk sabiti
birinci mertebe etken **değil**: `_ATAC_SAT`'ı 50 kat düşürmek eşiği yalnız
0.789 → 0.728 indiriyor.

⚠️ **Eşikleri `B2` ve `D2` bitmeden yeniden kalibre etme.** Aksi halde ölü kanalları
telafi etmek için eşik indirmiş olursun — değişmez 7'nin ihlali.

## Bilgi taşımayan kanallar

- `sequence_specificity` 41/41 sitede **1.0** — ham skorlar 8.0-14.5 aralığında 12 ayrık
  değer taşıyor ve `_clamp` hepsini eziyor. 0.20 ağırlık sabit bir offset. Düzeltme `C1`;
  yerine gelecek haritalama bir **modelleme kararıdır** ve ön kayda yazılır (`A10`).
- `biophysics_structure` analitik tavanı **0.345** — ΔG ölü (41/41 site aynı +31.10).
- `execution_safety` 41 sitede **2** farklı değer.
- Nominal 1.00 ağırlığın **%35'inden azı** gerçek bilgi taşıyor.

## Ölü modül

`src/scoring/domain_scores.py`'ın **sıfır üretim çağıranı** var, ama ikinci ve çelişkili
bir satürasyon sabitleri seti (5 kata kadar farklı) ve ters bir RBP işareti taşıyor. En
büyük test dosyasındaki 91 testin 44'ü **onu** test ediyor — `test_h3k27me3_represses_
active_histones` yeşil geçerken üretimde h3k27me3 hiç bağlı değil.

Silinecek (`B8`), ama **önce o 44 testin davranışsal niyeti üretim yoluna aktarılmalı**:
o testler projedeki tek yerde yazılı niyeti taşıyor.

## `site_id` sözleşmesi

Site kimliği `OffTargetSite.site_id`, `src/core/models.py`'de bir `@computed_field`:
`gene:transcript:chrom:start`. Stage 2 üretir, diğer her aşama **birebir** anahtar olarak
kullanır — **dizgiyi asla yeniden kurma**, o kayma Bulgu-2'nin sebebiydi. Alan sırası
yük taşıyor (`epigenetic_merger` 0. alanı gen, HTML şablonu 1. alanı transkript sayar);
`tests/unit/test_models.py::test_site_id_layout` pinliyor.

⚠️ Aşamaların bir lokusta **anlaşması**, o lokusun **doğru** olduğu anlamına gelmez.
