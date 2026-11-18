"""Pure logic behind the SessionStart status line (roadmap H4).

Everything here is a function of its arguments: roadmap text in, items out;
measurement outcome in, one line of text out. The hook script does the I/O
(git, ruff, mypy, the filesystem) and hands the results here to be worded, so
that the wording — especially the difference between "clean" and "not
measured" — is testable without a venv, a timeout or a tool that is missing.

Invariant 2 is the reason that split exists. A status line that prints "ruff:
temiz" because ruff could not be found is the same class of bug as a fallback
that returns 0.0 because a source was unreachable: the failure reads as the
safe answer. ``NOT_MEASURED`` is the sentinel that keeps those two apart, and
``tests/hooks/test_session_status.py`` pins every path that must carry it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

#: Printed wherever a measurement did not happen. Never the same string as a pass.
NOT_MEASURED = "ÖLÇÜLMEDİ"

#: The ruff scope CI gates on (roadmap H6) — the single authority for it. The
#: workflow spells the same directories out and
#: `tests/hooks/test_ci_workflow.py` pins that copy to this tuple, so the two
#: cannot drift apart in a merge.
#:
#: `tests/` at large carries 50 findings and an earlier version of this comment
#: called all of them cosmetic. Measured 2026-11-18: 32 are (21 F401, 10 I001,
#: 1 UP041 — all autofixable), but 7 are `B017` blind `pytest.raises(Exception)`
#: assertions, sitting on the scoring-weight validator and on the ClinVar and
#: gnomAD clients — modules with open findings. Those are a finding of their
#: own, not debt to sweep through the gate. Widening this tuple before they are
#: dealt with makes CI red on day one, and a CI that is red on arrival gets
#: switched off.
RUFF_SCOPE = ("src", ".claude/hooks", "tests/hooks")

#: Where the empirical null gate (roadmap E1) is expected to leave its result.
NULL_GATE_GLOBS = ("reports/null_gate*.json", "results/*/null_gate*.json")

_PHASE = re.compile(r"^###\s+(FAZ\s+[^\n]*?)\s*$")
_ROW = re.compile(r"^\|\s*\*\*([A-Z]\d+[a-z]?)\*\*\s*\|(.*)$")
_ID = re.compile(r"\b([A-Z]\d+[a-z]?)\b")
_STATUS = re.compile(r"^(TODO|DOING|DONE(\([^)]*\))?|BLOCKED\([^)]*\)|DROPPED\([^)]*\))$")

_NONE_CELL = {"—", "-", "–", ""}


@dataclass(frozen=True)
class Item:
    """One roadmap row: a unit of work, its dependencies and its status."""

    id: str
    phase: str
    work: str
    deps: list[str] = field(default_factory=list)
    criterion: str = ""
    status: str = "—"


def _cells(rest: str) -> list[str]:
    """Split a markdown row on unescaped pipes only (``\\|`` is literal text)."""
    return [c.replace("\0", r"\|").strip() for c in rest.replace(r"\|", "\0").split("|")]


def parse_roadmap(text: str) -> list[Item]:
    """Parse SCIENTIFIC_ROADMAP.md into items, in file order.

    Handles both table shapes in that file: the five-column tables
    (id · work · dependency · acceptance · status) and FAZ G's four-column one,
    which drops the acceptance column. The dependency cell is always the second
    cell after the id and the status is always the last, so neither shape needs
    its own parser.

    Args:
        text: The full contents of the roadmap file.

    Returns:
        Every ``**ID**`` row as an :class:`Item`, in the order they appear.
    """
    items: list[Item] = []
    phase = ""
    for line in text.splitlines():
        heading = _PHASE.match(line)
        if heading:
            phase = heading.group(1).strip()
            continue
        row = _ROW.match(line)
        if not row:
            continue
        item_id, rest = row.group(1), row.group(2)
        cells = _cells(rest)
        # Rows end with a closing pipe, which splits into a trailing empty cell.
        if cells and not cells[-1]:
            cells.pop()
        raw_deps = cells[1] if len(cells) > 1 else ""
        deps = [] if raw_deps in _NONE_CELL else _ID.findall(raw_deps)
        last = cells[-1].strip("* ").strip() if cells else ""
        status = last if _STATUS.match(last) else "—"
        # Five-column tables are work · deps · acceptance · status; FAZ G's
        # four-column one drops the acceptance cell rather than leaving it empty.
        criterion = cells[2] if len(cells) >= 4 else ""
        items.append(
            Item(
                id=item_id,
                phase=phase,
                work=cells[0] if cells else "",
                deps=deps,
                criterion=criterion,
                status=status,
            )
        )
    return items


def is_done(status: str) -> bool:
    """Whether a status cell counts as closed.

    ``DONE`` means an acceptance script ran and exited 0. ``DONE(beyan)`` means
    no script could express the criterion, so a human-readable declaration was
    recorded instead (roadmap `H5`): auditable, but not verified. The weaker
    word is deliberate and must stay visible in the table — but both are
    closed, so work behind them may start and both are counted. Treating the
    declared form as open would stall the queue; leaving it out of the counts
    is exactly how `DOING` already vanished from the launch block (`H11`).

    Args:
        status: A parsed status cell.

    Returns:
        ``True`` for either closing verdict.
    """
    return status == "DONE" or status.startswith("DONE(")


def ready_items(items: list[Item]) -> list[Item]:
    """Every ``TODO`` whose dependencies are all ``DONE``, in file order.

    A dependency that is not defined anywhere in the roadmap counts as unmet.
    Promoting an item because its dependency was mistyped is exactly the kind of
    quiet reordering this file exists to prevent.

    Args:
        items: Parsed roadmap items.

    Returns:
        The items that can be started now.
    """
    status = {item.id: item.status for item in items}
    return [
        item
        for item in items
        if item.status == "TODO" and all(is_done(status.get(dep, "")) for dep in item.deps)
    ]


def next_item(items: list[Item]) -> Item | None:
    """The first startable item in roadmap order, or ``None`` if there is none.

    Args:
        items: Parsed roadmap items.

    Returns:
        The item a new session should pick up (invariant 8: only that one).
    """
    ready = ready_items(items)
    return ready[0] if ready else None


def phase_text(items: list[Item], current: Item | None) -> str:
    """One line naming the active phase and how far through it the work is.

    Args:
        items: Parsed roadmap items.
        current: The item that will be worked next, or ``None``.

    Returns:
        A line such as ``FAZ 0 — Harness · 13 madde: 3 DONE, 10 TODO``.
    """
    if current is None:
        return "sıradaki madde yok — her bağımlılığı karşılanmış madde kapandı"
    phase = current.phase or "faz başlığı bulunamadı"
    in_phase = [item for item in items if item.phase == current.phase]
    done = sum(1 for item in in_phase if is_done(item.status))
    todo = sum(1 for item in in_phase if item.status == "TODO")
    return f"{phase} · {len(in_phase)} madde: {done} DONE, {todo} TODO"


def next_text(items: list[Item]) -> list[str]:
    """The next item, its unblocked siblings and its acceptance criterion.

    Args:
        items: Parsed roadmap items.

    Returns:
        One to three lines; the first always names the item or says there is none.
    """
    current = next_item(items)
    if current is None:
        return ["yok"]
    deps = ", ".join(f"{dep} ✓" for dep in current.deps) or "bağımlılığı yok"
    work = current.work.replace("**", "")
    if len(work) > 70:
        work = work[:67].rstrip() + "…"
    lines = [f"{current.id} — {work}  [{deps}]"]
    if current.criterion:
        criterion = current.criterion.replace("**", "")
        if len(criterion) > 76:
            criterion = criterion[:73].rstrip() + "…"
        lines.append(f"kabul: {criterion}")
    others = [item.id for item in ready_items(items) if item.id != current.id]
    if others:
        shown = ", ".join(others[:8])
        more = f" (+{len(others) - 8})" if len(others) > 8 else ""
        lines.append(f"hazır diğerleri: {shown}{more}")
    return lines


def _found_count(output: str) -> int | None:
    """The tool's own error total, if it printed one."""
    match = re.search(r"Found (\d+) error", output)
    return int(match.group(1)) if match else None


