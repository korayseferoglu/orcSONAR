"""Tests for the next-fix resolver (roadmap H5).

next-fix answers one question — which item may be worked on now (invariant 8) —
and it must answer it from the same parser the launch status block uses. A
second roadmap parser would drift from the first, which is the failure mode
`H9` exists to close.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".claude" / "skills" / "next-fix" / "scripts" / "next_fix.py"
HOOKS = ROOT / ".claude" / "hooks"

sys.path.insert(0, str(HOOKS))

import _status  # noqa: E402, I001

ROADMAP = """\
### FAZ 9 — Test fazı

| id | iş | bağımlılık | kabul | durum |
|---|---|---|---|---|
| **Z1** | kapanmış iş | — | koştu | **DONE** |
| **Z2** | beyanla kapanmış iş | Z1 | gözlendi | **DONE(beyan)** |
| **Z3** | sıradaki iş | Z2 | kabul betiği koşuyor | TODO |
| **Z4** | yazım hatalı bağımlılık | Z99 | olmaz | TODO |
| **Z5** | ikinci hazır iş | Z1 | koşuyor | TODO |
"""


@pytest.fixture
def roadmap(tmp_path: Path) -> Path:
    """A roadmap exercising both closing verdicts and a mistyped dependency."""
    path = tmp_path / "ROADMAP.md"
    path.write_text(ROADMAP, encoding="utf-8")
    return path


def run_next_fix(roadmap: Path, *args: str, acceptance: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Invoke the resolver the way the skill invokes it."""
    argv = [sys.executable, "-I", str(SCRIPT), "--roadmap", str(roadmap)]
    if acceptance is not None:
        argv += ["--acceptance-dir", str(acceptance)]
    return subprocess.run([*argv, *args], capture_output=True, text=True, timeout=120, cwd=ROOT)


# --------------------------------------------------------------------------
# the DONE(beyan) vocabulary, shared with the launch status block
# --------------------------------------------------------------------------


def test_declared_done_parses_as_a_status() -> None:
    """`DONE(beyan)` is a status, not an unparsed cell falling back to `—`."""
    items = {item.id: item for item in _status.parse_roadmap(ROADMAP)}
    assert items["Z2"].status == "DONE(beyan)"


def test_declared_done_satisfies_a_dependency() -> None:
    """Otherwise a declared closure would silently stall everything behind it."""
    items = _status.parse_roadmap(ROADMAP)
    assert [item.id for item in _status.ready_items(items)] == ["Z3", "Z5"]


def test_declared_done_is_counted_in_the_phase_line() -> None:
    """A closed item that no count includes is how `DOING` already got lost."""
    items = _status.parse_roadmap(ROADMAP)
    line = _status.phase_text(items, _status.next_item(items))
    assert "5 madde: 2 DONE" in line, line


# --------------------------------------------------------------------------
# the resolver
# --------------------------------------------------------------------------


def test_it_picks_the_first_item_whose_dependencies_are_met(roadmap: Path) -> None:
    """Roadmap order is the work order (invariant 8)."""
    proc = run_next_fix(roadmap, "--json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["id"] == "Z3"
    assert payload["ready"] == ["Z3", "Z5"]


def test_a_mistyped_dependency_does_not_promote_an_item(roadmap: Path) -> None:
    """`Z99` does not exist, so `Z4` is blocked, not ready."""
    proc = run_next_fix(roadmap, "--json")
    assert "Z4" not in json.loads(proc.stdout)["ready"]


def test_it_reports_whether_a_hard_gate_exists(roadmap: Path, tmp_path: Path) -> None:
    """The session needs to know up front whether closing will be verified."""
    directory = tmp_path / "acceptance"
    directory.mkdir()
    (directory / "Z3.sh").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    proc = run_next_fix(roadmap, "--json", acceptance=directory)
    assert json.loads(proc.stdout)["gate"] is not None


def test_a_missing_gate_is_reported_as_missing(roadmap: Path, tmp_path: Path) -> None:
    """Invariant 2: absence is stated, not left to look like presence."""
    proc = run_next_fix(roadmap, "--json", acceptance=tmp_path / "empty")
    payload = json.loads(proc.stdout)
    assert payload["gate"] is None
    assert "Z3.sh" in payload["gate_expected"]


def test_the_human_block_names_the_item_and_its_criterion(roadmap: Path, tmp_path: Path) -> None:
    """The default output is read by a person at the start of a session."""
    proc = run_next_fix(roadmap, acceptance=tmp_path / "empty")
    assert proc.returncode == 0, proc.stderr
    assert "Z3" in proc.stdout
    assert "kabul betiği koşuyor" in proc.stdout
    assert "değişmez 8" in proc.stdout, "the one-item rule belongs on this screen"


def test_it_exits_nonzero_when_nothing_is_ready(tmp_path: Path) -> None:
    """A finished phase must not print a stale item."""
    path = tmp_path / "ROADMAP.md"
    path.write_text(
        "### FAZ 9 — Test fazı\n\n| **Z1** | iş | — | koştu | **DONE** |\n",
        encoding="utf-8",
    )
    proc = run_next_fix(path)
    assert proc.returncode == 1
