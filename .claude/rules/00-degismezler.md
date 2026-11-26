# Değişmezler

Bu dosyanın `paths:` frontmatter'ı **yoktur** — her oturumda yüklenir. Sekiz kural, ve
her birinin arkasında bu repoda gerçekten olmuş bir ölçüm var. Gerekçeleri
`SCIENTIFIC_ROADMAP.md` §2'de, kanıtları `AUDIT.md` ve
`orcSONAR-denetim/DENETIM_RAPORU.md`'de (repo dışı bir dizin, yayında yok).

**Oturuma `SCIENTIFIC_ROADMAP.md` ile başla.** Bağımlılığı karşılanmış ilk `TODO`
maddesini al, **yalnız onu** yap, kabul kriterini koş.

---

**1 — `data/` salt-okunur, `results/`'a yalnız Snakemake yazar.**
`data/` elle küratörlü referans verisi; bir kısmı lisans kapılı ve yeniden indirilemez.
Makine-indirilen veri **`data/external/`** altına gider, `manifest.json`'da checksum'ıyla.
Bir sonuç dosyasını elle düzenlemek onu *düzeltmez*, **uydurur** — ve sonradan gerçek bir
koşudan ayırt edilemez.

**2 — Arıza yönü: veri yokluğu asla riski düşürmez.**
Yeni bir fallback açık bir *bilinmiyor* tipi döner, sayı dönmez. Sessiz `except: pass`
yazılmaz. *Ölçüm: üç bağımsız fallback de "güvenli" yönüne arızalanıyordu —
`encode_reader` `_NEUTRAL_SIGNAL = 0.0` (ham sinyal uzayında, altı modülden
ulaşılıyordu), ago2 URL yok → `0.0`, `mirbase_checker.py:200` istisna → `"SAFE"`.*

**Durum (2026-11-18, `B2` kapandı):** ilk ikisi düzeltildi — sabit artık
`UNKNOWN_SIGNAL = None` ve türetilmiş değerler de (`is_loaded`, `combined_signal`)
bilinmiyor olabiliyor; bilinmiyor **cache'lenmiyor**; merger'lar bilinmeyen kanalı
dışlayıp ağırlıkları yeniden normalize ediyor. `_bigwig_mean` ayrıca *kontig var,
sinyal yok* (ölçülmüş 0.0, korunuyor) ile *kontig dosyada yok* (bilinmiyor — `chr`
öneki hatasının düştüğü yer) durumlarını ayırıyor. **Hâlâ açık:**
`mirbase_checker.py:200` istisna yolunda `"SAFE"` döndürüyor (risk uzayında bir
fallback), ve `epigenetic_merger.py:12` `_NEUTRAL = 0.5` tanımlı olup **hiç
okunmuyor** — ölü sabit, kasıtlı olarak `B2`'de silinmedi çünkü bu satırın kanıtı.
Skor uzayındaki son sınır (`score_integrator._clamp(None) → 0.5`) `B3`'e bırakıldı;
0.5'i ham sinyal uzayına yazmak hiçbir zaman çözüm değildi, sentinel yanlış uzaydaydı.

**3 — Beyan = uygulanmış değil.**
Config'e anahtar eklemek onu bağlamaz. `git grep` ile üretim çağıranını göster, yoksa
ekleme. *Ölçüm: `mypy strict=true` (araç kurulu bile değildi), `max_mismatches: 12`
(hiçbir adayı elemiyor), `_NEUTRAL = 0.5`, h3k27me3 (config'de 9 tanım / üretimde 0
referans), `--json` (belgeliydi, çalışmıyordu), `curl -o` (koruma listesinde yoktu).*

**4 — Commit'lenmemiş = yok.**
"Tamam" demeden önce commit. *Ölçüm: h3k27me3 "wired ✅" hafıza kaydı hiçbir commit'te
yoktu; `verify-run` check 6 aylarca commit'siz bekledi.*

