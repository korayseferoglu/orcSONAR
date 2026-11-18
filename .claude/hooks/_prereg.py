"""Pre-registration lock logic — the one place that answers "is it locked?".

Invariant 6: once `docs/PRE_REGISTRATION.md` is committed it is read-only
forever, and the only legal change is a new `docs/PRE_REGISTRATION_v2.md` with
both versions reported in the publication. Moving a metric or a threshold after
seeing the result is this project's most consequential violation precisely
because it leaves no trace anyone would notice.

Two callers share this module, deliberately:

* `block-prereg-writes.py`, the `PreToolUse` hook that refuses the write
  (roadmap `H8`), and
* `.claude/skills/pre-register/scripts/pre_register.py`, which refuses to
  *open* a file that already exists.

They ask the same question about git, so the answer lives once. Two copies of
this check would drift, and the one that drifts is the one that stops
protecting anything (roadmap `H9`).
"""

from __future__ import annotations

import os
import subprocess

#: The file invariant 6 locks, relative to the project root.
LOCKED_RELATIVE = "docs/PRE_REGISTRATION.md"

#: The hook that enforces this lock. Named here because two places need to
#: agree on it: the `PreToolUse` wiring in settings.json and the launch status
#: block, which reports whether the lock has any enforcement at all. That
#: detector used to grep settings.json for "PRE_REGISTRATION" — the shape the
#: roadmap *described* — and so kept printing "H8 kurulmadı" after H8 shipped.
HOOK_FILENAME = "block-prereg-writes.py"

#: Where a change goes instead. Never blocked — it is the escape hatch, and a
#: lock with no legal route around it gets defeated rather than followed.
SUCCESSOR_RELATIVE = "docs/PRE_REGISTRATION_v2.md"


def project_root(default: str) -> str:
    """The project root, preferring Claude Code's own variable.

    Args:
        default: Fallback root, normally ``_hooklib.PROJECT_ROOT``.

    Returns:
        Absolute, resolved project root.
    """
    return os.path.realpath(os.environ.get("CLAUDE_PROJECT_DIR") or default)


def is_locked_target(path: str, root: str) -> bool:
    """Whether this write targets the locked pre-registration itself.

    Args:
        path: Absolute path the tool call writes to.
        root: Project root the lock is relative to.

    Returns:
        ``True`` only for the locked file. `_v2` and everything else is out of
        scope — the successor is how invariant 6 is *obeyed*, not evaded.
    """
    locked = os.path.realpath(os.path.join(root, LOCKED_RELATIVE))
    return os.path.realpath(path) == locked


def _git(args: list[str], repo: str) -> subprocess.CompletedProcess[str] | None:
    """Run git in ``repo``, or return ``None`` if it could not run at all."""
    try:
        return subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None


def git_committed(path: str, repo: str) -> bool | None:
    """Whether this path has at least one commit behind it.

    Three states, kept apart on purpose. A repository with no commits yet is
    not the same as a repository git could not read: in the first, nothing is
    committed and the answer is a confident ``False``; in the second there is
    no answer at all, and what to do about that depends on who is asking —
    see :func:`refuses`.

    Args:
        path: The file to ask about.
        repo: Repository to run git in.

    Returns:
        ``True`` if committed, ``False`` if certainly not, ``None`` if git
        could not be consulted.
    """
    inside = _git(["rev-parse", "--is-inside-work-tree"], repo)
    if inside is None or inside.returncode != 0:
        return None
    head = _git(["rev-parse", "--verify", "-q", "HEAD"], repo)
    if head is None:
        return None
    if head.returncode != 0:
        return False  # a repository with no commits: nothing in it is locked
    log = _git(["log", "-1", "--format=%H", "--", path], repo)
    if log is None or log.returncode != 0:
        return None
    return bool(log.stdout.strip())


def refuses(*, locked: bool, committed: bool | None) -> bool:
    """Whether the write must be refused.

    Args:
        locked: Whether the target is the locked pre-registration.
        committed: Result of :func:`git_committed`, or ``None`` if unknown.

    Returns:
        ``True`` to refuse.

    An unknown git state **refuses**. This is the opposite choice from the
    `pre-register` reader, which reports ÖLÇÜLMEDİ and touches nothing, and the
    difference is which way each one fails: a reader that guesses wrong prints
    a wrong line, while a lock that guesses wrong lets the one edit through
    that the whole rule exists to stop. "I could not tell" is not permission.
    """
    if not locked:
        return False
    return committed is not False
