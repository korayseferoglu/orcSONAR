"""Tests for the pre-register skill (roadmap H5, invariant 6).

Invariant 6 is the project's most consequential rule and the easiest to break
without anyone noticing: moving a metric or a threshold *after* seeing the
result, in a commit nobody reads three months later. The `H8` hook that will
block edits to a committed pre-registration does not exist yet, so until it
does this script is the only thing standing in that path — which is why the
lock is tested before the template is.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".claude" / "skills" / "pre-register" / "scripts" / "pre_register.py"


def run_pre_register(*args: str, repo: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Invoke the script the way the skill invokes it."""
    argv = [sys.executable, "-I", str(SCRIPT)]
    if repo is not None:
        argv += ["--repo", str(repo)]
    return subprocess.run([*argv, *args], capture_output=True, text=True, timeout=120, cwd=ROOT)


@pytest.fixture
def target(tmp_path: Path) -> Path:
    """A pre-registration path that does not exist yet."""
    return tmp_path / "docs" / "PRE_REGISTRATION.md"


# --------------------------------------------------------------------------
# invariant 6: a committed pre-registration is locked
# --------------------------------------------------------------------------


def test_a_committed_pre_registration_is_refused(tmp_path: Path) -> None:
    """The whole point of the rule: no edits after it is committed."""
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    locked = repo / "docs" / "PRE_REGISTRATION.md"
    locked.write_text("# ön kayıt\n\nbirincil metrik: AUROC\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "pre-register"], cwd=repo, check=True)

    proc = run_pre_register("--target", str(locked), repo=repo)
    assert proc.returncode == 1, proc.stdout
    assert "PRE_REGISTRATION_v2" in proc.stdout + proc.stderr, "it must name the only legal route"
    assert locked.read_text(encoding="utf-8") == "# ön kayıt\n\nbirincil metrik: AUROC\n"


def test_check_reports_the_lock_without_writing_anything(tmp_path: Path, target: Path) -> None:
    """`--check` is what other tooling will call; it must never write."""
    proc = run_pre_register("--check", "--target", str(target))
    assert proc.returncode == 0, proc.stdout
    assert not target.exists()
    assert "yok" in (proc.stdout + proc.stderr).lower()


def test_an_uncommitted_file_is_not_overwritten(tmp_path: Path) -> None:
    """A draft in progress is still somebody's work."""
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    draft = repo / "docs" / "PRE_REGISTRATION.md"
    draft.write_text("# taslak\n", encoding="utf-8")
    proc = run_pre_register("--target", str(draft), repo=repo)
    assert proc.returncode == 1, proc.stdout
    assert draft.read_text(encoding="utf-8") == "# taslak\n"


def test_an_unreadable_git_state_is_not_treated_as_unlocked(target: Path) -> None:
    """Invariant 2: "could not tell" must not fail toward "go ahead".

    A pre-registration whose lock state is unknown is exactly the case where
    guessing is worst, so the script reports ÖLÇÜLMEDİ and touches nothing.
    """
    target.parent.mkdir(parents=True)
    target.write_text("# taslak\n", encoding="utf-8")
    proc = run_pre_register("--target", str(target))
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "ÖLÇÜLMEDİ" in proc.stdout + proc.stderr
    assert target.read_text(encoding="utf-8") == "# taslak\n"


# --------------------------------------------------------------------------
# the template
# --------------------------------------------------------------------------


def test_it_writes_the_template_when_nothing_exists(target: Path) -> None:
    """The ordinary path: A12 starts from a filled-in skeleton."""
    proc = run_pre_register("--target", str(target))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert target.is_file()


@pytest.mark.parametrize(
    "section",
    ["Hipotez", "Birincil metrik", "Eşik", "Null model", "Durdurma kural", "Negatif sonuç"],
)
def test_the_template_locks_every_field_that_can_be_moved_later(target: Path, section: str) -> None:
    """Each of these is something it would be tempting to revise after the fact."""
    run_pre_register("--target", str(target))
    assert section in target.read_text(encoding="utf-8")


def test_the_template_states_that_it_becomes_read_only(target: Path) -> None:
    """Whoever opens this file next has to learn the rule from the file itself."""
    run_pre_register("--target", str(target))
    body = target.read_text(encoding="utf-8")
    assert "değişmez 6" in body
    assert "PRE_REGISTRATION_v2.md" in body


def test_the_template_has_no_filled_in_metric_or_threshold(target: Path) -> None:
    """A default threshold in a template is a threshold nobody chose.

    Pre-filled numbers get committed unread, and then the pre-registration
    locks a value that was never a decision.
    """
    run_pre_register("--target", str(target))
    body = target.read_text(encoding="utf-8")
    assert "<" in body and ">" in body, "fields must be angle-bracket placeholders"
    assert "AUROC" not in body, "do not suggest a metric; that is the author's call"
