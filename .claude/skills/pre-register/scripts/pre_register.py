#!/usr/bin/env python3
"""Open, or refuse to reopen, the locked pre-registration (invariant 6).

Usage:  pre_register.py [--check] [--target PATH] [--repo PATH]

Writes the `docs/PRE_REGISTRATION.md` skeleton when none exists, and **refuses**
when one does. A pre-registration that has been committed is read-only
forever: the only legal change is a new `docs/PRE_REGISTRATION_v2.md`, with
both versions reported in the publication.

The `H8` hook that will block edits to the committed file does not exist yet,
so until it does this script is the only thing in that path. It therefore
treats "exists" as refusal rather than only "committed" — an uncommitted draft
is still work in progress, and overwriting it loses decisions silently.

Every field in the template is a placeholder. A template that ships with a
metric or a threshold already in it locks a value nobody chose, which is the
same violation one commit earlier.

Exit status is 0 when the template was written, or when `--check` found no
lock; 1 when the file already exists or is locked; 2 when git could not be
consulted at all.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[3]
HOOKS = PROJECT_ROOT / ".claude" / "hooks"

sys.path.insert(0, str(HOOKS))

# Tek otorite: "kilitli mi?" sorusunun git tarafı `_prereg.py`'de, H8'in
# hook'uyla paylaşılıyor. İki kopya kayar ve kayan kopya korumayı bırakan
# kopyadır (yol haritası H9).
from _prereg import git_committed  # noqa: E402

TEMPLATE = """\
# Ön kayıt — orcSONAR

> **değişmez 6: bu dosya commit'lendikten sonra DÜZENLENMEZ.**
> Değişiklik gerekiyorsa `docs/PRE_REGISTRATION_v2.md` açılır ve yayında
> **ikisi de** raporlanır. Bir metriği ya da eşiği sonucu gördükten sonra
> değiştirmek bu projenin en sinsi ihlali olur — üç ay sonra kimsenin
> farketmeyeceği bir commit.

Tarih: {today} · Yol haritası maddesi: A12 · Commit: <bu dosyayı kilitleyen sha>

## 1. Hipotez

<Tek cümle, yönüyle. "X, Y'yi öngörür" değil: "X artarsa Y azalır" gibi
işaretli ve yanlışlanabilir bir ifade.>

## 2. Birincil metrik

<Tek metrik. Birden fazla yazmak, sonradan geçeni seçmek demektir.>

Nasıl hesaplanacağı: <formül ya da fonksiyon adı, belirsizlik bırakmadan>

## 3. İkincil metrikler

<Varsa listele. Birincil olanla yer değiştiremezler.>

## 4. Eşikler ve karar kuralı

- Başarı eşiği: <sayı ve birimi>
- Bu eşik neden bu: <önceki ölçüm, literatür ya da güç analizi>
- Eşiğin altı: <ne sonuçlanır — bu da bir sonuçtur, değişmez 7>

## 5. Null modeli

<Gözlemi neyle karşılaştırıyorsun? Permütasyon, ampirik null, eşleştirilmiş
kontrol kümesi — ve kaç tekrar. Null yoksa hipotez test edilemez.>

Çoklu test düzeltmesi: <yöntem, örn. BH-FDR; ve q eşiği>

## 6. Örneklem ve veri

- Kapsam: <gen, hücre hattı, kaç site>
- Dışlama kuralları: <önceden, veriyi görmeden>
- Veri sürümleri: <kaynak + sürüm/accession; hepsi hg38>

## 7. Analiz planı

<Hangi adımlar, hangi sırayla. Burada yazılmayan bir analiz keşifseldir ve
yayında öyle etiketlenir.>

## 8. Durdurma kuralı

<Analiz ne zaman biter? "Sonuç anlamlı olana kadar koşturmak" bir kural
değil, ihlaldir.>

## 9. Negatif sonuç

<Hipotez doğrulanmazsa ne rapor edilecek ve nereye. Değişmez 7: negatif sonuç
kabul edilir ve bir yayın yolu vardır. Ağırlık, eşik ya da sabit ayarlayarak
pozitif sonuç aramak ihlaldir — ölü kanalları telafi etmek için eşik
indirmek de bu kategoridedir.>

## 10. Keşifsel (ön kayıt dışı)

<Yapmayı düşündüğün ama teste sokmadığın şeyler. Buraya yazmak serbest;
sonradan buradan birincil metriğe taşımak değil.>

## Sapma günlüğü

Bu dosya kilitlendikten sonra plandan her sapma buraya **değil**,
`docs/PRE_REGISTRATION_v2.md`'ye yazılır. Bu bölüm kasıtlı olarak boştur.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default=str(PROJECT_ROOT / "docs" / "PRE_REGISTRATION.md"))
    parser.add_argument("--repo", default=str(PROJECT_ROOT))
    parser.add_argument("--check", action="store_true", help="report the lock state, write nothing")
    args = parser.parse_args()

    target = Path(args.target)
    repo = Path(args.repo)

    if not target.exists():
        if args.check:
            print(f"{target} yok — ön kayıt henüz açılmadı (A12).")
            return 0
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(TEMPLATE.format(today=date.today().isoformat()), encoding="utf-8")
        print(
            f"{target} yazıldı.\n\n"
            "Her alan köşeli parantezli bir yer tutucu — hiçbiri doldurulmuş gelmiyor,\n"
            "çünkü varsayılan bir eşik kimsenin seçmediği bir eşiktir.\n\n"
            "Doldur, sonra commit et. O commit'ten sonra dosya salt-okunur:\n"
            "değişiklik gerekirse docs/PRE_REGISTRATION_v2.md açılır ve yayında\n"
            "ikisi de raporlanır (değişmez 6)."
        )
        return 0

    committed = git_committed(target, repo)
    if committed is None:
        print(
            f"{target} var, ama git durumu okunamadı — kilitli olup olmadığı\n"
            "ÖLÇÜLMEDİ. Dosyaya dokunmuyorum; elle kontrol et.",
            file=sys.stderr,
        )
        return 2
    if committed:
        print(
            f"❌ {target} commit'lenmiş — KİLİTLİ (değişmez 6).\n\n"
            "Bu dosya artık düzenlenmez. Tek yasal yol:\n"
            "  docs/PRE_REGISTRATION_v2.md açılır, neyin neden değiştiği yazılır,\n"
            "  ve yayında İKİSİ DE raporlanır.\n\n"
            "Metriği ya da eşiği sonucu gördükten sonra değiştirmek bu projenin\n"
            "en sinsi ihlalidir; bu yüzden burada duruyor."
        )
        return 1
    print(
        f"❌ {target} var ama commit'lenmemiş — üzerine yazmıyorum.\n\n"
        "Yarısı doldurulmuş bir ön kayıt da birinin kararıdır. Devam etmek için\n"
        "dosyayı elle düzenle; sıfırdan başlamak istiyorsan önce kendin sil.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
