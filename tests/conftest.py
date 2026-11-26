"""Shared pytest fixtures for orcSONAR test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.models import GenomicRegion, SarnaInput


@pytest.fixture
def sample_region() -> GenomicRegion:
    """A canonical VEGFA promoter-proximal region on chr6."""
    return GenomicRegion(chrom="chr6", start=43768652, end=43769652, strand="+")


@pytest.fixture
def sample_sarna_input() -> SarnaInput:
    """Default proof-of-concept saRNA targeting VEGFA in HeLa."""
    return SarnaInput(
        sequence="GCAACCATAGCCTCGGCCGC",
        target_gene="VEGFA",
        cell_line="HeLa",
    )


@pytest.fixture
def tmp_cache_db(tmp_path: Path) -> Path:
    """Temporary SQLite cache database path."""
    return tmp_path / "test_cache.db"


@pytest.fixture
def tmp_config_yaml(tmp_path: Path) -> Path:
    """Write a minimal valid config.yaml to a temp file."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "target_gene: VEGFA\n"
        "cell_line: HeLa\n"
        "sarna_sequence: GCAACCATAGCCTCGGCCGC\n",
        encoding="utf-8",
    )
    return cfg


# ---------------------------------------------------------------------------
# Suite receipt for the commit gate (roadmap H7)
# ---------------------------------------------------------------------------
#
# The commit gate must measure **freshness**, not run the suite: the full run
# takes ~3.7 minutes and a gate that adds that to every commit gets bypassed
# (H7's own row says so). Freshness needs a marker, and inferring one from
# `.coverage` does not work — measured: a single-file run still reports all 73
# `src/` files as measured, because `--cov=src` instruments the package whether
# the tests import it or not. So the suite writes its own receipt instead of
# the gate guessing from a side effect.


def pytest_sessionfinish(session, exitstatus) -> None:  # type: ignore[no-untyped-def]
    """Record what this run actually was, for `block-stale-commit.py`.

    `selected` matters as much as `exitstatus`: a green run of one test file is
    not evidence about the suite, and without recording the invocation's scope
    the gate could be satisfied by the fastest test in the repository.

    Args:
        session: The pytest session.
        exitstatus: Process exit status pytest will return.
    """
    import json
    import time
    from pathlib import Path as _Path

    try:
        config = session.config
        root = _Path(str(config.rootpath))
        testpaths = list(config.getini("testpaths") or [])
        args = [str(a) for a in config.args]
        # A whole-suite run is one whose args are exactly the configured
        # testpaths (or their absolute form), with no -k/-m narrowing.
        normalised = {
            str(_Path(a).resolve()) for a in args
        }
        expected = {str((root / p).resolve()) for p in testpaths}
        whole_suite = bool(expected) and normalised == expected
        if config.getoption("keyword", default="") or config.getoption(
            "markexpr", default=""
        ):
            whole_suite = False

        receipt = {
            "at": time.time(),
            "exitstatus": int(exitstatus),
            "whole_suite": whole_suite,
            "args": args,
            "collected": getattr(session, "testscollected", None),
            "failed": getattr(session, "testsfailed", None),
        }
        out = root / "reports" / "last-suite.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    except Exception:  # noqa: BLE001
        # A receipt that cannot be written must not fail the suite. The gate
        # treats a missing or stale receipt as "not run", which is the safe
        # direction (invariant 2).
        pass
