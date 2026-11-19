# Onarım sırası — 2026-11-19 denetiminden

Girdi: `reports/DENETIM_2026-11-19.md` (13 bulgu) +
`reports/bio-reviewer_gnomad-polymorphism-channel_2026-11-19.md` (F1-F11).

Bu dosya **öneridir, otorite değildir.** Ne yapılacağının otoritesi
`SCIENTIFIC_ROADMAP.md`; maddeler oraya taşınmadan bağlayıcı olmaz.
Değişmez 8 aynen geçerli: **her oturum yalnız bir madde.**

---

## Sıralamayı üreten beş kural

Liste keyfi değil; şu beş kuraldan çıkıyor ve çatışma olduğunda üsttekiler
kazanıyor:

1. **Yanlış cevap, yanlış sayıdan önce gelir.** Aracın "risk yok" demesi,
   bir kanalın yanlış ölçülmesinden kategorik olarak daha tehlikelidir.
2. **Tüketici, üreticiden önce.** `None` yazmaya başlamadan önce `None`'ı
   tüketenlerin çökmemesi gerekir. `B2` bunu ters yaptı: stage-4 üreticileri
   `null` yazar hale geldi, stage-6 tüketicisi `None`'da çöküyor.
3. **İzolasyon, deneyden önce.** Bir koşuyu referans koşuları bozmadan ve
   gerçekten izole ederek yapamıyorsan, koşudan öğrendiğin şey güvenilmez —
   bu denetim bunu kendi üstünde ölçtü.
4. **Ölçüm, modellemeden önce.** Girdileri uydurma olan bir modelin
   ağırlığını ayarlamak değişmez 7'nin ihlaline giden yol.
5. **Bir sayının *anlamını* değiştiren her şey ön kayda gider** (`A12`),
   ve `B12`'nin sayıları okunmadan **önce** kilitlenir.

---

## FAZ R0 — Koşu yalan söyleyemesin

> Üçü de küçük. Üçü de bittiğinde bir koşuya ilk kez güvenilebilir.

### R0.1 — Boş arama uzayı koşuyu durdursun *(Bulgu 12)* 🔴🔴 **ÖNCE BU**

Bugün: `bg` cache'i eskiyor → Ensembl 504 → `get_background_transcriptome`
**boş liste** dönüyor → 0 site → `risk=SAFE (0.0000)` → **exit 0**.

İki ayrı düzeltme, ikisi de gerekli:

- `transcriptome_fetcher.py:149` — hiçbir kanonik transkript çözülemediğinde
  **istisna atsın**, boş liste dönmesin. 183 genin 183'ünün birden
  kaybolması bir ölçüm değil, bir arızadır.
- `report_generator` — **0 site ≠ SAFE.** Sıfır site "analiz edilmedi"
  demek; `risk_class` bu durumda bir risk sınıfı değil, açık bir
  *bilinmiyor* olmalı.

Kabul: arka plan çözülemeyen bir koşu **sıfırdan farklı** çıkış kodu verir;
0 siteli bir rapor hiçbir koşulda `SAFE` yazmaz.

*Neden ilk:* kural 1. Bu listedeki tek "yanlış cevap" bulgusu; geri kalan
hepsi yanlış sayı. Ayrıca bağımlılığı yok, bugün yapılabilir.

### R0.2 — `--output-dir` ya bağlansın ya silinsin *(Bulgu 11)* 🟠

`Snakefile:14` `RESULTS = Path("results")` sabitliyor, `results_dir`'in
kurallarda sıfır okuyucusu var, ama `README.md:344` bayrağı belgeliyor.

İki seçenek, **karar gerekiyor**: (a) `results_dir`'i `Snakefile` ve
`rules/*.smk` boyunca bağla, (b) bayrağı ve README satırını sil.
(a) tercih edilir — çünkü R0.3 ve `B12` öncesi deneme koşuları için bir
çıkış yolu gerekiyor.

*Neden burada:* kural 3. Bu bayrak çalışmadan her deneme koşusu
`results/`'un üzerine yazar — rule 20'nin tavanlarını ölçtüğü veriyi yok
eder.

### R0.3 — Adapter'lar config'i gerçekten yüklesin *(Bulgu 13)* 🔴

`load_config()`'in üretimde tek çağrıcısı var (`cli.py:167`). 14 adapter
config'i kwargs'tan kuruyor; geçirilmeyen her alan `config.py:48-59`'daki
sabite düşüyor — 12 `data_paths` girdisi dahil.

