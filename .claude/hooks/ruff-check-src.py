#!/usr/bin/env python3
"""PostToolUse: lint a just-edited src/*.py with ruff and report back.

Advisory, never blocking — the findings are returned as additionalContext so
they land in the model's context and can be fixed in the same turn. If ruff is
not installed anywhere we can find it, that is reported once rather than
failing the edit.
"""

from __future__ import annotations

import json
import subprocess
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from _hooklib import PROJECT_ROOT, find_tool, read_payload, rel, target_path, under  # noqa: E402


def find_ruff() -> list[str] | None:
    """Locate ruff: active venv, then the project venvs, then PATH.

    The lookup itself lives in ``_hooklib.find_tool`` because the SessionStart
    hook (H4) needs the same one for both ruff and mypy, and a second copy of a
    tool path is how the stale copy survives (roadmap H9).
    """
    found = find_tool("ruff")
    return [found] if found else None


def emit(context: str) -> None:
    """Hand text back to the model without blocking the edit."""
    json.dump(
        {
            "suppressOutput": True,
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": context,
            },
        },
        sys.stdout,
    )
    sys.exit(0)


payload = read_payload()
path = target_path(payload)

if not (path and path.endswith(".py") and under(path, "src")):
    sys.exit(0)

ruff = find_ruff()
if ruff is None:
    emit(
        "ruff is not installed, so the post-edit lint on "
        f"{rel(path)} was skipped. Install it with: pip install 'ruff>=0.6' "
        "(it is already declared in pyproject.toml's dev extra)."
    )

try:
    proc = subprocess.run(
        [*ruff, "check", path],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
except (OSError, subprocess.TimeoutExpired) as exc:
    emit(f"ruff check on {rel(path)} could not run: {exc}")

if proc.returncode == 0:
    sys.exit(0)

output = (proc.stdout + proc.stderr).strip()
emit(f"ruff check reported issues in {rel(path)}:\n\n{output}")
