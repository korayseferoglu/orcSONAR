#!/usr/bin/env python3
"""A10b — G:U sallantısının +0,5 ağırlığının ölçümü (ön kayıt §7.8).

    python3 reports/a10b-gu-agirligi-2026-11-27/olcum.py

İki ölçüm, ikisi de depo içinde (ağ gerekmez):

1. **Ağırlık seed bölgesinde FİİLEN uygulanıyor mu?** İndeks seed'in tam
   ters komplementeri üzerine kurulu (`seed_aligner._build_seed_index`), yani
   iddia: bulunan her sitede seed'in yedi pozisyonu Watson-Crick ve G:U
   **hiç** oluşmuyor. Sentetik bir transkriptle doğrudan ölçülüyor.
2. **0,5 termodinamikten türetilebilir mi?** Projenin kendi Turner
   parametrelerinden (`data/4_Biyofizik_Yapısal/Turner_Rules/rna.stack.dg`)
   G:U yığınlarının ΔG'si, aynı bağlamdaki Watson-Crick yığınlarına
   oranlanıyor. Oran sabit değilse, hiçbir sabit ağırlık onu temsil edemez.

⚠️ `data/` salt-okunur; bu betik yalnız okuyor (değişmez 1).
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STACK = ROOT / "data" / "4_Biyofizik_Yapısal" / "Turner_Rules" / "rna.stack.dg"
BASES = "ACGU"
COMPLEMENT = {"A": "U", "U": "A", "G": "C", "C": "G"}
WATSON_CRICK = {("A", "U"), ("U", "A"), ("G", "C"), ("C", "G")}
WOBBLE = {("G", "U"), ("U", "G")}


def seed_region_wobbles() -> dict[str, object]:
    """İndeksin bulduğu bir sitede seed bölgesinde kaç G:U var?"""
    sys.path.insert(0, str(ROOT))
    from src.stage2_offtarget_scan.seed_aligner import (  # noqa: PLC0415
        _SEED_START,
        _build_seed_index,
        _extract_seed,
        _score_alignment,
    )

    import yaml  # noqa: PLC0415

    config = yaml.safe_load((ROOT / "config" / "config.yaml").read_text(encoding="utf-8"))
    sarna = str(config["sarna_sequence"]).upper().replace("T", "U")
    seed_length = int(config["seed_length"])
    seed = _extract_seed(sarna, seed_start=_SEED_START, seed_length=seed_length)
    reverse_complement = "".join(COMPLEMENT[b] for b in reversed(seed))

    # Seed komplementeri gömülü, gerisi G ile dolu bir transkript: G dolgusu
    # seed DIŞINDA bilerek G:U ve eşleşmezlik üretiyor.
    filler = "G" * 40
    transcript = filler + reverse_complement + filler
    index = _build_seed_index({"T1": transcript}, seed)
    out: dict[str, object] = {
        "sarna": sarna, "n": len(sarna), "seed": seed,
        "seed_reverse_complement": reverse_complement,
        "index_positions": index.get("T1", []),
        "sites": [],
    }
    seed_end = _SEED_START + seed_length - 1
    for position in index.get("T1", []):
        window_start = position - (len(sarna) - 1 - seed_end)
        window_end = window_start + len(sarna)
        if window_start < 0 or window_end > len(transcript):
            continue
        window = transcript[window_start:window_end]
        result = _score_alignment(sarna, window, seed_length=seed_length)
        wobbles_in_seed = 0
        for i in range(_SEED_START, _SEED_START + seed_length):
            pair = (sarna[i], window[len(sarna) - 1 - i].replace("T", "U"))
            if pair in WOBBLE:
                wobbles_in_seed += 1
        out["sites"].append({
            "position": position,
            "score": result.score,
            "mismatches": result.mismatches,
            "gu_wobbles_total": result.gu_wobbles,
            "seed_mismatches": result.seed_mismatches,
            "gu_wobbles_in_seed": wobbles_in_seed,
        })
    return out


def turner_tables() -> list[tuple[tuple[str, str], dict[tuple[str, str], float]]]:
    """`rna.stack.dg`'nin altı 4x4 tablosu: (ilk çift, {(X, Y): ΔG})."""
    lines = [
        line.rstrip("\n")
        for line in STACK.read_text(encoding="utf-8", errors="replace").splitlines()
    ]
    tables: list[tuple[tuple[str, str], dict[tuple[str, str], float]]] = []
    i = 0
    while i < len(lines):
        head = re.fullmatch(r"([ACGU])X", lines[i].strip())
        if head and i + 1 < len(lines):
            second = re.fullmatch(r"([ACGU])Y", lines[i + 1].strip())
            if second is None:
                i += 1
                continue
            rows: dict[str, list[str]] = {}
            j = i + 2
            while j < len(lines) and len(rows) < 4:
                parts = lines[j].split()
                if (parts and parts[0] in BASES and len(parts) == 5
                        and not lines[j].lstrip().startswith("#")):
                    rows[parts[0]] = parts[1:]
                j += 1
            if len(rows) == 4:
                table: dict[tuple[str, str], float] = {}
                for x, values in rows.items():
                    for y, value in zip(BASES, values):
                        if value != ".":
                            table[(x, y)] = float(value)
                tables.append(((head.group(1), second.group(1)), table))
                i = j
                continue
        i += 1
    return tables


