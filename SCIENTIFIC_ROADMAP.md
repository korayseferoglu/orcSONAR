# orcSONAR — Bilimsel Yol Haritası

> Bu dosya bir plan değil, bir **durum makinesidir.** Yeni bir oturum açan model
> buradan başlar: §2 değişmezlerini okur, bağımlılığı karşılanmış ilk `TODO` maddesini
> bulur, **yalnız onu** yapar, kabul kriterini koşar, durumu günceller.
>
> Kanıt tabanı: `AUDIT.md` (repo içi, Bulgu-1…15) ve
> `/home/koray/orcSONAR-denetim/DENETIM_RAPORU.md` (10 uzman denetimi, 2026-11-16).
> Bu dosyadaki her "neden" bir ölçüme dayanır. Yeni iddia eklenecekse ölçümü de eklenir.
>
> Durum alfabesi: `TODO` · `DOING` · `DONE` · `BLOCKED(<id>)` · `DROPPED(<gerekçe>)`

---

## 0. Hedef hakkında dürüstlük — bunu ilk oku

**Metodolojik titizlik** olarak Nature standardı bu planla ulaşılabilir: ön kayıt,
gerçek-referansa karşı doğrulama, ablasyon, kalibrasyon, belirsizlik raporlama,
bit düzeyinde tekrarlanabilirlik.

**Nature'ın kendisi** (ve Nature Methods / Nature Biotechnology) için bu plan **yeterli
değildir.** Eksik üç şey:

1. **Islak-lab doğrulaması yok.** Tahminlerin en az bir hatta RT-qPCR/RNA-seq ile
   ölçülmesi gerekir. Plan saf in-silico.
2. **Yeni biyolojik bulgu yok.** Araç bir yöntem; Nature ailesi yöntemden bir *keşif* bekler.
3. **Algoritmik yenilik yok.** Kanıt birleştirme şeması özgün ama kavramsal yenilik değil.

**Gerçekçi hedef dergiler:** *Nucleic Acids Research* · *Genome Biology* ·
*Bioinformatics* · *Briefings in Bioinformatics* · *NAR Genomics and Bioinformatics* ·
*Molecular Therapy – Nucleic Acids*.

**Nature ailesine geçiş yolu:** bir ıslak-lab işbirliği + ondan çıkan biyolojik sonuç.
Bu plan o işbirliğinin **ön koşulunu** üretir — güvenilir, kalibre edilmiş, önceden
kaydedilmiş tahminler. Bugünkü haliyle hiçbir laboratuvar bu çıktıyla deney tasarlamaz;
plan bittiğinde tasarlayabilir.

---

## 1. İki iddia, iki ayrı kritik yol

Projenin iki iddiası **farklı bağımlılık zincirlerinde.** Karıştırmak üç ay kaybettirir.

| | **İDDİA 1 — seed off-target taraması** | **İDDİA 2 — hücre-hattı özgüllüğü** |
|---|---|---|
| Cümle | Bu saRNA'nın guide ipliği, siRNA gibi şu genleri baskılayabilir | Aynı saRNA farklı hatlarda farklı siteleri riskli bulur |
| Birim | **gen düzeyi** | site düzeyi |
| Gerçek referans | **var ve bol** — GSE5814/5769/5291 (HeLa) | **yok** — aynı saRNA'nın iki desteklenen hatta transkriptom-geniş ölçümü kamuya açık değil |
| Ön koşul | C1 (`_clamp`) + D1 (tam GENCODE) | D2 (ekzon yürüyüşü) + B6 (site-başına çarpan) + canlı kanallar |
| Splice-körlüğü (Bulgu-8) etkiler mi | **HAYIR** — etiket gen düzeyinde | **EVET** — doğrudan bozar |
| Sonuç | **doğrulanabilir → yayının ana gövdesi** | **doğrulanamaz → kalibre edilmiş hipotez üreteci, sınırı açık yazılır** |

