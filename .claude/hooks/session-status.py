#!/usr/bin/env python3
"""SessionStart: print the project's real state before the first prompt.

Roadmap item H4. A new session starts with CLAUDE.md and the rules loaded —
documents, all of them, which is precisely this project's failure mode: the
documents asserted things the code did not do and the drift survived for
months. Six measurements go out instead:

    faz          where the work queue stands
    sıradaki     the first TODO whose dependencies are met (invariant 8)
    ön kayıt     is docs/PRE_REGISTRATION.md locked — and does anything enforce it
    commit'siz   uncommitted files (invariant 4: uncommitted is nothing)
    ruff/mypy    run now, not remembered
    null kapısı  the last empirical-null result (E1), or that it has never run

Every one is measured at launch. Where a measurement cannot be taken the line
says ``ÖLÇÜLMEDİ`` rather than going quiet, because a silent line reads as a
clean one and that is invariant 2 in the one place every session looks.

The wording lives in ``_status.py`` and is tested in
``tests/hooks/test_session_status.py``; this file only gathers the inputs.
SessionStart cannot block, and nothing here is allowed to wedge a launch: any
failure degrades to a line saying so, and the hook always exits 0.
"""

from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
from datetime import UTC, datetime

sys.path.insert(0, __file__.rsplit("/", 1)[0])

import _status  # noqa: E402
from _hooklib import PROJECT_ROOT, find_tool, read_payload  # noqa: E402

ROADMAP = "SCIENTIFIC_ROADMAP.md"
PRE_REGISTRATION = "docs/PRE_REGISTRATION.md"
SETTINGS = ".claude/settings.json"

FOOTER = (
    "  değişmez 8: yalnız sıradaki maddeyi yap · değişmez 5: testi önce kırmızı göster\n"
    "  değişmez 4: commit'lenmeden bitmiş sayılmaz · otorite: SCIENTIFIC_ROADMAP.md"
)


def run(args: list[str], timeout: int) -> tuple[int | None, str]:
    """Run a command under the project root and never raise.

    Args:
        args: argv of the command.
        timeout: Seconds to wait before giving up.

    Returns:
        ``(returncode, output)``; the code is ``None`` if the command could not
        be run at all, in which case the output carries the reason.
    """
    try:
        proc = subprocess.run(
            args,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    return proc.returncode, proc.stdout + proc.stderr


def git(*args: str, timeout: int = 10) -> str | None:
    """Return trimmed git output, or ``None`` if the call did not succeed."""
    code, output = run(["git", *args], timeout)
    return output.strip() if code == 0 else None


def lint(name: str, args: list[str], timeout: int) -> tuple[bool, int | None, str]:
    """Run a linter if it can be found.

    Args:
        name: Executable name.
        args: Arguments after the executable.
        timeout: Seconds to wait.

    Returns:
        ``(found, returncode, output)`` for the matching ``_status`` wording
        function; ``returncode`` is ``None`` when the run itself failed.
    """
    tool = find_tool(name)
    if tool is None:
        return False, None, ""
    code, output = run([tool, *args], timeout)
    return True, code, output


def null_gate() -> tuple[str | None, dict | None]:
    """Find the newest null-gate artifact (roadmap E1) and read it.

    Returns:
        ``(project-relative path, parsed JSON)``; ``(None, None)`` when the gate
        has never written a result, which is today's true state.
    """
    hits: list[str] = []
    for pattern in _status.NULL_GATE_GLOBS:
        hits += glob.glob(os.path.join(PROJECT_ROOT, pattern))
    if not hits:
        return None, None
    newest = max(hits, key=os.path.getmtime)
    try:
        with open(newest, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        payload = None
    return os.path.relpath(newest, PROJECT_ROOT), payload


def main() -> str:
    """Gather every measurement and lay out the status block."""
    payload = read_payload()
    source = payload.get("source") or "startup"

    try:
        with open(os.path.join(PROJECT_ROOT, ROADMAP), encoding="utf-8") as handle:
            items = _status.parse_roadmap(handle.read())
    except OSError as exc:
        items = []
        roadmap_error = f"{_status.NOT_MEASURED} — {ROADMAP} okunamadı: {exc}"
    else:
        roadmap_error = "" if items else f"{_status.NOT_MEASURED} — {ROADMAP} ayrıştırılamadı"

    current = _status.next_item(items)
    statuses = {item.id: item.status for item in items}

    branch = git("rev-parse", "--abbrev-ref", "HEAD") or "?"
    head = git("log", "-1", "--format=%h") or "?"
    porcelain = git("status", "--porcelain")

    prereg_path = os.path.join(PROJECT_ROOT, PRE_REGISTRATION)
    try:
        with open(os.path.join(PROJECT_ROOT, SETTINGS), encoding="utf-8") as handle:
            settings = handle.read()
    except OSError:
        settings = ""

    ruff_found, ruff_code, ruff_out = lint(
        "ruff",
        ["check", *(d for d in _status.RUFF_SCOPE if os.path.exists(os.path.join(PROJECT_ROOT, d)))],
        15,
    )
    mypy_found, mypy_code, mypy_out = lint("mypy", ["src/"], 20)
    gate_path, gate_payload = null_gate()

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    header = f"orcSONAR durumu — {now} · {branch} @ {head} · açılış: {source}"

    rows: list[tuple[str, list[str]]] = [
        ("faz", [roadmap_error or _status.phase_text(items, current)]),
        ("sıradaki", [roadmap_error] if roadmap_error else _status.next_text(items)),
        (
            "ön kayıt",
            [
                _status.prereg_text(
                    exists=os.path.exists(prereg_path),
                    committed=git("log", "-1", "--format=%h", "--", PRE_REGISTRATION) or None,
                    a12_status=statuses.get("A12", "?"),
                    enforced="PRE_REGISTRATION" in settings,
                )
            ],
        ),
        ("commit'siz", [_status.uncommitted_text(porcelain)]),
        ("ruff", [_status.ruff_text(found=ruff_found, returncode=ruff_code, output=ruff_out)]),
        ("mypy", [_status.mypy_text(found=mypy_found, returncode=mypy_code, output=mypy_out)]),
        ("null kapısı", [_status.null_gate_text(path=gate_path, payload=gate_payload)]),
    ]
    return _status.render(header, rows, FOOTER)


try:
    sys.stdout.write(main() + "\n")
except Exception as exc:  # noqa: BLE001 - a status line must never wedge a launch
    sys.stdout.write(
        f"orcSONAR durumu {_status.NOT_MEASURED} — session-status.py düştü: "
        f"{type(exc).__name__}: {exc}\n"
        f"  SCIENTIFIC_ROADMAP.md'yi elle oku; durum satırına bu oturumda güvenme.\n"
    )
sys.exit(0)
