"""Unit tests for src/scoring/ — Stage 7 domain normalisation, integrator, classifier."""

from __future__ import annotations

import math

import pytest

from src.core.config import RiskThresholds, ScoringWeights
from src.core.models import (
    AdarRiskResult,
    Ago2Result,
    CircRNAResult,
    ClinvarResult,
    ClinvarVariant,
    CosmicResult,
    DomainScores,
    G4Result,
    GenomicRegion,
    GnomadResult,
    ImmuneResult,
    M6AResult,
    MirbaseResult,
    OffTargetSite,
    PhylopResult,
    RBPResult,
    RepeatResult,
    ShapeResult,
    ThermoResult,
)
from src.scoring.classifier import RiskClass, classify, get_recommendation
from src.scoring.domain_scores import (
    normalize_biophysics_score,
    normalize_epigenetic_score,
    normalize_execution_score,
    normalize_sequence_score,
    normalize_variant_score,
)
from src.scoring.integrator import ScoreIntegrator, _validate_weights

# ---------------------------------------------------------------------------
# Shared test fixtures / factories
# ---------------------------------------------------------------------------

_REGION = GenomicRegion(chrom="chr1", start=1000, end=1100, strand="+")


def _offtarget(match_type: str = "perfect") -> OffTargetSite:
    return OffTargetSite(
        gene="FAKE",
        transcript_id="ENST00000000001",
        region=_REGION,
        seed_match_type=match_type,  # type: ignore[arg-type]
        mismatches=0,
        alignment_score=1.0,
    )


def _mirbase(max_score: float = 0.0, risk: str = "SAFE") -> MirbaseResult:
    return MirbaseResult(
        sarna_seed="GCAGCAU",
        max_overlap_score=max_score,
        risk_level=risk,  # type: ignore[arg-type]
    )


def _repeat(adar: float = 0.0) -> RepeatResult:
    return RepeatResult(region=_REGION, adar_risk_score=adar)


def _cosmic(density: float = 0.0, tier1: bool = False) -> CosmicResult:
    return CosmicResult(region=_REGION, density_score=density, has_tier1_gene=tier1)


def _gnomad(max_af: float = 0.0) -> GnomadResult:
    return GnomadResult(region=_REGION, max_af=max_af)


def _clinvar(pathogenic: int = 0, likely: int = 0) -> ClinvarResult:
    return ClinvarResult(
        region=_REGION,
        pathogenic_count=pathogenic,
        likely_pathogenic_count=likely,
    )


def _phylop(conservation: float = 0.5) -> PhylopResult:
    return PhylopResult(region=_REGION, conservation_score=conservation)


def _thermo(delta_g: float = -10.0) -> ThermoResult:
    return ThermoResult(delta_g=delta_g)


def _shape(access: float = 0.5, available: bool = True) -> ShapeResult:
    return ShapeResult(
        region=_REGION,
        accessibility_score=access,
        data_available=available,
    )


def _m6a(score: float = 0.0) -> M6AResult:
    return M6AResult(region=_REGION, cell_line="HeLa", m6a_score=score)


def _adar(score: float = 0.0) -> AdarRiskResult:
    return AdarRiskResult(region=_REGION, adar_score=score)


def _g4(risk: float = 0.0) -> G4Result:
    return G4Result(risk_score=risk)


def _ago2(loading: float = 0.0, loaded: bool = False) -> Ago2Result:
    return Ago2Result(
        region=_REGION, cell_line="HeLa", loading_score=loading, is_loaded=loaded
    )


def _rbp(comp: float = 0.0) -> RBPResult:
    return RBPResult(region=_REGION, cell_line="HeLa", competition_score=comp)


def _circrna(sponge: bool = False, count: int = 0, avail: bool = True) -> CircRNAResult:
    return CircRNAResult(
        region=_REGION,
        sponge_risk=sponge,
        overlap_count=count,
        data_available=avail,
    )


def _immune(risk: float = 0.0, level: str = "SAFE") -> ImmuneResult:
    return ImmuneResult(risk_score=risk, risk_level=level)


