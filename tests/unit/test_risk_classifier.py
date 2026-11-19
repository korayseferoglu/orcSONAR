"""Unit tests for Stage 7 risk classification.

This module had no tests at all — it is part of the ``run()`` adapter layer
that Snakemake actually calls and that AUDIT.md's Bulgu-3 measures at 0%
coverage.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.scoring.risk_classifier import run as risk_classifier_run

_THRESHOLDS = {"safe": 0.3, "warning": 0.6, "high_risk": 0.8}


def _write_scores(path: Path, domain_scores: dict[str, dict[str, float]]) -> None:
    path.write_text(
        json.dumps(
            {
                "domain_scores": domain_scores,
                "base_scores": {},
                "cell_context": {},
                "weights": {},
            }
        ),
        encoding="utf-8",
    )


class TestNothingClassifiedIsNotSafe:
    """Classifying nothing must not produce a verdict of SAFE.

    Audit 2026-11-19, Bulgu 12. ``worst_class`` was initialised to
    ``RiskClass.SAFE`` and emitted even when the loop body never ran, so a run
    with zero sites reported ``risk=SAFE (0.0000)``. That conflates "we
    classified the sites and the worst was SAFE" with "there was nothing to
    classify" — and the second is not a statement about the saRNA at all.

    R0.1a closed the outage that produced zero sites upstream, but the
    conflation here is independent of how the zero arose, so it is pinned
    separately.
    """

    def test_zero_sites_does_not_claim_safe(self, tmp_path: Path) -> None:
        scores = tmp_path / "stage7_scores.json"
        out = tmp_path / "stage7_classification.json"
        _write_scores(scores, {})

        risk_classifier_run(
            scores_path=str(scores),
            thresholds=_THRESHOLDS,
            output_path=str(out),
            log_path=str(tmp_path / "rc.log"),
        )

        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["overall_risk_class"] != "SAFE", (
            "a run that classified nothing reported SAFE — absence of sites is "
            "not evidence of safety (invariant 2)"
        )
        assert payload["overall_risk_class"] is None
        assert payload["overall_risk_score"] is None

    def test_a_real_site_still_classifies_normally(self, tmp_path: Path) -> None:
        """The guard must not disturb the ordinary path."""
        scores = tmp_path / "stage7_scores.json"
        out = tmp_path / "stage7_classification.json"
        _write_scores(
            scores,
            {
                "GENE:ENST1:chr1:100": {
                    "sequence_specificity": 0.1,
                    "variant_toxicity": 0.1,
                    "biophysics_structure": 0.1,
                    "epigenetic_context": 0.1,
                    "execution_safety": 0.1,
                }
            },
        )

        risk_classifier_run(
            scores_path=str(scores),
            thresholds=_THRESHOLDS,
            output_path=str(out),
            log_path=str(tmp_path / "rc.log"),
        )

        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["overall_risk_class"] in ("SAFE", "WARNING", "HIGH_RISK", "DANGEROUS")
        assert isinstance(payload["overall_risk_score"], float)
        assert len(payload["site_classifications"]) == 1
