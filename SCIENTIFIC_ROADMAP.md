# orcSONAR — Bilimsel Yol Haritası

> Bu dosya bir plan değil, bir **durum makinesidir.** Yeni bir oturum açan model
> buradan başlar: §2 değişmezlerini okur, bağımlılığı karşılanmış ilk `TODO` maddesini
> bulur, **yalnız onu** yapar, kabul kriterini koşar, durumu günceller.
>
> Kanıt tabanı: `AUDIT.md` (repo içi, Bulgu-1…15),
> `orcSONAR-denetim/DENETIM_RAPORU.md` (10 uzman denetimi, 2026-11-16) ve
> `orcSONAR-denetim/PLAN_DENETIMI_FABLE.md` (plan denetimi, 2026-11-17).
> Her "neden" bir ölçüme dayanır. Yeni iddia eklenecekse ölçümü de eklenir.
>
> Durum alfabesi: `TODO` · `DOING` · `DONE` · `BLOCKED(<id>)` · `DROPPED(<gerekçe>)`

---

## 0. Hedef hakkında dürüstlük — bunu ilk oku

**Metodolojik titizlik** olarak Nature standardı bu planla ulaşılabilir. **Nature'ın
kendisi** için yeterli değil: ıslak-lab doğrulaması yok, yeni biyolojik bulgu yok,
algoritmik yenilik yok. Nature ailesine geçiş için bir ıslak-lab işbirliği + ondan çıkan
biyolojik sonuç gerekir; bu plan o işbirliğinin **ön koşulunu** üretir.

**Hedef dergi tek bir liste değil — `E3a`/`E4a` sonucunun fonksiyonu.** Bunu baştan
tabloya yazmak, sonuç kötü geldiğinde ağırlık ayarlama cazibesini ortadan kaldıran tek
yapısal önlemdir (bkz. değişmez 7):

| sonuç | uygun venue |
|---|---|
| Tabanları **net geçiyor** + çok-omik katman ölçülebilir katkı veriyor | *NAR Genomics and Bioinformatics* · *Bioinformatics* (Application Note) · *Briefings in Bioinformatics* · iyi giderse *NAR* denenebilir |
| Tabanları geçiyor, çok-omik katman katkı vermiyor (**en olası**) | *NAR GAB* · *BMC Bioinformatics* · *PLOS Computational Biology* (ablasyon/benchmark çerçevesiyle) |
| Tabanları **geçmiyor** | **negatif/benchmark makalesi** — *NAR GAB*, *F1000Research*, *PLOS ONE*. Çerçeve: *"siRNA off-target verisi saRNA tasarım araçlarını test etmek için yeniden amaçlanabilir ve mevcut yaklaşımlar şans üstüne çıkmıyor."* Bu gerçek ve atıf alan bir katkıdır — `saRNA Designer`'ın kendi README'si bunun boşluk olduğunu söylüyor |
| saRNA güvenliği çerçevesi | *Molecular Therapy – Nucleic Acids* her üç senaryoda da makul |

⚠️ *NAR* ve *Genome Biology* bu çıktı için **fazla iyimser**: ikisi de birden çok bağımsız
veri setinde yerleşik araçlara net üstünlük ve topluluk kaynağı bekliyor. Elde 2006 tarihli,
yeniden amaçlanmış, tek hücre hattı verisi var. Ve asıl hakem itirazı şu olacak:
*"saRNA aracını siRNA verisiyle doğruladınız."* Bu itiraz `A1` + `A10` ile yönetilebilir,
ama NAR düzeyinde tek başına yeterli savunma değil.

---

## 1. ÜÇ iddia, üç ayrı kritik yol

| | **İDDİA 1 — P_silence** | **İDDİA 2 — hücre-hattı özgüllüğü** | **İDDİA 3 — Impact ağırlıklandırması** |
|---|---|---|---|
| cümle | Bu dupleksin ipliği şu genleri siRNA gibi baskılar | Aynı saRNA farklı hatlarda farklı siteleri riskli bulur | Susturulması daha kötü sonuç doğuracak genler doğru önceliklendiriliyor |
| bileşen | `sequence_specificity`, `biophysics_structure`, ifade/erişilebilirlik | `cell_modifier` | `variant_toxicity`, `execution_safety` |
| birim | **gen düzeyi** | site düzeyi | gen düzeyi |
| gerçek referans | **var ve bol** — GSE5814/5769/5291 (HeLa) | **yok** — aynı saRNA'nın iki desteklenen hatta transkriptom-geniş ölçümü kamuya açık değil | **yok ve hiçbir zaman olmayacak** — log2FC susturulmayı ölçer, sonucun ağırlığını değil |
| ön koşul | `C1` + `C3` + `D1` (+ `C0`, `C0b`) | `D2` + `B6` + canlı kanallar | — |
| splice-körlüğü etkiler mi | **HAYIR** — etiket gen düzeyinde, seed uzayı cDNA'da | **EVET** | hayır |
| sonuç | **doğrulanabilir → yayının gövdesi** | **doğrulanamaz → sınırı açık yazılır** | **doğrulanamaz → açıkça etiketlenmiş tasarım kararı** |

**İddia 3 neden ayrı:** gerçek referans (log2FC) yalnız *susturulmayı* ölçüyor.
`variant_toxicity` (0.15) + `execution_safety` (0.20) = nominal ağırlığın **~%35'i**,
etiketin **tanım gereği göremediği** bir boyutu ölçüyor — bir onkogenin susturulma
olasılığı, o onkogende kaç COSMIC mutasyonu olduğundan bağımsızdır. Bu bileşenler
*kusursuz çalışsa bile* PR-AUC'yi **düşürürler**. Ayrıştırılmazsa `E3a` pozitif çıksa
neyin işe yaradığı belirsiz, negatif çıksa negatiflik bir hatanın değil **kategori
karışıklığının** sonucu olur — ve değişmez 7 bir kaçış deliğine dönüşür. Bkz. `A7`.

**İddia 1'in kritik yolu kasıtlı olarak koordinatsızdır.** Doğrulandı: seed arama uzayı
ve ona bağlı her şey (`gene`, `transcript_id`, `tx_start`, `tx_end`, `mismatches`,
`alignment_score`) cDNA koordinat sisteminde hesaplanıyor; `GenomicRegion`
`seed_aligner.py:105-112`'de türetilip bir daha okunmuyor. Bu yüzden `E3a` ekzon
yürüyüşünü (`D2`) **beklemez**.

---

## 2. DEĞİŞMEZLER — hiçbir madde bunları ihlal edemez

1. **`data/` salt-okunur** (elle küratörlü referans verisi). Makine-indirilen veri
   `data/external/` altına gider, manifest'li. **`results/` elle düzenlenmez; yalnız
   Snakemake yazar.** Sonucu elle düzenlemek veri uydurmaktır.
2. **Arıza yönü kuralı:** veri yokluğu asla riski düşürmez. Yeni bir fallback açık bir
   *bilinmiyor* tipi döner, sayı dönmez. Sessiz `except: pass` yazılmaz.
   *Ölçüm: üç bağımsız fallback de "güvenli" yönüne arızalanıyordu —
   `_NEUTRAL_SIGNAL = 0.0`, ago2 URL yok → `0.0`, `mirbase_checker.py` istisna → `"SAFE"`.*
3. **Beyan = uygulanmış değil.** `git grep` ile üretim çağıranını göster, yoksa ekleme.
   *Ölçüm: `mypy strict=true` (araç kurulu değildi), `max_mismatches: 12` (atıl),
   `_NEUTRAL = 0.5` (hiç okunmuyor), h3k27me3 (9 config tanımı / 0 referans),
   `--json` (belgeliydi, çalışmıyordu).*
4. **Commit'lenmemiş = yok.**
   *Ölçüm: h3k27me3 "wired ✅" hafızası hiçbir commit'te yoktu; `verify-run` check 6
   aylarca commit'siz bekledi.*
5. **Test önce kırmızı olmalı.** Hatayı yakalayan test, düzeltmeden önce başarısız
   olduğu **gösterilmeden** merge edilmez. `fix-done` bu kanıtı sorar.
   *Ölçüm: 917 test yeşil geçerken bilinen üç hatanın üçünü de yakalamıyordu.*
6. **Ön kayıt kilitlidir.** `docs/PRE_REGISTRATION.md` `A6`'da commit'lendikten sonra
   düzenlenmez — bir hook da bunu engeller (`A2.6`). Değişiklik gerekiyorsa
   `docs/PRE_REGISTRATION_v2.md` açılır ve **ikisi de** yayında raporlanır.
7. **Negatif sonuç kabul edilir ve bir yayın yolu vardır** (§0 tablosu, üçüncü satır).
   Ağırlık, eşik veya sabit ayarlayarak pozitif sonuç aramak bu planın ihlalidir.
   **Özellikle:** ölü kanalları telafi etmek için eşik indirmek de bu kategoridedir.
8. **Her madde tek iştir.** Geçerken başka bir bulgu düzeltilmez.

---

## 3. MADDELER

> **Fazlar gruplamadır; otorite bağımlılık grafiğidir.** Birkaç madde kendi fazından
> sonraki bir fazdaki maddeye bağlıdır — en belirgini `C0` (bölge anotasyonu), GENCODE
> GTF'yi gerektirdiği için `D0`'a bağlı. `/next-fix` sırayı **grafikten** çözer, dosya
> sırasından değil.
>
> Grafiğin tutarlılığı (benzersiz id, tanımsız bağımlılık, döngü, kapsam ihlali, kapsam
> sayılarının tutması) mekanik olarak kontrol edilebilir. Kontrol **henüz CI'da değil** —
> prototip `orcSONAR-denetim/check_roadmap.py`, CI'a bağlanması `H6`/`H9`.
> Bu kontrol yazıldığı ilk gün gerçek bir çelişki yakaladı (`F4` üç aylık kapsamın
> içindeyken bağımlılığı `F1` dışarıdaydı) — hatırlanacak bir şey değil, kapı olmalı.