def _domain(
    seq: float = 0.0,
    var: float = 0.0,
    epi: float = 0.0,
    bio: float = 0.0,
    exc: float = 0.0,
) -> DomainScores:
    return DomainScores(
        sequence_specificity=seq,
        variant_toxicity=var,
        epigenetic_context=epi,
        biophysics_structure=bio,
        execution_safety=exc,
    )


DEFAULT_WEIGHTS: dict[str, float] = {
    "sequence_specificity": 0.20,
    "variant_toxicity": 0.15,
    "epigenetic_context": 0.20,
    "biophysics_structure": 0.25,
    "execution_safety": 0.20,
}


# ===========================================================================
# classifier.py
# ===========================================================================


class TestRiskClassEnum:
    def test_all_values_present(self) -> None:
        values = {rc.value for rc in RiskClass}
        assert values == {"SAFE", "WARNING", "HIGH_RISK", "DANGEROUS"}

    def test_str_subclass(self) -> None:
        assert isinstance(RiskClass.SAFE, str)
        assert RiskClass.SAFE == "SAFE"


class TestClassify:
    def test_zero_is_safe(self) -> None:
        assert classify(0.0) == RiskClass.SAFE

    def test_below_safe_threshold(self) -> None:
        assert classify(0.29) == RiskClass.SAFE

    def test_at_safe_threshold_is_warning(self) -> None:
        assert classify(0.30) == RiskClass.WARNING

    def test_warning_midpoint(self) -> None:
        assert classify(0.45) == RiskClass.WARNING

    def test_at_warning_threshold_is_high_risk(self) -> None:
        assert classify(0.60) == RiskClass.HIGH_RISK

    def test_high_risk_midpoint(self) -> None:
        assert classify(0.70) == RiskClass.HIGH_RISK

    def test_at_high_risk_threshold_is_dangerous(self) -> None:
        assert classify(0.80) == RiskClass.DANGEROUS

    def test_one_is_dangerous(self) -> None:
        assert classify(1.0) == RiskClass.DANGEROUS

    def test_score_clamped_below_zero(self) -> None:
        assert classify(-0.5) == RiskClass.SAFE

    def test_score_clamped_above_one(self) -> None:
        assert classify(1.5) == RiskClass.DANGEROUS

    def test_custom_thresholds(self) -> None:
        t = RiskThresholds(safe=0.5, warning=0.7, high_risk=0.9)
        assert classify(0.4, t) == RiskClass.SAFE
        assert classify(0.6, t) == RiskClass.WARNING
        assert classify(0.8, t) == RiskClass.HIGH_RISK
        assert classify(0.95, t) == RiskClass.DANGEROUS


class TestGetRecommendation:
    def test_returns_string_for_each_class(self) -> None:
        for rc in RiskClass:
            rec = get_recommendation(rc)
            assert isinstance(rec, str)
            assert len(rec) > 10

    def test_safe_recommendation_mentions_validation(self) -> None:
        rec = get_recommendation(RiskClass.SAFE)
        assert "validat" in rec.lower() or "proceed" in rec.lower()

    def test_dangerous_recommendation_mentions_redesign(self) -> None:
        rec = get_recommendation(RiskClass.DANGEROUS)
        assert any(
            word in rec.lower() for word in ("redesign", "re-target", "not advance")
        )


# ===========================================================================
# domain_scores.py — normalize_sequence_score
# ===========================================================================


