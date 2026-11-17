#!/usr/bin/env python3
"""Decide whether a roadmap item may be called finished (roadmap H5).

Usage:  fix_done.py <ID> --red-first TEXT [--declare TEXT]
                    [--roadmap PATH] [--acceptance-dir PATH] [--timeout SEC]

Two things have to be true before work is closed, and they fail in different
ways, so this gate checks them separately.

**Invariant 5 — the test was red first.** No hook can measure this: a test that
never failed before the fix proves only that it does not fail now. 917 tests
were green in this repo while all three known bugs were live. So `--red-first`
is mandatory and must say something. An item that genuinely changes no code
passes `--red-first "yok: <reason>"`; the exemption is recorded, never silent.

**The acceptance criterion.** If `.claude/acceptance/<ID>.sh` exists it is run
and a non-zero exit **refuses the item**, with the script's own output shown.
No amount of prose gets past it. If no such script exists the criterion cannot
be machine-checked (`H4`'s was "the block prints at launch" — only observable
in a later session), so `--declare` records what was observed instead and the
verdict is the visibly weaker `DONE(beyan)`: auditable, but not verified. The
two verdicts must never blur, which is why one word distinguishes them in the
table (invariant 3 — declared is not implemented).

This gate does not edit the roadmap. It prints the status cell to write; the
evidence prose that belongs in the row needs judgement, and a script rewriting
a 2000-character table row is a worse risk than the typing it saves.

Exit status is 0 when the item may be closed, 1 when it is refused, 2 when the
item or the roadmap could not be read at all.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import textwrap
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[3]
HOOKS = PROJECT_ROOT / ".claude" / "hooks"

sys.path.insert(0, str(HOOKS))

import _status  # noqa: E402, I001

ABSENT = "yok:"


def red_first_problem(evidence: str | None) -> str | None:
    """Why this red-first evidence is not acceptable, or ``None`` if it is.

    Args:
        evidence: The ``--red-first`` text, or ``None`` if it was not given.

    Returns:
        A refusal reason for the operator, or ``None`` when the evidence stands.
    """
    if evidence is None or not evidence.strip():
        return (
            "kırmızı-önce kanıtı verilmedi (değişmez 5).\n"
            "  Düzeltmeden ÖNCE başarısız olduğunu gösterdiğin testi ve çıktısını yaz:\n"
            '    --red-first "test_x fix öncesi kırmızıydı: AssertionError ..."\n'
            "  Kod değişmeyen bir maddeyse gerekçesiyle muaf tut:\n"
            f'    --red-first "{ABSENT} bu madde yalnız belge değiştiriyor"'
        )
    text = evidence.strip()
    if text.rstrip(":").lower() == ABSENT.rstrip(":") or (
        text.lower().startswith(ABSENT) and not text[len(ABSENT) :].strip()
    ):
        return (
            f'"{text}" bir gerekçe değil.\n'
            f'  Muafiyet nedenini yaz: --red-first "{ABSENT} <neden kırmızı-önce yok>"'
        )
    return None


def run_gate(script: Path, timeout: int) -> tuple[int | None, str]:
    """Run an acceptance script and capture everything it said.

    Args:
        script: The acceptance script to run.
        timeout: Seconds to allow.

    Returns:
        ``(returncode, combined output)``; the code is ``None`` if the script
        could not be run at all, which counts as a refusal, never a pass.
    """
    try:
        proc = subprocess.run(
            ["bash", str(script)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None, f"kabul betiği {timeout} saniyede bitmedi"
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"kabul betiği koşturulamadı: {type(exc).__name__}: {exc}"
    return proc.returncode, (proc.stdout + proc.stderr).rstrip()


def _block(lines: list[str]) -> str:
    """Indent a verdict block for the terminal."""
    return textwrap.indent("\n".join(lines), "  ")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("item", help="roadmap item id, e.g. H6")
    parser.add_argument("--red-first", dest="red_first", help="evidence the test failed first")
    parser.add_argument("--declare", help="what was observed, when no gate can exist")
    parser.add_argument("--roadmap", default=str(PROJECT_ROOT / "SCIENTIFIC_ROADMAP.md"))
    parser.add_argument("--acceptance-dir", default=str(PROJECT_ROOT / ".claude" / "acceptance"))
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()

    item_id = args.item.strip()
    try:
        text = Path(args.roadmap).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"yol haritası okunamadı: {exc}", file=sys.stderr)
        return 2

    items = {item.id: item for item in _status.parse_roadmap(text)}
    item = items.get(item_id)
    if item is None:
        print(f"{item_id} yol haritasında yok. Yazım hatası mı?", file=sys.stderr)
        return 2
    if _status.is_done(item.status):
        print(
            f"{item_id} zaten kapalı ({item.status}). Yeniden kapatmak,\n"
            "o arada gerçekten ne değiştiğini gizler.",
            file=sys.stderr,
        )
        return 2
    if item.status not in {"TODO", "DOING"}:
        print(f"{item_id} açık bir madde değil (durum: {item.status}).", file=sys.stderr)
        return 2

    print(f"fix-done {item_id}\n")
    print(_block([f"kabul      {item.criterion or 'yol haritasında yazılmamış (!)'}"]), end="\n\n")

    problem = red_first_problem(args.red_first)
    if problem is not None:
        print(_block([f"❌ {problem}", "", f"{item_id} açık kalıyor."]))
        return 1
    red_first = args.red_first.strip()

    expected = Path(args.acceptance_dir) / f"{item_id}.sh"
    if expected.is_file():
        if args.declare:
            print(_block(["⚠️  --declare yok sayıldı: bu maddenin sert kapısı var."]), end="\n\n")
        code, output = run_gate(expected, args.timeout)
        print(_block([f"kapı       {expected}", f"çıkış      {code if code is not None else 'koşamadı'}"]))
        if output:
            print(_block(["", output]))
        print()
        if code != 0:
            print(_block([f"❌ REDDEDİLDİ — {item_id} açık kalıyor, kapı geçmedi."]))
            return 1
        print(
            _block(
                [
                    "✅ KABUL — kapı geçti, doğrulanmış kapanış.",
                    "",
                    "durum hücresi:  **DONE**",
                    f"kırmızı-önce:   {red_first}",
                    "",
                    "şimdi: kanıtı satıra yaz, durumu çevir, commit et (değişmez 4).",
                ]
            )
        )
        return 0

    if not args.declare or not args.declare.strip():
        print(
            _block(
                [
                    f"❌ Kabul betiği yok: {expected}",
                    "",
                    "İki yoldan biri, üçüncüsü yok:",
                    f"  1) betiği yaz ({expected.name}, çıkış 0 = geçti) — doğrulanmış kapanış,",
                    "  2) kriter makineyle ölçülemiyorsa gözlemini beyan et:",
                    '       --declare "ne gözlendi, nerede, ne zaman"',
                    "     kapanış daha zayıf olur ve tabloda öyle görünür.",
                    "",
                    f"{item_id} açık kalıyor.",
                ]
            )
        )
        return 1

    print(
        _block(
            [
                f"kapı       YOK ({expected.name} yazılmamış) — makineyle doğrulanmadı",
                "",
                "✅ KABUL(beyan) — denetlenebilir, doğrulanmamış.",
                "",
                "durum hücresi:  **DONE(beyan)**",
                f"kırmızı-önce:   {red_first}",
                f"beyan:          {args.declare.strip()}",
                "",
                "şimdi: beyanı satıra VE commit mesajına yaz (başka kimse doğrulayamaz),",
                "durumu çevir, commit et (değişmez 4).",
            ]
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