**5 — Test önce kırmızı olmalı.**
Hatayı yakalayan test, düzeltmeden **önce başarısız olduğu gösterilmeden** merge
edilmez. *Ölçüm: 917 test yeşil geçerken bilinen üç hatanın üçünü de yakalamıyordu. Ve
`H1`'de kırmızı-önce kontrolü, testlerin carve-out'u değil hiç var olmayan bir korumayı
test ettiğini ortaya çıkardı — `curl`/`wget` açığı böyle bulundu.*

**6 — Ön kayıt kilitlidir.**
`docs/PRE_REGISTRATION.md` `A12`'de commit'lendikten sonra düzenlenmez (hook: `H8`).
Değişiklik gerekiyorsa `docs/PRE_REGISTRATION_v2.md` açılır ve **ikisi de** yayında
raporlanır. Metrik ya da eşiği sonucu gördükten sonra değiştirmek bu projenin en sinsi
ihlali olur: üç ay sonra kimsenin farketmeyeceği bir commit.

**7 — Negatif sonuç kabul edilir ve bir yayın yolu vardır.**
Ağırlık, eşik veya sabit ayarlayarak pozitif sonuç aramak ihlaldir. **Özellikle:** ölü
kanalları telafi etmek için eşik indirmek de bu kategoridedir — bir risk aracında
yapılabilecek en tehlikeli hamle.

**8 — Her madde tek iştir.**
Geçerken başka bir bulgu düzeltilmez. Fark ettiğin şeyi yol haritasına yaz, oraya bırak.

---

## Kanonik gerçekler nerede yazılı

Bir gerçeği **tek** yerde tut. İkinci kopya kaymaya başlar — yanlış `0.5` değeri beş
dosyaya yayılmıştı ve biri QA kapısını işlevsiz bırakmıştı.

| id | gerçek | otorite |
|---|---|---|
| `kaynak_detaylari` | kaynak başına chr-prefix, kolon düzeni, endpoint, **format başına koordinat tabanı** | `docs/DATA_SOURCES.md` — tek otorite. `orcsonar-data-sources` skill'i onun **ilan edilmiş yüklenebilir özeti**: yeni iddia eklemez, yalnız tekrar eder |
| `koordinat_semantigi` | strand semantiği, seed dilimi, işaret/birim kuralları, bugünkü arama uzayı | `.claude/rules/10-koordinatlar.md` |
| `skor_formulu` | skor formülü, ağırlıkları, `cell_modifier` sabitleri, risk sınıfı eşikleri, satürasyon sabitleri | `.claude/rules/20-skor-degismezleri.md` |
| `fallback_sentineli` | fallback sentineli | bu dosya, değişmez 2 |
| `hucre_hatlari` | desteklenen hücre hatları ve accession'ları | `config/cell_lines.yaml` |
| `dg_esikleri` | ΔG eşikleri (`delta_g_strong` / `delta_g_moderate`) | `config/config.yaml` |
| `fon_kumesi_boyutu` | off-target arama uzayının bugünkü boyutu | `src/stage2_offtarget_scan/transcriptome_fetcher.py` (`_BACKGROUND_GENES` tanımı) |
| `is_sirasi` | ne yapılacak ve hangi sırayla | `SCIENTIFIC_ROADMAP.md` |

Yeni bir yere kopyalama. Gerekiyorsa otoriteye işaret et.

Son üç satır `H9`'da eklendi: `dg_esikleri`, `fon_kumesi_boyutu` ve `skor_formulu`'nun
genişletilmiş hali daha önce **hiçbir otoriteye bağlı değildi**, ve otoritesi olmayan
bir gerçek için kapı bir ihlali sınıflandıramaz. Bir değer için otorite, onun **tek
tanım yeri**dir (config anahtarı ya da sabitin kendisi); prose o sayıyı tekrar etmez,
oraya işaret eder.

**Bu tablonun makine-okunur hali `.claude/authority.yaml`.** İkisi bir gerçeğin iki
gösterimi olduğu için kapı (`.claude/hooks/check-single-copy.py`) onları birbirine
karşı da kontrol eder: yalnız birinde olan bir `id` kapıyı kırmızıya düşürür. Tek-kopya
kuralının kaydın kendisine uygulanması.