class TestNormalizeSequenceScore:
    def test_no_hits_returns_low_score(self) -> None:
        score = normalize_sequence_score([], _mirbase(), _repeat())
        assert score == pytest.approx(0.0)

    def test_one_perfect_hit_raises_score(self) -> None:
        score = normalize_sequence_score([_offtarget("perfect")], _mirbase(), _repeat())
        assert score > 0.1

    def test_perfect_hit_higher_than_wobble(self) -> None:
        perf = normalize_sequence_score([_offtarget("perfect")], _mirbase(), _repeat())
        wobble = normalize_sequence_score(
            [_offtarget("G:U_wobble")], _mirbase(), _repeat()
        )
        assert perf > wobble

    def test_wobble_higher_than_mismatch(self) -> None:
        wob = normalize_sequence_score(
            [_offtarget("G:U_wobble")], _mirbase(), _repeat()
        )
        mis = normalize_sequence_score([_offtarget("mismatch")], _mirbase(), _repeat())
        assert wob > mis

    def test_multiple_perfect_hits_increases_score(self) -> None:
        one = normalize_sequence_score([_offtarget()], _mirbase(), _repeat())
        two = normalize_sequence_score(
            [_offtarget(), _offtarget()], _mirbase(), _repeat()
        )
        assert two > one

    def test_score_saturates_at_one(self) -> None:
        hits = [_offtarget("perfect")] * 10
        score = normalize_sequence_score(hits, _mirbase(1.0), _repeat(1.0))
        assert score == pytest.approx(1.0, abs=1e-9)

    def test_mirbase_contributes_to_score(self) -> None:
        no_mir = normalize_sequence_score([], _mirbase(0.0), _repeat())
        high_mir = normalize_sequence_score([], _mirbase(1.0), _repeat())
        assert high_mir > no_mir

    def test_repeat_adar_contributes_to_score(self) -> None:
        no_rep = normalize_sequence_score([], _mirbase(), _repeat(0.0))
        high_rep = normalize_sequence_score([], _mirbase(), _repeat(1.0))
        assert high_rep > no_rep

    def test_output_in_range(self) -> None:
        score = normalize_sequence_score(
            [_offtarget(), _offtarget("G:U_wobble")], _mirbase(0.5), _repeat(0.3)
        )
        assert 0.0 <= score <= 1.0

    def test_all_safe_inputs_near_zero(self) -> None:
        score = normalize_sequence_score([], _mirbase(0.0), _repeat(0.0))
        assert score == pytest.approx(0.0)


# ===========================================================================
# domain_scores.py — normalize_variant_score
# ===========================================================================


class TestNormalizeVariantScore:
    def test_all_zero_inputs(self) -> None:
        score = normalize_variant_score(
            _cosmic(0.0), _gnomad(0.0), _clinvar(0, 0), _phylop(0.0)
        )
        assert score == pytest.approx(0.0)

    def test_high_cosmic_raises_score(self) -> None:
        low = normalize_variant_score(
            _cosmic(0.0), _gnomad(), _clinvar(), _phylop(0.0)
        )
        high = normalize_variant_score(
            _cosmic(1.0), _gnomad(), _clinvar(), _phylop(0.0)
        )
        assert high > low

    def test_tier1_cosmic_amplifies_score(self) -> None:
        no_tier = normalize_variant_score(
            _cosmic(0.5, tier1=False), _gnomad(), _clinvar(), _phylop()
        )
        tier1 = normalize_variant_score(
            _cosmic(0.5, tier1=True), _gnomad(), _clinvar(), _phylop()
        )
        assert tier1 > no_tier

    def test_clinvar_pathogenic_raises_score(self) -> None:
        no_clin = normalize_variant_score(
            _cosmic(), _gnomad(), _clinvar(0, 0), _phylop()
        )
        clin = normalize_variant_score(
            _cosmic(), _gnomad(), _clinvar(2, 0), _phylop()
        )
        assert clin > no_clin

    def test_high_conservation_raises_score(self) -> None:
        low = normalize_variant_score(_cosmic(), _gnomad(), _clinvar(), _phylop(0.0))
        high = normalize_variant_score(_cosmic(), _gnomad(), _clinvar(), _phylop(1.0))
        assert high > low

    def test_high_gnomad_af_reduces_score(self) -> None:
        no_af = normalize_variant_score(_cosmic(0.5), _gnomad(0.0), _clinvar(), _phylop())
        high_af = normalize_variant_score(
            _cosmic(0.5), _gnomad(1.0), _clinvar(), _phylop()
        )
        assert high_af < no_af

    def test_output_in_range(self) -> None:
        score = normalize_variant_score(
            _cosmic(1.0, True), _gnomad(0.0), _clinvar(5, 2), _phylop(1.0)
        )
        assert 0.0 <= score <= 1.0

    def test_max_inputs_saturates_at_one(self) -> None:
        score = normalize_variant_score(
            _cosmic(1.0, True), _gnomad(0.0), _clinvar(10, 10), _phylop(1.0)
        )
        assert score == pytest.approx(1.0, abs=1e-9)

    def test_all_safe_inputs_low_score(self) -> None:
        score = normalize_variant_score(
            _cosmic(0.0), _gnomad(1.0), _clinvar(0, 0), _phylop(0.0)
        )
        assert score == pytest.approx(0.0, abs=1e-9)