### FAZ 0 — Harness (≈3 gün)

> Tasarım gerekçeleri: `orcSONAR-denetim/PLAN_A_CLAUDE_MIMARISI.md`.
> Buradaki maddeler **sıra**, o dosya **neden**. Harness, projenin beş arıza tipini
> (H1 beyan-bağlanmamış · H2 commit'siz-yapılmış · H3 arıza yönü · H4 kopya-kayma ·
> H5 ölü kodda yeşil test) yapısal olarak imkânsız kılmak için var.

| id | iş | bağımlılık | kabul kriteri | durum |
|---|---|---|---|---|
| **H1** | **Dizin sözleşmesi.** `data/` elle küratörlü salt-okunur; **`data/external/`** makine-indirilen, manifest'li, yazılabilir; `results/` yalnız Snakemake. Sözleşme `CLAUDE.md` + `data/external/README.md`'de; yaptırım iki hook'ta (`_hooklib.is_writable_data`); `manifest.json` şema v1. **31 test** (`tests/hooks/`) prefix tuzağı (`data/externalEVIL`), `..` kaçışı ve "dışarı taşıma" dahil pinliyor. ⚠️ Kırmızı-önce kontrolü **gerçek bir açık buldu:** `curl`/`wget` hedef bayrakları hiç denetlenmiyordu — `curl -o results/<koşu>/stage7_scores.json` sonuç uyduruyordu. Kapatıldı. | — | `pytest tests/hooks/` yeşil; carve-out kaldırılınca kırmızı | **DONE** |
| **H2** | **`.claude/rules/`** — `00-degismezler.md` (paths yok, her oturum), `10-koordinatlar.md` ve `20-skor-degismezleri.md` (`paths:` ile kapsamlı). CLAUDE.md 139 → **115 satır**; taşınan içerik kopya olarak bırakılmadı. Ajanlara `skills: [orcsonar-data-sources]` + açık `effort`. ⚠️ **`30-veri-kaynaklari.md` kasıtlı olarak YAZILMADI** — chr-prefix tablosu zaten `docs/DATA_SOURCES.md`'de ve skill'inde; üçüncü kopya H4'ü çözmek yerine kötüleştirirdi. Otorite tablosu `00-degismezler.md` sonunda. ⚠️ **Yükleme doğrulanmadı:** rules açılışta/glob eşleşmesinde yüklenir, onları yazan oturumdan gözlenemez. `InstructionsLoaded` hook'u (`log-instructions-loaded.py`) kuruldu; kanıt **sonraki oturum açılışında** `.claude/instructions-loaded.log`'da. Yanlış bir glob ile çalışan bir glob bu log olmadan ayırt edilemez. ⚠️ **2026-11-17, sonraki oturum: enstrümanın kendisi ölüydü.** `log-instructions-loaded.py` 577c721'de **`100644`** commit'lenmişti (çalıştırılan diğer dört hook `100755`); shell onu çağıramıyor → açılış event'i `exit 126 Permission denied` ile düşüyor, log hiç yaratılmıyor. Kırmızı-önce kanıtı: elle çağrı `exit=126`; `chmod +x` sonrası aynı çağrı `exit=0` ve satır yazıldı. **H1 arıza tipinin, onu yakalamak için kurulan araçta tekrarı.** Düzeltildi + commit'lendi. ⚠️ **Kabul kriteri hâlâ karşılanmadı ve bu oturumda karşılanamaz:** açılış yolu `conditionalRule:!1` ile yalnız **glob'suz** kuralları yüklüyor (yani `00-degismezler`), `10-`/`20-` ancak `path_glob_match` ile gelir — ve bu oturumda ne `src/core/models.py` Read'i ne `tests/unit/*.py` Write'ı onları yükledi (içerikleri context'e girmedi, log boş kaldı). Glob'ların kendisi elendi: eşleştirme proje-köküne-göreli yolda gitignore semantiğiyle yapılıyor ve her iki dosyanın `paths:` değerleri de `git check-ignore` ile doğrulandı (`src/**/*.py` → `src/core/models.py` MATCH; `20-`'nin üçü de MATCH). ✅ **Kriter karşılandı (2026-11-17 11:55 UTC, logger düzeltildikten sonra).** Log üç kural dosyasını da gösteriyor: `CLAUDE.md` + `00-degismezler.md` → `session_start`; `src/scoring/integrator.py` Read'i → `20-skor-degismezleri.md` **ve** `10-koordinatlar.md`, ikisi de `load_reason: path_glob_match`, `trigger_file_path` ile. Yani `paths:` kapsamlı kurallar **atıl değil**, CLAUDE.md'nin "dokununca yüklenir" iddiası doğru. Not: Claude Code `paths:` değerlerindeki `/**` sonekini kırpıyor — log `20-`'nin glob'larını `["src/scoring","src/stage7_*","src/reporting"]` olarak gösteriyor; gitignore semantiğinde eşdeğer, `git check-ignore` ile doğrulandı. | H1 | `.claude/instructions-loaded.log` üç kural dosyasını da gösteriyor | **DONE** |
| **H3** | **Ajanlar:** her opus ajanına **açık `effort`** (⚠️ Opus 5.5 varsayılanı `medium` — bugünkü `bio-reviewer` koordinat denetimini medium'da yapıyor); `bio-reviewer` → xhigh; `literature-scout` → high; 🆕 `biostatistician` (opus/xhigh) ve `coordinate-engineer` (opus/xhigh + `isolation: worktree`); üç ajana rapor dizinine **Write**. ✅ **Yapıldı 2026-11-17.** Altı ajanın altısında da açık `effort`: `bio-reviewer` xhigh · `biostatistician` xhigh 🆕 · `coordinate-engineer` xhigh + `isolation: worktree` 🆕 · `literature-scout` high · `data-source-validator` medium · `pipeline-verifier` medium. `reports/` açıldı (README'li, **kasıtlı olarak gitignore'lanmadı** — değişmez 4 gereği bir rapor `git status`'ta görünür ve insan commit'lemeye karar verir). ⚠️ **"Yalnız rapor dizinine" kısmı yaptırımsız:** ajan frontmatter'ında `tools:` alanının yol kapsamı aldığına dair kanıt bulunamadı (Claude Code 2.1.326), o yüzden `Write` düz verildi ve kısıt her üç ajanın prompt'unda **yazılı bir kural**, hook'la zorlanan bir kural değil. `data/` ve `results/` zaten her yazar için korunuyor; korunmayan `src/`. Bunu H3 kapsamında düzeltmedim (değişmez 8) — yaptırım isteniyorsa `H11`'e `FileChanged`/`PreToolUse` kapısı olarak eklenmeli. | H2 | `.claude/agents/*.md` frontmatter'ında `effort` var | **DONE** |
| **H4** | **`SessionStart` hook'u** — faz, sıradaki madde, ön kayıt kilidi durumu, commit'siz dosya sayısı, ruff/mypy, null kapısının son sonucu. H1+H2 arıza tiplerini birlikte kapatır. ✅ **Yazıldı 2026-11-17:** `session-status.py` (ölçüm toplar) + `_status.py` (saf mantık + sözcükleme, test edilebilir). Altı ölçüm de **açılışta koşuluyor, hatırlanmıyor** — ruff ve mypy gerçekten çağrılıyor; ölçüm alınamazsa satır `ÖLÇÜLMEDİ` diyor, çünkü sessiz bir satır temiz bir satır gibi okunur (değişmez 2, her oturumun baktığı tek yerde). Sıradaki madde grafikten çözülüyor: ilk `TODO`, bağımlılıklarının **hepsi** `DONE` olan; **tanımsız bağımlılık karşılanmamış sayılır** (yazım hatası bir maddeyi öne alamaz). ⚠️ **H2'nin hook tuzağı artık teste bağlı:** `test_settings_hooks_are_executable`, `settings.json`'ın çağırdığı her hook'u hem diskte hem **git index'inde** (`100755`) doğruluyor — 2995092'de kaybedilen oturumun regresyon testi. Kırmızı-önce kanıtı: `_status` yokken 14 test kırmızı (toplama hatası + 13), exec-bit testi `session-status.py` commit'lenene kadar kırmızı. ⚠️ **Kapsam dışı bırakıldı:** `.claude/instructions-loaded.log` özeti (H4'ün altı maddesinde yok — `H11` adayı); `log-instructions-loaded.py` docstring'indeki o iddia düzeltildi. ⚠️ **Kabul kriteri H2'nin gözlemlenebilirlik tuzağını taşıyor:** elle çağrıda `exit=0` ve tam blok basılıyor, ama bir `SessionStart` çıktısı onu yazan oturumdan görülemez — kriter ancak **sonraki açılışta** kapanır. ✅ **Kriter karşılandı (2026-11-17 12:33 UTC — sonraki açılış).** `/clear` açılışında blok context'in **en üstünde** basıldı (environment bloğundan ve kullanıcı mesajından önce, `SessionStart:clear hook success`). Altı ölçümün altısı da değer taşıyor, hiçbiri `ÖLÇÜLMEDİ` değil: sıradaki `H6` (+8 hazır madde), ön kayıt yok/`A12` TODO/`H8` kurulmadı, commit'siz 0 dosya, ruff üç dizinde temiz, mypy 72 hata, null kapısı hiç koşmadı. ruff ve mypy açılışta gerçekten çağrıldı — hatırlanmadı. ⚠️ **Aynı açılışta görülen sapma, kapsamı gereği düzeltilmedi (değişmez 8):** faz satırı `13 madde: 3 DONE, 9 TODO` diyor, toplamı 12. `_status.py:156-158` yalnız `DONE` ve `TODO` sayıyor; `DOING`/`BLOCKED`/`DROPPED` `len(in_phase)`'e giriyor ama dökümde görünmüyor — yani **üzerinde çalışılan madde, her oturumun baktığı tek yerde kayboluyor.** `H4`'ün `DONE` olmasıyla sayı 13'e oturup semptom kaybolur, sözcükleme hatası kalır; `H11`'e eklendi. 🔴→🟢 **Aynı açılışın bulduğu ve H4 kapsamında düzeltilen hata:** `commit'siz` satırı dosya adını **`CIENTIFIC_ROADMAP.md`** diye bastı. `git()` tüm çıktıya `strip()` uyguluyordu; `git status --porcelain` kolon-biçimli (`XY path`) ve **staged olmayan** bir değişiklikte ilk kolon boş, dolayısıyla satır bir karakter sola kayıp `line[3:]` dosya adının içinden başlıyordu. İki uç da tek başına doğru (`uncommitted_text(' M x')` doğru çalışıyor) — kayıp **dikişte**, bu yüzden 65 testin hiçbiri görmedi (değişmez 5'in ölçümü, bu dosyada bir kez daha). Düzeltme: `git()` yalnız `rstrip()` yapar + script `if __name__ == "__main__"` ile sarıldı (collector'lar import edilip test edilebilsin diye). Kırmızı-önce: `test_git_keeps_the_porcelain_status_columns` ve `test_unstaged_file_is_named_in_full` düzeltmeden önce **ikisi de kırmızı**, sonra 67/67 yeşil. ⚠️ İlk açılışta çalışma ağacı temiz olduğu için satır `0 dosya` diyordu — hata **yalnız düzeltilecek bir şey varken** görünür oluyordu. | H2 | oturum açılışında durum basılıyor | **DONE** |
| **H5** | **`next-fix` + `fix-done` + `pre-register` skill'leri.** `fix-done` kabul komutunu koşar, geçmezse **reddeder**, ve **"kırmızı-önce" kanıtını sorar** (değişmez 5 — hiçbir hook bunu ölçemez). `pre-register` Faz A'dan önce hazır olmalı. ✅ **Yapıldı 2026-11-17.** Üç skill `.claude/skills/{next-fix,fix-done,pre-register}/` altında, her biri `SKILL.md` + `scripts/`. **Kabul modeli hibrit** (karar bu oturumda alındı): `.claude/acceptance/<ID>.sh` varsa `fix-done` onu koşar ve **çıkış ≠ 0 → maddeyi reddeder**, hiçbir gerekçe geçmez; betik yoksa kriter makineyle ölçülemiyor demektir (`H4`'ünki "blok açılışta basılıyor" — ancak sonraki oturumda gözlenebilir), `--declare` gözlemi kaydeder ve kapanış görünür biçimde daha zayıf olur: **`DONE(beyan)`** — denetlenebilir, doğrulanmamış. İki yargı asla birbirine karışmaz (değişmez 3). `--declare`, kapısı olan bir maddede **yok sayılır**; prose bir kapıyı geçemez. Sözcük dağarcığı `_status.py`'ye eklendi: `is_done()` iki biçimi de kapalı sayar (bağımlılık çözümü **ve** faz sayımı — `DONE(beyan)`'ı saymamak `DOING`'in `H11`'de kaybolduğu hatayı yeniden üretirdi), `preregistration_text` kilidi de ondan okur. `next_fix.py` yol haritasını **`_status.py` ile** okur, kendi parser'ını yazmaz (`H9`'un kapatacağı kopya-kayma). ⚠️ **`exit 0` tuzağı belgelendi** (`.claude/acceptance/README.md`): ölçülemeyen bir kriter için `exit 0` betiği yazmak kapıyı yalanlar, kapısız olmaktan kötüdür. ⚠️ **`fix-done` yol haritasını yazmaz** — kasıtlı: satıra giren kanıt prose'u yargı gerektiriyor ve 2000 karakterlik bir tablo satırını yeniden yazan betik, kazandırdığı yazım işinden büyük risk. Test bunu kilitliyor (`test_the_gate_does_not_write_the_roadmap`). ⚠️ **`pre-register` bugün `H8`'in yerine duran tek yaptırım:** commit'lenmiş dosyayı reddeder ve `PRE_REGISTRATION_v2.md`'yi adlandırır; git'in üç durumu ayrı tutulur (commit'li → kilitli / commit'siz repo → kesin açık / git okunamadı → **çıkış 2, ÖLÇÜLMEDİ, dosyaya dokunulmaz**, değişmez 2). Şablonun **her alanı** köşeli parantezli yer tutucu, önerilen metrik/eşik yok — varsayılan bir eşik kimsenin seçmediği eşiktir. Kırmızı-önce kanıtı: `test_fix_done.py` + `test_next_fix.py` 20 kırmızı (2'si sahte-yeşildi — `python -I` eksik dosyada çıkış 2 veriyor, iki test tam onu bekliyordu; betikler yazılınca anlamlı hale geldiler), `test_pre_register.py` 12 kırmızı; sonra **102/102 yeşil**, ruff temiz. Kapanış kapının kendisinden geçti: `.claude/acceptance/H5.sh` çıkış 0 — kapının ilk gerçek kullanımı kendi maddesi üzerinde. ⚠️ **Yorumlayıcı — ilk yazımdaki "sapma" iddiası yanlıştı, düzeltildi:** projenin yorumlayıcısı `~/.venvs/orcsonar` (Python 3.12.3, `pytest` 9.0.3 = `pyproject.toml` pin'i; `envs/orcsonar.yaml` bunun henüz oluşturulmamış conda aynası). Testler ilk turda yanlışlıkla `~/miniforge3/envs` altındaki bir conda ortamıyla koşuldu — o **başka bir çalışmanın** ortamı (Python 3.11.15, `orcsonar` kurulu değil) ve orada tek ortam olduğu için seçilmişti. Bu satırda bir süre "env adı sapması" diye gerçek olmayan bir bulgu durdu; tam olarak bu dosyanın var olma nedeni olan hata tipi (değişmez 3), bu yüzden silinmedi, yazılı bırakıldı. Doğru ortamda yeniden koşuldu: `tests/hooks` 102/102 ve `H5.sh` çıkış 0. Kabul betiği `$PYTHON` → `python3` → `python` sırasıyla arar ve **bulamazsa geçmez** (sessizce atlamaz); kanonik yorumlayıcıyı CI'da `H6` sabitleyecek. ⚠️ `DONE(beyan)` henüz hiçbir maddede kullanılmadı — ilk kullanımında tabloda tek sözcükle ayırt edilebilir olmalı. | H4 | üçü de çalışıyor; `fix-done` geçmeyen maddeyi reddediyor | **DONE** |
| **H6** | **CI** — `pytest` + `ruff check src/` **bloke edici**, `mypy` **bilgilendirici**, null kapısı (`E1`) eklendiğinde bloke edici. ⚠️ `B10`'a **da** `B10a`'ya **da** bağlı değil: 39 kosmetik generic anotasyon ana deneyin kritik yolunda duramaz, ve mypy bilgilendirici kurulduğu için hata sayısı CI'ı kırmaz. ⚠️ Ruff kapsamı: `src/`, `.claude/hooks/`, `tests/hooks/` bugün temiz; **`tests/` geri kalanında 50 birikmiş hata var** (F401, I001, B017, F841 — kosmetik). CI ya bu kapsamla kurulur ya da birikmiş borç önce temizlenir; kapsamı sessizce geniş bırakmak CI'ı ilk gün kırmızı yapar ve kapatılmasına yol açar. ✅ **Yapıldı 2026-11-18:** `.github/workflows/ci.yml` (tek `gate` job'ı, ubuntu-latest) + `tests/hooks/test_ci_workflow.py` — workflow'un **her kararını** kilitleyen 11 test, ve bu testler CI'ın kendi içinde koşuyor, yani dosya ile kuralları bir merge'de ayrışamıyor. ⚠️ **Satırdaki "50 kosmetik" iddiası yanlıştı, ölçülüp düzeltildi:** 31'i mekanik (21 `F401`, 10 `I001`, 1 `UP041` — hepsi `[*]`), ama **7'si `B017` kör `pytest.raises(Exception)`** ve skor-ağırlığı doğrulayıcısı ile ClinVar/gnomAD istemcilerinin üstünde duruyorlar; borç değil **bulgu**. Ayrı maddelere çıkarıldı: `H14` (mekanik 31) ve `H15` (yargı gerektiren 19). Aynı yanlış iddia `_status.py:RUFF_SCOPE` yorumunda da vardı, orada da düzeltildi. 🔴→🟢 **CI'ı ilk gün kırmızı yapacak asıl tuzak:** `pyproject.toml` linter'ları **taban** ile veriyordu (`ruff>=0.6`, `mypy>=1.11`). CI her koşuda en son ruff'ı kurar, yeni bir ruff sürümü kural ekler ve **hiç değişmemiş bir ağaç** kırmızıya düşer — bir CI'ın kapatılmasının en bilinen yolu. Dördü de tam pin'lendi (`ruff==0.16.7`, `mypy==2.4.1`, iki stub) ve `test_the_linters_are_pinned_exactly` bunu kilitliyor; stub'lar da pin'li çünkü mypy'nin hata sayısını durum satırı **sayı olarak** basıyor. **Ölçümler (hepsi bu oturumda koşuldu):** ağ kapalıyken tam takım 1019 passed (96 s) → testler ağa bağımlı değil; veri olmayan temiz klonda 948 passed + **71 skipped** (133 s) → CI yeşil olacak ama suitenin %7'sini hiç koşmuyor, o yüzden `-rs` eklendi, atlananlar log'da görünüyor; `git archive` tarball'ında `tests/hooks`'tan **8 test düşüyor** (exec-bit'i git index'inde arıyorlar) → CI tarball üzerinde koşturulamaz, `actions/checkout` zorunlu ve test bunu kilitliyor. Bağımlılıklar: `pip install -e ".[dev]"` tek otorite; `src` importları için kurulum **gerekmiyor** (`__init__.py`'ler repo kökünü `sys.path`'e koyuyor, temiz klonda doğrulandı) ama pin'leri pyproject'ten almanın tek yolu bu. Wheel durumu ölçüldü: `pyBigWig==0.3.25` cp312 `manylinux_2_17` wheel'i **var** (ilk probe'um `--platform manylinux_2_28` verdiğim için yanlış "yok" demişti), `pysam==0.23.3` cp312 wheel'i var, **`hic-straw==1.3.1`'in Linux wheel'i hiç yok** (yalnız macOS cp39 + sdist) → her zaman kaynaktan derleniyor, o yüzden `libcurl4-openssl-dev` + `zlib1g-dev` apt adımı. ⚠️ Yorumlayıcı **3.12**: suitenin yeşil olduğu ölçülmüş tek sürüm. `requires-python = ">=3.11"` iddiası **hiç ölçülmedi** (değişmez 3) — 3.11 matrisi eklemek CI'ı ilk gün kırmızı yapma riski, kendi maddesi olmalı. ⚠️ `--cov-fail-under` **konmadı**: `run()` adapterları %0 (Bulgu-3), eşik ilk günde düşerdi; ayrıca bir coverage eşiği test yazmakla da test silmekle de karşılanır. mypy `continue-on-error`. ⚠️ Action'lar sürüm etiketiyle (`@v4`/`@v5`), SHA ile değil — bu projenin pin disiplinine göre bir tutarsızlık, ama üçüncü-parti action'ı SHA'ya çivilemek ayrı bir karar. ⚠️ **Kriter ikiye bölündü, daraltılmadı:** kapı (`.claude/acceptance/H6.sh`) yalnız yerelde ölçülebilir yarıyı ölçüyor ve "Actions'da yeşil + zorunlu" için açıkça **ÖLÇÜLMEDİ** basıyor; o yarı `H6b`. `H6` + `H6b` birleşimi özgün "CI yeşil ve zorunlu" ifadesinin aynısı. | H2 | CI kurulu, kararları kilitli, koştuğu komutlar yerelde geçiyor (ikinci yarı: `H6b`) | **DONE** |
| **H6b** | **CI'ın "zorunlu" yarısı** — GitHub Actions'da ilk koşunun yeşil olması, ve `main` için **required status check** olarak işaretlenmesi. ⚠️ `H6`'dan ayrıldı çünkü bu yarı yerelde ölçülemez: branch protection bir repo **ayarı**, `gh` bu makinede kurulu değil, ve bir kabul betiğine `exit 0` yazıp geçmiş saymak kapıyı yalanlamak olur (`.claude/acceptance/README.md`). Bölme kriteri **daraltmıyor**, iki yarının her birine hak ettiği yargıyı veriyor — ve zayıf olan yarı `TODO` olarak görünür kalıyor. Yalnız **beyanla** kapanır: `fix-done H6b --declare "<koşu linki + ayarın ekran görüntüsü/doğrulaması>"` → `DONE(beyan)`. Ayarda aranacak kontrolün adı **`CI / gate`** (workflow adı `CI`, tek job'ın adı `gate`); job yeniden adlandırılırsa branch protection'daki zorunlu kontrol **sessizce kopar** ve kapı açık kalır — `test_ci_workflow.py`'de job adını kilitleyen bir test yok, `H6b` kapanırken eklenmeli. Ayarı çeviren insan olmak zorunda; bu, projede `DONE(beyan)`'ın ilk gerçek kullanımı olacak. ⚠️ `H5`'in kapı modelinde bir boşluğu ortaya çıkardı: kriteri **kısmen** makineyle ölçülebilen maddeler için `fix-done`'ın "kapı + beyan" bileşimi yok, bu yüzden bölme gerekti. Üçüncü böyle bir madde çıkarsa `fix-done`'a kısmi-kapı semantiği eklenmeli (`H11` adayı). ✅ **Birinci yarı ölçüldü (2026-11-18), beyan değil:** `gh` kuruldu (`~/.local/bin/gh` 2.105.0, SHA256 doğrulandı) ve giriş yapıldı; `gh run list` → koşu `44320928560`, sha `8132fc5`, workflow `CI`, job `gate`, **conclusion: success**, on bir adımın hepsi yeşil. `hic-straw` sdist derlemesi runner'da gerçekten çalıştı (3m45s). ⚠️ **İlk yazımdaki "bu planda YAPILAMAZ" iddiası YANLIŞTI — geri çekildi.** Private repoda `gh api repos/.../branches/main/protection` ve `.../rulesets` **HTTP 403** *"Upgrade to GitHub Pro or make this repository public"* dönüyordu, ve ben bu **okuma kısıtını yokluk kanıtına** çevirdim: "ayar yapılmış olamaz" dedim. Doğrusu "doğrulayamıyorum"du. Repo public yapılınca aynı endpoint'ler okunabildi ve **kurallar oradaydı**: `main-1` (aktif, `refs/heads/main`, silme + force-push engelli) ve `main-2` (aktif, `required_status_checks`). Yani 403, kuralların yokluğunu değil yalnız okunamadığını gösteriyordu — değişmez 2'nin kendi üzerime düşen hali. 🔴 **Ama gerçek durum da "kurulu" değildi:** `main-2`'nin `required_status_checks` listesi **boş** (`[]`) — kural aktif, ayar sayfası yeşil, **ve hiçbir merge engellenmiyor.** Bu satıra teorik bir tuzak olarak yazdığım "GitHub var olmayan/boş bir ad listesini de kabul eder, kural yeşil görünür" cümlesinin gerçekte olmuş hali. ⚠️ Repo bu nedenle (ve kullanıcı kararıyla) **public** yapıldı; public öncesi denetim ve README'nin ölçülmüş sınırları `e8b21c2`'de. **Bu maddenin ayrılmasının karşılığı tam olarak buydu:** beyanla kapatılsaydı yol haritası "main korumalı" iddiasını kalıcı olarak taşıyacaktı ve `main`'e korumasız merge edilebildiği ancak bir kaza anında görülecekti. Kriter **gevşetilmiyor** (değişmez 7); karar kullanıcının, dört yol var: **(1)** repo public yapılır → koruma ücretsiz açılır, **(2)** GitHub Pro'ya geçilir, **(3)** koruma yok olarak kabul edilir ve yayında dürüst bir sınır olarak **yazılır**, **(4)** yerel `pre-push` hook'u `main`'e push'u HEAD için yeşil koşu yoksa reddeder — ⚠️ bu *yaptırım değil*, yalnız bu makinede çalışır ve `--no-verify` ile atlanır; (3) ile birlikte yazılabilir ama (1)/(2)'nin yerine geçmez. ✅ **Kapı yazıldı: `.claude/acceptance/H6b.sh`** — dört ölçüm: `gh` var ve giriş yapılmış mı (yoksa **geçmez**, atlamaz) · HEAD için CI koşusu `success` mi (süren koşu ile hiç koşu olmaması ayrı mesajlar) · `main`'i hedefleyen **aktif** bir kuralın zorunlu kontrol listesi boş değil mi · ve **o adın gerçekten koşan bir kontrol adı olduğu** (`commits/<sha>/check-runs` ile karşılaştırma). Dördüncüsü bu maddenin bütün sebebi: onsuz kapı da yalan söyleyebilirdi. Betik **403'ü "kural yok" diye okumuyor**, ayrı bir arıza olarak bildiriyor. Kırmızı-önce: boş liste varken kapı reddediyor. Kalan tek adım, zorunlu listeye `gate` (sağlayıcı `github-actions`, `integration_id: 15368` — kaynağından okundu, varsayılmadı) eklenmesi; repo ayarı yazan API çağrısı bu oturumda araç izniyle engellendi, o yüzden kullanıcı tarafından yapılıyor. ⚠️ **Yan bulgu (gelecek kapılar için):** Actions REST API'si `continue-on-error` ile maskelenmiş bir başarısızlığı adım sonucu olarak **`success`** gösteriyor — mypy çıkış 1 verdiği hâlde adım `success`, hata yalnız annotation'da. Yani koşu sonuçlarını programatik okuyan bir kapı, mypy'nin bilgilendirici olduğunu göremez. | H6 | Actions'da yeşil koşu var ve `main`'de zorunlu kontrol olarak işaretli | BLOCKED(GitHub planı — private repo + ücretsiz plan) |
| **H7** | **Commit kapısı** — `PreToolUse` + `if: "Bash(git commit *)"`. ⚠️ pytest işareti **mtime-taze** olmalı: düzenlemeden *önce* koşulan pytest kapıyı açarsa kapının kendisi H1 arızası üretir. `src/`→`tests/` koşulu **uyarı**, bloke edici değil (proxy çok kaba; saf refaktörü ve Faz D worktree'sini engeller). | H6 | eski pytest ile commit reddediliyor | TODO |
| **H8** | **Ön kayıt kilidi** — `PreToolUse` + `if: "Edit(docs/PRE_REGISTRATION.md)"` → `A12` commit'i varsa reddet. ⚠️ **Faz A'dan ÖNCE bitmeli.** Değişmez 6 bugün yalnız bir belge cümlesi; ihlali en sinsi arıza (sonucu görüp eşiği oynatmak). | — | kilitli dosyaya edit reddediliyor | TODO |
| **H9** | **Tek-kopya kapısı (H4 arıza tipinin gerçek çözümü).** Kanonik gerçekler otorite listesi dışında bir dosyada görünürse CI kırmızı. ⚠️ Otorite listesi önce tanımlanır — ham grep `docs/DATA_SOURCES.md`'deki **meşru** kopyaya takılır ve kapı ilk günde kapatılır. | H2, H6 | otorite tablosu yazılı; kapı CI'da | TODO |
| **H10** | **Run manifest** — her koşu çıktısına git SHA, config hash, kaynak sürümleri, seed'ler, `data/external/` checksum'ları. *Dört mevcut koşunun "eski iki-parçalı `site_id`" formatında olduğu elle keşfedildi.* `G-VI` kapısının parçası. | H6 | her `results/*/` altında `manifest.json` | TODO |
| **H11** | `FileChanged` (config anahtarı eklendi ama üretim çağıranı yok → uyarı) + `PostToolUse`'a mypy + `Stop`'ta **bloke etmeyen** özet. ⚠️ `Stop` üzerinde bloke etme **düşürüldü**: `H7` aynı kuralı daha iyi bir noktada uyguluyor. 🆕 **Durum satırı sayım dökümü** — `_status.phase_text()` yalnız `DONE` ve `TODO` sayıyor; `DOING`/`BLOCKED`/`DROPPED` `len(in_phase)`'e giriyor ama dökümde görünmüyor. **İki kez oldu, ikincisi daha kötü:** `H4`'te (2026-11-17) `13 madde: 3 DONE, 9 TODO` — üzerinde çalışılan madde kayboldu; `H6b`'de (2026-11-18) `16 madde: 6 DONE, 9 TODO` — **`BLOCKED` madde kayboldu**, yani kullanıcı kararı bekleyen ve kendi başına asla ilerlemeyecek tek madde, her oturumun baktığı yerde görünmez oldu. Önceliği buna göre yüksek. (Eski kayıtta `_status.py:156-158` yazıyordu; `is_done()` eklenince satır kaydı kaydı — bu yüzden artık fonksiyon adıyla anılıyor.) 🆕 Ayrıca `H3`'ten: ajan `Write`'ına yol kapsamı (`src/` korunmuyor) ve `H4`'ten: `.claude/instructions-loaded.log` özeti. | H6 | üçü de çalışıyor | TODO |
| **H12** | **Sandbox** — `sandbox.filesystem.denyWrite`: `data/` **minus** `data/external/**`. `results/` sandbox'a **konmaz** (Snakemake yazacak). `block-bash-writes.py`'nin kabul ettiği `python3 -c open(...)` deliğini kapatır. Sıra: `failIfUnavailable: false` → `snakemake -n` + tam koşu ile doğrula → kalıcı. | H1, H6 | `data/` yazma engelleniyor, `data/external/` ve `results/` çalışıyor | TODO |
| **H13** | `null-check` + `claim-check` skill'leri (`claim-check`: `context: fork`, sonnet/high). | H3, H6 | ikisi de çalışıyor | TODO |
| **H14** | **`tests/` ruff borcu — mekanik kısım.** 31 bulgu: 21 `F401` kullanılmayan import, 10 `I001` import sırası, 1 `UP041`; üçü de `[*]` otomatik düzeltilir ve davranış-nötr. Tek `ruff --fix` commit'i. ⚠️ `H15`'in yargı gerektiren 19'uyla **aynı commit'e girmez** — girerse 7 gerçek bulgu kosmetik bir temizliğin içinde kaybolur, ki bu tam olarak `H9`'un kapatmaya çalıştığı türden bir gizlenmedir. İkisi de bittikten sonra `_status.RUFF_SCOPE` genişletilir ve `.github/workflows/ci.yml` ile `tests/hooks/test_ci_workflow.py` ona göre güncellenir. | H6 | `ruff check tests` mekanik kuralların hepsinde temiz; kapsam henüz genişletilmedi | TODO |
| **H15** | **`tests/` ruff borcu — bulgu kısmı: 7 kör istisna iddiası.** `B017 pytest.raises(Exception)` *herhangi* bir istisnayı kabul eder, alan adı yazım hatasından gelen `TypeError` dahil. Nerede durdukları önemli: `test_config.py:21` **skor ağırlıkları toplamı 1.0 doğrulayıcısı**, `test_config.py:44` `load_config` geçersiz hücre hattı, `test_clinvar_client.py:185,228` (denetimde **%100 ölü** çıkan kaynak), `test_gnomad_client.py:265,300` (**işareti ters** bulunan kaynak), `test_repeat_scanner.py:199`. Aynı dosyada `test_missing_file_raises` `FileNotFoundError` ile düzgün yazılmış — kalıp biliniyor, tutarsız uygulanmış. Her biri beklenen istisna **tipine** daraltılır ve daraltıldıktan sonra da geçtiği gösterilir; geçmiyorsa testin ne doğruladığı belli değildi ve o da bir bulgudur. Kalan 11: 5 `F841` + `B007`×3, `E741`, `SIM117`, `E402` — tek tek bakılır, hepsi kosmetik değil. *Ölçüldü 2026-11-18:* `test_tss_mapper.py:177`'deki kullanılmayan `rsps` **kasıtlı ve doğru** (boş `RequestsMock` = "hiç HTTP çağrısı olmasın" iddiası, isimlendirme artığı); `test_thermodynamics.py:247`'deki `mm_result` terk edilmiş taslak kalıntısı ve üstündeki yorum asserte **edilmeyen** bir karşılaştırmayı anlatıyor. | H14 | 7 `B017`'nin hepsi tipli ve her biri daraltıldıktan sonra da geçiyor | TODO |

---

### FAZ A — Ön kayıt (kod yazılmaz, 2-3 gün)

> `biostatistician` ajanı **burada** devreye girer, Faz E'de değil — en pahalı hatalar
> ön kayıt anında yapılır ve ön kayıt kilitlidir.

| id | iş | bağımlılık | kabul kriteri | durum |
|---|---|---|---|---|
| **A1** | Mekanizma kararı: modellenen şey **saRNA dupleksinin her iki ipliğinin** siRNA-benzeri seed off-target'ı. ⚠️ "guide ipliğinin" demek PR-AUC tavanını düşürür — etiketteki pasajer-iplik pozitifleri tanım gereği görülemez (bkz. `C0b`). | H5 | `docs/PRE_REGISTRATION.md` §1 mekanizmayı tek cümlede söylüyor | TODO |
| **A2** | Gerçek referans setini kilitle: **GSE5814** (68 örnek, HeLa, seed pozisyon mutantları — en güçlü), GSE5769, GSE5291, GSE41924, GSE44256/44105, GSE278438/9. | A1 | §2'de accession + n + tasarım | TODO |
| **A2b** | **Her accession'ın kimliğini, yayınını ve tasarımını NCBI'dan doğrula — kilitlemeden önce.** Ön kayıt kilitli olduğu için yanlış accession geri alınamaz. *Yapıldı: GSE5814 = Jackson ve ark. 2006, PMID **16682560**, "Widespread siRNA off-target transcript silencing mediated by seed region sequence complementarity". (Birmingham 2006 Nat Methods 3:199 **başka** bir veri setidir.)* | A2 | her accession için doğrulanmış PMID + örnek sayısı | TODO |
| **A3** | Etiket tanımı: gen düzeyinde belirgin aşağı regülasyon, eşik önceden sabit (öneri `log2FC ≤ −0.3`). | A2b | §3'te eşik sayı olarak | TODO |
| **A4** | Metrik: **PR-AUC** (birincil) + ROC-AUC + ECDF/KS. ⚠️ Bu literatürde ROC-AUC standart değil — siSPOTR Spearman, SeedMatchR KS kullanıyor; tek metrik olarak AUC "olağan karşılaştırma" sayılmaz. CV: leave-one-siRNA-out. | A3 | §4'te metrik + CV şeması | TODO |
| **A5** | **Tabanlar — üçü de 3'UTR tanımlı:** (i) 3'UTR 7mer-m8 varlığı/sayısı, (ii) siSPOTR POTS, (iii) **transkript / 3'UTR uzunluğu tek başına**. ⚠️ (iii) kritik: denetim hit ile cDNA uzunluğu arasında **r = 0.349** buldu; uzun ve yüksek ifadeli transkriptler hem daha çok seed eşleşmesi hem daha güvenilir DE çağrısı alır. | A4 | §5'te üç taban tanımlı, bölge açıkça yazılı | TODO |
| **A6a** | **Kabul kriteri:** orcSONAR'ın PR-AUC'si her üç tabanı da leave-one-siRNA-out CV'de **ve uzunluk tabakaları içinde** aşmalı. Aşmazsa sonuç **negatif olarak** raporlanır (§0, üçüncü satır). | A5 | §6'da sayısal eşik | TODO |
| **A7** | **Skoru iki açık bileşene ayır — planın en önemli bilimsel kazancı.** `P_silence` = f(sequence_specificity, biophysics_structure, ifade/erişilebilirlik) → **doğrulanabilir**. `Impact` = g(variant_toxicity, execution_safety) → **gerçek referansı yok**, önceliklendirme katmanı olarak açıkça etiketlenir. ⚠️ **İki ayrı sütun olarak raporlanır.** Birleşik tek skor istenirse birleştirme kuralı ayrı bir ön kayıt maddesidir ve gerekçesi yazılır — çarpımsal form (`P × Impact`) kanıtsız bir etkileşim modeli varsayar. | A1 | §7'de ayrışma ve her bileşenin doğrulanabilirlik durumu yazılı | TODO |
| **A8** | **Detectability filtresi:** değerlendirme evreni "HeLa'da ölçülebilir düzeyde ifade edilen genler" (CCLE elde). İfade edilmeyen gen aşağı regüle olamaz; ön kayıtta olmazsa PR-AUC yapay şişer ve sonradan eklemek ihlal olur. | A3 | §8'de filtre tanımı + eşik | TODO |
| **A9** | **On-target ve ikincil etki dışlaması:** hedef genin kendisi ve bilinen doğrudan alt akışı pozitif sayılamaz. | A3 | §9'da dışlama listesi kuralı | TODO |
| **A10** | **`_clamp` yerine gelecek haritalamayı ön kayda yaz.** `alignment_score`'u [0,1]'e **nasıl** haritalayacağın bir modelleme kararıdır (min-max? teorik maksimuma bölme? yüzdelik?) ve sonucu gördükten sonra değiştirilemez. Bugünkü `_clamp` bir hata; yerine gelecek şey bir **karar**. | A4 | §10'da haritalama formülü | TODO |
| **A11** | **RNAa'nın yeri:** promoter/RNAa arama uzayı ikinci bir çıktı sütunu olarak **raporlanır ama doğrulanmaz** — her saRNA için promoter penceresine seed eşleşmesi hesaplanır, `validated: false` etiketiyle sunulur. `promoter_region.py` zaten var, iplik-farkında ve doğru, yalnız hiç okunmuyor. Maliyet ~0; projenin kimliğini korur, doğrulanmamış iddia üretmez. | A1 | §11'de yazılı | TODO |
| **A12** | Ön kaydı commit'le, hash'ini not et. Bundan sonraki her analiz bu hash'e atıf yapar. **Bu commit'ten sonra dosya kilitlidir** — kilidi `H8` uygular, o yüzden `H8` bu maddeden önce bitmiş olmalı. | H8, A6a, A7, A8, A9, A10, A11 | `git log -1 --format=%H docs/PRE_REGISTRATION.md` | TODO |

---

### FAZ B-HIZLI — doğruluk değişmezleri (2 gün, `E3a`'dan önce)

> Lokus-bağımlı kanalların onarımı buraya **girmez** — onlar `D2`'den sonra bir kez
> yapılır (B-sonra). Burada yalnız "yeni sayı üretmeden önce düzeltilmesi gereken"
> doğruluk değişmezleri var.

| id | iş | bağımlılık | kabul kriteri | durum |
|---|---|---|---|---|
| **B0** | **Cache'e `schema_version` + geçersizleme. ÖNCE BU.** `clinvar:%` anahtarları koordinat tabanlı; `B1` düzeltilse bile eski boş sonuç **30 gün** servis edilir ve düzeltmenin işe yaramadığı sanılır. | — | yeni sürüm eski anahtarları kullanmıyor (test) | TODO |
| **B1** | **ClinVar'ı canlandır** — `clinvar_client.py:134-138` literal `+AND+` gönderiyor, `requests` `%2B`'ye kodluyor. Canlı A/B: kodun biçimi **0**, doğrusu aynı pencerede **121 patojenik**. 15 dakika / 2 karakter. | B0 | >0 patojenik varyant; regresyon testi | TODO |
| **B2** | **Fallback'i *bilinmiyor* tipine çevir.** `_NEUTRAL_SIGNAL = 0.0` → açık sentinel. ⚠️ Sentinel'i 0.5 yapmak **yetmez**: sabit ham-sinyal uzayında, 0.5 sözleşmesi skor uzayında (AUDIT.md Bulgu-10). | — | hiçbir fallback yolu sayısal risk değeri dönmüyor | TODO |
| **B4** | **gnomAD işaretini düzelt** — üretici "korunmuş = 1.0 = yüksek risk", tüketici `variant_merger.py:36-38` `1.0 - skor` ile tersliyor. | — | işaret testi: korunmuş > polimorfik | TODO |
| **B10a** | **İki gerçek mypy hatasını düzelt** (geri kalan 72 değil): `shape_profile.py:300-301` `max()`/`min()` çağrısı `int \| None` üzerinde ve üstündeki `type: ignore[arg-type]` mypy'nin bildirdiği kodu bile kapsamıyor; `transcriptome_fetcher.py:258-267` `None` koordinatı `TranscriptInfo`'ya verebiliyor → ValidationError → `seed_aligner`'ın **sessiz düşürme** yoluna gidiyor. ⚠️ İkincisi `D1`'de 250k transkriptle **ölçeklenerek** sessiz kayıp üretir. | — | iki hata kapandı, regresyon testi var | TODO |
| *(CI)* | CI kurulumu **`H6`**'dadır — Faz 0'a taşındı, burada tekrar edilmez. | — | — | — |

---

### FAZ C — İddia 1'in ölçtüğü kanalları çalışır hale getir (1-1,5 hafta)

| id | iş | bağımlılık | kabul kriteri | durum |
|---|---|---|---|---|
| **C1** | **`_clamp`'i düzelt — gün 1-2.** Ham seed skorları 41 sitede **12 ayrık değer** taşıyor (8.0, 8.5 … 14.5) ve sabit `1.0`'a eziliyor. Bu, bugün projede **koordinat hatasından etkilenmeyen, site bazında gerçekten farklılaşan ve gerçek referansla doğrudan karşılaştırılabilir tek kanal** — ve İddia 1'in ölçtüğü şeyin ta kendisi. Haritalama `A10`'dan gelir. | A10 | `sequence_specificity` 41/41 sabit değil; `A10`'daki formül uygulandı | TODO |
| **C0** | **3'UTR / CDS / 5'UTR bölge anotasyonu.** Her siteye `region_class ∈ {5utr, cds, 3utr}`. ⚠️ **Doğrulandı: bölge farkındalığı bugün sıfır** (`grep -riE "utr\|cds_start" src/` → gerçek isabet yok). Tabanların hepsi literatürde 3'UTR tanımlı; bu olmadan `E3a` savunulamaz. GENCODE GTF `CDS`/`UTR` özelliklerini zaten taşıyor → `D0` indirildiğinde neredeyse bedava (Faz D tasarrufunun **üçüncü yüzü**). | D0 | her sitede `region_class` var | TODO |
| **C0b** | **İki ipliği de tara.** Her siteye `strand_origin ∈ {guide, passenger}`. ⚠️ **Doğrulandı: `seed_aligner.py:198` yalnız `reverse_complement(seed)` indeksliyor.** GSE5814 gibi bir sette pasajer-iplik off-target'ları **etikette mevcut**; tek iplik tarayan tahminci onları tanım gereği göremez → PR-AUC tavanı 1'in altında ve sebebi skor kalitesi değil. Maliyet: `run_seed_scan`'i ikinci dizi ile bir kez daha çağırmak. | — | her sitede `strand_origin`; iki iplik de taranıyor | TODO |
| **C3** | **ΔG'yi PAKET olarak düzelt** — hizalama + hedef + eşik **birlikte**. `delta_g_calculator.py:79-82` fazladan `reversed()` yüzünden 18/20 "mismatch" → 41/41 site aynı **+31.10**. Hizalamayı tek başına düzeltirsen **−43.80** çıkar ve `≤ −30` eşiğiyle tüm siteler 1.0'a fırlar. ⚠️ **`C2`'ye bağlı DEĞİL ve Faz D'yi beklemiyor:** `tx_start`/`tx_end` payload'da mevcut (`"tx_start": 7093, "tx_end": 7113`), hedef dizi cache'li cDNA'dan dilimlenebilir. Temiz varyant: stage 2 ayrıca 20-nt `target_window` emit etsin (~3 satır). Tamamen dizi-hesaplı → `E3a`'ya dahil. | — | ΔG negatif, siteler arası varyans > 0, hiçbir site 1.0'a saplanmıyor | TODO |
| **C4** | **Çift sayımı kaldır** — epigenetik ve execution sinyalleri hem `base_score`'a hem `cell_modifier`'a giriyor. `apply_cell_modifier()` `scoring_weights`'i hiç okumuyor; `0.40/0.40/0.20` ve `0.30 + 1.40×` hardcoded. `A7` ayrışmasının doğal sonucu. | A7 | `config.yaml` ağırlığını değiştirmek skoru öngörülen oranda değiştiriyor | TODO |

---

### FAZ D — GENCODE geçişi (5-7 hafta)

> **Tasarruf kararı:** Bulgu-6 (183 gen), Bulgu-8 (splice-körlüğü) ve `C0` (bölge
> anotasyonu) **aynı işin üç yüzü** — GENCODE GTF ekzon bloklarını *ve* CDS/UTR
> özelliklerini zaten taşıyor.
> **Ama tek commit değil, iki checkpoint:** `D1` bittiğinde ana ağaca merge edilebilir
> bir durak olmalı (indeks çalışıyor, koordinatlar hâlâ eski ve işaretli). Aksi halde
> İddia 1 gereksiz yere `D2`/`D4`'ü bekler. `isolation: worktree` önerilir.

| id | iş | bağımlılık | kabul kriteri | durum |
|---|---|---|---|---|
| **D0** | GENCODE sürümünü seç ve indir (GTF + transkript FASTA) → **`data/external/`** (bkz. değişmez 1; `data/` sandbox'ı bu dizini dışarıda bırakır). | — | sürüm + checksum `docs/DATA_SOURCES.md`'de | TODO |
| **D1** | **Yerel seed indeksi** (~250k transkript) — **checkpoint 1, merge edilebilir.** Mevcut `_BACKGROUND_GENES` 183 gen (iki docstring "~250 genes" diyor, o da yanlış). Geçerlilik itirazının kökü: 41 hit'in geldiği 29 genin **tamamı** listeden; zenginleşme biyolojiden değil **transkript uzunluğundan** (r = 0.349, medyan cDNA 5.326 vs 2.828 nt). | D0 | 183-gen listesi kodda yok; tarama tam transkriptom üzerinde | TODO |
| **D2** | **Ekzon yapısı + cDNA→genomik yürüyüş** — checkpoint 2. *Ölçüm: medyan sapma **30.732 bp**, maks 182.707 (EGFR), 39/41 site >1 kb; "doğru" çıkan 2 site retained-intron izoformu.* Pencereler sistematik olarak **intron içine** düşüyor → korunmasız, mutasyon-seyrek, kapalı kromatin → **risk sistematik olarak küçümseniyor.** | D1 | ekzon-farkında koordinatlar; `D3` sayıları tutuyor | TODO |
| **D5** | **Toplu/yerel anotasyon mimarisi — planın eksik maliyeti.** Site-başına uzak sorgu → yerel, indeksli, önceden materyalize edilmiş anotasyon deposu (BigWig aralık çıkarımı tek seferde; COSMIC/gnomAD/ClinVar bölgesel dökümü yerel tabix/parquet; interval-tree aralık sorgusu). ⚠️ **Aritmetik:** 4⁷ = 16.384 nt'de bir rastgele 7-mer → ~450 Mb GENCODE cDNA'da **~24.000 site/koşu**. Yalnız gnomAD (1 req/s) tek koşuda **6,7 saat**; `E3b` için 100-150 siRNA → **2-4 milyon site-anotasyonu**. **Bu madde olmadan `E3b` koşamaz.** | D1 | tam koşu site-başına uzak sorgu yapmıyor; 24k site < 1 saat | TODO |
| **D3** | **Yeniden koş ve doğrula.** Beklenen: COSMIC 31→**350**, phyloP ort. 0.027→**0.418**, phyloP>2 site 0→**16**, m6A 0→**10**. | D2, D5 | ölçülen değerler bu mertebelerde | TODO |
| **D4** | **Eşikleri yeniden kalibre et.** `max_mismatches: 12` şu an **hiçbir adayı elemiyor** (≤12→41, ≤8→28, ≤6→7, ≤4→0, ≤3→0); modül docstring'i "max 3" diyor, 3 olsaydı çıktı boş olurdu. (Not: `core/config.py:82` varsayılanı 3 ama `rules/stage2_offtarget.smk:16` configfile'dan 12 alıyor — iki paralel config yolu.) | D3 | eşik gerekçesi + hassasiyet analizi | TODO |
| **C2** | **Satürasyon sabitlerini veriden türet.** ⚠️ **`D3`'ten ÖNCE YAPILAMAZ.** Faz D'den önceki dağılımlar **intron içinden** ölçülmüştür; sabitleri onlardan türetmek **koordinat hatasını kalibrasyona gömer** ve `D3`'ün doğrulamasını kendi kendini doğrulayan hale getirir — değişmez 7 ihlali. *(`hic_contact` CEBPA_HepG2'de 16.226× SAT.)* | D3 | satüre site oranı hiçbir ham sinyalde >%50 değil | TODO |

---

### FAZ B-SONRA — lokus-bağımlı kanallar (Faz D sonrası)

> Bunlar `D2`'den önce onarılırsa, lokuslar değişince hepsi yeniden koşulup yeniden
> yorumlanmak zorunda kalır. Doğru lokusların olduğu ilk anda bir kez yapılır.

| id | iş | bağımlılık | kabul kriteri | durum |
|---|---|---|---|---|
| **B3** | **`provenance` + `coverage` her siteye.** Skorun kaçta kaçı gerçek ölçümden geliyor; `coverage` eşiğin altındaysa **skor üretmeyi reddet.** Bilimsel aleti prototipten ayıran şey budur. Ayrıca `/verify-run` check 4'ün ham `0.0`'ı "ölü kaynak" ile "gerçekten sessiz lokus"tan ayırabilmesi buna bağlı. | B2, D3 | her sitede `provenance` + `coverage`; eşik altı `null` skor + gerekçe | TODO |
| **B5** | **Hi-C anchor'ı promotere bağla** — `hic_fetcher.py:44-47` `regions[0]` kullanıyor (köşegen bin). `promoter_region` tüm repoda hiç okunmuyor. *VEGFA_HeLa'da `hic_contact` 41 sitenin 34'ünde `0.0`.* | D3 | anchor `promoter_region`; temaslar köşegen dışı | TODO |
| **B6** | **`cell_modifier`'ı site-başına yap** — `epigenetic_merger.py:137-147` tüm sitelerin ortalamasını üretiyor, `risk_classifier.py:73` aynı sözlüğü herkese veriyor → koşu başına **tek sabit çarpan** (`final/base` 6. haneye kadar sabit; Spearman(base,final) = 1.000000 4/4 koşuda). Monoton sabit çarpan sıralamayı değiştiremez. | D3 | aynı koşuda ≥2 farklı çarpan; Spearman < 1.0 | TODO |
| **B8** | **Ölü `domain_scores.py`'ı sil.** ⚠️ **Önce 44 testin davranışsal niyetini üretim yoluna aktar** — o testler projedeki tek yerde yazılı niyeti taşıyor (H3K27me3 yönü, RBP işareti, satürasyon sabitleri). Değişmez 5 gereği yeni testlerin önce kırmızı olduğu gösterilir, sonra modül silinir. | D3 | `git grep domain_scores src/` boş; niyet testleri üretim yoluna karşı yeşil | TODO |
| **B9** | **AGO2 accession'larını düzelt** — K562 ENCFF426YFB = shRNA-KD RNA-seq, HepG2 ENCFF097LEQ = ChIP-seq; **ikisi de eCLIP değil**. HeLa'da zaten `null` (8 hattın 6'sında null). | D3 | accession'lar gerçekten AGO2 eCLIP | TODO |
| **B10** | mypy strict'i sıfıra indir (72 hata, 39'u eksik generic), sonra CI'da bloke ediciye çevir. | H6 | `mypy src/` 0 hata | TODO |
| **G0** | **API yanıtlarını dondur** — tüm uzak kaynakların versiyonlu snapshot'ı + checksum. ⚠️ **`G-VI` bugünkü haliyle yapısal olarak geçilemez:** Stage 7 tekrarlanabilir olsa da Stage 2-6 canlı API'lere bağlı. | D5 | taze makinede aynı snapshot ile aynı sayılar | TODO |
| *(manifest)* | Run manifest **`H10`**'dadır — Faz 0'a taşındı, burada tekrar edilmez. | — | — | — |

---

### FAZ E — Doğrulama

| id | iş | bağımlılık | kabul kriteri | durum |
|---|---|---|---|---|
| **E1** | **Null kapısını kalıcı hale getir** — 16.384 7-mer ampirik null. *Ölçüm: gözlenen 42 hit vs beklenen 52.7 (%47.4 yüzdelik, ortalamanın **altında**); BH-FDR sonrası **0/41** anlamlı.* ⚠️ Sonucunu `reports/null_gate.json`'a yazar (ya da `results/<koşu>/null_gate.json`): `H4` durum satırı açılışta o dosyayı okuyup son sonucu basar, bulamazsa "hiç koşmadı" der. Başka bir yere yazarsan durum satırı sessizce "hiç koşmadı" demeye devam eder. | H6, H13 | CI'da koşuyor, p-değeri raporlanıyor | TODO |
| **E2** | **Scrambled saRNA negatif kontrolü** — aynı boru hattı rastgele dizilerle. Veri gerektirmeyen en ucuz adım. | E1 | skor dağılımı karşılaştırması | TODO |
| **E0** | **GEO veri mühendisliği** — 6 seriyi indir, normalize et, prob→Ensembl gen eşlemesi, replikatlar, log2FC matrisi. ⚠️ Plan bunu "accession kilitle" sanıyordu; gerçekte **3-5 günlük ayrı iş** ve `E3a`'nın gerçek ön koşulu. | A12 | log2FC matrisi + eşleme raporu | TODO |
| **E0b** | **siSPOTR POTS tabanını uygula** — 3'UTR seed frekans tablosu. Taban kendiliğinden gelmiyor, kurulması gereken bir araç. | C0 | POTS skoru hesaplanıyor, referans değerlerle doğrulandı | TODO |
| **E3a** | **ANA DENEY — seed katmanı, gen düzeyi, koordinatsız.** Girdi: `P_silence` bileşenleri (`sequence_specificity` + ΔG + `region_class` + `strand_origin`). Tabanlar: üçü de (`A5`). CV: leave-one-siRNA-out. ⚠️ Tamamen dizi-hesaplı — **hiçbir API çağrısı yok**, `D5`'i beklemez. | A12, C1, C3, C0, C0b, D1, E0, E0b, E1 | `A6a` kriteri karşılandı **veya** negatif sonuç açıkça raporlandı | TODO |
| **E4a** | **ABLASYON (seed + ΔG).** Hangi bileşen ne kadar katkı veriyor? ⚠️ Bu, yayının **asıl bilimsel çekirdeği.** *Ölçüm: nominal 1.00 ağırlığın %35'inden azı gerçek bilgi taşıyor.* Varyans payı tablosu bu maddenin kabul kriterinin parçası. | E3a | bileşen bazlı katkı + varyans payı tablosu | TODO |
| **E3b** | **Tam bileşik skor** (`P_silence` + `Impact`, tüm kanallar canlı, doğru lokuslar). | E3a, D4, C4, D5 | raporlandı; `Impact` sütunu `validated: false` | TODO |
| **E4b** | **Tam ablasyon** — çok-omik katman seed katmanının üstüne bilgi ekliyor mu? | E3b | domain bazlı katkı tablosu | TODO |
| **B7** | **ADAR + H3K27me3 kanallarını bağla.** ⚠️ **`E4b`'den sonra.** Hiçbir mevcut kanalın bilgi taşıdığı gösterilmemişken yeni kanal eklemek ölü ağırlığa ölü ağırlık eklemektir. Kabul kriteri: `E4b` tablosunda epigenetik domain sıfırdan farklı katkı gösterdi. Yön kararı `A1`'e bağlı. | E4b | `stage4_histones.json`'da `h3k27me3_signals` | TODO |
| **E5** | **Ortogonal kanıt — AGO2 eCLIP** (K562 ENCSR048YXG, HeLa E-MTAB-12944). HepG2 için AGO2 eCLIP yok. | D3, B9 | zenginleşme testi | TODO |

---

### FAZ F — Kalibrasyon ve dürüst sınırlar (2 hafta)

| id | iş | bağımlılık | kabul kriteri | durum |
|---|---|---|---|---|
| **F1** | **Risk sınıfı eşiklerini `E3b`'nin eğrisinden türet.** ⚠️ **`B2` ve `D2` bitmeden kalibre etme** — aksi halde ölü kanalları telafi etmek için eşik indirmiş olursun, ki bu değişmez 7'nin ihlali ve bir risk aracında en tehlikeli hamledir. *Düzeltilmiş ölçüm: gözlenen çarpan 0.707–0.809; HIGH_RISK için gereken base 0.741–0.848, base tavanı 0.836 (biyofizik bugünkü tavanıyla) → **HIGH_RISK erişilebilir ama ulaşılmamış**; DANGEROUS için 1.05 gerekiyor → **erişilemez**. Erişilememenin kök nedeni `_ATAC_SAT` değil (SAT'ı 50× düşürmek eşiği yalnız 0.789→0.728 indiriyor), **`_NEUTRAL_SIGNAL = 0.0` + intronik lokuslar**.* | E3b, B2, D2 | eşikler veriden; her sınıf erişilebilir | TODO |
| **F3** | **Belirsizlik raporlama** — `B3`'ün `coverage` alanı üstüne güven/tahmin aralığı. | B3, E3b | her tahmin yanında belirsizlik | TODO |
| **F4** | **`docs/METHODS.md`** — hakem okuyacak düzeyde. `docs/` şu an yalnız `DATA_SOURCES.md` içeriyor. ⚠️ Bağımlılığı `E4a`, `F1` **değil**: yöntem belgesi *yapılmış olanı* anlatır. Üç aylık kapsamda `F1` dışarıda kaldığı için risk sınıfı eşikleri o sürümde **kalibre edilmemiş olarak** raporlanır; `F1` indiğinde belge güncellenir. | E4a | her aşama, sabit ve eşik gerekçeli (ya da gerekçesizliği açıkça yazılı) | TODO |
| **F5** | **`docs/LIMITATIONS.md`** — İddia 2 ve İddia 3'ün doğrulanamadığı, hangi veriyle doğrulanabileceği, hangi kaynakların ölü/vekil olduğu. §5 tablosu buraya taşınır. | F4 | her satır ölçümlü | TODO |

---

### FAZ G — Yayın

| id | iş | bağımlılık | durum |
|---|---|---|---|
| **G1** | Preprint (bioRxiv), ön kayıt hash'ine atıfla; venue §0'ın koşullu tablosundan | F5 | TODO |
| **G2** | Zenodo DOI + tam tekrarlanabilirlik paketi (`G0` snapshot'ları, sürümler, checksum'lar, seed'ler) | G1 | TODO |
| **G3** | Dergi gönderimi | G2 | TODO |
| **E6** | *(madde değil)* GSE42024 (MCF7/HIC-1) — n=3v3, tek saRNA. **Metrik iddiası olmayan tek paragraf + tek şekil olarak Tartışma'ya.** Ayrı yol haritası maddesi değil; hakeme "asıl mekanizmayı neden doğrulamadınız" sorusunu davet ediyor. | G1 | — |

---

## 4. ÜÇ AYLIK MİNİMUM SAVUNULABİLİR YAYIN

Tam kapsam **4,5-6 ay**. Üç ayda savunulabilir bir preprint ancak kapsamı keserek:

```
İÇERİDE (50 madde):
  H1 H2 H3 H4 H5 H6 H6b H7 H8 H9 H10 H11 H12 H13 H14 H15
  A1 A2 A2b A3 A4 A5 A6a A7 A8 A9 A10 A11 A12
  B0 B1 B2 B4 B10a
  C0 C0b C1 C3
  D0 D1
  E0 E0b E1 E2 E3a E4a E6
  F4 F5 G1

DIŞARIDA — ikinci yayın (21 madde):
  B3 B5 B6 B7 B8 B9 B10
  C2 C4
  D2 D3 D4 D5
  E3b E4b E5
  F1 F3
  G0 G2 G3
  + İddia 2'nin tamamı
```

Bu kapsam **tek bir yanlışlanabilir iddiayı** (İddia 1) gerçekten kapatır.
Kapsam kesilmezse üç ayda **hiçbir** iddia kapanmaz.

**Prensip: en ucuz yanlışlama önce.** Gerçek referansa karşı ilk sayı **3. haftada**
alınabilir. Seed katmanı 3'UTR tabanlarını geçmiyorsa, 24 kanalı onarmak için
harcanacak haftalar zaten yanlış yatırımdı — ve bunu baştan öğrenirsin.

---

## 5. "BİLİMSEL" TANIMI — dokuz kapı

Hepsi geçilmeli; sekizi geçip biri kalırsa proje bilimsel **değildir**, kısmi puan yok.

| kapı | soru | nasıl ölçülür | şu an |
|---|---|---|---|
| G-I | Yanlışlanabilir, ön kayıtlı iddia var mı? | `docs/PRE_REGISTRATION.md` commit'li, metrik + eşik sayı olarak | ✗ |
| G-II | Gerçek referansa karşı test edildi mi? | `E3a` koşmuş, sonuç raporlanmış (pozitif **veya** negatif) | ✗ |
| G-III | Tabanı geçiyor mu **yoksa geçmediğini söylüyor mu**? | `E4a`/`E4b` ablasyon tablosu | ✗ |
| G-IV | Bilmediğini biliyor mu? | `B3` `coverage` + `F3`; eşik altı skor **üretilmiyor** | ✗ |
| G-V | Sabitler veriden mi — **ve doğrulanmış koordinatlardan mı**? | `C2` (`D3` sonrası) + `F1`; hiçbir sihirli sayı gerekçesiz değil | ✗ |
| G-VI | Bit düzeyinde tekrarlanabilir mi? | **`G0`** snapshot'ları + `H1` manifest; taze makinede aynı sayılar | ✗ |
| **G-VII** | **İnşa geçerliliği:** skorladığım şey, etiketin ölçtüğü şey mi? | `A7` ayrışması yapılmış; `E3a` yalnız `P_silence`'ı test ediyor | ✗ |
| **G-VIII** | **Arıza yönü:** her kanalın işaret testi var mı; veri yokluğu riski düşürüyor mu? | Her veri kanalı için işaret/monotonluk testi CI'da; "veri yok → sayı dönmüyor" testi | ✗ |
| **G-IX** | **Test edilen kod = sevk edilen kod** | 32 `run()` adaptörünün kapsaması >0; ölü modüle karşı test yok | ✗ |

> **G-VIII neden kapı:** denetimin bulduğu en tekrarlayan hata sınıfı **işaret/yön**
> hatası (gnomAD tersine, fallback güvenli yöne, Hi-C köşegene, mirbase istisnası "SAFE").
> Bu bir kerelik düzeltme değil, kalıcı bir sınıf.
> **G-IX neden kapı:** `test_h3k27me3_represses_active_histones` yeşil geçerken sıfır
> üretim etkisi var.

### Fayda ölçütü — kapı DEĞİL, ayrı

Dokuz kapı geçilince proje **bilimsel** olur; **faydalı olduğu gösterilmiş olmaz.**

> *orcSONAR, 3'UTR 7mer-m8 ve siSPOTR POTS tabanlarını leave-one-siRNA-out CV'de PR-AUC
> olarak **ve uzunluk tabakaları içinde** aşarsa **faydalıdır**; aşmazsa **bilimsel ama
> faydasızdır** ve yayın bir benchmark/negatif sonuç makalesidir (§0, üçüncü satır).*

Bu ayrım G-III'ün dürüstlüğünü korurken kendini kandırma riskini kaldırır.

---

## 6. ASLA YAZILMAYACAKLAR (kapı geçilene kadar)

| iddia | neden yazılamaz | hangi madde açar |
|---|---|---|
| "hücre hattına özgü risk tahmini" | koşu başına tek sabit çarpan; sıralamayı değiştiremiyor | `B6` (+ doğrulama için veri yok → `F5`'te sınır) |
| "saRNA **RNAa** off-target aracı" | arama uzayı promotersiz olgun mRNA (`type="cdna"`) | `A1` + `A11` (`validated: false` sütun) |
| herhangi bir **bulgu** cümlesi ("RISC makinesini riskli buldu") | 183-gen listesi × transkript uzunluğu artefaktı (r = 0.349) | `D1` + `A5`(iii) uzunluk tabanı |
| "termodinamik değerlendirme yapıyor" | 41/41 site aynı +31.10 | `C3` |
| "ClinVar / patojenik varyant entegrasyonu" | 119 site / 4 koşu → 0 varyant | `B1` |
| "graceful degradation" | fallback "güvenli" yönüne arızalanıyor | `B2` |
| "bölge-farkında seed analizi" | `region_class` yok, bölge farkındalığı **sıfır** | `C0` |
| "her iki iplik değerlendiriliyor" | yalnız `reverse_complement(seed)` indeksleniyor | `C0b` |
| herhangi bir doğruluk/performans sayısı | hiç ölçülmedi | `E3a` |

---

## 7. Yol haritası dışında, zaten yapılanlar

- **`fix(verify-run)`** — check 4 ölüydü (yalnız `0.5` nöbetçisini sayıyordu; gerçek
  nöbetçi `0.0`). Artık iki nöbetçiyi ayrı sayıyor; VEGFA_HeLa'da **7 yeni bulgu**
  (`hic_contact` %82.9, `groseq_signal` %78.0, `ago2`/`rbp` `raw_signal` %100). Yanlış
  `0.5` iddiası beş yerden temizlendi. `--json` düzeltildi. Check 6 commit'lendi.
  `AUDIT.md` worktree'ye geri alındı.
- **`chore(ruff)`** — 71 lint hatası; 6 `zip()`'e `strict=True` (hiçbiri aktif hata
  değildi, doğrulandı); 2 sessiz `except: pass` loglamaya çevrildi; mypy kuruldu ve ilk
  kez ölçüldü (72 hata → `B10a`/`B10`); ajanlara `omitClaudeMd: true`.
- **Plan denetimi (Fable 5.2, 2026-11-17)** — 30 öneri; 27'si koşulsuz, 3'ü
  değiştirilerek kabul edildi. Adjudikasyon:
  `orcSONAR-denetim/PLAN_REVIZYON_TASLAGI.md`.
- **`H1` dizin sözleşmesi** — `data/external/` carve-out'u iki hook'ta, 31 testle
  pinlendi. Kırmızı-önce kontrolü `curl`/`wget` açığını ortaya çıkardı (aşağıda).
