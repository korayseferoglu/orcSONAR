"""Tests for the fix-done gate (roadmap H5).

fix-done is the only place in this harness that may call work finished, so
almost every test below is about what it **refuses**. A gate that can only say
yes is not a gate — that is invariant 3, and `mypy strict=true`, `h3k27me3` and
`--json` were all lost to exactly that shape of mistake.

Two closing verdicts exist and they must never blur into one:

* ``DONE`` — an acceptance script ran and exited 0. Machine-checked.
* ``DONE(beyan)`` — no script could exist for this item, so a human-readable
  declaration was recorded instead. Auditable, but not verified.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".claude" / "skills" / "fix-done" / "scripts" / "fix_done.py"

ROADMAP = """\
### FAZ 9 — Test fazı

| id | iş | bağımlılık | kabul | durum |
|---|---|---|---|---|
| **Z1** | kapanmış iş | — | koştu | **DONE** |
| **Z2** | açık iş | Z1 | kabul betiği var | TODO |
| **Z3** | gözlemle kapanan iş | Z1 | sonraki açılışta görülüyor | TODO |
"""


@pytest.fixture
def roadmap(tmp_path: Path) -> Path:
    """A minimal roadmap with one closed item and two open ones."""
    path = tmp_path / "ROADMAP.md"
    path.write_text(ROADMAP, encoding="utf-8")
    return path


def run_fix_done(roadmap: Path, *args: str, acceptance: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Invoke the gate the way the skill invokes it."""
    argv = [sys.executable, "-I", str(SCRIPT), "--roadmap", str(roadmap)]
    if acceptance is not None:
        argv += ["--acceptance-dir", str(acceptance)]
    return subprocess.run([*argv, *args], capture_output=True, text=True, timeout=120, cwd=ROOT)