# ===========================================================================
# domain_scores.py — normalize_epigenetic_score
# ===========================================================================


class TestNormalizeEpigeneticScore:
    def test_all_zero_returns_zero(self) -> None:
        score = normalize_epigenetic_score(0.0, {}, 0.0, 0.0, 0.0)
        assert score == pytest.approx(0.0)

    def test_max_inputs_saturate_at_one(self) -> None:
        histones = {"h3k4me3": 100.0, "h3k27ac": 100.0, "h3k27me3": 0.0}
        score = normalize_epigenetic_score(100.0, histones, 100.0, 100.0, 100.0)
        assert score == pytest.approx(1.0, abs=1e-9)

    def test_high_atac_raises_score(self) -> None:
        low = normalize_epigenetic_score(0.0, {}, 0.0, 0.0, 0.0)
        high = normalize_epigenetic_score(20.0, {}, 0.0, 0.0, 0.0)
        assert high > low

    def test_h3k27me3_represses_active_histones(self) -> None:
        active_only = normalize_epigenetic_score(
            0.0, {"h3k4me3": 15.0, "h3k27ac": 15.0, "h3k27me3": 0.0}, 0.0, 0.0, 0.0
        )
        repressed = normalize_epigenetic_score(
            0.0, {"h3k4me3": 15.0, "h3k27ac": 15.0, "h3k27me3": 15.0}, 0.0, 0.0, 0.0
        )
        assert repressed < active_only

    def test_ccle_expression_raises_score(self) -> None:
        low = normalize_epigenetic_score(0.0, {}, 0.0, 0.0, 0.0)
        high = normalize_epigenetic_score(0.0, {}, 0.0, 0.0, 12.0)
        assert high > low

    def test_missing_histone_keys_default_to_zero(self) -> None:
        score_empty = normalize_epigenetic_score(5.0, {}, 0.0, 0.0, 0.0)
        score_explicit = normalize_epigenetic_score(
            5.0, {"h3k4me3": 0.0, "h3k27ac": 0.0, "h3k27me3": 0.0}, 0.0, 0.0, 0.0
        )
        assert score_empty == pytest.approx(score_explicit)

    def test_output_in_range(self) -> None:
        histones = {"h3k4me3": 8.0, "h3k27ac": 5.0, "h3k27me3": 3.0}
        score = normalize_epigenetic_score(7.0, histones, 2.5, 0.1, 4.0)
        assert 0.0 <= score <= 1.0

    def test_closed_chromatin_low_expression_returns_low(self) -> None:
        score = normalize_epigenetic_score(0.0, {"h3k27me3": 15.0}, 0.0, 0.0, 0.0)
        assert score < 0.1


# ===========================================================================
# domain_scores.py — normalize_biophysics_score
# ===========================================================================


