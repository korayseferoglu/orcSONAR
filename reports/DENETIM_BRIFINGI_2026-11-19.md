# Denetim brifingi — 2026-11-18/19 oturumu

Bu dosya bir **özet değil**. Bir sonraki oturumun bu işi denetleyebilmesi için
yazıldı, ve denetimin işe yaraması için güvenilmemesi gerekiyor: aşağıdaki her
şey iddiadır, kanıt adresi verilmiştir, ve **nereden saldırılması gerektiği**
de yazılıdır. İddiaları doğrulamadan "tamam" demek, bu oturumun bütün bulguları
üretme biçimini çöpe atar.

**Kapsam:** `0980b22..ee4a1ad` — 22 commit, 91 dosya, +4986/−465, 31 yeni dosya.

```bash
git log --oneline 0980b22..ee4a1ad
git diff --stat 0980b22..ee4a1ad
```

---

## 1. Önce temel durumu kendin ölç

Hiçbirini bu dosyadan okuma, koş:

```bash
PY=~/.venvs/orcsonar/bin/python           # tek doğru yorumlayıcı
$PY -m pytest -q -o addopts="" -p no:cacheprovider   # bekleniyor: 1086 passed
$PY -m ruff check src .claude/hooks tests; echo $?    # bekleniyor: 0
$PY -m mypy src/ | tail -1                            # bekleniyor: 73 (taban 72)
~/.local/bin/gh run list -L 3                         # son koşu success olmalı
```

⚠️ `ruff ... | tail -1` **yazma**. Boru hattının çıkış kodu son aşamanınkidir;
bu oturumda tam olarak böyle bir maskeleme yapıldı ve kırmızı bir commit
push'landı (`41e7e8f` → CI failure, `bd229c1` ile onarıldı).

Kapılar (her biri kendi maddesini ölçer, çoğu tam takımı koşar):

```bash
for g in H5 H6 H8 H14 H15 B0 B1 B2 B2a B4; do
  PYTHON=$PY bash .claude/acceptance/$g.sh >/dev/null 2>&1 \
    && echo "$g ✓" || echo "$g ✗"
done
```

---

## 2. Kapatılan maddeler ve iddiaları

| madde | iddia | kanıt |
|---|---|---|
| `H4` | Durum bloğu açılışta basılıyor; `commit'siz` satırındaki off-by-one düzeltildi | `.claude/hooks/session-status.py` `git()`, `tests/hooks/test_session_status.py` |
| `H5` | `next-fix`/`fix-done`/`pre-register`; hibrit kapı modeli | `.claude/skills/`, `tests/hooks/test_fix_done.py` |
| `H6`/`H6b` | CI bloke edici, `main`'de `gate` zorunlu | `.github/workflows/ci.yml`, `tests/hooks/test_ci_workflow.py` |
| `H8` | Ön kayıt kilidi yaptırımlı | `.claude/hooks/block-prereg-writes.py`, `_prereg.py` |
| `H14`/`H15` | `tests/` ruff-temiz; 7 kör iddia tipli | `tests/` geneli, `.claude/acceptance/H15.sh` |
| `B0` | Cache sürümleme + geçersizleme | `src/core/cache.py`, `tests/unit/test_cache_versioning.py` |
| `B1` | ClinVar canlı; bozuk sorgu artık sessiz kalmıyor | `src/stage3_variant_tox/clinvar_client.py` |
| `B2`/`B2a` | Fallback açık *bilinmiyor*; adapter'lar sıfır yazmıyor | `encode_reader.py`, 4 `*_fetcher.py`, `tests/unit/test_stage4_fetchers.py` |
| `B4` | gnomAD işareti düzeltildi | `src/stage3_variant_tox/variant_merger.py` |

Her satırın gerekçesi `SCIENTIFIC_ROADMAP.md`'deki kendi maddesinde; **oradaki
sayılar da iddiadır**, yeniden ölçülmeli.

---

## 3. Buradan saldır — bildiğim zayıf noktalar

Sırayla, en önemliden:

**(a) Boru hattı hiç koşulmadı.** Bugün `B0`/`B1`/`B2`/`B2a`/`B4` boru hattının
davranışını değiştirdi ve **hiçbiri gerçek bir koşuyla doğrulanmadı** — hepsi
birim düzeyinde. `results/` altındaki dört koşu 17 Eylül'den. En değerli
denetim adımı: `B12`'yi koşturmak ya da en azından tek bir `snakemake` koşusu
yapıp `verify-run` ile bakmak. Özellikle: adapter'lar artık `null` yazıyor —
stage-7 ve HTML rapor bunu kaldırıyor mu? `score_integrator._clamp(None) → 0.5`
yolunu okudum ama **çalıştırmadım**.