def write_gate(tmp_path: Path, item: str, body: str) -> Path:
    """Create an acceptance script for ``item`` and return its directory."""
    directory = tmp_path / "acceptance"
    directory.mkdir(exist_ok=True)
    script = directory / f"{item}.sh"
    script.write_text(f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8")
    script.chmod(0o755)
    return directory


# --------------------------------------------------------------------------
# the item has to exist and be open
# --------------------------------------------------------------------------


def test_unknown_item_is_refused(roadmap: Path) -> None:
    """A typo must not quietly close nothing and report success."""
    proc = run_fix_done(roadmap, "Z99", "--red-first", "test ilk koşuda kırmızıydı")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "Z99" in proc.stdout + proc.stderr


def test_already_closed_item_is_refused(roadmap: Path) -> None:
    """Re-closing a DONE item hides whatever actually changed."""
    proc = run_fix_done(roadmap, "Z1", "--red-first", "test ilk koşuda kırmızıydı")
    assert proc.returncode == 2, proc.stdout + proc.stderr


# --------------------------------------------------------------------------
# invariant 5: red-first evidence is never optional
# --------------------------------------------------------------------------


def test_missing_red_first_evidence_is_refused(roadmap: Path, tmp_path: Path) -> None:
    """No hook can measure invariant 5, so the gate has to ask for it."""
    gate = write_gate(tmp_path, "Z2", "exit 0")
    proc = run_fix_done(roadmap, "Z2", acceptance=gate)
    assert proc.returncode == 1, proc.stdout
    assert "DONE" not in proc.stdout.replace("DONE(beyan)", ""), proc.stdout


def test_blank_red_first_evidence_is_refused(roadmap: Path, tmp_path: Path) -> None:
    """Whitespace is not evidence."""
    gate = write_gate(tmp_path, "Z2", "exit 0")
    proc = run_fix_done(roadmap, "Z2", "--red-first", "   ", acceptance=gate)
    assert proc.returncode == 1, proc.stdout


def test_red_first_may_be_declared_absent_with_a_reason(roadmap: Path, tmp_path: Path) -> None:
    """Some items change no code; the exemption is recorded, not silent."""
    gate = write_gate(tmp_path, "Z2", "exit 0")
    proc = run_fix_done(
        roadmap, "Z2", "--red-first", "yok: bu madde yalnız belge değiştiriyor", acceptance=gate
    )
    assert proc.returncode == 0, proc.stdout
    assert "yok:" in proc.stdout


def test_bare_absent_red_first_without_a_reason_is_refused(roadmap: Path, tmp_path: Path) -> None:
    """`yok` on its own is a shrug; it needs the reason after the colon."""
    gate = write_gate(tmp_path, "Z2", "exit 0")
    proc = run_fix_done(roadmap, "Z2", "--red-first", "yok", acceptance=gate)
    assert proc.returncode == 1, proc.stdout


# --------------------------------------------------------------------------
# the hard gate
# --------------------------------------------------------------------------


def test_failing_acceptance_script_rejects_the_item(roadmap: Path, tmp_path: Path) -> None:
    """H5's own acceptance criterion: a failing item must be refused."""
    gate = write_gate(tmp_path, "Z2", "echo '3 test kırmızı'; exit 1")
    proc = run_fix_done(roadmap, "Z2", "--red-first", "test ilk koşuda kırmızıydı", acceptance=gate)
    assert proc.returncode == 1, proc.stdout
    assert "REDDEDİLDİ" in proc.stdout, proc.stdout
    assert "3 test kırmızı" in proc.stdout, "the gate must show why it refused"


def test_passing_acceptance_script_closes_the_item_as_verified(roadmap: Path, tmp_path: Path) -> None:
    """A green gate closes to DONE, not to the weaker declared verdict."""
    gate = write_gate(tmp_path, "Z2", "echo '67/67 yeşil'; exit 0")
    proc = run_fix_done(roadmap, "Z2", "--red-first", "iki test fix'ten önce kırmızıydı", acceptance=gate)
    assert proc.returncode == 0, proc.stdout
    assert "**DONE**" in proc.stdout, proc.stdout
    assert "beyan" not in proc.stdout.split("REDDEDİLDİ")[0] or "DONE(beyan)" not in proc.stdout


def test_a_declaration_cannot_override_a_failing_gate(roadmap: Path, tmp_path: Path) -> None:
    """Once a script exists, prose must not be able to talk past it."""
    gate = write_gate(tmp_path, "Z2", "exit 1")
    proc = run_fix_done(
        roadmap,
        "Z2",
        "--red-first",
        "test kırmızıydı",
        "--declare",
        "bence geçiyor",
        acceptance=gate,
    )
    assert proc.returncode == 1, proc.stdout
    assert "REDDEDİLDİ" in proc.stdout


# --------------------------------------------------------------------------
# the declared path, for criteria no script can express
# --------------------------------------------------------------------------


def test_no_script_and_no_declaration_is_refused(roadmap: Path, tmp_path: Path) -> None:
    """Without a gate or a declaration there is nothing to audit later."""
    proc = run_fix_done(
        roadmap, "Z3", "--red-first", "test kırmızıydı", acceptance=tmp_path / "empty"
    )
    assert proc.returncode == 1, proc.stdout
    assert "Z3.sh" in proc.stdout, "the gate should name the file it looked for"


def test_declaration_closes_the_item_as_declared_not_verified(roadmap: Path, tmp_path: Path) -> None:
    """The weaker verdict must be visibly weaker in the roadmap."""
    proc = run_fix_done(
        roadmap,
        "Z3",
        "--red-first",
        "yok: gözlem maddesi",
        "--declare",
        "blok 12:33 UTC'de en üstte basıldı, exit=0",
        acceptance=tmp_path / "empty",
    )
    assert proc.returncode == 0, proc.stdout
    assert "**DONE(beyan)**" in proc.stdout, proc.stdout
    assert "12:33" in proc.stdout, "the declaration itself belongs in the output"


def test_blank_declaration_is_refused(roadmap: Path, tmp_path: Path) -> None:
    """An empty declaration is the silent-accept path this gate exists to close."""
    proc = run_fix_done(
        roadmap,
        "Z3",
        "--red-first",
        "yok: gözlem maddesi",
        "--declare",
        "  ",
        acceptance=tmp_path / "empty",
    )
    assert proc.returncode == 1, proc.stdout


# --------------------------------------------------------------------------
# the gate never edits the roadmap itself
# --------------------------------------------------------------------------


def test_the_gate_does_not_write_the_roadmap(roadmap: Path, tmp_path: Path) -> None:
    """Closing is a human-reviewed edit; the gate only issues the verdict.

    The evidence prose that belongs in the row needs judgement, and a script
    that rewrites a 2000-character table row is a worse risk than the typing it
    saves.
    """
    before = roadmap.read_text(encoding="utf-8")
    gate = write_gate(tmp_path, "Z2", "exit 0")
    run_fix_done(roadmap, "Z2", "--red-first", "kırmızıydı", acceptance=gate)
    assert roadmap.read_text(encoding="utf-8") == before