class TestNormalizeBiophysicsScore:
    def test_very_negative_delta_g_gives_high_score(self) -> None:
        # At ΔG=-30, thermo_risk≈0.982; with neutral shape (0.5) and zero others:
        # score = 0.35×0.982 + 0.25×0.5 ≈ 0.469 — well above a low ΔG baseline.
        score = normalize_biophysics_score(
            _thermo(-30.0), _shape(0.5), _m6a(), _adar(), _g4()
        )
        assert score > 0.40

    def test_near_zero_delta_g_gives_low_score(self) -> None:
        score = normalize_biophysics_score(
            _thermo(0.0), _shape(0.0, False), _m6a(0.0), _adar(0.0), _g4(0.0)
        )
        assert score < 0.3

    def test_more_negative_delta_g_gives_higher_score(self) -> None:
        low = normalize_biophysics_score(
            _thermo(-5.0), _shape(0.5), _m6a(), _adar(), _g4()
        )
        high = normalize_biophysics_score(
            _thermo(-25.0), _shape(0.5), _m6a(), _adar(), _g4()
        )
        assert high > low

    def test_shape_data_unavailable_uses_neutral(self) -> None:
        unavail = normalize_biophysics_score(
            _thermo(-10.0), _shape(0.9, False), _m6a(), _adar(), _g4()
        )
        neutral = normalize_biophysics_score(
            _thermo(-10.0), _shape(0.5, True), _m6a(), _adar(), _g4()
        )
        assert unavail == pytest.approx(neutral, abs=1e-9)

    def test_high_m6a_raises_score(self) -> None:
        low = normalize_biophysics_score(
            _thermo(-10.0), _shape(0.5), _m6a(0.0), _adar(), _g4()
        )
        high = normalize_biophysics_score(
            _thermo(-10.0), _shape(0.5), _m6a(1.0), _adar(), _g4()
        )
        assert high > low

    def test_high_adar_raises_score(self) -> None:
        low = normalize_biophysics_score(
            _thermo(-10.0), _shape(0.5), _m6a(), _adar(0.0), _g4()
        )
        high = normalize_biophysics_score(
            _thermo(-10.0), _shape(0.5), _m6a(), _adar(1.0), _g4()
        )
        assert high > low

    def test_high_g4_raises_score(self) -> None:
        low = normalize_biophysics_score(
            _thermo(-10.0), _shape(0.5), _m6a(), _adar(), _g4(0.0)
        )
        high = normalize_biophysics_score(
            _thermo(-10.0), _shape(0.5), _m6a(), _adar(), _g4(1.0)
        )
        assert high > low

    def test_output_in_range(self) -> None:
        score = normalize_biophysics_score(
            _thermo(-20.0), _shape(0.8), _m6a(0.6), _adar(0.4), _g4(0.3)
        )
        assert 0.0 <= score <= 1.0

    def test_sigmoid_at_minus_ten_is_near_half(self) -> None:
        # Expected: 1/(1+exp(-10/5+2)) = 1/(1+exp(0)) = 0.5, contribution 0.35*0.5=0.175
        score = normalize_biophysics_score(
            _thermo(-10.0), _shape(0.0, False), _m6a(0.0), _adar(0.0), _g4(0.0)
        )
        # neutral shape=0.5 (unavailable), so: 0.35*0.5 + 0.25*0.5 = 0.30
        expected = 0.35 * 0.5 + 0.25 * 0.5
        assert score == pytest.approx(expected, abs=1e-4)


# ===========================================================================
# domain_scores.py — normalize_execution_score
# ===========================================================================


class TestNormalizeExecutionScore:
    def test_all_zero_returns_zero(self) -> None:
        score = normalize_execution_score(
            _ago2(0.0), _rbp(0.0), _circrna(False, 0, True), _immune(0.0)
        )
        assert score == pytest.approx(0.0)

    def test_high_ago2_raises_score(self) -> None:
        low = normalize_execution_score(
            _ago2(0.0), _rbp(0.0), _circrna(), _immune()
        )
        high = normalize_execution_score(
            _ago2(1.0), _rbp(0.0), _circrna(), _immune()
        )
        assert high > low

    def test_sponge_risk_raises_score(self) -> None:
        no_sponge = normalize_execution_score(
            _ago2(0.0), _rbp(0.0), _circrna(False, 0, True), _immune()
        )
        sponge = normalize_execution_score(
            _ago2(0.0), _rbp(0.0), _circrna(True, 0, True), _immune()
        )
        assert sponge > no_sponge

    def test_no_data_circrna_uses_zero(self) -> None:
        no_data = normalize_execution_score(
            _ago2(0.0), _rbp(0.0), _circrna(False, 5, False), _immune()
        )
        with_data = normalize_execution_score(
            _ago2(0.0), _rbp(0.0), _circrna(False, 5, True), _immune()
        )
        assert no_data < with_data

    def test_high_immune_score_raises_score(self) -> None:
        low = normalize_execution_score(
            _ago2(0.0), _rbp(0.0), _circrna(), _immune(0.0)
        )
        high = normalize_execution_score(
            _ago2(0.0), _rbp(0.0), _circrna(), _immune(1.0)
        )
        assert high > low

    def test_all_max_inputs_gives_max_possible(self) -> None:
        # RBP contribution is halved by design (competition_score × 0.5),
        # so the actual maximum is 0.35 + 0.075 + 0.20 + 0.30 = 0.925.
        score = normalize_execution_score(
            _ago2(1.0), _rbp(1.0), _circrna(True, 10, True), _immune(1.0)
        )
        assert score == pytest.approx(0.925, abs=1e-6)

    def test_output_in_range(self) -> None:
        score = normalize_execution_score(
            _ago2(0.6), _rbp(0.4), _circrna(False, 2, True), _immune(0.7)
        )
        assert 0.0 <= score <= 1.0

    def test_rbp_half_weight_reflected(self) -> None:
        # rbp=1.0 contributes 0.15 * 0.5 = 0.075 to score (all others zero)
        score = normalize_execution_score(
            _ago2(0.0), _rbp(1.0), _circrna(False, 0, True), _immune(0.0)
        )
        assert score == pytest.approx(0.15 * 0.50, abs=1e-6)


