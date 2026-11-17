#!/usr/bin/env python3
"""Resolve the one roadmap item a session may work on next (invariant 8).

Usage:  next_fix.py [--json] [--roadmap PATH] [--acceptance-dir PATH]

Reads SCIENTIFIC_ROADMAP.md and prints the first `TODO` whose dependencies are
all closed, together with its full work text, its acceptance criterion, and
whether a machine-checkable gate exists for it under `.claude/acceptance/`.
That last line matters before the work starts, not after: an item with no gate
can only ever close to the weaker `DONE(beyan)` verdict, and knowing that up
front is the difference between writing the gate and arguing for an exemption.

The roadmap is parsed by `.claude/hooks/_status.py` — the same parser the
launch status block uses. A second parser here would drift from that one, which
is the failure mode roadmap `H9` exists to close.

Exit status is 0 when an item was printed, 1 when nothing is ready, 2 when the
roadmap could not be read.
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[3]
HOOKS = PROJECT_ROOT / ".claude" / "hooks"

sys.path.insert(0, str(HOOKS))

import _status  # noqa: E402, I001

FOOTER = (
    "değişmez 8: yalnız bu maddeyi yap, geçerken başka bulgu düzeltme\n"
    "değişmez 5: hatayı yakalayan testi düzeltmeden önce kırmızı göster\n"
    "değişmez 4: commit'lenmeden bitmiş sayılmaz · kapanış: fix-done"
)


def gate_path(acceptance_dir: Path, item_id: str) -> Path:
    """Where the acceptance script for an item is expected to live.

    Args:
        acceptance_dir: Directory holding the acceptance scripts.
        item_id: Roadmap item id, e.g. ``H6``.

    Returns:
        The expected path, whether or not it exists.
    """
    return acceptance_dir / f"{item_id}.sh"


def _wrap(text: str, indent: str) -> str:
    """Wrap a long roadmap cell for a terminal, keeping the hanging indent."""
    body = " ".join(text.replace("**", "").split())
    lines = textwrap.wrap(body, width=86) or [""]
    return f"\n{indent}".join(lines)


def render(item: _status.Item, others: list[str], gate: Path | None, expected: Path) -> str:
    """Lay out the block a person reads at the start of a session.

    Args:
        item: The item to work on.
        others: Ids of the other currently startable items.
        gate: The acceptance script, if it exists.
        expected: Where that script was looked for.

    Returns:
        The printable block.
    """
    pad = " " * 15  # matches the label column below: 2 + 11 + 2
    if gate is None:
        gate_line = (
            f"YOK — beklenen: {expected}\n{pad}"
            "yazılmazsa kapanış `DONE(beyan)` olur: denetlenebilir, doğrulanmamış"
        )
    else:
        gate_line = f"{expected} ✓ — fix-done bunu koşacak, geçmezse reddedecek"
    rows = [
        ("iş", _wrap(item.work, pad)),
        ("bağımlılık", ", ".join(f"{dep} ✓" for dep in item.deps) or "yok"),
        ("kabul", _wrap(item.criterion, pad) if item.criterion else "yazılmamış (!)"),
        ("kapı", gate_line),
    ]
    if others:
        rows.append(("hazır diğerleri", ", ".join(others)))
    lines = [f"sıradaki madde — {item.id}   ({item.phase or 'faz başlığı yok'})", ""]
    lines += [f"  {label:<11}  {value}" for label, value in rows]
    lines += ["", textwrap.indent(FOOTER, "  ")]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roadmap", default=str(PROJECT_ROOT / "SCIENTIFIC_ROADMAP.md"))
    parser.add_argument("--acceptance-dir", default=str(PROJECT_ROOT / ".claude" / "acceptance"))
    parser.add_argument("--json", action="store_true", help="emit machine-readable fields")
    args = parser.parse_args()

    try:
        text = Path(args.roadmap).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"yol haritası okunamadı: {exc}", file=sys.stderr)
        return 2

    items = _status.parse_roadmap(text)
    ready = _status.ready_items(items)
    if not ready:
        print(
            "sıradaki madde yok — bağımlılığı karşılanmış her madde kapandı.\n"
            "Bir sonraki faza geçmek bir karar; yol haritasını elle oku.",
            file=sys.stderr,
        )
        return 1

    item = ready[0]
    expected = gate_path(Path(args.acceptance_dir), item.id)
    gate = expected if expected.is_file() else None

    if args.json:
        print(
            json.dumps(
                {
                    "id": item.id,
                    "phase": item.phase,
                    "work": item.work,
                    "deps": item.deps,
                    "criterion": item.criterion,
                    "status": item.status,
                    "gate": str(gate) if gate else None,
                    "gate_expected": str(expected),
                    "ready": [other.id for other in ready],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(render(item, [other.id for other in ready[1:]], gate, expected))
    return 0


if __name__ == "__main__":
    sys.exit(main())
