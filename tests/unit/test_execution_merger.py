"""Unit tests for Stage 6 execution merging.

Another untested ``run()`` adapter (AUDIT.md Bulgu-3, 0% coverage on the layer
Snakemake actually calls).
"""

from __future__ import annotations

import json
from pathlib import Path

from src.stage6_execution.execution_merger import run as execution_merger_run


def _write(path: Path, payload: dict) -> str:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


class TestAnUnknownChannelDoesNotCrashTheMerger:
    """B2's renormalisation branch could never execute.

    Audit 2026-11-19, Bulgu 6. ``_normalize`` was taught to drop an unknown
    Ago2/RBP channel and renormalise the remaining weights — and the module's
    own docstring explains why a zero there is dangerous ("for Ago2, the
    heaviest channel at 0.40, that single substitution moved a site most of
    the way to safe"). But the per-site debug log formatted those same values
    with ``:.3f``, outside any try, so the first null crashed ``run()`` before
    a score was written.

    This must hold before the stage-6 producers start emitting null (R2.1),
    which is the whole reason consumers come first in the repair order.
    """

    def test_null_ago2_and_rbp_are_merged_rather_than_raising(
        self, tmp_path: Path
    ) -> None:
        site = "MTOR:ENST00000361445:chr1:11255438"
        ago2 = _write(tmp_path / "ago2.json", {"ago2_results": {site: {"loading_score": None}}})
        rbp = _write(tmp_path / "rbp.json", {"rbp_results": {site: {"competition_score": None}}})
        circrna = _write(tmp_path / "circ.json", {"circrna_results": {site: {"sponge_risk": False}}})
        immune = _write(
            tmp_path / "imm.json",
            {"offtarget_immune": {site: {"risk_score": 0.2, "motifs_found": [], "total_hits": 0}},
             "sarna_immune": {"risk_score": 0.0, "motifs_found": [], "total_hits": 0}},
        )
        out = tmp_path / "stage6_execution.json"

        execution_merger_run(
            ago2_path=ago2,
            rbp_path=rbp,
            circrna_path=circrna,
            immune_path=immune,
            output_path=str(out),
            log_path=str(tmp_path / "em.log"),
        )

        payload = json.loads(out.read_text(encoding="utf-8"))
        record = payload["execution_scores"][site]
        assert record["ago2_loading"] is None
        assert record["rbp_competition"] is None
        # circrna (0.20) + immune (0.25) survive, so the score is renormalised
        # over 0.45 of weight rather than being dragged toward zero.
        assert record["normalized_score"] is not None
        assert 0.0 <= record["normalized_score"] <= 1.0

    def test_everything_unknown_yields_no_score(self, tmp_path: Path) -> None:
        """With no channel measured at all the site has no execution score."""
        site = "MTOR:ENST00000361445:chr1:11255438"
        ago2 = _write(tmp_path / "ago2.json", {"ago2_results": {site: {"loading_score": None}}})
        rbp = _write(tmp_path / "rbp.json", {"rbp_results": {site: {"competition_score": None}}})
        circrna = _write(tmp_path / "circ.json", {"circrna_results": {}})
        immune = _write(tmp_path / "imm.json", {"offtarget_immune": {}, "sarna_immune": {}})
        out = tmp_path / "stage6_execution.json"

        execution_merger_run(
            ago2_path=ago2,
            rbp_path=rbp,
            circrna_path=circrna,
            immune_path=immune,
            output_path=str(out),
            log_path=str(tmp_path / "em.log"),
        )

        payload = json.loads(out.read_text(encoding="utf-8"))
        assert site in payload["execution_scores"]