# ===========================================================================
# integrator.py — _validate_weights
# ===========================================================================


class TestValidateWeights:
    def test_valid_weights_pass(self) -> None:
        _validate_weights(DEFAULT_WEIGHTS)  # should not raise

    def test_weights_not_summing_to_one_raise(self) -> None:
        bad = dict(DEFAULT_WEIGHTS)
        bad["sequence_specificity"] = 0.50  # sum = 1.50
        with pytest.raises(ValueError, match="sum to 1.0"):
            _validate_weights(bad)

    def test_invalid_key_raises(self) -> None:
        bad = dict(DEFAULT_WEIGHTS)
        bad["unknown_domain"] = 0.0
        bad["sequence_specificity"] = 0.20  # keep sum roughly correct
        with pytest.raises(ValueError, match="Invalid weight keys"):
            _validate_weights(bad)

    def test_weights_sum_exactly_to_one(self) -> None:
        sw = ScoringWeights()
        weights = {
            "sequence_specificity": sw.sequence_specificity,
            "variant_toxicity": sw.variant_toxicity,
            "epigenetic_context": sw.epigenetic_context,
            "biophysics_structure": sw.biophysics_structure,
            "execution_safety": sw.execution_safety,
        }
        assert math.isclose(sum(weights.values()), 1.0, abs_tol=1e-9)
        _validate_weights(weights)  # must not raise

    def test_partial_weights_valid_if_sum_one(self) -> None:
        # Provide only some keys as long as sum = 1.0
        w = {"sequence_specificity": 0.60, "biophysics_structure": 0.40}
        _validate_weights(w)

    def test_float_precision_tolerance(self) -> None:
        # 0.1 + 0.1 + 0.1 + 0.1 + 0.6 may not be exactly 1.0 in IEEE 754
        w = {
            "sequence_specificity": 0.1,
            "variant_toxicity": 0.1,
            "epigenetic_context": 0.1,
            "biophysics_structure": 0.1,
            "execution_safety": 0.6,
        }
        _validate_weights(w)  # must not raise


# ===========================================================================
# integrator.py — ScoreIntegrator.integrate
# ===========================================================================


class TestScoreIntegratorIntegrate:
    def setup_method(self) -> None:
        self.si = ScoreIntegrator()

    def test_all_zero_domain_scores_return_zero(self) -> None:
        result = self.si.integrate(_domain(0, 0, 0, 0, 0), DEFAULT_WEIGHTS)
        assert result == pytest.approx(0.0)

    def test_all_one_domain_scores_return_one(self) -> None:
        result = self.si.integrate(_domain(1, 1, 1, 1, 1), DEFAULT_WEIGHTS)
        assert result == pytest.approx(1.0)

    def test_weighted_sum_computed_correctly(self) -> None:
        ds = _domain(seq=1.0, var=0.0, epi=0.0, bio=0.0, exc=0.0)
        result = self.si.integrate(ds, DEFAULT_WEIGHTS)
        assert result == pytest.approx(0.20, abs=1e-9)

    def test_output_clamped_at_zero(self) -> None:
        # All zeros → 0.0 (already tested, just confirm non-negative)
        result = self.si.integrate(_domain(0, 0, 0, 0, 0), DEFAULT_WEIGHTS)
        assert result >= 0.0

    def test_output_clamped_at_one(self) -> None:
        result = self.si.integrate(_domain(1, 1, 1, 1, 1), DEFAULT_WEIGHTS)
        assert result <= 1.0

    def test_invalid_weights_raise(self) -> None:
        bad = dict(DEFAULT_WEIGHTS)
        bad["sequence_specificity"] = 0.99  # sum != 1
        with pytest.raises(ValueError):
            self.si.integrate(_domain(), bad)

    def test_biophysics_has_highest_weight_in_defaults(self) -> None:
        # With default weights, biophysics (0.25) contributes most for equal scores.
        ds_bio = _domain(bio=1.0)
        ds_seq = _domain(seq=1.0)
        result_bio = self.si.integrate(ds_bio, DEFAULT_WEIGHTS)
        result_seq = self.si.integrate(ds_seq, DEFAULT_WEIGHTS)
        assert result_bio > result_seq


