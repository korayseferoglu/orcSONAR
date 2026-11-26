#!/usr/bin/env python3
"""PostToolUse: type-check a just-edited src/*.py with mypy and report back.

Advisory, mirroring `ruff-check-src.py`. mypy is informational in CI too (80
errors today, roadmap B10), so blocking here would stop every edit on debt that
predates the edit.

One deliberate narrowing: mypy is run on the single edited file rather than the
package. Whole-package output would be dominated by those 80 pre-existing
errors and the one line the author just introduced would be invisible — a
report nobody can act on is the same as no report.
"""

from __future__ import annotations

import json
import subprocess
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from _hooklib import PROJECT_ROOT, find_tool, read_payload, rel, target_path, under  # noqa: E402


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

mypy = find_tool("mypy")
if mypy is None:
    # Reported once rather than silently skipped: `mypy strict=true` sat in
    # this project's config while the tool was not installed anywhere, which is
    # invariant 3's own worked example.
    emit(
        f"mypy is not installed, so the post-edit type check on {rel(path)} was "
        "skipped. It is declared in pyproject.toml's dev extra."
    )

try:
    proc = subprocess.run(
        [mypy, "--no-error-summary", "--hide-error-context", path],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=90,
    )
except (OSError, subprocess.TimeoutExpired) as exc:
    emit(f"mypy on {rel(path)} could not run: {exc}")

if proc.returncode == 0:
    sys.exit(0)

output = (proc.stdout + proc.stderr).strip()
if not output:
    sys.exit(0)

emit(
    f"mypy reported type issues in {rel(path)} (informational — CI does not "
    f"block on these, roadmap B10):\n\n{output}"
)
