"""Unit tests for src/stage5_biophysics/adar_risk.py."""

from __future__ import annotations

import pytest

from src.core.models import (
    AdarRiskResult,
    GenomicRegion,
    RepeatEntry,
    RepeatResult,
    ShapeResult,
)
from src.stage5_biophysics.adar_risk import (
    _alu_risk,
    _shape_ds_risk,
    calculate_adar_risk,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_REGION = GenomicRegion(chrom="chr1", start=1000, end=2000)


def _repeat_result(has_alu: bool, alu_count: int = 1) -> RepeatResult:
    repeats: list[RepeatEntry] = []
    if has_alu:
        for i in range(alu_count):
            repeats.append(
                RepeatEntry(
                    chrom="chr1",
                    start=1000 + i * 100,
                    end=1100 + i * 100,
                    rep_name=f"AluSx_{i}",
                    rep_class="SINE",
                    rep_family="Alu",
                )
            )
    return RepeatResult(
        region=_REGION,
        repeats=repeats,
        has_alu=has_alu,
        adar_risk_score=0.0,
    )


def _shape(ss_frac: float, available: bool = True) -> ShapeResult:
    return ShapeResult(
        region=_REGION,
        mean_reactivity=ss_frac,
        accessibility_score=ss_frac / 2.0,
        single_stranded_fraction=ss_frac,
        data_available=available,
    )


# ---------------------------------------------------------------------------
# _alu_risk
# ---------------------------------------------------------------------------


class TestAluRisk:
    def test_no_alu(self):
        assert _alu_risk(_repeat_result(has_alu=False)) == pytest.approx(0.0)

    def test_single_alu(self):
        assert _alu_risk(_repeat_result(has_alu=True, alu_count=1)) == pytest.approx(0.8)

    def test_two_alus(self):
        assert _alu_risk(_repeat_result(has_alu=True, alu_count=2)) == pytest.approx(0.9)

    def test_three_alus(self):
        assert _alu_risk(_repeat_result(has_alu=True, alu_count=3)) == pytest.approx(1.0)

    def test_many_alus_capped(self):
        assert _alu_risk(_repeat_result(has_alu=True, alu_count=10)) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# _shape_ds_risk
# ---------------------------------------------------------------------------


class TestShapeDsRisk:
    def test_none_returns_neutral(self):
        assert _shape_ds_risk(None) == pytest.approx(0.5)

    def test_unavailable_returns_neutral(self):
        s = _shape(ss_frac=1.0, available=False)
        assert _shape_ds_risk(s) == pytest.approx(0.5)

    def test_fully_single_stranded(self):
        # ss_frac=1.0 → ds_frac=0.0 → risk 0.0
        assert _shape_ds_risk(_shape(1.0)) == pytest.approx(0.0)

    def test_fully_double_stranded(self):
        # ss_frac=0.0 → ds_frac=1.0 → risk 1.0
        assert _shape_ds_risk(_shape(0.0)) == pytest.approx(1.0)

    def test_half_and_half(self):
        assert _shape_ds_risk(_shape(0.5)) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# calculate_adar_risk
# ---------------------------------------------------------------------------


class TestCalculateAdarRisk:
    def test_no_alu_no_shape(self):
        rr = _repeat_result(has_alu=False)
        result = calculate_adar_risk(_REGION, rr, shape_result=None)
        assert isinstance(result, AdarRiskResult)
        assert result.adar_score == pytest.approx(0.0)
        assert result.shape_used is False

    def test_alu_only_no_shape(self):
        """Without SHAPE, combined score equals Alu risk."""
        rr = _repeat_result(has_alu=True, alu_count=1)
        result = calculate_adar_risk(_REGION, rr, shape_result=None)
        assert result.adar_score == pytest.approx(0.8)
        assert result.shape_used is False

    def test_alu_with_fully_single_stranded_shape(self):
        """Alu present but region is fully single-stranded → lower combined risk."""
        rr = _repeat_result(has_alu=True, alu_count=1)
        result = calculate_adar_risk(_REGION, rr, shape_result=_shape(1.0))
        # combined = 0.6 × 0.8 + 0.4 × 0.0 = 0.48
        assert result.adar_score == pytest.approx(0.48, abs=0.01)
        assert result.shape_used is True

    def test_no_alu_with_fully_double_stranded_shape(self):
        """No Alu but region is fully double-stranded → moderate risk from SHAPE."""
        rr = _repeat_result(has_alu=False)
        result = calculate_adar_risk(_REGION, rr, shape_result=_shape(0.0))
        # combined = 0.6 × 0.0 + 0.4 × 1.0 = 0.4
        assert result.adar_score == pytest.approx(0.4, abs=0.01)
        assert result.shape_used is True

    def test_alu_with_half_ds_shape(self):
        rr = _repeat_result(has_alu=True, alu_count=1)
        result = calculate_adar_risk(_REGION, rr, shape_result=_shape(0.5))
        # combined = 0.6 × 0.8 + 0.4 × 0.5 = 0.48 + 0.20 = 0.68
        assert result.adar_score == pytest.approx(0.68, abs=0.01)

    def test_unavailable_shape_treated_as_none(self):
        """Shape with data_available=False should be treated as neutral."""
        rr = _repeat_result(has_alu=True, alu_count=1)
        unavailable = _shape(ss_frac=1.0, available=False)
        result_none = calculate_adar_risk(_REGION, rr, shape_result=None)
        result_unavail = calculate_adar_risk(_REGION, rr, shape_result=unavailable)
        # Both should give the same score (Alu-only path)
        assert result_none.adar_score == pytest.approx(result_unavail.adar_score, abs=0.001)

    def test_score_bounds(self):
        rr = _repeat_result(has_alu=True, alu_count=10)
        result = calculate_adar_risk(_REGION, rr, shape_result=_shape(0.0))
        assert 0.0 <= result.adar_score <= 1.0

    def test_region_preserved(self):
        rr = _repeat_result(has_alu=False)
        result = calculate_adar_risk(_REGION, rr)
        assert result.region == _REGION

    def test_fields_present(self):
        rr = _repeat_result(has_alu=True)
        result = calculate_adar_risk(_REGION, rr, shape_result=_shape(0.5))
        assert hasattr(result, "alu_risk")
        assert hasattr(result, "shape_ds_risk")
        assert hasattr(result, "adar_score")
        assert hasattr(result, "shape_used")
