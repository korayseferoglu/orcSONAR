# Denetim koşusu — 2026-11-19 16:16-16:19 UTC

> ⛔ **Bu bir `results/` koşusu DEĞİLDİR ve oraya kopyalanmamalıdır.**
> Burada durmasının sebebi tam olarak budur: değişmez 1'e göre `results/`'a
> yalnız Snakemake yazar, ve bir denetim düzeneğinde üretilmiş bir koşunun
> oraya konması onu sonradan kanonik bir koşudan **ayırt edilemez** hale
> getirir. Bu dosyalar **kanıttır**, sonuç değil.

`reports/DENETIM_2026-11-19.md` **Bulgu 12**'nin ham kanıtı.

## Ne koşuldu

| | |
|---|---|
| commit | `4232e19` (detached worktree) |
| hedef | `VEGFA` / `HeLa`, saRNA `GCAACCATAGCCTCGGCCGC` |
| komut | `python -m src.cli --gene VEGFA --cell-line HeLa --sarna-sequence ... --cores 4` |
| yorumlayıcı | `~/.venvs/orcsonar/bin/python` (3.12.3) |
| süre | ~3 dakika |
| çıkış | **0** — `32 of 32 steps (100%) done` |

## Düzenek — neden normal bir koşu değil

- Ayrı `git worktree` (repo'nun `results/`'una yazmasın diye; `--output-dir`
  **bağlı değil**, bkz. Bulgu 11)
- `data/` → canlı dizine **symlink** (1.5 GB, salt okundu)
- cache → `sqlite3.backup()` ile alınmış **kopya**
- ⚠️ **Kopya izolasyonu tutmadı.** `transcriptome_fetcher` config'i değil
  sabit varsayılanı kullandığı için canlı `data/cache/orcsonar_cache.db`'yi
  açtı (Bulgu 13). Canlı cache 1893 → 1731 satıra düştü; 182
  `bg:canonical:*` satırı kayboldu.

## Sonuç

```
report_generator: 0 sites, risk=SAFE (0.0000)
```

Referans koşu (`results/VEGFA_HeLa`, 2026-09-17) **41 site** taşıyor.
Bu koşu **sıfır** buldu ve yine de `SAFE` raporlayıp `exit 0` döndü.

**Sebep zinciri** (`run-logs/seed_alignment.log` içinde satır satır okunabilir):

1. `cache:get:178` — `bg:canonical:*` satırları `schema v0` → eskimiş →
   düşürüldü (182 kez)
2. `transcriptome_fetcher:_batch_lookup_symbols:239` — Ensembl REST
   **`504 Gateway Time-out`** (80'lik ve 22'lik batch'ler)
3. `transcriptome_fetcher:get_background_transcriptome:149` —
   **"no canonical transcripts resolved — returning empty"**
4. `seed_aligner:run:395` — **"scanning 20 transcripts total (0 background +
   target gene)"**
5. `find_offtargets:58` — `Seed 'CAACCAU' hit 0/20 transcripts` → **0 site**

## Bu koşunun NE gösterdiği, ne GÖSTERMEDİĞİ

**Gösterdiği:** bir veri kaynağı arızası boru hattının tamamını "risk yok"a
çevirebiliyor, başarılı çıkış koduyla (Bulgu 12); ve `config.yaml`'ın yol
bloğu çalışma zamanında bağlı değil (Bulgu 13).

**Göstermediği:** 0 site olduğu için stage 3-6 **hiçbir kaynağa gitmedi**.
Yani Bulgu 1/2/3/6'nın arıza yolları bu koşuda **tetiklenmedi** ve `null`'un
stage-7 ile HTML raporundan sağ çıkıp çıkmadığı **hâlâ bilinmiyor**. Onun için
Ensembl'in döndüğü bir **dolu** koşu gerekiyor.
