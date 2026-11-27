"""The ΔG thresholds are gone, and no number replaced them.

Roadmap C3d. `C3` was closed as a negative result on the grounds that "the
literature offers no transportable per-site ΔG threshold". The physics fix it
made stands. The grounds were wrong: the search had covered only the siRNA
*design* / Ui-Tei family, and per-site scoring functions exist — RIsearch2
(Alkan et al., NAR 2017, PMID 28108657), which combines interaction energy
with site accessibility and transcript abundance, and PITA's
`ddG = ΔG_duplex − ΔG_open` (Kertesz et al. 2007, PMID 17893677).

What the literature does *not* offer is a threshold, and it does not offer one
on purpose. PITA says so in as many words — "our model employs no such
parameters or thresholds" — TargetScan's context++ is a percentile-scaled
regression, Lu & Mathews use continuous SVM features. The two published
cutoffs (Shao 2007's ΔG_disruption > −10 / < −19; RNAxs's P_u ≥ 0.01157) are
**accessibility** quantities fitted to labelled data, not duplex energies, so
they do not transport.

Three findings make keeping the old mapping worse than removing it:

* **the sign is inverted over half the duplex.** Kamola et al. 2015 (PLoS
  Comput Biol, PMID 26657993 — Ui-Tei's own group): "siRNA with high GC
  content in the non-seed region have 'weaker' off-target effects", and on the
  target side "the high GC contents in the off-target sequences corresponding
  to siRNA positions 8-15 reduces the potency of off-target effects"
  (r = 0.23, p = 1.2e-13; r = 0.17, p = 9.3e-07). A monotone
  "more negative ⇒ riskier" score has the sign backwards for positions 8-20.
* **the calculation itself is contested.** Same paper: "the currently
  established calculation procedure of thermodynamic profiles is not
  applicable for such discontinuous duplexes" — which is why they switched to
  GC content. That is a published objection to summing a Turner
  nearest-neighbour energy over a mismatched 20-nt duplex as if it were a
  contiguous helix.
* **a bare duplex ΔG is the one configuration repeatedly measured to carry no
  information.** Tafer 2008 found duplex energy added nothing over
  accessibility plus asymmetry; Kertesz found ΔG_duplex alone was noise
  (r = 0.36, p < 0.11) until the opening cost was subtracted; MIRZA-G found
  the unpaired probability beat RNAup's opening energy.

So this item deletes the thresholds and does **not** substitute a new mapping.
The raw per-site ΔG stays, recorded in native units as rule 10 allows. The
derived [0, 1] contribution becomes *unknown*, because any mapping chosen now
would be an unregistered modelling decision made after seeing the data — the
thing invariant 6 and `A10` exist to prevent. The merger already excludes an
unknown channel and renormalises (`B2`), so honesty costs nothing mechanically.
Building the accessibility term is `C3e`.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CALC = ROOT / "src" / "stage5_biophysics" / "delta_g_calculator.py"
MERGER = ROOT / "src" / "stage5_biophysics" / "biophysics_merger.py"
CONFIG = ROOT / "config" / "config.yaml"
SMK = ROOT / "rules" / "stage5_biophysics.smk"


class TestNoThresholdSurvivesAnywhere:
    """Three copies existed, with different constants. All three go."""

    def test_config_no_longer_declares_them(self) -> None:
        raw = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        assert "delta_g_strong" not in raw
        assert "delta_g_moderate" not in raw

    def test_config_model_no_longer_declares_them(self) -> None:
        from src.core.config import OrcSonarConfig

        assert "delta_g_strong" not in OrcSonarConfig.model_fields
        assert "delta_g_moderate" not in OrcSonarConfig.model_fields

    def test_the_snakemake_rule_no_longer_passes_them(self) -> None:
        text = SMK.read_text(encoding="utf-8")
        assert "dg_strong" not in text
        assert "dg_moderate" not in text

    def test_the_calculator_has_no_threshold_mapping(self) -> None:
        text = CALC.read_text(encoding="utf-8")
        assert "_dg_to_risk_score" not in text
        # The module-level copies were dead as well as wrong.
        assert "_DG_STRONG" not in text
        assert "_DG_MODERATE" not in text
        assert "_DG_NEUTRAL" not in text

    def test_the_merger_has_no_threshold_mapping(self) -> None:
        text = MERGER.read_text(encoding="utf-8")
        assert "_delta_g_risk" not in text
        assert "_DG_REFERENCE" not in text
        assert "_DG_STRONG" not in text


class TestTheRawEnergyIsKeptAndTheScoreIsUnknown:
    def test_calculator_still_emits_the_raw_per_site_energy(self) -> None:
        """Deleting the mapping must not delete the measurement."""
        text = CALC.read_text(encoding="utf-8")
        assert '"delta_g"' in text
        assert "calculate_duplex_dg" in text

    def test_calculator_emits_no_risk_score_number(self) -> None:
        """The field stays, its value is always null.

        Written as a direct assertion rather than a negative-lookahead regex:
        the first version was `r'"risk_score":\\s*(?!None)'`, which matches
        `"risk_score": None` anyway — `\\s*` backtracks to zero characters and
        the lookahead is then evaluated at the space. A test whose pattern can
        fire on the string it is meant to accept is the H19 lesson in
        miniature.
        """
        text = CALC.read_text(encoding="utf-8")
        assignments = re.findall(r'"risk_score":\s*([^,\n]+)', text)
        assert assignments, "the risk_score field disappeared entirely"
        assert set(assignments) == {"None"}, (
            f"the calculator still writes a derived risk number: {assignments}"
        )

    def test_merger_treats_delta_g_as_unmeasured_for_now(self) -> None:
        from src.stage5_biophysics.biophysics_merger import _normalize

        # ΔG known, everything else unknown → no channel is scorable yet, so
        # the domain score must be unknown rather than derived from ΔG alone.
        assert (
            _normalize(
                delta_g=-30.0,
                shape_acc=None,
                m6a_score=None,
                adar_score=None,
                g4_risk=None,
            )
            is None
        )

    def test_a_measured_channel_still_scores(self) -> None:
        """The control: renormalisation is not broken, ΔG is just abstaining."""
        from src.stage5_biophysics.biophysics_merger import _normalize

        score = _normalize(
            delta_g=-30.0,
            shape_acc=0.8,
            m6a_score=None,
            adar_score=None,
            g4_risk=None,
        )
        assert score == 0.8

    def test_delta_g_cannot_change_the_score(self) -> None:
        """The property that makes the abstention real rather than nominal."""
        from src.stage5_biophysics.biophysics_merger import _normalize

        kwargs = {
            "shape_acc": 0.4,
            "m6a_score": 0.6,
            "adar_score": None,
            "g4_risk": None,
        }
        assert _normalize(delta_g=-43.8, **kwargs) == _normalize(
            delta_g=-7.1, **kwargs
        ) == _normalize(delta_g=None, **kwargs)


class TestTheReasonIsWrittenWhereSomeoneWouldReAddIt:
    """A deleted constant comes back unless the deletion explains itself."""

    def test_the_calculator_cites_the_objection(self) -> None:
        text = CALC.read_text(encoding="utf-8")
        assert "26657993" in text, "Kamola 2015 not cited where the mapping was"
        assert "discontinuous" in text

    def test_the_merger_points_at_the_successor_item(self) -> None:
        text = MERGER.read_text(encoding="utf-8")
        assert "C3e" in text
        assert "28108657" in text, "RIsearch2 not cited as the intended successor"