def ruff_text(*, found: bool, returncode: int | None, output: str) -> str:
    """Word the ruff result, keeping "did not run" distinct from "clean".

    Args:
        found: Whether a ruff executable was located at all.
        returncode: Its exit status, or ``None`` if it could not be run.
        output: Combined stdout/stderr, or the reason it could not run.

    Returns:
        One line for the status block.
    """
    scope = " ".join(RUFF_SCOPE)
    if not found:
        return f"{NOT_MEASURED} — ruff bulunamadı (venv: ~/.venvs/orcsonar)"
    if returncode is None:
        return f"{NOT_MEASURED} — koşturulamadı: {output.strip() or 'bilinmeyen hata'}"
    if returncode == 0:
        return f"temiz — {scope}"
    count = _found_count(output)
    if count is None:
        count = len(re.findall(r"^\S+:\d+:\d+: ", output, re.M))
    return f"{count} hata — {scope}"


def mypy_text(*, found: bool, returncode: int | None, output: str) -> str:
    """Word the mypy result. Informational in CI (H6), blocking only at B10.

    Args:
        found: Whether a mypy executable was located at all.
        returncode: Its exit status, or ``None`` if it could not be run.
        output: Combined stdout/stderr, or the reason it could not run.

    Returns:
        One line for the status block.
    """
    if not found:
        return f"{NOT_MEASURED} — mypy bulunamadı (venv: ~/.venvs/orcsonar)"
    if returncode is None:
        return f"{NOT_MEASURED} — koşturulamadı: {output.strip() or 'bilinmeyen hata'}"
    if returncode == 0:
        return "temiz — src/"
    count = _found_count(output)
    tail = f"{count} hata" if count is not None else "hata var (sayı okunamadı)"
    return f"{tail} — src/ (bilgilendirici; bloke edici B10'da)"


