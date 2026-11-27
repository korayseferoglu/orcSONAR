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

import json
import os
import re
import shlex
import subprocess
import sys
import time
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


# ---------------------------------------------------------------------------
# H20 — the two frictions this gate created, measured while landing H19
# ---------------------------------------------------------------------------


def _lifted(name: str) -> Any:
    """Lift one pure function out of the hook source, as `_detector` does."""
    text = HOOK.read_text(encoding="utf-8")
    start = text.index("_GLOBAL_FLAGS_WITH_VALUE")
    end = text.index("HOW = (")
    namespace: dict[str, Any] = {"re": re, "shlex": shlex}
    exec(text[start:end], namespace)  # noqa: S102
    return namespace[name]


class TestPytestChainedBeforeCommit:
    """`pytest && git commit` cannot work, and must say so rather than lie.

    The gate inspects the command string **before** the command runs, so at
    inspection time the receipt is still the stale one and the commit is
    refused — even though the chain would have produced a fresh receipt a
    minute later. That is a real consequence of inspecting-before-running and
    it is not fixable here; what *is* fixable is the message. The generic
    "receipt is stale" wording sent two sessions looking for a staleness bug
    that did not exist.
    """

    @pytest.mark.parametrize(
        "command",
        [
            "pytest -q && git commit -m x",
            "python -m pytest && git commit -m x",
            "python3 -m pytest -q tests && git commit -am x",
            "~/.venvs/orcsonar/bin/python -m pytest -q && git commit -m x",
            "pytest -q; git commit -m x",
        ],
    )
    def test_chain_is_recognised(self, command: str) -> None:
        assert _lifted("pytest_precedes_commit")(command) is True

    @pytest.mark.parametrize(
        "command",
        [
            "git commit -m x",
            "git commit -m x && pytest -q",  # the other order is fine
            "git add -A && git commit -m x",
            "echo 'pytest && git commit' >> notes.md",
            "grep -n pytest Makefile",
        ],
    )
    def test_other_commands_are_not_that_chain(self, command: str) -> None:
        assert _lifted("pytest_precedes_commit")(command) is False

    def test_the_hook_explains_the_ordering(self) -> None:
        """The limit has to be stated where it is hit, not only in a roadmap row."""
        text = HOOK.read_text(encoding="utf-8")
        assert "pytest_precedes_commit" in text
        assert "ayrı" in text  # the message tells you to split the two calls


class TestGateReadsWholeSuiteEvidence:
    """A narrowed run must not refuse the next commit (the H20 criterion)."""

    def _verdict(self, receipt: dict[str, Any], tmp_path: Path) -> str:
        path = tmp_path / "receipt.json"
        path.write_text(json.dumps(receipt), encoding="utf-8")
        done = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(
                {"tool_name": "Bash", "tool_input": {"command": "git" + " commit -m p"}}
            ),
            capture_output=True,
            text=True,
            timeout=60,
            env=dict(os.environ, ORCSONAR_SUITE_RECEIPT=str(path)),
        )
        return done.stdout + done.stderr

    def test_fresh_whole_suite_then_partial_run_is_allowed(
        self, tmp_path: Path
    ) -> None:
        now = time.time() + 3600  # newer than any tracked file
        receipt = {
            "at": now,
            "exitstatus": 0,
            "whole_suite": False,
            "args": ["tests/hooks/test_commit_gate.py"],
            "collected": 17,
            "failed": 0,
            "last_whole_suite": {
                "at": now,
                "exitstatus": 0,
                "collected": 1246,
                "failed": 0,
                "args": ["tests"],
            },
        }
        assert "BLOCKED" not in self._verdict(receipt, tmp_path)

    def test_a_partial_run_that_failed_still_refuses(self, tmp_path: Path) -> None:
        now = time.time() + 3600
        receipt = {
            "at": now,
            "exitstatus": 1,
            "whole_suite": False,
            "collected": 17,
            "failed": 2,
            "last_whole_suite": {"at": now, "exitstatus": 0, "collected": 1246},
        }
        out = self._verdict(receipt, tmp_path)
        assert "BLOCKED" in out
        assert "en son test koşusu BAŞARISIZ" in out

    def test_stale_whole_suite_evidence_still_refuses(self, tmp_path: Path) -> None:
        """Freshness is measured on the evidence, not on the latest run."""
        receipt = {
            "at": time.time() + 3600,
            "exitstatus": 0,
            "whole_suite": False,
            "collected": 17,
            "failed": 0,
            "last_whole_suite": {"at": 1.0, "exitstatus": 0, "collected": 1246},
        }
        out = self._verdict(receipt, tmp_path)
        assert "BLOCKED" in out
        assert "BAYAT" in out

    def test_a_red_whole_suite_refuses_even_if_a_later_partial_run_passed(
        self, tmp_path: Path
    ) -> None:
        now = time.time() + 3600
        receipt = {
            "at": now,
            "exitstatus": 0,
            "whole_suite": False,
            "collected": 1,
            "failed": 0,
            "last_whole_suite": {"at": now, "exitstatus": 1, "failed": 4},
        }
        out = self._verdict(receipt, tmp_path)
        assert "BLOCKED" in out
        assert "TAM TAKIM koşusu BAŞARISIZ" in out

    def test_no_whole_suite_run_ever_refuses(self, tmp_path: Path) -> None:
        receipt = {
            "at": time.time() + 3600,
            "exitstatus": 0,
            "whole_suite": False,
            "collected": 17,
            "failed": 0,
        }
        out = self._verdict(receipt, tmp_path)
        assert "BLOCKED" in out
        assert "tam takım HİÇ koşmadı" in out

    def test_the_chain_gets_its_own_message_not_the_staleness_one(
        self, tmp_path: Path
    ) -> None:
        """A correct refusal with a misleading reason costs sessions."""
        now = time.time() + 3600
        receipt = {
            "at": now,
            "exitstatus": 0,
            "whole_suite": True,
            "collected": 1246,
            "failed": 0,
            "last_whole_suite": {"at": now, "exitstatus": 0, "collected": 1246},
        }
        path = tmp_path / "receipt.json"
        path.write_text(json.dumps(receipt), encoding="utf-8")
        done = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": "pytest -q && git" + " commit -m p"},
                }
            ),
            capture_output=True,
            text=True,
            timeout=60,
            env=dict(os.environ, ORCSONAR_SUITE_RECEIPT=str(path)),
        )
        out = done.stdout + done.stderr
        assert "BLOCKED" in out
        assert "tek bir komut olarak çalışmaz" in out
        assert "BAYAT" not in out