Bu ayrım projeyi kurtarır: İddia 1 kapatılabilir ve kapandığında elde **doğrulanmış bir
yöntem** olur. İddia 2 dürüstçe "doğrulanmamış" etiketiyle sunulur — saRNA alanında
doğrulanmış bir off-target aracı literatürde **yok** (`saRNA Designer` kendi
README'sinde "şans üstü ayırt edicilik gösterilemedi" yazıyor).

---

## 2. DEĞİŞMEZLER — hiçbir madde bunları ihlal edemez

1. **`data/` ve `results/` salt-okunur.** Sonucu elle düzenlemek veri uydurmaktır.
2. **Arıza yönü kuralı:** veri yokluğu asla riski düşürmez. Yeni bir fallback açık bir
   *bilinmiyor* tipi döner, sayı dönmez. Sessiz `except: pass` yazılmaz.
   *Ölçüm: üç bağımsız fallback de "güvenli" yönüne arızalanıyordu —
   `_NEUTRAL_SIGNAL = 0.0`, ago2 URL yok → `0.0`, `mirbase_checker.py` istisna → `"SAFE"`.*
3. **Beyan = uygulanmış değil.** Config'e anahtar eklemek onu bağlamaz. `git grep` ile
   üretim çağıranını göster, yoksa ekleme.
   *Ölçüm: `mypy strict=true` (araç kurulu değildi), `max_mismatches: 12` (atıl),
   `_NEUTRAL = 0.5` (hiç okunmuyor), h3k27me3 (9 config tanımı / 0 üretim referansı),
   `--json` (belgeliydi, çalışmıyordu).*
4. **Commit'lenmemiş = yok.** "Tamam" demeden önce commit.
   *Ölçüm: h3k27me3 "wired ✅" hafızası hiçbir commit'te yoktu; `verify-run` check 6
   aylarca commit'siz bekledi.*
5. **Test önce kırmızı olmalı.** Hatayı yakalayan test, düzeltmeden önce başarısız
   olduğu gösterilmeden merge edilmez.
   *Ölçüm: 917 test yeşil geçerken bilinen üç hatanın üçünü de yakalamıyordu.*
6. **Ön kayıt kilitlidir.** `docs/PRE_REGISTRATION.md` yazıldıktan sonra metrik veya
   eşik *sonucu gördükten sonra* değiştirilmez. Değiştirilirse ayrı bir ön kayıt açılır
   ve ikisi de yayında raporlanır.
7. **Negatif sonuç kabul edilir.** "Epigenetik katman seed eşleşmesinin üstüne bilgi
   eklemiyor" geçerli bir sonuçtur ve yayınlanır. Ağırlık ayarlayarak pozitif sonuç
   aramak bu planın ihlalidir.
8. **Her madde tek iştir.** Geçerken başka bir bulgu düzeltilmez.

---

## 3. MADDELER

### FAZ A — Ön kayıt (kod yazılmaz)

| id | iş | bağımlılık | kabul kriteri | durum |
|---|---|---|---|---|
| **A1** | Mekanizma kararını yaz: modellenen şey **saRNA guide ipliğinin siRNA-benzeri seed off-target'ı**. Promoter/RNAa taraması ikinci bir arama uzayı olarak sonraya kaydedilir, bugünkü kodun iddiası değildir. | — | `docs/PRE_REGISTRATION.md` §1 mekanizmayı tek cümlede söylüyor | TODO |
| **A2** | Gerçek referans setini kilitle: **GSE5814** (seed pozisyon 1-19 tek-nükleotid mutantları, en güçlü), GSE5769, GSE5291, GSE41924, GSE44256/44105, GSE278438/9 — hepsi HeLa. | A1 | §2'de accession listesi + her birinin n'i | TODO |
| **A3** | Etiket tanımını kilitle: gen düzeyinde belirgin aşağı regülasyon, eşik önceden sabit (öneri `log2FC ≤ −0.3`). | A2 | §3'te eşik sayı olarak yazılı | TODO |
| **A4** | Metriği kilitle: **PR-AUC** (sınıf dengesiz) + ROC-AUC + ECDF/KS. Tabanlar: **7mer-m8 sayımı** ve **siSPOTR POTS skoru**. CV: leave-one-siRNA-out. ⚠️ Bu literatürde ROC-AUC standart değil (siSPOTR Spearman, SeedMatchR KS kullanıyor) — tek metrik olarak AUC "olağan karşılaştırma" sayılmaz. | A3 | §4'te metrik + taban + CV şeması yazılı | TODO |
| **A5** | **Kabul kriterini kilitle:** hangi sayı geldiğinde "çalışıyor" denecek. Öneri: orcSONAR'ın PR-AUC'si her iki tabanı da leave-one-siRNA-out CV'de aşmalı; aşmazsa sonuç **negatif olarak** raporlanır. | A4 | §5'te sayısal eşik yazılı ve commit'li | TODO |
| **A6** | Ön kaydı commit'le, hash'ini not et. Bundan sonraki her analiz bu hash'e atıf yapar. | A5 | `git log -1 --format=%H docs/PRE_REGISTRATION.md` | TODO |

**Faz A: 1 gün, 0 satır kod.** Mevcut en yüksek etkili bilimsel hamle ve bedava.
Ön kayıt olmadan, 183→250k gen geçişi ve ayarlanabilir ağırlıklarla yapay başarı
üretmek kaçınılmazdır.

---

### FAZ B — Arıza yönünü düzelt, ölü kanalları aç

| id | iş | bağımlılık | kabul kriteri | durum |
|---|---|---|---|---|
| **B0** | **Cache'e `schema_version` + geçersizleme komutu. ÖNCE BU.** `clinvar:%` anahtarları koordinat tabanlı; B1 düzeltilse bile eski boş sonuç **30 gün** servis edilir ve düzeltmenin işe yaramadığı sanılır. Aynı tuzak `phylop:`/`gnomad:`/`encode_signal:` için de geçerli. | — | yeni sürümle açılan cache eski anahtarları kullanmıyor (test) | TODO |
| **B1** | **ClinVar'ı canlandır** — `clinvar_client.py:134-138` literal `+AND+` gönderiyor, `requests` `%2B`'ye kodluyor. Canlı A/B: kodun biçimi **0**, doğrusu aynı pencerede **121 patojenik**. 0.25 ağırlıklı kaynak tamamen ölü, 119 site / 4 koşu → 0 varyant. HTTP 200 döndüğü için hata sayılmıyor. | B0 | aynı bölgede >0 patojenik varyant; regresyon testi eklendi | TODO |
| **B2** | **Fallback'i *bilinmiyor* tipine çevir.** `_NEUTRAL_SIGNAL = 0.0` → açık sentinel. Veri yokluğu artık "kapalı kromatin" sayılmıyor. ⚠️ Sentinel'i 0.5 yapmak **yetmez**: sabit ham-sinyal uzayında, 0.5 sözleşmesi skor uzayında (AUDIT.md Bulgu-10). | — | hiçbir fallback yolu sayısal risk değeri dönmüyor | TODO |
| **B3** | **Her siteye `provenance` + `coverage` alanı.** Skorun kaçta kaçı gerçek ölçümden geliyor, hangi kaynaklar katkı yaptı. `coverage` eşiğin altındaysa **skor üretmeyi reddet.** Bilimsel aleti prototipten ayıran şey budur: alet bilmediğini bilir. Ayrıca `/verify-run` check 4'ün ham `0.0`'ı "ölü kaynak" ile "gerçekten sessiz lokus"tan ayırabilmesi buna bağlı. | B2 | her site JSON'unda `provenance` + `coverage`; eşik altı site `null` skor + gerekçe | TODO |
| **B4** | **gnomAD işaretini düzelt** — üretici `gnomad_client.py:261-280` "korunmuş = 1.0 = yüksek risk" der; tüketici `variant_merger.py:36-38` `1.0 - skor` ile tersler. Korunmuş bölge en düşük riski alıyor. | — | işaret testi: korunmuş bölge > polimorfik bölge | TODO |
| **B5** | **Hi-C anchor'ı promotere bağla** — `hic_fetcher.py:44-47` `regions[0]` kullanıyor (köşegen bin, yapay maksimum temas). `promoter_region` tüm repoda hiç okunmuyor. *Ölçüm: VEGFA_HeLa'da `hic_contact` 41 sitenin 34'ünde `0.0`.* | — | anchor `promoter_region`; temas değerleri köşegen dışı | TODO |
| **B6** | **`cell_modifier`'ı site-başına yap** — `epigenetic_merger.py:137-147` tüm sitelerin ortalamasını üretiyor, `risk_classifier.py:73` aynı sözlüğü herkese veriyor. Sonuç: koşu başına **tek sabit çarpan** (`final/base` 6. haneye kadar sabit, Spearman(base,final) = 1.000000 4/4 koşuda) → sıralamayı değiştiremiyor. "Hücreye özgü" iddiası matematiksel olarak kodda yok. | — | aynı koşuda ≥2 farklı çarpan; Spearman(base,final) < 1.0 | TODO |
| **B7** | **ADAR + H3K27me3 kanallarını bağla.** H3K27me3 config'de 9 kez tanımlı, üretimde **0 referans**, hiçbir commit'te yok. ⚠️ Yön kararı önce: mekanizma A (sitoplazmik seed) için yüksek H3K27me3 → düşük risk; mekanizma B (RNAa) için tam tersi. A1'e uy. ⚠️ `test_h3k27me3_represses_active_histones` **yeşil geçiyor** çünkü ölü `domain_scores.py`'ı test ediyor. | A1 | `stage4_histones.json` anahtarlarında `h3k27me3_signals` var | TODO |
| **B8** | **Ölü `domain_scores.py`'ı sil** + ona bağlı 44 testi. Sıfır üretim çağıranı, ikinci ve çelişkili satürasyon sabitleri (5× fark), ters RBP işareti. İki doğruluk kaynağı taşımanın anlamı yok. | — | `git grep domain_scores src/` boş; kalan testler yeşil | TODO |
| **B9** | **AGO2 accession'larını düzelt** — K562 ENCFF426YFB = shRNA-KD RNA-seq, HepG2 ENCFF097LEQ = ChIP-seq; **ikisi de eCLIP değil**. HeLa'da zaten `null`. | — | accession'lar gerçekten AGO2 eCLIP; `data-source-validator` OK diyor | TODO |
| **B10** | **mypy strict'i sıfıra indir, sonra kapı yap.** İlk ölçüm (2026-11-17): **72 hata / 35 dosya**; 39'u eksik generic parametre. İki tanesi gerçek gizli hata: `shape_profile.py:300-301` `max()`/`min()` çağrısı `int | None` üzerinde ve üstündeki `type: ignore[arg-type]` mypy'nin bildirdiği kodu bile kapsamıyor; `transcriptome_fetcher.py:258-267` `None` koordinatı `TranscriptInfo`'ya verebiliyor ve çıkan ValidationError `seed_aligner`'ın düşürme yoluna gidiyor. | — | `mypy src/` 0 hata | TODO |
| **B11** | **CI kur** — pytest + `ruff check src/` + `mypy src/` + null kapısı (E1). | B8, B10 | CI yeşil ve zorunlu | TODO |

**Faz B ≈ 1 hafta.** B1 iki karakter / 15 dakika — projenin en yüksek etki/maliyet
oranlı tek işi.

---

### FAZ C — Skoru bilgi taşır hale getir

| id | iş | bağımlılık | kabul kriteri | durum |
|---|---|---|---|---|
| **C1** | **`_clamp`'i düzelt** — ham seed skorları 8.0–14.5 aralığında, sabit `1.0`'a eziliyor; 0.20 ağırlık sıfır bilgi taşıyor. **E3'ün ön koşulu**: düzeltilmezse PR-AUC ≈ 0.5 çıkar ve nedeni skor değil klemplenme olur. | — | `sequence_specificity` 41/41 sabit değil | TODO |
| **C2** | **Satürasyon sabitlerini veriden türet** — `_ATAC_SAT = 50` vb. uydurma; yüzdeliklerden hesapla. *Ölçüm: CEBPA_HepG2'de `hic_contact` **16.226× SAT**'a ulaşıyor — sabit mertebe olarak yanlış.* Asıl darboğaz `_ATAC_SAT`; HIGH_RISK'in erişilemezliğinin kök nedeni bu. | B11 | hiçbir ham sinyalde satüre site oranı >%50 (`/verify-run` check 6 geçiyor) | TODO |
| **C3** | **ΔG'yi PAKET olarak düzelt** — hizalama + hedef + eşik **birlikte**. `delta_g_calculator.py:79-82` fazladan `reversed()` yüzünden 18/20 "mismatch" → 41/41 site aynı **+31.10**. Hizalamayı tek başına düzeltirsen **−43.80** çıkar, `≤ −30` eşiğiyle tüm siteler riski 1.0'a fırlar. Motor (`thermodynamics.py`) doğru; hata yalnız adaptörde. | C2 | ΔG negatif, siteler arası varyans > 0, hiçbir site 1.0'a saplanmıyor | TODO |
| **C4** | **Çift sayımı kaldır** — epigenetik ve execution sinyalleri hem `base_score`'a hem `cell_modifier`'a giriyor; `config.yaml` ağırlıkları göründüğü anlamı taşımıyor. `apply_cell_modifier()` `weights`'i hiç okumuyor, `0.40/0.40/0.20` ve `0.30 + 1.40×` hardcoded. | C3 | `config.yaml` ağırlığını değiştirmek skoru öngörülen oranda değiştiriyor (test) | TODO |

**Faz C ≈ 1 hafta.**

---

### FAZ D — Tek en yüksek kaldıraçlı iş: GENCODE geçişi

> **Önemli tasarruf:** Bulgu-6 (183 gen) ve Bulgu-8 (splice-körlüğü) **aynı işin iki
> yüzü.** GENCODE GTF transkript başına ekzon bloklarını zaten taşıyor; yerel seed
> indeksini GTF'den kurduğunda cDNA→genomik yürüyüş neredeyse bedava çıkıyor. Bugünkü
> Ensembl REST `type="cdna"` yolu ekzon bilgisi taşımadığı için ayrı iş gibi
> görünüyorlar. **Tek blok yap.** `isolation: worktree` önerilir.

| id | iş | bağımlılık | kabul kriteri | durum |
|---|---|---|---|---|
| **D0** | GENCODE sürümünü seç ve indir (GTF + transkript FASTA). ⚠️ `data/` salt-okunur ve hook'lar yazmayı engelliyor — indirme yolu ve manifest kaydı önce kararlaştırılacak. | — | sürüm + checksum `docs/DATA_SOURCES.md`'de kayıtlı | TODO |
| **D1** | **Yerel seed indeksi** (~250k transkript). Mevcut `_BACKGROUND_GENES` 183 gen (iki docstring hâlâ "~250 genes" diyor, o da yanlış). Geçerlilik itirazının kökü: 41 hit'in geldiği 29 genin tamamı listeden; zenginleşme biyolojiden değil **transkript uzunluğundan** (r = 0.349, medyan cDNA 5.326 vs 2.828 nt). | D0 | 183-gen listesi kodda yok; tarama tam transkriptom üzerinde | TODO |
| **D2** | **`TranscriptInfo`'ya ekzon yapısı + cDNA→genomik yürüyüş.** `seed_aligner.py:105-112` cDNA offsetini genomik sınıra ekliyor. *Ölçüm: medyan sapma **30.732 bp**, maks 182.707 (EGFR), 39/41 site >1 kb; "doğru" çıkan 2 site retained-intron izoformu.* Pencereler sistematik olarak intron içine düşüyor → korunmasız, mutasyon-seyrek, kapalı kromatin → **risk sistematik olarak küçümseniyor.** | D1 | ekzon-farkında koordinatlar; D3 sayıları tutuyor | TODO |
| **D3** | **Yeniden koş ve doğrula.** Beklenen (denetimde Ensembl'den hesaplandı): COSMIC 31→**350**, phyloP ort. 0.027→**0.418**, phyloP>2 site 0→**16**, m6A 0→**10**. | D2 | ölçülen değerler bu mertebelerde | TODO |
| **D4** | Eşikleri yeniden kalibre et. `max_mismatches: 12` şu an **hiçbir adayı elemiyor** (≤12→41, ≤8→28, ≤6→7, ≤4→0, ≤3→0); modül docstring'i "max 3" diyor, 3 olsaydı çıktı boş olurdu. 250k transkriptte eşik yeniden anlam kazanacak. | D3 | eşik gerekçesi yazılı + hassasiyet analizi | TODO |

**Faz D ≈ 3-4 hafta.**

---

### FAZ E — Projenin bilimsel hale geldiği an

| id | iş | bağımlılık | kabul kriteri | durum |
|---|---|---|---|---|
| **E1** | **Null kapısını kalıcı hale getir** — 16.384 7-mer ampirik null. *Ölçüm: gözlenen 42 hit vs beklenen 52.7 (%47.4 yüzdelik, ortalamanın **ALTINDA**); BH-FDR sonrası **0/41** anlamlı.* Her koşu bu soruyu otomatik cevaplamalı. | B11 | null kapısı CI'da koşuyor, p-değeri raporlanıyor | TODO |
| **E2** | **Scrambled saRNA negatif kontrolü** — aynı boru hattı rastgele dizilerle. Veri gerektirmeyen en ucuz adım. | E1 | skor dağılımı karşılaştırması raporda | TODO |
| **E3** | **Katman A — ana deney.** A2'nin GEO setleri, gen düzeyi etiket, leave-one-siRNA-out CV, PR-AUC + KS, tabanlar 7mer-m8 ve siSPOTR POTS. | A6, C1, D4, E1 | A5'teki kabul kriteri karşılandı **veya** negatif sonuç açıkça raporlandı | TODO |
| **E4** | **ABLASYON — zorunlu.** `base_score + cell_modifier`, çıplak 7mer-m8 sayımını geçiyor mu? Geçmiyorsa 24 kaynağın hiçbiri bilgi eklemiyor demektir. **Yayının asıl bilimsel çekirdeği bu.** *Ölçüm: nominal 1.00 ağırlığın **%35'inden azı** gerçek bilgi taşıyor.* | E3 | her domain için katkı/ablasyon tablosu | TODO |
| **E5** | **Katman B — ortogonal kanıt.** AGO2 eCLIP (K562 ENCSR048YXG, HeLa E-MTAB-12944): yüksek skorlu lokuslar piklerle zenginleşiyor mu? ⚠️ D2 bitmeden koşturma — genomik lokus tabanlı. HepG2 için AGO2 eCLIP yok. | D3, B9 | doğru assay accession'ları + zenginleşme testi | TODO |
| **E6** | **Katman C — saRNA vaka çalışmaları (nitel).** GSE42024 (MCF7/HIC-1). ⚠️ Yalnız açıklayıcı örnek; AUC iddia edilmez (n küçük, on-target ikincil etkiler karışık). | E3 | raporda nitel bölüm, metrik iddiası yok | TODO |

**Faz E ≈ 2 hafta.** E3 geçtiğinde proje "çalışan prototip"ten "doğrulanmış yöntem"e geçer.

---

### FAZ F — Kalibrasyon ve dürüst sınırlar

| id | iş | bağımlılık | kabul kriteri | durum |
|---|---|---|---|---|
| **F1** | **Risk sınıfı eşiklerini E3'ün PR/ROC eğrisinden türet.** 0.3/0.6/0.8 şu an uydurma. *Ölçüm: `base_score` üst sınırı 0.9125 iken HIGH_RISK için >0.99 gerekiyor → **HIGH_RISK ve DANGEROUS matematiksel olarak erişilemez**; 4 koşunun hepsi 0.298–0.408 aralığında.* | E3 | eşikler veriden; her sınıf erişilebilir | TODO |
| **F2** | **Varyans payı raporla**, nominal ağırlık değil. Hangi domain skoru gerçekten ne kadar oynatıyor. | E4 | hassasiyet analizi tablosu | TODO |
| **F3** | **Belirsizlik raporlama.** B3'ün `coverage` alanı üstüne güven/tahmin aralığı. | B3, E3 | her tahmin yanında belirsizlik | TODO |
| **F4** | **`docs/METHODS.md`** — hakem okuyacak düzeyde yöntem belgesi. `docs/` şu an yalnız `DATA_SOURCES.md` içeriyor. | F1, F2 | her aşama, sabit ve eşik gerekçeli | TODO |
| **F5** | **`docs/LIMITATIONS.md`** — İddia 2'nin doğrulanamadığı, hangi veriyle doğrulanabileceği, hangi kaynakların ölü/vekil olduğu. CV ve yayın savunmasının merkezi; §5 tablosu buraya taşınır. | F4 | tablo taşındı, her satır ölçümlü | TODO |

**Faz F ≈ 2 hafta.**

---

### FAZ G — Yayın

| id | iş | bağımlılık | durum |
|---|---|---|---|
| **G1** | Preprint (bioRxiv), ön kayıt hash'ine atıfla | F5 | TODO |
| **G2** | Zenodo DOI + tam tekrarlanabilirlik paketi (sürümler, checksum'lar, seed'ler) | G1 | TODO |
| **G3** | Dergi seçimi ve gönderim (§0'daki gerçekçi liste) | G2 | TODO |

---

## 4. "BİLİMSEL" TANIMI — altı kabul kapısı

Proje bu altı kapının **hepsi** geçildiğinde bilimsel sayılır. Beşi geçip biri kalırsa
proje bilimsel **değildir**; kısmi puan yok.

| kapı | soru | nasıl ölçülür | şu an |
|---|---|---|---|
| G-I | Yanlışlanabilir bir iddia var mı? | `docs/PRE_REGISTRATION.md` commit'li, metrik + eşik sayı olarak yazılı | ✗ |
| G-II | Gerçek referansa karşı test edildi mi? | E3 koşmuş, sonuç raporlanmış (pozitif **veya** negatif) | ✗ |
| G-III | Tabanı geçiyor mu, yoksa geçmediğini söylüyor mu? | E4 ablasyon tablosu | ✗ |
| G-IV | Bilmediğini biliyor mu? | B3 `coverage` + F3 belirsizlik; eşik altı skor **üretilmiyor** | ✗ |
| G-V | Sabitler ve eşikler veriden mi geliyor? | C2 + F1; hiçbir sihirli sayı gerekçesiz değil | ✗ |
| G-VI | Bit düzeyinde tekrarlanabilir mi? | G2 paketi taze makinede aynı sayıları üretiyor | kısmen (Stage 7 zaten tekrarlanabilir) |

---

## 5. ASLA YAZILMAYACAKLAR (kapı geçilene kadar)

| iddia | neden yazılamaz | hangi madde açar |
|---|---|---|
| "hücre hattına özgü risk tahmini" | koşu başına tek sabit çarpan; sıralamayı değiştiremiyor | B6 (+ doğrulama için veri yok → F5'te sınır olarak yazılır) |
| "saRNA off-target aracı" | arama uzayı promotersiz olgun mRNA (`type="cdna"`); RNAa off-target'ı bu mimaride tespit edilemez | A1 (iddiayı daralt) |
| herhangi bir **bulgu** cümlesi ("RISC makinesini riskli buldu") | 183-gen listesi × transkript uzunluğu artefaktı (r = 0.349) | D1 |
| "termodinamik değerlendirme yapıyor" | 41/41 site aynı +31.10; biyofizik domaininin analitik tavanı 0.345 | C3 |
| "ClinVar / patojenik varyant entegrasyonu" | 119 site / 4 koşu → 0 varyant | B1 |
| "graceful degradation" | fallback "güvenli" yönüne arızalanıyor, riski bastırıyor | B2 |
| herhangi bir doğruluk/performans sayısı | hiç ölçülmedi | E3 |

---

## 6. Yol haritası dışında, zaten yapılanlar

Bu dosya açılmadan önce tamamlanan harness/doğruluk düzeltmeleri:

- **`fix(verify-run)`** — `/verify-run` check 4 ölüydü: yalnız `0.5` nöbetçisini sayıyordu,
  gerçek nöbetçi `0.0` olduğu için %100 fallback'li metriklerde hiç bulgu üretmiyordu.
  Artık iki nöbetçiyi ayrı sayıyor; VEGFA_HeLa'da **7 yeni bulgu** ortaya çıktı
  (`hic_contact` %82.9, `groseq_signal` %78.0, `ago2`/`rbp` `raw_signal` %100).
  Yanlış `0.5` iddiası beş yerden temizlendi. `--json` artık yalnız JSON basıyor.
  Check 6 (satürasyon) commit'lendi. `AUDIT.md` worktree'ye geri alındı.
- **`chore(ruff)`** — 71 lint hatası temizlendi; 6 `zip()`'e `strict=True` (hiçbiri aktif
  hata değildi, doğrulandı — garanti artık çağrı yerinde), 2 sessiz `except: pass`
  loglamaya çevrildi, mypy kuruldu ve ilk kez ölçüldü (→ B10),
  ajanlara `omitClaudeMd: true`, hook matcher'ları `NotebookEdit`'i de kapsıyor.