def wobble_ratios() -> dict[str, object]:
    """G:U yığın ΔG'sinin aynı bağlamdaki WC medyanına oranı."""
    tables = turner_tables()
    per_context: list[dict[str, object]] = []
    ratios: list[float] = []
    all_wobble: list[float] = []
    all_wc: list[float] = []
    for (first5, first3), table in tables:
        wobble = [v for k, v in table.items() if k in WOBBLE]
        canonical = [v for k, v in table.items() if k in WATSON_CRICK]
        if not wobble or not canonical:
            continue
        median_wc = statistics.median(canonical)
        all_wobble.extend(wobble)
        all_wc.extend(canonical)
        context_ratios = [v / median_wc for v in wobble]
        ratios.extend(context_ratios)
        per_context.append({
            "first_pair": f"{first5}:{first3}",
            "wobble_dg": sorted(wobble),
            "wc_median_dg": median_wc,
            "ratio_min": min(context_ratios),
            "ratio_max": max(context_ratios),
        })
    return {
        "tables": len(tables),
        "per_context": per_context,
        "ratio_min": min(ratios), "ratio_max": max(ratios),
        "ratio_median": statistics.median(ratios),
        "wobble_dg_min": min(all_wobble), "wobble_dg_max": max(all_wobble),
        "wc_dg_min": min(all_wc), "wc_dg_max": max(all_wc),
    }


def main() -> int:
    print("(1) seed bölgesinde G:U oluşabiliyor mu?")
    try:
        seed = seed_region_wobbles()
    except Exception as exc:  # noqa: BLE001
        print(f"  ölçülemedi: {exc}", file=sys.stderr)
        return 2
    print(f"  saRNA n={seed['n']}, seed={seed['seed']}, "
          f"ters komplementer={seed['seed_reverse_complement']}")
    for site in seed["sites"]:  # type: ignore[union-attr]
        print(f"  pos={site['position']}: skor={site['score']}, "
              f"eşleşmezlik={site['mismatches']}, G:U(toplam)="
              f"{site['gu_wobbles_total']}, seed eşleşmezliği="
              f"{site['seed_mismatches']}, **seed'de G:U="
              f"{site['gu_wobbles_in_seed']}**")

    print("\n(2) 0,5 termodinamikten türetilebilir mi?")
    if not STACK.exists():
        print(f"  {STACK} yok — ölçüm atlandı", file=sys.stderr)
        ratios: dict[str, object] = {}
    else:
        ratios = wobble_ratios()
        print(f"  {ratios['tables']} Turner tablosu okundu")
        print(f"  {'ilk çift':9s} {'G:U yığın ΔG':>22s} {'WC medyan':>10s} {'oran':>14s}")
        for entry in ratios["per_context"]:  # type: ignore[union-attr]
            print(f"  {entry['first_pair']:9s} "
                  f"{str([f'{v:+.2f}' for v in entry['wobble_dg']]):>22s} "
                  f"{entry['wc_median_dg']:10.2f} "
                  f"{entry['ratio_min']:+.2f}…{entry['ratio_max']:+.2f}".rjust(14))
        print(f"  oran aralığı {ratios['ratio_min']:+.2f} … "
              f"{ratios['ratio_max']:+.2f}, medyan {ratios['ratio_median']:.2f}")
        print(f"  G:U yığın ΔG {ratios['wobble_dg_min']:+.2f} … "
              f"{ratios['wobble_dg_max']:+.2f} kcal/mol "
              f"(İŞARET DEĞİŞİYOR); WC {ratios['wc_dg_min']:+.2f} … "
              f"{ratios['wc_dg_max']:+.2f} (her zaman kararlılaştırıcı)")

    (HERE / "olcum.json").write_text(json.dumps({
        "measured_at": "2026-11-27",
        "seed_region": seed,
        "turner_wobble_ratios": ratios,
    }, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
