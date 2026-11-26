"""Tests for the pre-registration lock (roadmap H8, invariant 6).

Invariant 6 is the project's most consequential rule and, until this hook, it
had **zero enforcement**: `docs/PRE_REGISTRATION.md` was protected by a sentence
in a document and by the `pre-register` skill, which only guards the path where
the file is *created*. An `Edit` call on a committed pre-registration walked
straight through, because a skill is invoked deliberately and a hook is not.

The failure it prevents is seeing a result and then moving the metric or the
threshold — a small commit nobody rereads three months later.

The decision matrix lives in `_prereg.py` as pure logic and is tested directly;
the hook is a thin adapter and is tested end to end through its stdin protocol.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / ".claude" / "hooks"
HOOK = HOOKS / "block-prereg-writes.py"

sys.path.insert(0, str(HOOKS))

import _prereg  # noqa: E402, I001


def run_hook(payload: dict[str, object], project_dir: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Invoke the hook the way Claude Code invokes it: JSON on stdin."""
    env = dict(os.environ)
    if project_dir is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    return subprocess.run(
        [sys.executable, "-I", str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=60,
        cwd=ROOT,
        env=env,
    )


ROADMAP_HEAD = (
    "### FAZ A — Ön kayıt\n\n"
    "| id | iş | bağımlılık | kabul kriteri | durum |\n"
    "|---|---|---|---|---|\n"
)


def make_repo(
    tmp_path: Path, *, commit: bool, a12: str | None = "TODO"
) -> Path:
    """A repo with the draft, optionally committed, with A12 in a given state.

    `a12` is what decides the lock now, not whether the file has a commit
    (roadmap H19). `None` omits the row entirely, which is the unreadable case.
    """
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "docs" / "PRE_REGISTRATION.md").write_text("# ön kayıt\n", encoding="utf-8")
    roadmap = ROADMAP_HEAD
    if a12 is not None:
        roadmap += f"| **A12** | ön kaydı commit'le | — | kilitli | {a12} |\n"
    (repo / "SCIENTIFIC_ROADMAP.md").write_text(roadmap, encoding="utf-8")
    if commit:
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "draft"], cwd=repo, check=True)
    return repo


# --------------------------------------------------------------------------
# the decision matrix (pure)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("relative", "expected"),
    [
        ("docs/PRE_REGISTRATION.md", True),
        ("docs/PRE_REGISTRATION_v2.md", False),
        ("docs/PRE_REGISTRATION_v3.md", False),
        ("docs/DATA_SOURCES.md", False),
        ("src/core/models.py", False),
    ],
)
def test_only_the_locked_file_is_in_scope(tmp_path: Path, relative: str, expected: bool) -> None:
    """`_v2` is the legal route for a change and must never be blocked."""
    assert _prereg.is_locked_target(str(tmp_path / relative), str(tmp_path)) is expected


def test_a_closed_a12_is_refused() -> None:
    """The rule itself: once A12 is closed the file is read-only."""
    assert _prereg.refuses(locked=True, a12=True)


def test_an_open_a12_is_allowed() -> None:
    """While A12 is open the plan is still being written.

    This is the case the first implementation got wrong: it keyed on the file
    having any commit, so writing §1 and committing it locked the document
    while A12 was still TODO, and A2-A11 became unwritable (H19).
    """
    assert not _prereg.refuses(locked=True, a12=False)


def test_an_unreadable_status_is_refused() -> None:
    """A lock that cannot tell must refuse, not wave through.

    This is the opposite direction from `pre-register`'s *reader*, which
    reports ÖLÇÜLMEDİ and touches nothing. Here the question is whether to
    permit a write, and "I could not tell" is not permission.
    """
    assert _prereg.refuses(locked=True, a12=None)


def test_an_unrelated_file_is_never_refused() -> None:
    """Whatever the roadmap says, a file outside the lock is not in scope."""
    for a12 in (True, False, None):
        assert not _prereg.refuses(locked=False, a12=a12)


# --------------------------------------------------------------------------
# the hook end to end
# --------------------------------------------------------------------------


