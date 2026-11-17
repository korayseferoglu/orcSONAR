---
paths:
  - "src/**/*.py"
  - "tests/**/*.py"
  - "rules/*.smk"
---

# Koordinat ve dizi değişmezleri

Kod düzeyi kurallar. **Kaynak başına chr-prefix tablosu burada DEĞİL** —
`docs/DATA_SOURCES.md` otorite, `orcsonar-data-sources` skill'i onun yüklenebilir özeti.
Burada yalnız formatın ve biyolojinin dayattığı, her modülün uyması gereken şeyler var.

## Genom yapısı

**Her koordinat hg38/GRCh38.** İstisna yok. hg19/GRCh37 bir koordinat, buildleri
liftOver'sız karıştıran bir çağrı, ya da varsayılanı GRCh37 olan bir endpoint → bulgu.

## Koordinat tabanları — tablo burada değil

Format başına taban (`BED` 0-tabanlı yarı-açık, `VCF` 1-tabanlı kapalı, …)
`docs/DATA_SOURCES.md`'de ve `orcsonar-data-sources` skill'inde. Buraya kopyalamıyorum;
iki kopya kaymaya başlar.

Buradaki kural **aritmetik**: her taban dönüşümü bir off-by-one adayıdır. Aralık
uzunluğu yarı-açıkta `end - start`, kapalıda `end - start + 1`. İkisini karıştırmak
sessizce bir nükleotid kaydırır ve hiçbir mevcut test bunu kendiliğinden yakalamaz —
dönüşümü her iki yönde de doğrula.

## Strand — promoter penceresi artan koordinat değildir

Promoter penceresi TSS'e göre **−1000 / +200**, yani *transkripsiyon yönünde* yukarı/
aşağı. Eksi iplikli bir gende bu, genomik koordinatta `[TSS − 200, TSS + 1000]` demektir.

Ters-komplement alma, seed çıkarma ve pencere kurma **hepsi** strand'e uymalı. Eksi
iplikli bir transkriptin `tx_start`/`tx_end`'inin artan sırada olduğunu varsayma.

## Seed — `[1:8]`

Off-target seed'i guide'ın **2-8. pozisyonları**, 1-tabanlı ve kapalı. Python diliminde
`[1:8]`. Burada bir off-by-one koşudaki **her** hit'i değiştirir.

⚠️ `mirbase_checker.py:200`'deki istisna yolu `sarna_sequence[:7]` yazıyor — yani
pozisyon 1-7, yanlış seed. Yalnız hata yolunda, ama raporlanan seed yanlış.

## İşaret ve birim

- Dupleks **ΔG kcal/mol ve negatif olmalı.** Pozitif ΔG dupleks oluşmadı demektir —
  bulgu, sonuç değil. kcal/kJ karışıklığı, ΔG vs ΔG°37, °C vs K, ve yanlış sırayla
  çıkarmadan gelen işaret dönmeleri bu projede gerçekten olmuş hatalar.
- phyloP ve phastCons **farklı ölçekler**; birbirinin yerine kullanılamaz.
- Risk modeline giren skorlar `[0, 1]` olmalı. Normalize edilmemiş ham sinyal → bulgu.
  *İstisna, kasıtlı:* `stage4_epigenetic.json`'daki ham sinyal alanları (`atac_signal`,
  `h3k4me3_signal`, `hic_contact`, `ccle_expression` …) native birimlerinde durur;
  normalizasyon tüketicide olur. Onlara uygulanan tek fiziksel kural negatif olmamaları.

## Arama uzayı — bugün ne olduğunu bil

Seed taraması **cDNA uzayında** yapılıyor: `gene`, `transcript_id`, `tx_start`,
`tx_end`, `mismatches`, `alignment_score` hepsi transkript dizisi üzerinde hesaplanır.
`GenomicRegion` `seed_aligner.py:105-112`'de *sonradan* türetilir ve `seed_aligner`
içinde bir daha okunmaz.

İki sonucu var ve ikisi de önemli:
- **Hangi genin hit aldığı** sorusu splice-körlüğünden (yol haritası `D2`) **etkilenmez**.
- Türetilen genomik koordinat **yanlıştır** — medyan sapma 30.732 bp, 41 sitenin 39'u
  >1 kb. Genomik lokusa dayanan her kaynak (COSMIC, gnomAD, ClinVar, phyloP, ATAC, ChIP,
  GRO-seq, Hi-C, Ago2, RBP, m6A, circRNA, RepeatMasker) yanlış yerden okuyor. SHAPE, ΔG,
  G4, miRBase, immün ve CCLE etkilenmez.

Ayrıca bugün **yalnız tek iplik** taranıyor (`seed_aligner.py:198` sadece
`reverse_complement(seed)` indeksliyor) ve **bölge farkındalığı yok** — `region_class`
(5'UTR/CDS/3'UTR) diye bir şey yok. İkisi de yol haritasında: `C0b` ve `C0`.
