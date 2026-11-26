"""Tests that pin the CI workflow's decisions (roadmap H6).

A CI that is red on a commit which changed nothing gets switched off, and a CI
that is green on everything was never a gate. Each test here locks one decision
that would quietly turn CI into one or the other:

* the linters are **pinned**, so a new ruff release cannot redden a branch that
  did not change,
* ruff's scope is the one clean set and it comes from a single authority,
* ruff and pytest **block**, mypy does not,
* the checkout is a real git repository, because `tests/hooks` reads file modes
  out of the git index,
* no coverage floor yet, because the `run()` adapters sit at 0% (Bulgu-3) and a
  floor would fail on arrival.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
HOOKS = ROOT / ".claude" / "hooks"

sys.path.insert(0, str(HOOKS))

import _status  # noqa: E402, I001

#: The interpreter the suite is actually green on: 1019 passed on 3.12.3.
#: `requires-python` claims >= 3.11, which nothing has measured (invariant 3).
MEASURED_PYTHON = "3.12"


@pytest.fixture(scope="module")
def workflow() -> dict[str, Any]:
    """The parsed workflow, or a clear failure if it is not there yet."""
    assert WORKFLOW.is_file(), f"{WORKFLOW} yok"
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "workflow did not parse as a mapping"
    return data


def steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    """Every step of every job, flattened."""
    found: list[dict[str, Any]] = []
    for job in workflow.get("jobs", {}).values():
        for step in job.get("steps", []):
            if isinstance(step, dict):
                found.append(step)
    return found


def step_with(workflow: dict[str, Any], needle: str) -> dict[str, Any] | None:
    """The first step whose `run` or `uses` mentions ``needle``."""
    for step in steps(workflow):
        body = f"{step.get('run', '')} {step.get('uses', '')}"
        if needle in body:
            return step
    return None


def blocking(step: dict[str, Any]) -> bool:
    """Whether a failing step fails the job."""
    return not step.get("continue-on-error", False)


# --------------------------------------------------------------------------
# it has to run at all
# --------------------------------------------------------------------------


def test_the_workflow_triggers_on_push_and_pull_request(workflow: dict[str, Any]) -> None:
    """A gate nothing triggers is not a gate.

    YAML 1.1 reads a bare `on:` key as the boolean ``True``, so the trigger
    block has to be fetched under both spellings. Reading only ``"on"`` is a
    silent empty-dict, which would make this test pass against no triggers at
    all.
    """
    triggers = workflow.get("on", workflow.get(True))
    assert isinstance(triggers, dict), f"no trigger block: {triggers!r}"
    assert "push" in triggers
    assert "pull_request" in triggers


def test_it_checks_out_a_real_git_repository(workflow: dict[str, Any]) -> None:
    """`tests/hooks` reads file modes from the git index, not just from disk.

    Measured: the same tests run against a `git archive` export fail 8 times
    because there is no index to read, while a clean clone passes 109/109. So
    CI must check out, never unpack a tarball.
    """
    assert step_with(workflow, "actions/checkout") is not None


def test_it_runs_the_interpreter_the_suite_was_measured_on(workflow: dict[str, Any]) -> None:
    """3.12 is the version 1019 tests are known green on."""
    setup = step_with(workflow, "actions/setup-python")
    assert setup is not None, "no setup-python step"
    assert str(setup.get("with", {}).get("python-version", "")) == MEASURED_PYTHON


# --------------------------------------------------------------------------
# the pins: a CI that reddens on its own is a CI that gets switched off
# --------------------------------------------------------------------------


def test_the_linters_are_pinned_exactly() -> None:
    """`ruff>=0.6` lets a release three months from now redden an old commit.

    ruff adds and changes rules between minor versions. With a floor instead of
    a pin, CI's verdict on an unchanged tree depends on the day it runs, and
    the status block's "mypy 72 hata" drifts for the same reason.
    """
    body = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for tool in ("ruff", "mypy"):
        assert f'"{tool}>=' not in body, f"{tool} is pinned with a floor, not =="
        assert f'"{tool}==' in body, f"{tool} has no exact pin"


def test_dependencies_come_from_the_pyproject_dev_extra(workflow: dict[str, Any]) -> None:
    """One authority for the pins: the dev extra, not a second list in YAML."""
    install = step_with(workflow, "pip install")
    assert install is not None, "nothing installs the dependencies"
    assert "[dev]" in install["run"]


def test_no_step_installs_a_linter_on_its_own(workflow: dict[str, Any]) -> None:
    """Installing ruff separately would walk straight past the pin."""
    for step in steps(workflow):
        run = step.get("run", "")
        for tool in ("ruff", "mypy"):
            assert f"pip install {tool}" not in run, f"{tool} installed outside the dev extra"


# --------------------------------------------------------------------------
# what blocks and what does not
# --------------------------------------------------------------------------


def test_ruff_gates_exactly_the_clean_scope(workflow: dict[str, Any]) -> None:
    """The scope has one authority: `_status.RUFF_SCOPE`.

    The workflow spells the directories out, because a YAML line that computes
    them is unreadable where it matters most. The copy is allowed only because
    this test pins it to the authority — and this test runs in CI, so the two
    cannot drift apart in a merge.
    """
    step = step_with(workflow, "ruff check")
    assert step is not None, "no ruff step"
    for directory in _status.RUFF_SCOPE:
        assert directory in step["run"], f"ruff does not cover {directory}"


def test_ruff_now_gates_the_whole_tests_tree(workflow: dict[str, Any]) -> None:
    """The debt that kept `tests/` out of the gate is gone (H14 + H15).

    This test used to assert the opposite — that `tests` must *not* appear —
    because the tree carried 50 findings and widening the gate would have made
    CI red on arrival. 32 were mechanical (H14) and 18 needed judgement (H15),
    including 7 blind `pytest.raises(Exception)` that were findings rather than
    debt. With all of them closed, the premise is gone and leaving the gate
    narrow would let the debt build back up unseen.
    """
    step = step_with(workflow, "ruff check")
    assert step is not None
    assert "tests" in step["run"].split(), "ruff should gate tests/ now that it is clean"


def test_ruff_and_pytest_block_the_job(workflow: dict[str, Any]) -> None:
    """These two are the gate. If they cannot fail the job, nothing is gated."""
    for needle in ("ruff check", "pytest"):
        step = step_with(workflow, needle)
        assert step is not None, f"no {needle} step"
        assert blocking(step), f"{needle} is marked continue-on-error"


def test_mypy_runs_but_does_not_block(workflow: dict[str, Any]) -> None:
    """72 errors today (roadmap B10); blocking on them would stop every branch."""
    step = step_with(workflow, "mypy")
    assert step is not None, "mypy does not run at all — then its number is unmeasured"
    assert not blocking(step), "mypy blocks; B10 has to land before that is honest"


def test_there_is_no_coverage_floor_yet(workflow: dict[str, Any]) -> None:
    """A floor fails on arrival: the `run()` adapters CI exercises sit at 0%.

    Bulgu-3. Raising coverage is its own work; a floor added here would be
    satisfied by deleting tests just as easily as by writing them.
    """
    body = WORKFLOW.read_text(encoding="utf-8")
    assert "--cov-fail-under" not in body


# ---------------------------------------------------------------------------
# Reproducibility of the runner itself (roadmap H16)
# ---------------------------------------------------------------------------

_FLOATING_RUNNERS = {"ubuntu-latest", "macos-latest", "windows-latest"}


def test_the_runner_image_is_not_a_floating_tag(workflow: dict[str, Any]) -> None:
    """H6's whole rule is that CI must not go red on an unchanged tree.

    `ubuntu-latest` breaks it by construction: the image moves underneath the
    workflow. It is not hypothetical — the label moved from 24.04 to 26.04
    during this project's life, and the source build of hic-straw plus the apt
    packages it needs are exactly the kind of thing that changes with it.
    """
    runs_on = workflow["jobs"]["gate"]["runs-on"]
    assert runs_on not in _FLOATING_RUNNERS, (
        f"runs-on: {runs_on} is a floating tag; pin the image version"
    )


def test_every_action_is_pinned_to_a_commit_sha(workflow: dict[str, Any]) -> None:
    """A tag is mutable; a commit SHA is not.

    `ruff==0.16.7` in the dev extra is pointless if the CI enforcing it can be
    re-pointed by whoever owns the action's tag. Each `uses:` therefore carries
    a 40-hex SHA, with the human-readable version in a trailing comment.
    """
    bad: list[str] = []
    for step in steps(workflow):
        uses = step.get("uses")
        if not uses:
            continue
        ref = uses.split("@", 1)[1] if "@" in uses else ""
        if not re.fullmatch(r"[0-9a-f]{40}", ref):
            bad.append(uses)
    assert not bad, f"not SHA-pinned: {bad}"


def test_each_pinned_action_names_its_version_in_a_comment() -> None:
    """A bare SHA is unreadable, and unreadable pins get replaced by tags.

    The comment is what makes the pin maintainable, so it is part of the
    contract rather than a courtesy.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    for line in text.splitlines():
        if "uses:" in line and "@" in line:
            assert "#" in line.split("@", 1)[1], f"no version comment: {line.strip()}"