# ===========================================================================
# integrator.py — ScoreIntegrator.apply_cell_modifier
# ===========================================================================


class TestApplyCellModifier:
    def setup_method(self) -> None:
        self.si = ScoreIntegrator()

    def test_neutral_context_returns_base_score(self) -> None:
        ctx = {"atac_score": 0.5, "expression_score": 0.5, "execution_score": 0.5}
        result = self.si.apply_cell_modifier(0.6, ctx)
        assert result == pytest.approx(0.6, abs=1e-9)

    def test_closed_chromatin_reduces_risk(self) -> None:
        # atac=0, expression=0, execution=0 → modifier=0.3 → risk halved
        ctx = {"atac_score": 0.0, "expression_score": 0.0, "execution_score": 0.0}
        base = 0.7
        result = self.si.apply_cell_modifier(base, ctx)
        assert result < base
        assert result == pytest.approx(base * 0.30, abs=1e-9)

    def test_open_chromatin_amplifies_risk(self) -> None:
        ctx = {"atac_score": 1.0, "expression_score": 1.0, "execution_score": 1.0}
        base = 0.4
        result = self.si.apply_cell_modifier(base, ctx)
        assert result > base

    def test_closed_chromatin_can_push_dangerous_to_safe(self) -> None:
        # base=0.7 (HIGH_RISK) → modifier=0.3 → final=0.21 (SAFE)
        ctx = {"atac_score": 0.0, "expression_score": 0.0, "execution_score": 0.0}
        result = self.si.apply_cell_modifier(0.7, ctx)
        assert result < 0.30  # SAFE threshold

    def test_missing_keys_default_to_neutral(self) -> None:
        result = self.si.apply_cell_modifier(0.6, {})
        assert result == pytest.approx(0.6, abs=1e-9)

    def test_output_clamped_at_one(self) -> None:
        ctx = {"atac_score": 1.0, "expression_score": 1.0, "execution_score": 1.0}
        result = self.si.apply_cell_modifier(1.0, ctx)
        assert result == pytest.approx(1.0, abs=1e-9)

    def test_output_clamped_at_zero(self) -> None:
        ctx = {"atac_score": 0.0, "expression_score": 0.0, "execution_score": 0.0}
        result = self.si.apply_cell_modifier(0.0, ctx)
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_context_scores_clamped_to_range(self) -> None:
        ctx_low = {"atac_score": -5.0, "expression_score": -5.0, "execution_score": -5.0}
        ctx_high = {"atac_score": 5.0, "expression_score": 5.0, "execution_score": 5.0}
        result_low = self.si.apply_cell_modifier(0.5, ctx_low)
        result_high = self.si.apply_cell_modifier(0.5, ctx_high)
        # Clamped to same as 0.0 and 1.0 extremes
        neutral_low = self.si.apply_cell_modifier(
            0.5, {"atac_score": 0.0, "expression_score": 0.0, "execution_score": 0.0}
        )
        neutral_high = self.si.apply_cell_modifier(
            0.5, {"atac_score": 1.0, "expression_score": 1.0, "execution_score": 1.0}
        )
        assert result_low == pytest.approx(neutral_low, abs=1e-9)
        assert result_high == pytest.approx(neutral_high, abs=1e-9)


# ===========================================================================
# integrator.py — ScoreIntegrator.classify_risk
# ===========================================================================


