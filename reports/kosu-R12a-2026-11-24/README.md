# R12a doğrulama koşusu — 2026-11-24

> ⛔ **Bu bir `results/` koşusu DEĞİLDİR ve oraya kopyalanmamalıdır** — kanıt,
> sonuç değil (değişmez 1; `reports/denetim-kosusu-2026-11-19/README.md`
> aynı gerekçeyi taşıyor).

`R12a`'nın kabul kanıtı: `_LOOKUP_BATCH` 80 → 20 değişikliğinden sonra arka
plan kapsamı tam geliyor mu?

## Ne koşuldu

| | |
|---|---|
| commit | `51fcb39` + `R12a` çalışma ağacı |
| hedef | `VEGFA` / `HeLa`, saRNA `GCAACCATAGCCTCGGCCGC` |
| düzenek | kopya cache + `--output-dir` (ikisi de `R2`/`R3`'te bağlandı) |
| süre | ~16 dk |
| çıkış | **0** — 32/32 adım |

## Sonuç

| | 2026-11-19 (batch=80) | bu koşu (batch=20) |
|---|---|---|
| arka plan kapsamı | 22/182 (**%12**) | **182/182 (%100)** |
| taranan transkript | 48 | **208** |
| off-target site | 4 | **41** |
| kayıp batch / 504 | 2 batch | **0** |
| risk sınıfı | SAFE (0.2909) | **WARNING** (0.3260) |

41 site, 2026-09-17 referans koşusunun sayısıyla aynı — arama uzayı geri geldi.

`stage2_seed_hits.json`:

```json
"background_coverage": {"requested": 182, "resolved": 182, "fraction": 1.0}
```

## Domain dağılımı (n=41)

| domain | maks | ortalama | ayrık değer |
|---|---|---|---|
| `sequence_specificity` | 1.0000 | 1.0000 | **1** (sabit — `C1`, `_clamp` eziyor) |
| `variant_toxicity` | 0.6698 | 0.2282 | 34 |
| `epigenetic_context` | 0.6095 | 0.2232 | 40 |
| `biophysics_structure` | 0.2933 | 0.0704 | 19 |
| `execution_safety` | 0.2222 | 0.1680 | **2** |

⚠️ Bu tablo `R10`'un (`_clamp(None) → 0.5`) kararını besliyor ve
`ARASTIRMA_R1.3_R4.2_2026-11-19.md` §1.4'teki ilk ölçümü **düzeltti**: o
sayılar %12 kapsamlı koşudan geliyordu ve iddiayı olduğundan güçlü
gösteriyordu.

## Bu koşunun NE göstermediği

`B12` hâlâ kapanmadı: bu tek bir koşu (VEGFA/HeLa), `B12` dördünü istiyor ve
`H10` (run manifest) olmadan dört koşu birbirinden ayırt edilemez. Ayrıca
`verify-run` `background_coverage`'ı **okumuyor** — altı kontrolünün hiçbiri
ona bakmıyor, yani sakat bir koşu o kontrollerden temiz geçer (`R12b`'ye
yazıldı).
