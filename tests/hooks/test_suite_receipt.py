"""Tests for the suite receipt's schema and merge rule (roadmap H20).

H7 gave the commit gate a receipt to read. H20 is the friction that came with
it: the receipt was a single record of *the last pytest invocation of any
kind*, so running one acceptance script — every one of them runs a narrowed
pytest — overwrote the whole-suite evidence with `whole_suite: false` and the
next commit was refused. Measured twice while landing H19, and the cost was
3.5 minutes per gate run. A gate whose routine use costs that much is the gate
H7's own row warns about: the one that gets bypassed.

The fix is not to make partial runs write somewhere else. It is to notice that
a partial run **destroys no evidence**: the whole suite really did pass at
time T, and a later narrowed run does not make that less true. So the receipt
keeps two facts instead of one — the latest run (which can fail, and a failure
still refuses) and the latest *whole-suite* run (the freshness evidence).

Why the logic lives in `_receipt.py` rather than in the two callers: the writer
is `tests/conftest.py` and the reader is `block-stale-commit.py`, and a schema
known in two places is the drift `H9` exists to stop. The earlier proposal in
the roadmap row — an `ORCSONAR_SUITE_RECEIPT` in every acceptance script — was
rejected for the same reason: it spreads the obligation across twenty scripts,
and the twenty-first forgets it silently.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / ".claude" / "hooks"

sys.path.insert(0, str(HOOKS))

import _receipt  # noqa: E402


def _run(
    *, at: float, whole: bool, status: int = 0, collected: int = 1, failed: int = 0
) -> dict[str, object]:
    """A receipt record for one pytest invocation."""
    return {
        "at": at,
        "exitstatus": status,
        "whole_suite": whole,
        "args": ["tests"] if whole else ["tests/hooks/test_x.py"],
        "collected": collected,
        "failed": failed,
    }


class TestMergeKeepsWholeSuiteEvidence:
    """The whole point: a narrowed run must not erase a whole-suite result."""

    def test_whole_suite_run_records_itself_as_the_evidence(self) -> None:
        merged = _receipt.merge(None, _run(at=100.0, whole=True, collected=1246))
        assert merged["whole_suite"] is True
        assert merged["last_whole_suite"]["at"] == 100.0
        assert merged["last_whole_suite"]["collected"] == 1246

    def test_partial_run_preserves_the_earlier_whole_suite(self) -> None:
        previous = _receipt.merge(None, _run(at=100.0, whole=True, collected=1246))
        merged = _receipt.merge(previous, _run(at=200.0, whole=False, collected=17))
        # The latest-run fields are the new, narrowed run …
        assert merged["at"] == 200.0
        assert merged["whole_suite"] is False
        assert merged["collected"] == 17
        # … and the evidence is still the whole-suite run.
        assert merged["last_whole_suite"]["at"] == 100.0
        assert merged["last_whole_suite"]["collected"] == 1246

    def test_partial_run_after_partial_run_still_keeps_it(self) -> None:
        first = _receipt.merge(None, _run(at=100.0, whole=True))
        second = _receipt.merge(first, _run(at=200.0, whole=False))
        third = _receipt.merge(second, _run(at=300.0, whole=False))
        assert third["last_whole_suite"]["at"] == 100.0

    def test_a_newer_whole_suite_run_replaces_the_older_one(self) -> None:
        previous = _receipt.merge(None, _run(at=100.0, whole=True))
        merged = _receipt.merge(previous, _run(at=400.0, whole=True))
        assert merged["last_whole_suite"]["at"] == 400.0

    def test_a_failed_whole_suite_run_is_recorded_as_failed_not_dropped(self) -> None:
        """Hiding a red whole-suite run would be the dangerous direction."""
        previous = _receipt.merge(None, _run(at=100.0, whole=True))
        merged = _receipt.merge(previous, _run(at=400.0, whole=True, status=1, failed=3))
        assert merged["last_whole_suite"]["at"] == 400.0
        assert merged["last_whole_suite"]["exitstatus"] == 1
        assert merged["last_whole_suite"]["failed"] == 3


class TestMigrationFromTheOldSchema:
    """A receipt written before H20 has no `last_whole_suite` key at all."""

    def test_old_whole_suite_receipt_is_promoted_to_evidence(self) -> None:
        old = _run(at=100.0, whole=True, collected=1246)  # no nested key
        merged = _receipt.merge(old, _run(at=200.0, whole=False))
        assert merged["last_whole_suite"]["at"] == 100.0

    def test_old_partial_receipt_carries_no_evidence(self) -> None:
        old = _run(at=100.0, whole=False)
        merged = _receipt.merge(old, _run(at=200.0, whole=False))
        assert "last_whole_suite" not in merged

    def test_unreadable_previous_is_not_fatal(self) -> None:
        for junk in (None, [], "", 7, {"last_whole_suite": "nope"}):
            merged = _receipt.merge(junk, _run(at=200.0, whole=False))
            assert merged["at"] == 200.0
            assert "last_whole_suite" not in merged


class TestWholeSuiteEvidence:
    """What the gate asks the receipt."""

    def test_latest_run_is_the_evidence_when_it_was_the_whole_suite(self) -> None:
        receipt = _receipt.merge(None, _run(at=100.0, whole=True))
        evidence = _receipt.whole_suite_evidence(receipt)
        assert evidence is not None
        assert evidence["at"] == 100.0

    def test_nested_record_is_the_evidence_after_a_partial_run(self) -> None:
        previous = _receipt.merge(None, _run(at=100.0, whole=True))
        receipt = _receipt.merge(previous, _run(at=200.0, whole=False))
        evidence = _receipt.whole_suite_evidence(receipt)
        assert evidence is not None
        assert evidence["at"] == 100.0

    def test_no_whole_suite_run_means_no_evidence(self) -> None:
        receipt = _receipt.merge(None, _run(at=200.0, whole=False))
        assert _receipt.whole_suite_evidence(receipt) is None

    def test_nonsense_receipts_yield_no_evidence(self) -> None:
        """Unknown is not permission (invariant 2)."""
        for junk in (None, [], "x", 1, {}, {"whole_suite": False}):
            assert _receipt.whole_suite_evidence(junk) is None


class TestReceiptPath:
    """Writer and reader must resolve the same file, env override included."""

    def test_default_is_reports_last_suite_json(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.delenv("ORCSONAR_SUITE_RECEIPT", raising=False)
        assert _receipt.receipt_path("/tmp/x") == Path("/tmp/x/reports/last-suite.json")

    def test_env_override_wins(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("ORCSONAR_SUITE_RECEIPT", "/tmp/other.json")
        assert _receipt.receipt_path("/tmp/x") == Path("/tmp/other.json")

    def test_the_gate_uses_this_module(self) -> None:
        """Otherwise the two ends drift and the gate reads a stale schema."""
        hook = (HOOKS / "block-stale-commit.py").read_text(encoding="utf-8")
        assert "_receipt" in hook

    def test_conftest_uses_this_module(self) -> None:
        conftest = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
        assert "_receipt" in conftest


# ---------------------------------------------------------------------------
# H22 — a gate that proves a test goes red must not leave the red behind
# ---------------------------------------------------------------------------


class TestDeliberatelyRedGatesRedirectTheReceipt:
    """H20's sibling, and H20 does not cover it.

    H20 stopped a *narrowed* run from erasing the whole-suite evidence. But
    `A13.sh` and `H21.sh` prove their mechanisms work by perturbing a file and
    running pytest **red** on purpose. That red lands in the receipt's
    latest-run fields, and `H7`'s first check is "latest run failed → refuse",
    so the next commit is blocked. Measured: after A5 closed, running A13.sh
    left `exitstatus=1, failed=2` over 8 tests and the commit was refused,
    while the whole-suite evidence was still intact — so H20 had done its job
    and the poisoning was in a different field.

    This is the structural cost of self-verifying gates: if the only way to
    show a mechanism fires is to make it fire, the failure gets recorded
    somewhere. The fix is to point those runs at a throwaway receipt, and the
    test below is what stops the third such gate from forgetting (H21's
    lesson, one level down).
    """

    GATES_THAT_RUN_PYTEST_IN_A_SUBPROCESS = ("A13.sh", "H21.sh")

    def _acceptance(self, name: str) -> str:
        return (ROOT / ".claude" / "acceptance" / name).read_text(encoding="utf-8")

    def test_every_subprocess_pytest_redirects_the_receipt(self) -> None:
        """Scanned rather than asserted: a new gate must not be able to forget."""
        import re

        offenders: list[str] = []
        for name in self.GATES_THAT_RUN_PYTEST_IN_A_SUBPROCESS:
            text = self._acceptance(name)
            # Python-level invocations: subprocess.run([... "-m", "pytest" ...])
            for match in re.finditer(r'"-m",\s*"pytest"', text):
                window = text[max(0, match.start() - 600) : match.start() + 600]
                if "ORCSONAR_SUITE_RECEIPT" not in window:
                    offenders.append(
                        f"{name}: a subprocess pytest call near offset "
                        f"{match.start()} does not set ORCSONAR_SUITE_RECEIPT"
                    )
        assert not offenders, "; ".join(offenders)

    def test_the_scan_covers_the_gates_that_need_it(self) -> None:
        """A list that silently stops matching reality is worse than none."""
        import re
        from pathlib import Path as _Path

        acceptance = ROOT / ".claude" / "acceptance"
        spawning = {
            path.name
            for path in acceptance.glob("*.sh")
            if re.search(r'"-m",\s*"pytest"', path.read_text(encoding="utf-8"))
        }
        listed = set(self.GATES_THAT_RUN_PYTEST_IN_A_SUBPROCESS)
        assert spawning == listed, (
            f"gates spawning pytest in a subprocess: {sorted(spawning)}, "
            f"but the scan lists {sorted(listed)}"
        )
        assert isinstance(acceptance, _Path)
