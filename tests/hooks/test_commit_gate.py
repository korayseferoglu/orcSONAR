"""Tests for the stale-commit gate's command detection (roadmap H7).

The gate's hard part is not the staleness arithmetic, it is deciding *when to
care*. A substring search for "git commit" was the first attempt and it blocked
the pipe-test exercising it — the test's own payload contained the words. The
same mistake would block `grep "git commit" notes.md`, and a gate that fires on
unrelated commands gets removed rather than fixed.

Over-blocking is the safe direction when parsing genuinely fails (an unbalanced
quote), so that case is pinned too: refusing to parse must not wave a commit
through.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / ".claude" / "hooks" / "block-stale-commit.py"


def _detector() -> Any:
    """Extract `invokes_git_commit` without executing the hook's main body.

    The hook reads stdin and calls `sys.exit` at import time, so it cannot be
    imported; the function is lifted out of the source instead.
    """
    text = HOOK.read_text(encoding="utf-8")
    start = text.index("_GLOBAL_FLAGS_WITH_VALUE")
    end = text.index("HOW = (")
    namespace: dict[str, Any] = {"re": re, "shlex": shlex}
    exec(text[start:end], namespace)  # noqa: S102
    return namespace["invokes_git_commit"]


detect = _detector()


class TestItFiresOnARealCommit:
    """The commit forms that actually occur."""

    @pytest.mark.parametrize(
        "command",
        [
            "git commit -m x",
            'git commit -m "a message with words"',
            "git commit --amend --no-edit",
            "git -c user.name=t -c user.email=t@t commit -q",
            "cd /tmp/repo && git commit -m x",
            "/usr/bin/git commit",
            "GIT_AUTHOR_NAME=x git commit -m y",
        ],
    )
    def test_detected(self, command: str) -> None:
        """Each of these commits, so each must be gated."""
        assert detect(command) is True


class TestItStaysQuietOtherwise:
    """The false positives that made the first version unusable."""

    @pytest.mark.parametrize(
        "command",
        [
            # The exact shape that blocked this gate's own pipe-test.
            'echo \'{"tool_input":{"command":"git commit -m x"}}\'',
            'grep "git commit" notes.md',
            "python -c \"print('git commit')\"",
            "git status",
            "git log --oneline -5",
            "git add -A",
            "ls -la",
            "",
        ],
    )
    def test_not_detected(self, command: str) -> None:
        """None of these commits, so none may be gated."""
        assert detect(command) is False


class TestFailureDirection:
    """When the parse is ambiguous, over-block rather than under-block."""

    def test_unbalanced_quotes_still_detect_a_commit(self) -> None:
        """`shlex` raises here; the fallback must not let the commit through.

        A gate that silently passes whatever it cannot parse is a gate with a
        documented hole, and the hole is exactly where a careless commit goes.
        """
        assert detect("git commit -m \"unterminated") is True

    def test_a_subcommand_named_commit_elsewhere_is_not_a_commit(self) -> None:
        """`git log --grep=commit` is a search, not a commit."""
        assert detect("git log --grep=commit") is False
