"""One perturb/restore helper, and it never leaves stale bytecode (roadmap H23).

Several gates prove their mechanism fires by perturbing a tracked file, running
something, and restoring it. Each had grown its own helper — `A13.sh`'s
``perturb()`` and `H21.sh`'s ``with_patched()`` — and both carried the same
restore-and-assert logic. A fact known in two places is the drift `H9` exists
to stop, and here the second copy also hid a hazard neither author saw.

**The hazard, measured.** CPython validates a cached ``.pyc`` against the
source's *(whole-second mtime, byte size)* pair. Perturb a ``.py``, let
something import it, then restore the original within the same second at the
same size, and that pair is unchanged — so the stale bytecode keeps being
loaded. It bit this project live: `A10b`'s red-first probe changed the G:U
weight in ``seed_aligner.py`` from 0.5 to 0.6 and restored it with the bytes
asserted identical, yet the full suite then failed
``test_gu_wobble_detection`` with ``19.6 != 19.5`` while the source on disk
said ``0.5``. Deleting ``__pycache__`` alone fixed it.

**The dangerous direction is the other one.** The same masking can hide the
*perturbation*: a gate writes the broken version, the import reads the old
bytecode, the test stays green, and the gate concludes "the mechanism fires"
having fired nothing. That is a gate reporting verification it never
performed — the exact failure invariant 5 exists to catch, and `H21`'s own
lesson one level down: declared is not implemented.

So `TestTheTrapIsReal` builds the condition deterministically (``os.utime``
pins the mtime rather than racing the clock) and asserts the stale read. If
CPython ever changes its invalidation rule, that test goes red and tells us
this helper's reason has gone away — which is the point of keeping the
control.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / ".claude" / "hooks"
ACCEPTANCE = ROOT / ".claude" / "acceptance"

sys.path.insert(0, str(HOOKS))

import _perturb  # noqa: E402


def _import_value(directory: Path) -> str:
    """Import ``demo`` in a *fresh* interpreter and report its VALUE."""
    done = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, '.'); import demo; print(demo.VALUE)"],
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return done.stdout.strip()


def _module(directory: Path, body: bytes = b"VALUE = 0.5\n") -> Path:
    module = directory / "demo.py"
    module.write_bytes(body)
    return module


class TestTheTrapIsReal:
    """The control. Without this, the helper below is decoration."""

    def test_same_second_same_size_rewrite_is_invisible(self, tmp_path: Path) -> None:
        module = _module(tmp_path)
        pinned = module.stat().st_mtime
        assert _import_value(tmp_path) == "0.5"          # writes the .pyc

        # Same byte size, and the mtime pinned back to what the .pyc recorded.
        module.write_bytes(b"VALUE = 0.6\n")
        os.utime(module, (pinned, pinned))

        stale = _import_value(tmp_path)
        assert stale == "0.5", (
            "CPython no longer loads stale bytecode after a same-second, "
            "same-size rewrite — H23's reason may have gone away; re-measure "
            "before trusting this helper's necessity"
        )

    def test_the_cache_file_is_where_the_helper_looks(self, tmp_path: Path) -> None:
        _module(tmp_path)
        assert _import_value(tmp_path) == "0.5"
        cached = list((tmp_path / "__pycache__").glob("demo.*.pyc"))
        assert cached, "no bytecode was written; the trap cannot be reproduced"


class TestTheHelperDefeatsTheTrapBothWays:
    """Perturbation must be visible, and so must the restoration."""

    def test_perturbation_is_visible(self, tmp_path: Path) -> None:
        module = _module(tmp_path)
        pinned = module.stat().st_mtime
        assert _import_value(tmp_path) == "0.5"
        os.utime(module, (pinned, pinned))

        with _perturb.perturbed(module, "0.5", "0.6"):
            os.utime(module, (pinned, pinned))   # recreate the hostile condition
            assert _import_value(tmp_path) == "0.6", (
                "the perturbation was masked by stale bytecode — a gate here "
                "would report a mechanism verified having verified nothing"
            )

    def test_restoration_is_visible(self, tmp_path: Path) -> None:
        module = _module(tmp_path)
        pinned = module.stat().st_mtime
        assert _import_value(tmp_path) == "0.5"

        with _perturb.perturbed(module, "0.5", "0.6"):
            os.utime(module, (pinned, pinned))
            _import_value(tmp_path)              # let the 0.6 bytecode be written
        os.utime(module, (pinned, pinned))       # hostile again, after restore

        assert _import_value(tmp_path) == "0.5", (
            "the restoration was masked by stale bytecode — this is the live "
            "failure A10b hit"
        )

    def test_non_python_files_are_handled_too(self, tmp_path: Path) -> None:
        target = tmp_path / "notes.md"
        target.write_text("alpha\n", encoding="utf-8")
        with _perturb.perturbed(target, "alpha", "beta"):
            assert target.read_text(encoding="utf-8") == "beta\n"
        assert target.read_text(encoding="utf-8") == "alpha\n"


class TestTheHelperRefusesToCorruptTheRepository:
    def test_bytes_are_restored_exactly(self, tmp_path: Path) -> None:
        module = _module(tmp_path, b"VALUE = 0.5\n# trailing\n")
        original = module.read_bytes()
        with _perturb.perturbed(module, "0.5", "0.6"):
            pass
        assert module.read_bytes() == original

    def test_restoration_happens_even_when_the_body_raises(self, tmp_path: Path) -> None:
        module = _module(tmp_path)
        original = module.read_bytes()
        with pytest.raises(RuntimeError), _perturb.perturbed(module, "0.5", "0.6"):
            raise RuntimeError("boom")
        assert module.read_bytes() == original

    def test_an_anchor_that_is_not_unique_is_refused(self, tmp_path: Path) -> None:
        module = _module(tmp_path, b"A = 0.5\nB = 0.5\n")
        with pytest.raises(ValueError, match="2"), _perturb.perturbed(
            module, "0.5", "0.6"
        ):
            pass
        assert module.read_bytes() == b"A = 0.5\nB = 0.5\n"

    def test_a_missing_anchor_is_refused(self, tmp_path: Path) -> None:
        module = _module(tmp_path)
        with pytest.raises(ValueError, match="0"), _perturb.perturbed(
            module, "nowhere", "somewhere"
        ):
            pass

    def test_whole_text_replacement_is_available(self, tmp_path: Path) -> None:
        """H21 replaces a whole file rather than an anchor."""
        target = tmp_path / "workflow.yml"
        target.write_text("steps: []\n", encoding="utf-8")
        with _perturb.patched(target, "steps: [probe]\n"):
            assert target.read_text(encoding="utf-8") == "steps: [probe]\n"
        assert target.read_text(encoding="utf-8") == "steps: []\n"


# ---------------------------------------------------------------------------
# The scan: no gate may grow its own perturb helper again
# ---------------------------------------------------------------------------


def _scripts_with_their_own_perturb_helper() -> dict[str, list[str]]:
    """Acceptance scripts that write to a *parameter* of their own function.

    That shape — ``def f(path, ...): ... path.write_text(...)`` — is a generic
    perturb helper whatever it is pointed at, so it is the thing that must be
    shared. Writes into a ``tempfile`` directory are a different shape
    (``tmpd / "x"``) and are not caught, deliberately: those build fixtures,
    they do not perturb the repository.
    """
    out: dict[str, list[str]] = {}
    for script in sorted(ACCEPTANCE.glob("*.sh")):
        text = script.read_text(encoding="utf-8")
        helpers: list[str] = []
        for match in re.finditer(r"^def (\w+)\(([^)]*)\)", text, re.M):
            name, signature = match.group(1), match.group(2)
            parameters = {
                part.split(":")[0].split("=")[0].strip()
                for part in signature.split(",")
                if part.strip()
            }
            body = text[match.end() : match.end() + 1200]
            if any(re.search(rf"\b{re.escape(p)}\.write_(?:text|bytes)\(", body)
                   for p in parameters if p):
                helpers.append(name)
        if helpers:
            out[script.name] = helpers
    return out


class TestEveryPerturbingGateUsesTheSharedHelper:
    """H21's lesson, one level down: the list must not be able to go stale."""

    def test_no_gate_keeps_its_own_perturb_helper(self) -> None:
        offenders: list[str] = []
        for name, helpers in _scripts_with_their_own_perturb_helper().items():
            text = (ACCEPTANCE / name).read_text(encoding="utf-8")
            if "_perturb" not in text:
                offenders.append(f"{name}: {helpers}")
        assert not offenders, (
            "these gates write to a parameter of their own helper and do not "
            "route through `_perturb`, so a perturbation of a .py file there "
            "can be silently masked by stale bytecode: " + "; ".join(offenders)
        )

    def test_the_scanner_catches_a_fabricated_offender(self, tmp_path: Path) -> None:
        """A scanner nobody has shown to fire is a scanner nobody can trust."""
        fabricated = (
            "#!/usr/bin/env bash\n"
            '"$PY" - <<\'INNER\'\n'
            "def perturb(path, old, new):\n"
            "    original = path.read_bytes()\n"
            "    path.write_text(original.decode().replace(old, new))\n"
            "INNER\n"
        )
        script = ACCEPTANCE / "ZZ_fabricated_for_test.sh"
        assert not script.exists(), "fixture name collides with a real gate"
        script.write_text(fabricated, encoding="utf-8")
        try:
            found = _scripts_with_their_own_perturb_helper()
            assert script.name in found, (
                "the scanner missed a textbook ad-hoc perturb helper"
            )
            assert found[script.name] == ["perturb"]
        finally:
            script.unlink()

    def test_the_scanner_ignores_tempfile_fixtures(self, tmp_path: Path) -> None:
        """B19 and C3d write into tempfile dirs; flagging them would be noise."""
        fabricated = (
            "#!/usr/bin/env bash\n"
            '"$PY" - <<\'INNER\'\n'
            "with tempfile.TemporaryDirectory() as tmp:\n"
            "    tmpd = Path(tmp)\n"
            "    fixture = tmpd / 'mock.csv'\n"
            "    fixture.write_text('a,b\\n')\n"
            "INNER\n"
        )
        script = ACCEPTANCE / "ZZ_fixture_only_for_test.sh"
        assert not script.exists()
        script.write_text(fabricated, encoding="utf-8")
        try:
            assert script.name not in _scripts_with_their_own_perturb_helper()
        finally:
            script.unlink()

    def test_the_two_gates_that_perturb_are_still_the_only_ones(self) -> None:
        """If a third appears, it must be looked at rather than assumed fine."""
        found = set(_scripts_with_their_own_perturb_helper())
        assert found <= {"A13.sh", "H21.sh"}, (
            f"a new gate perturbs files: {sorted(found - {'A13.sh', 'H21.sh'})} — "
            "check that it routes through `_perturb`"
        )
