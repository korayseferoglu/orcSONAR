# Kabul betikleri

Bir `<ID>.sh` dosyası, `SCIENTIFIC_ROADMAP.md`'deki `<ID>` maddesinin kabul
kriterinin **makineyle koşulabilir** halidir. `fix-done <ID>` bu dosyayı bulursa
koşar ve **çıkış ≠ 0 ise maddeyi reddeder** — hiçbir gerekçe bu kapıyı geçmez.

Dosya yoksa madde yalnız `DONE(beyan)` ile kapanabilir: `fix-done` gözlemin
beyan edilmesini ister, kapanış tabloda görünür biçimde daha zayıf olur.
Yani betik yazmamak bir seçenek, ama bedeli kayıtlı.

## Kural

- Çıkış **0** = geçti, **≠ 0** = geçmedi. Başka anlam yok.
- Kriteri *ölçer*, kurmaz. Bir şeyi düzeltmeye kalkan kabul betiği kendi
  kriterini doğrular hale gelir.
- Yan etkisiz olmalı: `data/` ve `results/` salt-okunur (değişmez 1), geçici
  dosya gerekiyorsa `mktemp -d` kullan ve temizle.
- Çalışma dizini her zaman proje kökü (`fix-done` öyle çağırıyor).
- Eşik ya da ağırlık **bu dosyada ayarlanmaz**. Kriteri gevşetmek değişmez
  7'nin ihlali; kriter yanlışsa yol haritası satırı düzeltilir, betik değil.

## `exit 0` yazma tuzağı

Kriteri makineyle ölçülemeyen bir madde için (`H4`'ün kriteri "blok açılışta
basılıyor" — ancak sonraki oturumda gözlenebilir) `exit 0` içeren bir betik
yazmak kapıyı yalanlamaktır: `fix-done` geçtiğini sanır, kimse bir şey ölçmez.
Öyle maddelerde betik **yazılmaz**, `--declare` kullanılır.

## Python yorumlayıcısı

Test koşan betikler `pytest`i olan bir yorumlayıcıya ihtiyaç duyar ve bunu
`$PYTHON`, `python3`, `python` sırasıyla arar; bulamazsa **geçmez** (sessizce
atlamaz). Bugün bu ortam adı `envs/orcsonar.yaml`'daki `orcsonar` ile
eşleşmiyor — kurulu ve `pytest` içeren env `orccatch`. Kanonik yorumlayıcıyı
`H6` (CI) belirleyecek; o zamana kadar:

```bash
PYTHON=~/miniforge3/envs/orccatch/bin/python \
  python3 .claude/skills/fix-done/scripts/fix_done.py <ID> --red-first "..."
```
