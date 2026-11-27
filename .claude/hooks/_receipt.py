"""The suite receipt — one schema, shared by the writer and the gate.

`H7` gave the commit gate a receipt: `tests/conftest.py` records what a pytest
invocation was, and `block-stale-commit.py` refuses a commit the suite cannot
vouch for. `H20` is the friction that came with it.

The first receipt held **one** record: the last pytest invocation of any kind.
Every acceptance script in this repository runs a narrowed pytest, so running
one gate overwrote the whole-suite evidence with `whole_suite: false` and the
next commit was refused. Measured twice while landing `H19`; the cost was a
3.5-minute re-run per gate. That is the gate H7's own row warns about — the one
whose routine use is expensive enough that it gets bypassed.

The fix follows from what the evidence actually is. **A narrowed run destroys
no evidence:** the whole suite did pass at time T, and a later one-file run
does not make that less true. So the receipt keeps two facts:

* the **latest run** of any kind — because a run that *failed* is a reason to
  refuse, whatever its scope, and
* the **latest whole-suite run** — the freshness evidence the gate compares
  against the newest tracked mtime.

Nothing is hidden and nothing is overwritten: a red whole-suite run is recorded
as red, not dropped, so it keeps refusing until a green one replaces it.

Why this module exists rather than the logic sitting in both callers: the
writer is in `tests/` and the reader is in `.claude/hooks/`, and a schema known
in two places is exactly the drift `H9` exists to stop. The roadmap row's
original proposal — give every acceptance script an `ORCSONAR_SUITE_RECEIPT`
pointing at a throwaway path — was rejected for the same reason: it spreads one
obligation across twenty scripts, and the twenty-first forgets it in silence.
The variable is still honoured (`receipt_path`), because the acceptance gates
need to point both ends at a crafted fixture.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

#: Where the receipt lives, relative to the project root.
DEFAULT_RELATIVE = "reports/last-suite.json"

#: The environment variable that redirects both writer and reader. Used by the
#: acceptance gates to exercise refusal paths against crafted receipts without
#: touching the real one.
ENV_VAR = "ORCSONAR_SUITE_RECEIPT"

#: Fields copied into the preserved whole-suite record. `at` and `exitstatus`
#: are the two the gate decides on; the rest are there so a refusal message can
#: say what the run was.
EVIDENCE_FIELDS = ("at", "exitstatus", "collected", "failed", "args")


def receipt_path(project_root: str | os.PathLike[str]) -> Path:
    """The receipt file both ends must agree on.

    Args:
        project_root: Repository root.

    Returns:
        The override from :data:`ENV_VAR` when set, else the default path under
        ``project_root``.
    """
    override = os.environ.get(ENV_VAR)
    if override:
        return Path(override)
    return Path(project_root) / DEFAULT_RELATIVE


def _evidence_from(record: dict[str, Any]) -> dict[str, Any]:
    """The whole-suite record distilled from a full run record."""
    return {key: record[key] for key in EVIDENCE_FIELDS if key in record}


def merge(previous: Any, current: dict[str, Any]) -> dict[str, Any]:
    """Combine the run that just finished with what the receipt already knew.

    Args:
        previous: The receipt's previous contents, or any junk — a receipt that
            could not be parsed must not stop the suite from writing a new one.
        current: This run's record, including a ``whole_suite`` flag.

    Returns:
        The record to write. ``last_whole_suite`` is present whenever a
        whole-suite run is known, either this one or one from before.
    """
    merged = dict(current)
    merged.pop("last_whole_suite", None)

    if current.get("whole_suite"):
        merged["last_whole_suite"] = _evidence_from(current)
        return merged

    kept = None
    if isinstance(previous, dict):
        nested = previous.get("last_whole_suite")
        if isinstance(nested, dict):
            kept = nested
        elif previous.get("whole_suite"):
            # A receipt written before H20 has no nested key: its top-level
            # record *is* the whole-suite evidence. Without this branch the
            # first narrowed run after the upgrade would throw away a result
            # that is still perfectly valid.
            kept = _evidence_from(previous)
    if kept is not None:
        merged["last_whole_suite"] = kept
    return merged


def whole_suite_evidence(receipt: Any) -> dict[str, Any] | None:
    """The most recent whole-suite run the receipt knows about.

    Args:
        receipt: Parsed receipt contents, or anything at all.

    Returns:
        The record, or ``None`` when no whole-suite run is recorded. ``None``
        means *not measured*, and the gate treats that as a refusal: unknown is
        not permission (invariant 2).
    """
    if not isinstance(receipt, dict):
        return None
    if receipt.get("whole_suite"):
        return {key: value for key, value in receipt.items() if key != "last_whole_suite"}
    nested = receipt.get("last_whole_suite")
    return nested if isinstance(nested, dict) else None
