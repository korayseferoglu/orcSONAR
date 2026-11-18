"""Unknown-signal handling in the Stage 4 merge (roadmap B2, AUDIT.md Bulgu-10).

`encode_reader` substituted `_NEUTRAL_SIGNAL = 0.0` whenever a BigWig read
failed or a cell line had no accession for a mark, and six modules reach that
constant. For every one of those sources less signal means lower risk, so a
dead source did not produce a neutral site — it produced one that scores
**safe**. A completely broken source yields plausible output instead of an
error, which is why it survived four runs.

The property these tests pin is invariant 2: absence of data must never lower
the risk. Concretely, for the merged epigenetic score:

    score(channel unknown)  >  score(channel measured as 0.0)

and an unknown channel must not drag the score down at all — it is excluded and
the remaining weights are renormalised, so a site measured at level `v` on
every available channel scores `v` whether or not some channel is missing.

Deciding *whether a score may be produced at all* when too much is unknown is
roadmap `B3` (coverage threshold). B2's job is only to make "not measured"
distinguishable from "measured zero", and these tests do not encode any
threshold.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.stage4_epigenetic.epigenetic_merger import _compute_normalized, _normalize_signal

#: Mid-range raw values, one per channel, chosen so each normalises to 0.5
#: against its own saturation constant. That makes the weighted sum exactly 0.5
#: and keeps these tests about direction rather than calibration.
_HALF = {
    "atac": 25.0,
    "h3k4me3": 10.0,
    "h3k27ac": 10.0,
    "groseq": 5.0,
    "hic": 0.5,
    "ccle": 4.0,
}


def test_all_channels_at_half_score_half() -> None:
    """The baseline the other tests compare against."""
    assert _compute_normalized(**_HALF) == 0.5


def test_an_unknown_channel_is_not_treated_as_zero() -> None:
    """The invariant-2 property, stated as an inequality.

    A channel that could not be read must score strictly higher than the same
    channel measured as genuinely silent. Anything else means a failed source
    makes a site look safer than a real measurement would.
    """
    unknown = _compute_normalized(**{**_HALF, "atac": None})
    measured_zero = _compute_normalized(**{**_HALF, "atac": 0.0})
    assert unknown > measured_zero, (
        f"unknown ATAC ({unknown}) is not riskier than ATAC measured at zero "
        f"({measured_zero}) — a dead source still reads as safe"
    )


def test_an_unknown_channel_does_not_drag_the_score_down() -> None:
    """Exclude and renormalise, rather than contribute a zero.

    ATAC carries weight 0.25. Contributing zero would pull a 0.5 site to 0.375;
    excluding it leaves the site at 0.5, which is what the channels that *were*
    measured actually say.
    """
    assert _compute_normalized(**{**_HALF, "atac": None}) == 0.5


def test_every_channel_behaves_the_same_way_when_unknown() -> None:
    """Six modules reach the old constant; none of them may be the exception."""
    for channel in _HALF:
        unknown = _compute_normalized(**{**_HALF, channel: None})
        zero = _compute_normalized(**{**_HALF, channel: 0.0})
        assert unknown > zero, f"{channel}: unknown ({unknown}) not riskier than zero ({zero})"
        assert unknown == 0.5, f"{channel}: unknown dragged the score to {unknown}"


def test_a_measured_zero_still_lowers_the_score() -> None:
    """The fix must not erase real information.

    A locus the assay genuinely found silent is evidence, and it has to keep
    counting. Treating measured zeros as unknown would be the opposite error.
    """
    assert _compute_normalized(**{**_HALF, "atac": 0.0}) < 0.5


def test_no_channel_measured_yields_no_score() -> None:
    """With nothing measured there is nothing to average, so there is no number.

    Returning 0.0 here would be the original bug in its purest form, and
    returning 0.5 would be a number nobody measured.
    """
    nothing = dict.fromkeys(_HALF)
    assert _compute_normalized(**nothing) is None


def test_normalise_refuses_to_turn_unknown_into_a_number() -> None:
    """The lowest level: the helper must propagate the unknown, not absorb it."""
    assert _normalize_signal(None, 50.0) is None


def test_the_merged_json_carries_null_not_zero(tmp_path: Path) -> None:
    """End to end: an unknown raw signal must reach the JSON as `null`.

    `verify-run` check 4 counts raw zeros to estimate how much of a run is
    fallback rather than data. While an unknown is written as 0.0 that count
    cannot distinguish a dead source from a silent locus (roadmap `B3` builds
    on this).
    """
    from src.stage4_epigenetic.epigenetic_merger import run

    site = "VEGFA:ENST1:chr6:100"
    paths = {}
    for name, payload in {
        "atac": {"atac_signals": {site: None}},
        "histones": {
            "h3k4me3_signals": {site: 10.0},
            "h3k27ac_signals": {site: 10.0},
        },
        "groseq": {"groseq_signals": {site: 5.0}},
        "hic": {"hic_contacts": {site: 0.5}},
        # CCLE is keyed by GENE, not site id, and the field is `expression_value`.
        "ccle": {"ccle_results": {"VEGFA": {"expression_value": 4.0}}},
    }.items():
        p = tmp_path / f"{name}.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        paths[name] = str(p)

    out = tmp_path / "stage4.json"
    run(
        paths["atac"],
        paths["histones"],
        paths["groseq"],
        paths["hic"],
        paths["ccle"],
        str(out),
        str(tmp_path / "log.txt"),
    )
    merged = json.loads(out.read_text(encoding="utf-8"))
    record = next(iter(merged["epigenetic_scores"].values()))
    assert record["atac_signal"] is None, f"unknown ATAC written as {record['atac_signal']!r}"