class TestScoreIntegratorClassifyRisk:
    def setup_method(self) -> None:
        self.si = ScoreIntegrator()

    def test_zero_is_safe(self) -> None:
        assert self.si.classify_risk(0.0) == RiskClass.SAFE

    def test_one_is_dangerous(self) -> None:
        assert self.si.classify_risk(1.0) == RiskClass.DANGEROUS

    def test_custom_thresholds_used(self) -> None:
        t = RiskThresholds(safe=0.1, warning=0.2, high_risk=0.3)
        si = ScoreIntegrator(risk_thresholds=t)
        assert si.classify_risk(0.05) == RiskClass.SAFE
        assert si.classify_risk(0.15) == RiskClass.WARNING
        assert si.classify_risk(0.25) == RiskClass.HIGH_RISK
        assert si.classify_risk(0.50) == RiskClass.DANGEROUS


# ===========================================================================
# integrator.py — ScoreIntegrator.score (full pipeline)
# ===========================================================================


class TestScoreIntegratorScore:
    def setup_method(self) -> None:
        self.si = ScoreIntegrator()

    def test_all_safe_inputs_returns_safe(self) -> None:
        ds = _domain(seq=0.0, var=0.0, epi=0.0, bio=0.0, exc=0.0)
        ctx = {"atac_score": 0.0, "expression_score": 0.0, "execution_score": 0.0}
        final, risk = self.si.score(ds, ctx, DEFAULT_WEIGHTS)
        assert risk == RiskClass.SAFE
        assert final < 0.3

    def test_high_cosmic_high_expression_returns_dangerous(self) -> None:
        # Extreme values across all cell-dependent and independent channels.
        ds = _domain(seq=0.9, var=0.9, epi=0.9, bio=0.9, exc=0.9)
        ctx = {"atac_score": 1.0, "expression_score": 1.0, "execution_score": 1.0}
        final, risk = self.si.score(ds, ctx, DEFAULT_WEIGHTS)
        assert risk == RiskClass.DANGEROUS

    def test_closed_chromatin_reduces_risk_class(self) -> None:
        # Moderate base → closed chromatin pushes final score below WARNING.
        ds = _domain(seq=0.5, var=0.5, epi=0.5, bio=0.5, exc=0.5)
        open_ctx = {"atac_score": 1.0, "expression_score": 1.0, "execution_score": 1.0}
        closed_ctx = {"atac_score": 0.0, "expression_score": 0.0, "execution_score": 0.0}
        _, risk_open = self.si.score(ds, open_ctx, DEFAULT_WEIGHTS)
        _, risk_closed = self.si.score(ds, closed_ctx, DEFAULT_WEIGHTS)
        # Open should be higher risk than closed
        open_ordinal = [RiskClass.SAFE, RiskClass.WARNING, RiskClass.HIGH_RISK, RiskClass.DANGEROUS].index(risk_open)
        closed_ordinal = [RiskClass.SAFE, RiskClass.WARNING, RiskClass.HIGH_RISK, RiskClass.DANGEROUS].index(risk_closed)
        assert open_ordinal >= closed_ordinal

    def test_score_weights_sum_to_one_validation(self) -> None:
        bad_weights = dict(DEFAULT_WEIGHTS)
        bad_weights["sequence_specificity"] = 0.99
        with pytest.raises(ValueError, match="sum to 1.0"):
            self.si.score(_domain(), {}, bad_weights)

    def test_default_weights_used_when_none(self) -> None:
        ds = _domain(1.0, 0.0, 0.0, 0.0, 0.0)
        final_none, _ = self.si.score(ds, {})
        final_explicit, _ = self.si.score(ds, {}, DEFAULT_WEIGHTS)
        assert final_none == pytest.approx(final_explicit, abs=1e-9)

    def test_returns_tuple_of_float_and_riskclass(self) -> None:
        result = self.si.score(_domain(), {})
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], float)
        assert isinstance(result[1], RiskClass)

    def test_score_increases_monotonically_with_domain_inputs(self) -> None:
        ctx = {"atac_score": 0.5, "expression_score": 0.5}
        scores = []
        for level in [0.0, 0.25, 0.5, 0.75, 1.0]:
            ds = _domain(seq=level, var=level, epi=level, bio=level, exc=level)
            final, _ = self.si.score(ds, ctx, DEFAULT_WEIGHTS)
            scores.append(final)
        for i in range(len(scores) - 1):
            assert scores[i] <= scores[i + 1]
