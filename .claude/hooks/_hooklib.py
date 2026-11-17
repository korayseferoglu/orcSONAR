"""Shared helpers for orcSONAR's Claude Code hooks.

Every hook reads the tool-call JSON from stdin, decides, and either exits 0
(allow) or exits 2 with a reason on stderr (block). Anything unexpected —
malformed JSON, a tool shape we do not recognise — exits 0: a guard that
crashes must not wedge the session.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from typing import Any

# .claude/hooks/_hooklib.py -> project root
PROJECT_ROOT = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def read_payload() -> dict[str, Any]:
    """Parse the hook payload from stdin, or return {} if it is unusable."""
    try:
        data = json.load(sys.stdin)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def target_path(payload: dict[str, Any]) -> str | None:
    """Absolute, symlink- and ``..``-resolved path the tool call writes to."""
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    raw = tool_input.get("file_path")
    if not isinstance(raw, str) or not raw:
        return None
    if not os.path.isabs(raw):
        raw = os.path.join(payload.get("cwd") or PROJECT_ROOT, raw)
    return os.path.realpath(raw)


def under(path: str, *relative_dirs: str) -> bool:
    """True if ``path`` lies inside one of PROJECT_ROOT/<relative_dir>."""
    for rel in relative_dirs:
        root = os.path.realpath(os.path.join(PROJECT_ROOT, rel))
        if path == root or path.startswith(root + os.sep):
            return True
    return False


# The one writable path below data/. Everything else there is hand-curated
# reference data that no pipeline may touch; data/external/ is where machine
# downloads land (GENCODE and friends), each recorded in its manifest.
#
# The split exists because the guards and the planned sandbox rule would
# otherwise have to be switched off the week the GENCODE download lands — a
# rule declared and then disabled is worse than no rule, and is the exact
# failure mode this project keeps hitting. See SCIENTIFIC_ROADMAP.md H1.
DATA_EXTERNAL = "data/external"


def is_writable_data(path: str) -> bool:
    """True if ``path`` is inside the writable machine-download area."""
    return under(path, DATA_EXTERNAL)


def find_tool(name: str) -> str | None:
    """Locate a dev tool: the active venv, then the project venvs, then PATH.

    Hooks run with whatever environment the editor had, which is often not the
    project venv — ruff and mypy live in ``~/.venvs/orcsonar`` on this machine
    and are on no default PATH. One copy of that lookup, because two copies of
    a path are how the wrong one survives (roadmap H9).

    Args:
        name: Executable to look for, e.g. ``"ruff"``.

    Returns:
        Absolute path to the executable, or ``None`` if nothing was found.
    """
    candidates = []
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        candidates.append(os.path.join(venv, "bin", name))
    candidates += [
        os.path.join(PROJECT_ROOT, ".venv", "bin", name),
        os.path.expanduser(f"~/.venvs/orcsonar/bin/{name}"),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return shutil.which(name)


def rel(path: str) -> str:
    """Path relative to the project root, for readable messages."""
    try:
        return os.path.relpath(path, PROJECT_ROOT)
    except ValueError:
        return path


def written_text(payload: dict[str, Any]) -> str:
    """All NEW text this call introduces (Write content, Edit/MultiEdit new_string)."""
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return ""
    chunks: list[str] = []
    for key in ("content", "new_string"):
        value = tool_input.get(key)
        if isinstance(value, str):
            chunks.append(value)
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        for edit in edits:
            if isinstance(edit, dict) and isinstance(edit.get("new_string"), str):
                chunks.append(edit["new_string"])
    return "\n".join(chunks)


def block(message: str) -> None:
    """Refuse the tool call: exit 2 with the reason on stderr."""
    sys.stderr.write(message.rstrip() + "\n")
    sys.exit(2)