def test_it_blocks_an_edit_once_a12_is_closed(tmp_path: Path) -> None:
    """Exit 2 is how a PreToolUse hook refuses a call."""
    repo = make_repo(tmp_path, commit=True, a12="**DONE**")
    proc = run_hook(
        {
            "tool_name": "Edit",
            "cwd": str(repo),
            "tool_input": {"file_path": str(repo / "docs" / "PRE_REGISTRATION.md")},
        },
        project_dir=repo,
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "PRE_REGISTRATION_v2.md" in proc.stderr, "it must name the only legal route"


def test_it_allows_an_edit_to_an_uncommitted_draft(tmp_path: Path) -> None:
    """A12 has not happened yet; the author is still writing the thing."""
    repo = make_repo(tmp_path, commit=False, a12="TODO")
    proc = run_hook(
        {
            "tool_name": "Edit",
            "cwd": str(repo),
            "tool_input": {"file_path": str(repo / "docs" / "PRE_REGISTRATION.md")},
        },
        project_dir=repo,
    )
    assert proc.returncode == 0, proc.stderr


def test_a_committed_draft_stays_editable_while_a12_is_open(
    tmp_path: Path,
) -> None:
    """The discrimination the first version could not make (roadmap H19).

    Invariant 4 says uncommitted work does not exist, so §1 has to be committed
    as soon as it is written — and the first lock keyed on "the file has a
    commit", which turned that commit into the lock and left A2-A11 unwritable.
    H8's own gate could not see it either: its fixture committed with the
    message "A12", so "any commit" and "A12 is closed" looked identical.
    """
    repo = make_repo(tmp_path, commit=True, a12="TODO")
    proc = run_hook(
        {
            "tool_name": "Edit",
            "cwd": str(repo),
            "tool_input": {"file_path": str(repo / "docs" / "PRE_REGISTRATION.md")},
        },
        project_dir=repo,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_a_missing_a12_row_refuses(tmp_path: Path) -> None:
    """No row is unknown, not open — and unknown refuses."""
    repo = make_repo(tmp_path, commit=True, a12=None)
    proc = run_hook(
        {
            "tool_name": "Edit",
            "cwd": str(repo),
            "tool_input": {"file_path": str(repo / "docs" / "PRE_REGISTRATION.md")},
        },
        project_dir=repo,
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr


def test_it_allows_the_v2_route(tmp_path: Path) -> None:
    """Invariant 6's escape hatch: a new version, with both reported."""
    repo = make_repo(tmp_path, commit=True)
    proc = run_hook(
        {
            "tool_name": "Write",
            "cwd": str(repo),
            "tool_input": {"file_path": str(repo / "docs" / "PRE_REGISTRATION_v2.md"), "content": "# v2\n"},
        },
        project_dir=repo,
    )
    assert proc.returncode == 0, proc.stderr


def test_it_ignores_everything_else(tmp_path: Path) -> None:
    """A guard with a wide matcher must be narrow in what it refuses."""
    repo = make_repo(tmp_path, commit=True)
    proc = run_hook(
        {
            "tool_name": "Edit",
            "cwd": str(repo),
            "tool_input": {"file_path": str(repo / "docs" / "DATA_SOURCES.md")},
        },
        project_dir=repo,
    )
    assert proc.returncode == 0, proc.stderr


def test_a_malformed_payload_does_not_wedge_the_session() -> None:
    """Every sibling guard exits 0 on nonsense; a crashing hook blocks all work."""
    proc = subprocess.run(
        [sys.executable, "-I", str(HOOK)],
        input="not json at all",
        capture_output=True,
        text=True,
        timeout=60,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr


# --------------------------------------------------------------------------
# wiring
# --------------------------------------------------------------------------


def test_settings_wires_the_lock_on_every_write_tool() -> None:
    """A lock wired to only one of the write tools is not a lock.

    `test_settings_hooks_are_executable` separately proves the file is 100755
    on disk *and* in the git index — the regression test for the session H2
    lost to a hook committed 100644.
    """
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    matchers = [
        entry.get("matcher", "")
        for entry in settings.get("hooks", {}).get("PreToolUse", [])
        if any("block-prereg-writes.py" in h.get("command", "") for h in entry.get("hooks", []))
    ]
    assert matchers, "block-prereg-writes.py is not wired to PreToolUse"
    for tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        assert any(tool in m for m in matchers), f"{tool} is not covered"
