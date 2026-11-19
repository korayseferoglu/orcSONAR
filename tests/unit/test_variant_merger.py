"""Sign tests for the Stage 3 variant-toxicity merge (roadmap B4).

`gnomad_client` emits a field called `polymorphism_score`, but its own
docstring defines the value as a **risk** score:

    "High AF common variants -> polymorphic -> off-target risk is LOWER ->
     score approaches 0.  No variants -> conserved -> score = 1.0"
    (and, for the empty case: "no data -> assume conserved -> high risk")

So 1.0 means conserved and risky, 0.0 means polymorphic and tolerable. The
merger trusted the field *name* instead of that contract and inverted it, which
turned a conserved site into a zero-risk site and a polymorphic site into a
maximum-risk one.

Nothing tested this merger before — the `run()` adapters and mergers sit at 0%
coverage (AUDIT.md Bulgu-3), which is why a straight sign inversion survived in
a scored channel with a 0.20 weight.

These tests are about direction, not calibration. They say which way the number
has to move, and no threshold here is tuned to make anything pass.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.stage3_variant_tox.variant_merger import _normalize

#: Everything except gnomAD held at "no signal", so the comparisons isolate it.
_QUIET_COSMIC: dict[str, Any] = {"density_score": 0.0, "has_tier1_gene": False}
_QUIET_CLINVAR: dict[str, Any] = {"pathogenic_count": 0, "likely_pathogenic_count": 0}
_QUIET_PHYLOP: dict[str, Any] = {"conservation_score": 0.0}


def score_for(gnomad: dict[str, Any]) -> float:
    """Variant-toxicity score with gnomAD as the only moving input."""
    return _normalize(_QUIET_COSMIC, gnomad, _QUIET_CLINVAR, _QUIET_PHYLOP)


def test_a_conserved_region_scores_riskier_than_a_polymorphic_one() -> None:
    """B4's acceptance criterion, in one assertion.

    A region with no common population variation is under selection: a guide
    that binds there disrupts something that matters. A region already carrying
    a common variant is tolerated in the population.
    """
    conserved = score_for({"polymorphism_score": 1.0})
    polymorphic = score_for({"polymorphism_score": 0.0})
    assert conserved > polymorphic, (
        f"conserved={conserved} is not riskier than polymorphic={polymorphic} — "
        "the gnomAD channel is pointing the wrong way"
    )


def test_risk_rises_monotonically_with_the_producer_score() -> None:
    """Not just the endpoints: the whole channel must not be reversed."""
    scores = [score_for({"polymorphism_score": value}) for value in (0.0, 0.25, 0.5, 0.75, 1.0)]
    assert scores == sorted(scores), f"not monotonic in the risk direction: {scores}"
    assert scores[0] < scores[-1], "the channel carries no information"


def test_the_channel_moves_the_score_at_all() -> None:
    """A weight of 0.20 that never moves the output is a dead channel."""
    assert score_for({"polymorphism_score": 1.0}) != score_for({"polymorphism_score": 0.0})


def test_a_missing_gnomad_field_does_not_look_safe() -> None:
    """Invariant 2: absent data must never make a site look safer.

    The merger defaults the field to 1.0. Under the correct sign that is the
    conserved, risky end — which is the right direction to fail in. Under the
    inverted sign it was 0.0 risk, so a site with no gnomAD data read as
    perfectly safe.
    """
    missing = score_for({})
    polymorphic = score_for({"polymorphism_score": 0.0})
    assert missing >= polymorphic, (
        f"missing gnomAD data ({missing}) scores safer than a tolerated "
        f"polymorphic site ({polymorphic})"
    )


def test_the_error_path_neutral_lands_between_the_extremes() -> None:
    """`gnomad_client` returns 0.5 when a query fails unrecoverably.

    That is a neutral in *risk* space, so it has to sit between the two ends
    rather than at one of them. It is still a number standing in for "unknown"
    — roadmap `B2` replaces it with an explicit unknown type.
    """
    neutral = score_for({"polymorphism_score": 0.5})
    assert score_for({"polymorphism_score": 0.0}) < neutral < score_for({"polymorphism_score": 1.0})


class TestUnknownChannelsAreExcluded:
    """Two of the four domain mergers never learned B2's sentinel.

    Audit 2026-11-19, Bulgu 2. B2's acceptance criterion reads globally — "no
    fallback path returns a numeric risk value" — but the work stopped at
    stage 4 and stage 6. Here cosmic defaulted to 0.0 and clinvar to 0.0, both
    the *safe* end, so a source that failed made a site look cleaner than one
    that was actually measured.

    Note on scope: excluding an unknown and renormalising the rest is the
    estimator B2 chose for the other two mergers, and the audit's statistical
    review flags that choice as pre-empting roadmap B3. Matching it here is
    deliberate — four mergers disagreeing is worse than one contested
    estimator, and B3 can then change one rule in one place.
    """

    def test_an_unknown_channel_does_not_lower_the_score(self) -> None:
        full = _normalize(
            {"density_score": 0.8},
            {"polymorphism_score": 0.8},
            {"pathogenic_count": 1},
            {"conservation_score": 0.8},
        )
        without_cosmic = _normalize(
            {}, {"polymorphism_score": 0.8}, {"pathogenic_count": 1}, {"conservation_score": 0.8}
        )
        assert without_cosmic is not None and full is not None
        assert without_cosmic >= full, (
            "dropping a high-risk channel lowered the score — the unknown was "
            "counted as a measured zero"
        )

    def test_nothing_measured_yields_no_score(self) -> None:
        assert _normalize({}, {}, {}, {}) is None

    def test_everything_measured_is_unchanged(self) -> None:
        """Weights sum to 1.0, so full coverage must give the old answer."""
        score = _normalize(
            {"density_score": 0.4},
            {"polymorphism_score": 0.6},
            {"pathogenic_count": 0, "likely_pathogenic_count": 0},
            {"conservation_score": 0.2},
        )
        expected = 0.30 * 0.4 + 0.20 * 0.6 + 0.25 * 0.0 + 0.25 * 0.2
        assert score == pytest.approx(round(expected, 4))