En küçük doğru düzeltme: her kural adapter'a **config dosyası yolunu**
geçirsin, adapter `load_config()` çağırsın. Mekanik ve test edilebilir.

⚠️ 14 dosyaya dokunuyor — tek oturumluk iş ama geniş. Daha dar bir ilk adım
isteniyorsa: `data_paths` varsayılanlarını **kaldır** (zorunlu alan yap), o
zaman config'i yüklemeyen her çağrı ayağa kalkarken patlar. Değişmez 2'nin
ruhu: sessiz varsayılan yerine gürültülü arıza.

*Neden burada:* kural 3. Bu denetimin izolasyonu tam buradan sızdı ve canlı
cache 182 satır kaybetti.

---

## FAZ R1 — Bilinmiyor yolu çalışsın (**tüketiciler**)

> Kural 2. R2'den **önce** bitmeli, yoksa `null` yazan her üretici koşuyu
> çökertir.

### R1.1 — İki korumasız çökme noktası *(Bulgu 6)* 🔴

- `execution_merger.py:163-165` — `f"ago2={ago2:.3f}"`, `ago2` `None`
  olabiliyor → `TypeError`. Döngü içinde, `try` dışında.
  (`epigenetic_merger.py:236` aynı tuzağı görüp korumuş — kalıp mevcut.)
- `scoring/integrator.py:153-155` — `min(1.0, ctx.get("atac_score", 0.5))`;
  anahtar var ve değeri `null` olduğu için `.get` varsayılanı **hiç
  devreye girmiyor** → `TypeError`. Yol:
  `epigenetic_merger:247` → `score_integrator` → `risk_classifier:73`.

Kabul: ölçülmemiş Ago2/ATAC taşıyan bir site boru hattını çökertmiyor.

### R1.2 — `variant_merger` ve `biophysics_merger` bilinmiyor öğrensin *(Bulgu 2'nin merger yarısı)* 🔴

Dört domain merger'ının **ikisi** hâlâ sayısal varsayılan kullanıyor:
`variant_merger.py:34,46-49` (cosmic `0.0`, clinvar `0.0`, phylop `0.5`) ve
`biophysics_merger.py:105-110` (shape `0.5`, m6a/adar/g4 `0.0`).
Üçü güvenli yönde.

⚠️ Bunlar yalnız "kaynak arızalandı"da değil, **site upstream dosyada hiç
yokken** de tetikleniyor (`.get(site_id, {}).get(key, default)`).

### R1.3 — `_clamp(None) → 0.5` **kararı** *(B3 + A12)* ⚖️ **kod değil, karar**

`score_integrator._clamp` bilinmeyen domain skorunu `0.5`'e çeviriyor.
`biostatistician` ölçtü: `0.5`, dört koşuda `biophysics_structure`
(maks 0.345), `epigenetic_context` (maks 0.4905) ve `execution_safety`
(3 koşuda maks 0.25) domainlerinin **gözlenen maksimumunun üstünde** — yani
bilinmeyen bir domain, ölçülebilen her siteden riskli sıralanıyor.

Bu bir **modelleme kararı**, düzeltme değil. R4.1 ile birlikte ön kayda.

---

## FAZ R2 — Üreticiler bilinmiyor yazsın

> Artık güvenli. Bittiğinde `B2`'nin kriteri ilk kez **gerçekten** doğru olur.

### R2.1 — Stage-6 üreticileri *(Bulgu 3)* 🔴
`ago2_fetcher.py:49-52` (`loading_score: 0.0, is_loaded: False`),
`rbp_fetcher.py:49-53`, `circrna_checker.py:65`, `immune_screener.py:43`.
`execution_merger`'ın **kendi docstring'i** (`:61-65`) bu hatayı tarif
ediyor: *"for Ago2 — the heaviest channel at 0.40 — that single substitution
moved a site most of the way to 'safe'."*

### R2.2 — Kalan arıza yolları *(Bulgu 2)* 🔴
Stage 1/2/3/5'te 12 nokta daha; tam liste denetim raporunun Bulgu 2
tablosunda.

### R2.3 — Stage-3 adapter'ları istisnayı yutmasın *(Bulgu 1)* 🔴
`clinvar_client.run:345`, `gnomad_client.run:36`, `cosmic_scanner.run:33`,
`phylop_fetcher.run:35` — hepsi `logger.warning` ile yutup boş/sabit dosya
yazıyor. `B1`'in eklediği `APIError` tam burada ölüyor ve ClinVar kanalı
gene her sitede `0.0` oluyor.