def prereg_text(*, exists: bool, committed: str | None, a12_status: str, enforced: bool) -> str:
    """Word the state of the pre-registration lock (invariant 6).

    Three states matter and they are easy to confuse: the document may not
    exist; it may exist and still be editable; or ``A12`` may have locked it. A
    fourth is the dangerous one — locked on paper with no hook refusing edits —
    and it is called out by name, because invariant 3 says a rule nothing
    enforces is not a rule.

    Args:
        exists: Whether ``docs/PRE_REGISTRATION.md`` is on disk.
        committed: Short SHA of its last commit, or ``None`` if untracked.
        a12_status: Roadmap status of item ``A12``.
        enforced: Whether a hook in settings.json guards the file (``H8``).

    Returns:
        One line for the status block.
    """
    guard = "yaptırım: H8 kurulu" if enforced else "yaptırım: H8 kurulmadı"
    if not exists:
        return f"docs/PRE_REGISTRATION.md yok · A12 {a12_status} · {guard}"
    if is_done(a12_status):
        sha = committed or "commit yok (!)"
        warn = "" if enforced else "  ⚠️ belgede kilitli, kodda değil"
        return f"KİLİTLİ — A12 {sha} · {guard}{warn}"
    sha = committed or "commit'lenmemiş"
    return f"açık, düzenlenebilir — {sha} · A12 {a12_status} · {guard}"


def uncommitted_text(porcelain: str | None) -> str:
    """Word ``git status --porcelain`` output (invariant 4).

    Args:
        porcelain: Raw porcelain output, or ``None`` if git could not be run.

    Returns:
        One line for the status block.
    """
    if porcelain is None:
        return f"{NOT_MEASURED} — git durumu okunamadı"
    paths = [line[3:].strip() for line in porcelain.splitlines() if line.strip()]
    if not paths:
        return "0 dosya — çalışma ağacı temiz"
    shown = ", ".join(paths[:4])
    more = f" (+{len(paths) - 4})" if len(paths) > 4 else ""
    return f"{len(paths)} dosya: {shown}{more}  ⚠️ commit'lenmemiş = yok"


def null_gate_text(*, path: str | None, payload: dict[str, Any] | None) -> str:
    """Word the last empirical-null result, or its absence (roadmap E1).

    Args:
        path: Project-relative path of the newest null-gate artifact, if any.
        payload: Its parsed JSON contents, if they could be read.

    Returns:
        One line for the status block.
    """
    if path is None:
        return f"hiç koşmadı — E1 TODO (beklenen çıktı: {NULL_GATE_GLOBS[0]})"
    if not isinstance(payload, dict):
        return f"{path} var ama okunamadı — {NOT_MEASURED}"
    bits = []
    for key in ("at", "p_value", "observed", "expected", "significant", "verdict"):
        if key in payload:
            bits.append(f"{key}={payload[key]}")
    return f"{path} · " + (" · ".join(bits) if bits else f"tanınan alan yok — {NOT_MEASURED}")


def render(header: str, rows: list[tuple[str, list[str]]], footer: str = "") -> str:
    """Lay the status block out with an aligned label column.

    Args:
        header: First line, printed above the block.
        rows: ``(label, lines)`` pairs; later lines hang under the first.
        footer: Optional closing line.

    Returns:
        The full text the hook writes to stdout.
    """
    width = max((len(label) for label, _ in rows), default=0)
    out = [header, ""]
    for label, lines in rows:
        if not lines:
            lines = ["—"]
        out.append(f"  {label.ljust(width)}  {lines[0]}")
        out.extend(f"  {' ' * width}  {line}" for line in lines[1:])
    if footer:
        out += ["", footer]
    return "\n".join(out)
