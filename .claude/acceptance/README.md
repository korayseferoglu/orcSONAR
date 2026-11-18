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

## GitHub tarafı ölçülebilir — bir sınırla

`gh` kurulu (`~/.local/bin/gh`) ve giriş yapılmış, yani bir kabul betiği GitHub
tarafını **ölçebilir**: `gh run list`, `gh api repos/.../actions/runs/<id>/jobs`
gibi çağrılar çalışıyor.

İki tuzak:

- **Plan kapılı endpoint'ler 403 döner.** `branches/main/protection` ve
  `rulesets` bu repoda (private + ücretsiz plan) **HTTP 403** veriyor. 403'ü
  "kural yok" diye okuyan bir kapı, özelliğin kapalı olduğunu "koruma
  kapalı" ile karıştırır; ikisi ayrı şeyler ve ayrı yazılmalı (değişmez 2).
- **`continue-on-error` ile maskelenen başarısızlık API'de `success` görünür.**
  mypy çıkış 1 verdiği koşuda adım sonucu `success`, hata yalnız annotation'da.
  Bir adımın gerçekten geçtiğini API'nin adım sonucundan **çıkaramazsın**.

Ağ gerektiren bir kapı yazarken: ağ yoksa **geçmemeli**, sessizce atlamamalı.

## Python yorumlayıcısı

Test koşan betikler `pytest`i olan bir yorumlayıcıya ihtiyaç duyar ve bunu
`$PYTHON`, `python3`, `python` sırasıyla arar; bulamazsa **geçmez** (sessizce
atlamaz).

Projenin yorumlayıcısı bu makinede **`~/.venvs/orcsonar`** (Python 3.12.3,
`pytest` 9.0.3 — `pyproject.toml`'daki pin'in aynısı). `envs/orcsonar.yaml`
bunun conda aynası; o conda ortamı henüz oluşturulmuş değil. Sistem `python3`'ü
`pytest` içermiyor, o yüzden:

```bash
PYTHON=~/.venvs/orcsonar/bin/python \
  python3 .claude/skills/fix-done/scripts/fix_done.py <ID> --red-first "..."
```

⚠️ `~/miniforge3/envs` altındaki conda ortamları **bu projeye ait değil** —
başka çalışmalara ait ve `orcsonar` onların içinde kurulu değil. Orada tek bir
ortam bulunduğu için bir kez yanlış seçildi ve testler yanlış yorumlayıcıda
koştu; bu not o hatanın tekrarlanmaması için burada. Yorumlayıcıyı aramak
yerine yukarıdaki yoldan oku; CI'da `H6` onu sabitliyor.
