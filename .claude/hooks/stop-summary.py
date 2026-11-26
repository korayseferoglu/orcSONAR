#!/usr/bin/env python3
"""Stop: a short, non-blocking summary of what the session leaves behind.

Roadmap H11. Blocking on `Stop` was **dropped** on 2026-11-18 and that decision
stands: `H7` enforces the same rule at the commit, which is the point where it
can still be acted on. A `Stop` gate that refuses to end a session cannot be
satisfied by the session it is refusing — it just traps the user.

So this reports and never blocks. It answers the question a session actually
leaves open: is the work recorded? Invariant 4 says uncommitted is nonexistent,
and this session's own measurement added a sibling — unpushed is unverified,
because the branch had gone 7 days and 23 commits without CI.

It prints nothing when the tree is clean and in sync, because a summary that
appears every time stops being read.
"""

from __future__ import annotations

import json
import subprocess
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from _hooklib import PROJECT_ROOT  # noqa: E402


def git(args: list[str]) -> str | None:
    """Run a git command, returning None when it cannot be answered.

    Args:
        args: Arguments after ``git``.

    Returns:
        Stripped stdout, or None on failure.
    """
    try:
        done = subprocess.run(
            ["git", *args],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return done.stdout.strip()


def summary() -> str:
    """Build the one-line summary, or an empty string when there is nothing to say.

    Returns:
        A short message, or ``""``.
    """
    parts: list[str] = []

    porcelain = git(["status", "--porcelain"])
    if porcelain is None:
        # Cannot check is not the same as clean (invariant 2).
        return "git durumu okunamadı — commit'siz dosya olup olmadığı bilinmiyor"
    dirty = [line for line in porcelain.splitlines() if line.strip()]
    if dirty:
        parts.append(
            f"{len(dirty)} dosya commit'siz (değişmez 4: commit'lenmemiş = yok)"
        )

    branch = git(["rev-parse", "--abbrev-ref", "HEAD"])
    if branch and branch != "HEAD":
        ahead = git(["rev-list", "--count", f"origin/{branch}..HEAD"])
        if ahead is None:
            parts.append(f"'{branch}' uzakta yok — hiç push edilmemiş")
        elif ahead.isdigit() and int(ahead) > 0:
            parts.append(
                f"{ahead} commit push'lanmamış (push'lanmamış = CI görmemiş = "
                "doğrulanmamış)"
            )

    return " · ".join(parts)


text = summary()
if text:
    json.dump({"systemMessage": f"orcSONAR: {text}"}, sys.stdout)
sys.exit(0)