**(b) Kapıları ben yazdım, kendi işimi geçirmek için.** Bir kapı çözüme göre
şekillendirilebilir. Her kapı için sor: kriteri yol haritasından mı geliyor
yoksa benim yazdığım şeyden mi; ve mutasyonla gerçekten kırmızıya düşüyor mu.
Bu oturumda iki kapı yanlış ölçtü ve düzeltildi (`H15` yorumları yakalıyordu,
`B2a` `shape_profile`'ı B2'ye yazıyordu) — üçüncüsü olabilir.

**(c) `B2`'de tek taraflı bir modelleme kararı verdim.** Bilinmeyen kanal
**dışlanıp kalan ağırlıklar yeniden normalize ediliyor**. Bu, "eksik kanal,
mevcutların ortalaması gibi davranır" varsayımıdır. Sıfır katkıdan iyi, ama
`B3`'ün (coverage eşiği) vermesi gereken kararın bir kısmını önceden aldı.
Sorgulanmalı: `B2` bu kararı vermeli miydi, yoksa skoru `null` mu yapmalıydı?

**(d) `B4`'te işareti hizaladım, modeli sorgulamadım.** Üreticinin "polimorfik
→ düşük off-target riski" modelinin kendisi doğru mu? Ben yalnız tüketicinin
üreticinin sözleşmesiyle çeliştiğini gösterdim. Bu bir **biyoloji** sorusu —
`bio-reviewer` / `biostatistician` ajanlarına sorulmalı.

**(e) `B1`'in yeni istisnası kırılgan olabilir.** `_raise_on_query_complaint`
iyi-huylu mesaj listesinde **tek bir giriş** var (`"No items found."`).
E-utilities normal işleyişte başka bilgilendirici mesaj döndürüyorsa, stage-3
artık gereksiz yere patlar. Gerçek bir koşuda birkaç yüz bölge sorgulanarak
sınanmalı.

**(f) `B0` 1893 cache satırını geçersiz kıldı.** Gerekçe sağlam ama **ölçüm
değil muhakeme**: o satırların hepsinin gerçekten bozuk kodla yazıldığını
varsaydım. Maliyeti gerçek (gnomAD saniyede 1 istek).

**(g) Bütün "ölçülen" sayılar tek bir eski koşudan.** README'de `code`/`run`
diye ayırdım ama `run` işaretli her sayı (`36 SAFE / 5 WARNING`, kanal başına
ayrık değer sayıları) **B4/B2/B1 öncesi** bir koşudan. Bunlardan sonuç
çıkarılmamalı.

**(h) `H15`'te `match="500"` gibi desenler zayıf olabilir.** HTTPError'ın
string'inde URL de var; teorik olarak başka bir yerden "500" gelebilir.
`match="cell_line"` için yanlış-sebep testi yaptım, HTTP olanlar için yapmadım.

**(i) Üç geri çekilmiş iddia var.** Bu oturumda üç kez yanlış bir şey iddia
ettim ve geri çektim: "env adı sapması" (uydurma bulgu), "ayar yapılmış olamaz"
(403'ü yokluk kanıtına çevirmek), ve seed testindeki totolojik iddia. **Geri
çekmeler satırlarda yazılı** — ama dördüncü bir tane kalmış olabilir; özellikle
yol haritasındaki uzun kanıt satırlarını örnekleyerek kontrol et.

---

## 4. Bilerek açık bırakılanlar (bulgu olarak raporlanmasın)

- `domain_scores.py`'daki iki `None * float` — ölü modül, `B8` siliyor.
- `epigenetic_merger.py:12` `_NEUTRAL = 0.5` okunmuyor — değişmez 2'nin kanıtı
  olarak kasıtlı duruyor.
- `score_integrator._clamp(None) → 0.5` — skor uzayında, `B3`'e devredildi.
- `mirbase_checker` `"SAFE"` fallback'i + `[:7]` seed dilimi — `B11`.
- `requires-python = ">=3.11"` ölçülmemiş; CI 3.12'de.
- `ubuntu-latest` + Node 20 action'ları — `H16`.
- `verify-run` check 4: eski koşularda ham `0.0`'ın anlamı belirsiz (`H10` run
  manifest'i bunu çözecek).

---

## 5. Denetimi nasıl koşmanı öneririm

1. §1'deki temel ölçümleri kendin al.
2. `(a)`'yı yap: bir koşu + `verify-run`. Diğer her şeyden fazla bilgi verir.
3. `bio-reviewer` (xhigh) → `(d)` ve koordinat/işaret/birim iddiaları.
4. `biostatistician` (xhigh) → `(c)`: renormalizasyon kararı savunulabilir mi.
5. `pipeline-verifier` → `(a)`'nın çıktısını denetlesin.
6. Yol haritasındaki kanıt satırlarını örnekle: iddia ↔ kod ↔ test üçlüsü
   tutuyor mu.

Bir şey tutmuyorsa **düzeltme, raporla** — bu oturumun düzeltmeleri de aynı
oturumun varsayımlarını taşıyor olabilir.