### R2.4 — gnomAD arıza yolu *(Bulgu 5)* 🟠
`gnomad_client.py:123-129` arızada `polymorphism_score=0.5` üretiyor, yani
`B4`'ün koyduğu riskli `1.0` varsayılanı **hiç erişilemiyor**.

### R2.5 — `B2` kapısını yeniden yaz 🟠
`.claude/acceptance/B2.sh` yalnız stage-4 + stage-6 merger'ını sınıyor.
Kriter genel olduğuna göre kapı da **bütün aşamaları** taramalı.
(Brifing §3(b)'nin kendi hakkında yazdığı risk; `H14` bunun ikinci örneği.)

---

## FAZ R3 — Ölç

### R3.1 — `H14` kapısını emekliye ayır *(Bulgu 4)* 🟠 *(ucuz, her an)*
`H14.sh` iki ters kontrolü `H15` kasıtlı olarak geçersiz kıldı; kapı kalıcı
kırmızı. `DONE` bir maddenin kapısının "geçmedi" demesi, kırmızı kapıyı
normalleştirir.
**Genel ders, kayda değer:** bir kabul kapısı bir **anı** değil bir
**özelliği** ölçmeli. Diğer kapılar da bu gözle taranmalı.

### R3.2 — `B12`: dört koşuyu yeniden koş 🔴
Ancak R0-R2 bittikten sonra sayılar bir şey ifade eder.
⚠️ **Ensembl 2026-11-19 itibarıyla ayakta** (ölçüldü: `lookup/symbol`
HTTP 200, 22 s) — yani koşu artık mümkün, ama yavaş.
⚠️ Canlı cache 182 `bg:canonical:*` satırını kaybetti; ilk koşu onları
yeniden çekecek.

### R3.3 — `verify-run` + `pipeline-verifier` dört koşuda
Özellikle: `null` stage-7 ve HTML'den sağ çıkıyor mu — **bu hâlâ hiç
ölçülmedi.**

---

## FAZ R4 — Modelleme kararları (ön kayıt, `A12`)

> Kural 4 ve 5. Hiçbiri "düzeltme" değil; hepsi **karar**, ve `B12`'nin
> sayıları okunmadan önce kilitlenmeli.

### R4.1 — Kapsam tabanı *(Bulgu 7 + `B3`)* ⚖️
Bugün hiçbir minimum-kapsam kontrolü **yok**; tek kanal hayatta kalırsa
domain skorunun tamamı o kanal oluyor (ağırlık 1.0'a çıkıyor).
Ölçüldü (VEGFA_HeLa, n=41): CCLE düştüğünde **37/41 site güvenli yöne**
kayıyor, ortalama **−0.1087**.

`biostatistician`'ın önerisi (uygulanmadı, karar bekliyor): taban
**domain başına hayatta kalan ağırlık kütlesi** + **adlandırılmış kanal
şartı** (epigenetik için CCLE, execution için Ago2) + site başına `coverage`
raporlanması. Sayısal eşik **kasıtlı olarak önerilmedi** — dağılımı
gördükten sonra seçmek `A12` tuzağı.

⚠️ Ayrıca ön kayda **yazılmalı**: eksik-veri kestiricisi geliştirme
ortasında değişti, yönü ve ölçülen büyüklüğü (drop-one tablosu) ile birlikte.

### R4.2 — gnomAD kanalı: işaret doğru, değer değil *(Bulgu 8)* ⚖️
`bio-reviewer`'ın verdiği cevap: **`B4` doğru ve korunmalı** — bağlanma ve
sonuç eksenleri aynı yönü gösteriyor. Ama:
- büyüklük ~100 kat yanlış: AF = 0.01'de doğru çarpan `1 − AF` = **0.99**,
  kod **0.00** uyguluyor (`gnomad_client.py:280`). Ölçülen örnek:
  **%0.68'lik bir alel siteyi %68 "güvenli"ye taşıyor.**
- pozisyon ağırlığı yok — seed (2-8) dışı SNP ile seed içi SNP aynı puan
- `ref`/`alt` parse ediliyor (`:251-252`), skorda **hiç okunmuyor** → alt
  aleli guide'a uyan varyant yeni off-target *yaratır*, kod onu
  risk-azaltıcı sayar

Seçenekler (karar): (a) kanalı **anotasyona** indir, skordan çıkar;
(b) gen düzeyi kısıt metriğiyle değiştir (LOEUF/pLI/pTriplo) — gen-anahtarlı
olduğu için **`D2`'den etkilenmez** ve statik tablo, 1 Hz API yok;
(c) transfer fonksiyonunu `1 − AF`'ye çevir + pozisyon ağırlığı + `ref`/`alt`.

### R4.3 — "veri yok" ≠ "varyant yok" *(Bulgu 9)* ⚖️
`gnomad_client.py:277-278` boş pencereyi `1.0` sayıyor. Ölçüldü: referans
koşuda `variant_count` ortalaması **10.44**, **0/41 boş pencere** — yani
çağrılabilir bir 20-mer bu yoğunlukta boş dönmüyor; **boş = çağrılamadı.**
Düzeltme yolu: gnomAD'ın `coverage` alanını sorgula, ikisini ayır.

---

## FAZ R5 — Koordinatlar (en büyük iş, en sona)

### R5.1 — `GenomicRegion`'ın tabanını **ilan et** *(Bulgu 10)* 🟠
`models.py:10-28`'de taban beyanı yok, `length = end - start` (yarı-açık).
Tüketiciler üç farklı taban varsayıyor: gnomAD 1-tabanlı kapalı, `pysam` ve
pyBigWig 0-tabanlı yarı-açık.

🔎 **Araştırıldı ve doğrulandı:** gnomAD region sorgusu **1-tabanlı,
kapalı**; 0-tabanlı yarı-açıktan dönüşüm `start+1`, `stop = end`.
`_graphql_query` bugün dönüştürmeden geçiriyor ve kendi docstring'i
(`:217-219`) "0-based" diyor — yani sözleşme belgede de çelişkili.

Düzeltme: tabanı modelde ilan et, her tüketici **açıkça** dönüştürsün.

### R5.2 — `D2`/`D1` ile birlikte
Tek başına yapılması anlamsız: pencere zaten medyan **30.732 bp** yanlış
yerde (rule 10). 1 bazlık bir düzeltme 30 kb'lik bir sapmanın içinde
ölçülemez. R5.1 `D2`'nin kapsamına alınmalı.

---

## Hızlı tablo

| sıra | iş | bulgu | tip | boyut |
|---|---|---|---|---|
| R0.1 | boş arama uzayı → abort; 0 site ≠ SAFE | 12 | 🔴🔴 kod | S |
| R0.2 | `results_dir`'i bağla ya da bayrağı sil | 11 | 🟠 kod | S |
| R0.3 | adapter'lar `load_config()` çağırsın | 13 | 🔴 kod | M |
| R1.1 | iki çökme noktası | 6 | 🔴 kod | S |
| R1.2 | variant + biophysics merger bilinmiyor | 2 | 🔴 kod | M |
| R1.3 | `_clamp(None)` kararı | — | ⚖️ karar | — |
| R2.1 | stage-6 üreticileri | 3 | 🔴 kod | S |
| R2.2 | kalan arıza yolları | 2 | 🔴 kod | M |
| R2.3 | stage-3 yutma | 1 | 🔴 kod | S |
| R2.4 | gnomAD arıza yolu | 5 | 🟠 kod | S |
| R2.5 | `B2` kapısını genişlet | — | 🟠 kapı | S |
| R3.1 | `H14` kapısını emekliye ayır | 4 | 🟠 kapı | S |
| R3.2 | `B12` yeniden koşu | — | 🔴 ölçüm | L |
| R3.3 | `verify-run` ×4 | — | ölçüm | S |
| R4.1 | kapsam tabanı | 7 | ⚖️ ön kayıt | — |
| R4.2 | gnomAD değeri | 8 | ⚖️ ön kayıt | — |
| R4.3 | `coverage` ile boşluk ayrımı | 9 | ⚖️ ön kayıt | — |
| R5.1 | koordinat tabanı ilanı | 10 | 🟠 kod | M |
| R5.2 | `D2` exon walk | — | 🔴 kod | XL |

**Kapsam dışı bırakılanlar** (brifing §4, bilerek açık): ölü
`domain_scores.py` (`B8`), `epigenetic_merger.py:12` ölü `_NEUTRAL`,
`mirbase_checker` `"SAFE"` + `[:7]` (`B11`), `requires-python`,
`ubuntu-latest`/Node 20 (`H16`), `verify-run` check 4 (`H10`).
⚠️ Bunlardan `mirbase_checker`'ın `"SAFE"`'i Bulgu 12'de ana sonucu doğrudan
besledi — `B11`'in önceliği yeniden değerlendirilmeli.
