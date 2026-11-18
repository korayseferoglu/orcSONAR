"""Tests for the verify-run audit script's fallback accounting.

The script had no tests at all, which is how a constant inside it went false
without anyone noticing. `SENTINEL_RAW = 0.0` was commented "what the code
really writes", and that was true until roadmap B2 replaced the numeric
fallback with an explicit unknown. After B2 a raw `0.0` is a **measured**
zero and the thing worth counting is `null` — which the script dropped before
counting, because its numeric filter skips non-numbers.

Net effect, in the dangerous direction: the audit tool's fallback rate would
fall after B2 and read as an improvement that never happened. An audit tool
that silently stops measuring the thing it was built to measure is worse than
no audit tool, so these tests pin the accounting.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".claude" / "skills" / "verify-run" / "scripts" / "verify_run.py"

_spec = importlib.util.spec_from_file_location("verify_run", SCRIPT)
assert _spec is not None and _spec.loader is not None
verify_run = importlib.util.module_from_spec(_spec)
sys.modules["verify_run"] = verify_run
_spec.loader.exec_module(verify_run)

#: The one table the script treats as raw-signal space.
TABLE = "stage4_epigenetic.json:epigenetic_scores"


def tables_with(values: list[Any], field: str = "atac_signal") -> dict[str, Any]:
    """One raw-signal table carrying the given per-site values."""
    return {TABLE: {f"GENE:ENST1:chr1:{i}": {field: v} for i, v in enumerate(values)}}


def findings_by_space(findings: list[dict], space: str) -> list[dict]:
    """The findings recorded in one value space."""
    return [f for f in findings if f.get("space") == space]


def test_unmeasured_values_are_counted(verify_run_module: Any = verify_run) -> None:
    """A `null` raw signal is the post-B2 "not measured", and it must be seen."""
    _, _, findings = verify_run_module.check_fallback(tables_with([None, None, None, 12.0]))
    unknown = findings_by_space(findings, "unknown")
    assert unknown, f"nulls were not counted at all: {findings}"
    assert unknown[0]["hits"] == 3
    assert unknown[0]["of"] == 4, "the denominator must be every site carrying the field"


def test_unmeasured_values_are_attributable(verify_run_module: Any = verify_run) -> None:
    """Unlike a raw 0.0, a null says plainly that nothing was measured.

    That is the whole point of B2: this count needs no provenance field to be
    interpreted, so it must not be reported with the "cannot attribute" caveat
    that a 0.0 carries.
    """
    _, _, findings = verify_run_module.check_fallback(tables_with([None, 5.0]))
    assert findings_by_space(findings, "unknown")[0]["attributable"] is True


def test_a_measured_zero_is_no_longer_called_a_sentinel(verify_run_module: Any = verify_run) -> None:
    """After B2, 0.0 in a raw field means the assay found nothing there.

    It is still reported — a column of zeros is worth a human look, and runs
    produced before B2 carry 0.0 as their fallback — but the output must not
    assert it is `_NEUTRAL_SIGNAL`, a constant that no longer exists.
    """
    _, lines, findings = verify_run_module.check_fallback(tables_with([0.0, 0.0, 7.0]))
    raw = findings_by_space(findings, "raw")
    assert raw, "zeros should still be reported"
    assert raw[0]["attributable"] is False, "0.0 alone still cannot be attributed"
    text = "\n".join(lines)
    assert "_NEUTRAL_SIGNAL" not in text, text


def test_all_measured_reports_nothing(verify_run_module: Any = verify_run) -> None:
    """The clean case must stay clean, or the check cries wolf."""
    ok, lines, findings = verify_run_module.check_fallback(tables_with([1.0, 2.0, 3.0]))
    assert findings == []
    assert ok
    assert any("measured data" in line for line in lines)


def test_the_stale_sentinel_comment_is_gone() -> None:
    """The constant's own comment claimed it was what production writes.

    It is not, since B2. A false claim inside the audit tool is the failure
    this repository keeps hitting, so it is pinned here rather than left to a
    future reader to notice.
    """
    text = SCRIPT.read_text(encoding="utf-8")
    assert "_NEUTRAL_SIGNAL: what the code really writes" not in text
