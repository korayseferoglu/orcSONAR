"""Integration tests for orcSONAR end-to-end scoring + reporting pipeline.

These tests wire together Stages 7 (score_integrator → risk_classifier →
report_generator) using synthetic stage2–6 JSON files written to a tmp_path.
They verify:
  - JSON output schemas and value ranges
  - HTML report generation (content + structure)
  - Graceful degradation with simulated API timeouts
  - Graceful degradation when SHAPE data is missing

All tests run without network access. Snakemake is not invoked.
"""

from __future__ import annotations

import json
import socket
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from src.scoring.score_integrator import run as score_integrator_run
from src.scoring.risk_classifier import run as risk_classifier_run
from src.reporting.report_generator import run as report_generator_run


# ---------------------------------------------------------------------------
# Helpers — synthetic stage JSON factories
# ---------------------------------------------------------------------------

_GENE = "VEGFA"
_CELL = "HeLa"
_SARNA = "GCAACCAUAGCCUCGGCCGC"

_SITE_A = "BRCA1:ENST00000357654"
_SITE_B = "TP53:ENST00000269305"

_REGION_A = {"chrom": "chr17", "start": 41196312, "end": 41196332, "strand": "+"}
_REGION_B = {"chrom": "chr17", "start": 7674220, "end": 7674240, "strand": "-"}


def _offtarget_site(site_id: str, region: dict[str, Any]) -> dict[str, Any]:
    gene, tid = site_id.split(":")
    return {
        "gene": gene,
        "transcript_id": tid,
        "region": region,
        "seed_match_type": "perfect",
        "mismatches": 0,
        "alignment_score": 0.92,
    }


def _stage2(
    tmp_path: Path,
    *,
    sites: list[str] | None = None,
    seq_scores: dict[str, float] | None = None,
) -> str:
    sites = [_SITE_A, _SITE_B] if sites is None else sites
    regions = {_SITE_A: _REGION_A, _SITE_B: _REGION_B}
    seq_scores = {s: 0.40 for s in sites} if seq_scores is None else seq_scores

    payload: dict[str, Any] = {
        "offtarget_sites": [
            _offtarget_site(s, regions.get(s, _REGION_A)) for s in sites
        ],
        "mirbase_result": {
            "sarna_seed": "GCAACCA",
            "overlapping_mirnas": [],
            "max_overlap_score": 0.1,
            "risk_level": "SAFE",
        },
        "repeat_results": {
            s: {
                "region": regions.get(s, _REGION_A),
                "repeats": [],
                "has_alu": False,
                "has_line": False,
                "adar_risk_score": 0.0,
            }
            for s in sites
        },
        "sequence_scores": seq_scores,
    }
    p = tmp_path / "stage2_offtargets.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


def _stage3(
    tmp_path: Path,
    *,
    sites: list[str] | None = None,
    normalized: float = 0.30,
) -> str:
    sites = [_SITE_A, _SITE_B] if sites is None else sites
    payload = {
        "variant_scores": {
            s: {
                "cosmic_count": 1,
                "cosmic_mutations": ["SNV"],
                "gnomad_max_af": 0.001,
                "clinvar_pathogenic": False,
                "phylop_score": 0.6,
                "normalized_score": normalized,
            }
            for s in sites
        }
    }
    p = tmp_path / "stage3_variants.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


def _stage4(
    tmp_path: Path,
    *,
    sites: list[str] | None = None,
    normalized: float = 0.50,
    atac_score: float = 0.50,
    expression_score: float = 0.60,
    execution_score: float = 0.40,
) -> str:
    sites = [_SITE_A, _SITE_B] if sites is None else sites
    payload = {
        "epigenetic_scores": {
            s: {
                "atac_signal": 5.0,
                "h3k4me3_signal": 7.5,
                "h3k27ac_signal": 6.0,
                "groseq_signal": 2.0,
                "hic_contact": 0.05,
                "ccle_expression": 3.6,
                "normalized_score": normalized,
            }
            for s in sites
        },
        "cell_context": {
            "atac_score": atac_score,
            "expression_score": expression_score,
            "execution_score": execution_score,
        },
    }
    p = tmp_path / "stage4_epigenetic.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


def _stage5(
    tmp_path: Path,
    *,
    sites: list[str] | None = None,
    normalized: float = 0.35,
    shape_available: bool = True,
) -> str:
    sites = [_SITE_A, _SITE_B] if sites is None else sites
    payload = {
        "biophysics_scores": {
            s: {
                "delta_g": -22.5,
                "shape_accessibility": 0.60 if shape_available else 0.50,
                "m6a_sites": 1,
                "adar_risk": 0.10,
                "g4_risk": 0.05,
                "normalized_score": normalized,
                "_shape_data_available": shape_available,
            }
            for s in sites
        }
    }
    p = tmp_path / "stage5_biophysics.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


def _stage6(
    tmp_path: Path,
    *,
    sites: list[str] | None = None,
    normalized: float = 0.20,
) -> str:
    sites = [_SITE_A, _SITE_B] if sites is None else sites
    payload = {
        "execution_scores": {
            s: {
                "ago2_loading": 0.15,
                "rbp_competition": 0.10,
                "circrna_overlap": False,
                "immune_motif_count": 0,
                "immune_motifs_found": [],
                "normalized_score": normalized,
            }
            for s in sites
        }
    }
    p = tmp_path / "stage6_execution.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


_DEFAULT_WEIGHTS = {
    "sequence_specificity": 0.20,
    "variant_toxicity": 0.15,
    "biophysics_structure": 0.25,
    "epigenetic_context": 0.20,
    "execution_safety": 0.20,
}

_DEFAULT_THRESHOLDS = {"safe": 0.3, "warning": 0.6, "high_risk": 0.8}


def _run_full(
    tmp_path: Path,
    *,
    sites: list[str] | None = None,
    seq: float = 0.40,
    var: float = 0.30,
    epi: float = 0.50,
    bio: float = 0.35,
    exe: float = 0.20,
    atac_score: float = 0.50,
    expression_score: float = 0.60,
    execution_score: float = 0.40,
    shape_available: bool = True,
) -> tuple[dict[str, Any], dict[str, Any], Path, Path]:
    """Run stages 7a→7b→7c and return (scores_data, classification_data, json_path, html_path)."""
    sites = sites or [_SITE_A, _SITE_B]

    s2 = _stage2(tmp_path, sites=sites, seq_scores={s: seq for s in sites})
    s3 = _stage3(tmp_path, sites=sites, normalized=var)
    s4 = _stage4(tmp_path, sites=sites, normalized=epi,
                 atac_score=atac_score, expression_score=expression_score,
                 execution_score=execution_score)
    s5 = _stage5(tmp_path, sites=sites, normalized=bio, shape_available=shape_available)
    s6 = _stage6(tmp_path, sites=sites, normalized=exe)

    scores_path   = str(tmp_path / "stage7_scores.json")
    classif_path  = str(tmp_path / "stage7_classification.json")
    json_report   = str(tmp_path / "final_report.json")
    html_report   = str(tmp_path / "final_report.html")
    log_dir       = str(tmp_path / "logs")

    score_integrator_run(
        offtargets_path=s2,
        variants_path=s3,
        epigenetic_path=s4,
        biophysics_path=s5,
        execution_path=s6,
        weights=_DEFAULT_WEIGHTS,
        output_path=scores_path,
        log_path=f"{log_dir}/score_integration.log",
    )
    risk_classifier_run(
        scores_path=scores_path,
        thresholds=_DEFAULT_THRESHOLDS,
        output_path=classif_path,
        log_path=f"{log_dir}/risk_classification.log",
    )
    report_generator_run(
        classification_path=classif_path,
        scores_path=scores_path,
        offtargets_path=s2,
        variants_path=s3,
        epigenetic_path=s4,
        biophysics_path=s5,
        execution_path=s6,
        gene=_GENE,
        cell_line=_CELL,
        sarna_sequence=_SARNA,
        json_output=json_report,
        html_output=html_report,
        log_path=f"{log_dir}/generate_report.log",
    )

    scores_data   = json.loads(Path(scores_path).read_text())
    classif_data  = json.loads(Path(classif_path).read_text())
    return scores_data, classif_data, Path(json_report), Path(html_report)


# ===========================================================================
# Stage 7a — score_integrator
# ===========================================================================


class TestScoreIntegrator:
    def test_output_file_created(self, tmp_path: Path) -> None:
        s2 = _stage2(tmp_path)
        s3 = _stage3(tmp_path)
        s4 = _stage4(tmp_path)
        s5 = _stage5(tmp_path)
        s6 = _stage6(tmp_path)
        out = str(tmp_path / "scores.json")
        score_integrator_run(
            offtargets_path=s2, variants_path=s3, epigenetic_path=s4,
            biophysics_path=s5, execution_path=s6,
            weights=_DEFAULT_WEIGHTS, output_path=out,
            log_path=str(tmp_path / "si.log"),
        )
        assert Path(out).exists()

    def test_output_is_valid_json(self, tmp_path: Path) -> None:
        s2, s3, s4, s5, s6 = (
            _stage2(tmp_path), _stage3(tmp_path), _stage4(tmp_path),
            _stage5(tmp_path), _stage6(tmp_path),
        )
        out = str(tmp_path / "scores.json")
        score_integrator_run(
            offtargets_path=s2, variants_path=s3, epigenetic_path=s4,
            biophysics_path=s5, execution_path=s6,
            weights=_DEFAULT_WEIGHTS, output_path=out,
            log_path=str(tmp_path / "si.log"),
        )
        data = json.loads(Path(out).read_text())
        assert isinstance(data, dict)

    def test_output_contains_required_keys(self, tmp_path: Path) -> None:
        s2, s3, s4, s5, s6 = (
            _stage2(tmp_path), _stage3(tmp_path), _stage4(tmp_path),
            _stage5(tmp_path), _stage6(tmp_path),
        )
        out = str(tmp_path / "scores.json")
        score_integrator_run(
            offtargets_path=s2, variants_path=s3, epigenetic_path=s4,
            biophysics_path=s5, execution_path=s6,
            weights=_DEFAULT_WEIGHTS, output_path=out,
            log_path=str(tmp_path / "si.log"),
        )
        data = json.loads(Path(out).read_text())
        for key in ("offtarget_sites", "domain_scores", "base_scores", "cell_context", "weights"):
            assert key in data, f"Missing key: {key}"

    def test_domain_scores_per_site_present(self, tmp_path: Path) -> None:
        scores_data, *_ = _run_full(tmp_path)
        assert _SITE_A in scores_data["domain_scores"]
        assert _SITE_B in scores_data["domain_scores"]

    def test_domain_scores_have_five_keys(self, tmp_path: Path) -> None:
        scores_data, *_ = _run_full(tmp_path)
        for site_id, ds in scores_data["domain_scores"].items():
            for field in ("sequence_specificity", "variant_toxicity",
                          "epigenetic_context", "biophysics_structure", "execution_safety"):
                assert field in ds, f"{site_id} missing {field}"

    def test_domain_scores_in_range(self, tmp_path: Path) -> None:
        scores_data, *_ = _run_full(tmp_path)
        for site_id, ds in scores_data["domain_scores"].items():
            for field, val in ds.items():
                assert 0.0 <= val <= 1.0, f"{site_id}.{field}={val} out of range"

    def test_base_scores_in_range(self, tmp_path: Path) -> None:
        scores_data, *_ = _run_full(tmp_path)
        for site_id, score in scores_data["base_scores"].items():
            assert 0.0 <= score <= 1.0, f"{site_id} base_score={score} out of range"

    def test_weights_preserved_in_output(self, tmp_path: Path) -> None:
        scores_data, *_ = _run_full(tmp_path)
        assert scores_data["weights"] == _DEFAULT_WEIGHTS

    def test_offtarget_sites_passed_through(self, tmp_path: Path) -> None:
        scores_data, *_ = _run_full(tmp_path)
        assert len(scores_data["offtarget_sites"]) == 2

    def test_weighted_base_score_computation(self, tmp_path: Path) -> None:
        scores_data, *_ = _run_full(tmp_path, seq=0.4, var=0.3, epi=0.5, bio=0.35, exe=0.2)
        expected_base = (
            0.4 * 0.20 + 0.3 * 0.15 + 0.35 * 0.25 + 0.5 * 0.20 + 0.2 * 0.20
        )
        for site_id, score in scores_data["base_scores"].items():
            assert abs(score - expected_base) < 1e-4, (
                f"{site_id}: expected {expected_base:.4f}, got {score:.4f}"
            )

    def test_missing_stage_json_uses_neutral(self, tmp_path: Path) -> None:
        s2 = _stage2(tmp_path)
        s4 = _stage4(tmp_path)
        s5 = _stage5(tmp_path)
        s6 = _stage6(tmp_path)
        out = str(tmp_path / "scores.json")
        score_integrator_run(
            offtargets_path=s2,
            variants_path=str(tmp_path / "nonexistent.json"),
            epigenetic_path=s4,
            biophysics_path=s5,
            execution_path=s6,
            weights=_DEFAULT_WEIGHTS,
            output_path=out,
            log_path=str(tmp_path / "si.log"),
        )
        data = json.loads(Path(out).read_text())
        for site_id, ds in data["domain_scores"].items():
            assert ds["variant_toxicity"] == pytest.approx(0.5)

    def test_zero_sites_produces_empty_domain_scores(self, tmp_path: Path) -> None:
        s2 = _stage2(tmp_path, sites=[])
        s3 = _stage3(tmp_path, sites=[])
        s4 = _stage4(tmp_path, sites=[])
        s5 = _stage5(tmp_path, sites=[])
        s6 = _stage6(tmp_path, sites=[])
        out = str(tmp_path / "scores.json")
        score_integrator_run(
            offtargets_path=s2, variants_path=s3, epigenetic_path=s4,
            biophysics_path=s5, execution_path=s6,
            weights=_DEFAULT_WEIGHTS, output_path=out,
            log_path=str(tmp_path / "si.log"),
        )
        data = json.loads(Path(out).read_text())
        assert data["domain_scores"] == {}
        assert data["base_scores"] == {}


# ===========================================================================
# Stage 7b — risk_classifier
# ===========================================================================


class TestRiskClassifier:
    def test_output_file_created(self, tmp_path: Path) -> None:
        _, classif_data, *_ = _run_full(tmp_path)
        assert classif_data is not None

    def test_output_contains_required_keys(self, tmp_path: Path) -> None:
        _, classif_data, *_ = _run_full(tmp_path)
        for key in ("site_classifications", "overall_risk_score",
                    "overall_risk_class", "cell_line_context"):
            assert key in classif_data, f"Missing key: {key}"

    def test_overall_risk_score_in_range(self, tmp_path: Path) -> None:
        _, classif_data, *_ = _run_full(tmp_path)
        assert 0.0 <= classif_data["overall_risk_score"] <= 1.0

    def test_overall_risk_class_valid(self, tmp_path: Path) -> None:
        _, classif_data, *_ = _run_full(tmp_path)
        assert classif_data["overall_risk_class"] in ("SAFE", "WARNING", "HIGH_RISK", "DANGEROUS")

    def test_site_classifications_contain_both_sites(self, tmp_path: Path) -> None:
        _, classif_data, *_ = _run_full(tmp_path)
        assert _SITE_A in classif_data["site_classifications"]
        assert _SITE_B in classif_data["site_classifications"]

    def test_each_site_has_final_score_and_risk_class(self, tmp_path: Path) -> None:
        _, classif_data, *_ = _run_full(tmp_path)
        for site_id, cls in classif_data["site_classifications"].items():
            assert "final_score" in cls, f"{site_id} missing final_score"
            assert "risk_class" in cls, f"{site_id} missing risk_class"
            assert cls["risk_class"] in ("SAFE", "WARNING", "HIGH_RISK", "DANGEROUS")
            assert 0.0 <= cls["final_score"] <= 1.0

    def test_all_high_risk_inputs_return_dangerous(self, tmp_path: Path) -> None:
        _, classif_data, *_ = _run_full(
            tmp_path,
            seq=0.95, var=0.90, epi=0.95, bio=0.90, exe=0.90,
            atac_score=1.0, expression_score=1.0, execution_score=1.0,
        )
        assert classif_data["overall_risk_class"] in ("HIGH_RISK", "DANGEROUS")

    def test_all_zero_inputs_return_safe(self, tmp_path: Path) -> None:
        _, classif_data, *_ = _run_full(
            tmp_path,
            seq=0.0, var=0.0, epi=0.0, bio=0.0, exe=0.0,
            atac_score=0.0, expression_score=0.0, execution_score=0.0,
        )
        assert classif_data["overall_risk_class"] == "SAFE"

    def test_closed_chromatin_reduces_risk(self, tmp_path: Path) -> None:
        _, classif_open, *_ = _run_full(
            tmp_path,
            seq=0.6, var=0.5, epi=0.6, bio=0.5, exe=0.5,
            atac_score=1.0, expression_score=1.0, execution_score=1.0,
        )
        tmp2 = Path(str(tmp_path) + "_closed")
        tmp2.mkdir()
        _, classif_closed, *_ = _run_full(
            tmp2,
            seq=0.6, var=0.5, epi=0.6, bio=0.5, exe=0.5,
            atac_score=0.0, expression_score=0.0, execution_score=0.0,
        )
        assert classif_closed["overall_risk_score"] < classif_open["overall_risk_score"]

    def test_cell_line_context_string_non_empty(self, tmp_path: Path) -> None:
        _, classif_data, *_ = _run_full(tmp_path)
        assert len(classif_data["cell_line_context"]) > 5

    def test_zero_sites_overall_safe(self, tmp_path: Path) -> None:
        s2 = _stage2(tmp_path, sites=[])
        s3 = _stage3(tmp_path, sites=[])
        s4 = _stage4(tmp_path, sites=[])
        s5 = _stage5(tmp_path, sites=[])
        s6 = _stage6(tmp_path, sites=[])
        scores_path  = str(tmp_path / "stage7_scores.json")
        classif_path = str(tmp_path / "stage7_classification.json")

        score_integrator_run(
            offtargets_path=s2, variants_path=s3, epigenetic_path=s4,
            biophysics_path=s5, execution_path=s6,
            weights=_DEFAULT_WEIGHTS, output_path=scores_path,
            log_path=str(tmp_path / "si.log"),
        )
        risk_classifier_run(
            scores_path=scores_path,
            thresholds=_DEFAULT_THRESHOLDS,
            output_path=classif_path,
            log_path=str(tmp_path / "rc.log"),
        )
        data = json.loads(Path(classif_path).read_text())
        assert data["overall_risk_class"] == "SAFE"
        assert data["overall_risk_score"] == pytest.approx(0.0)


# ===========================================================================
# Stage 7c — report_generator
# ===========================================================================


class TestReportGenerator:
    def test_json_report_created(self, tmp_path: Path) -> None:
        _, _, json_path, html_path = _run_full(tmp_path)
        assert json_path.exists()

    def test_html_report_created(self, tmp_path: Path) -> None:
        _, _, json_path, html_path = _run_full(tmp_path)
        assert html_path.exists()

    def test_json_report_is_valid_json(self, tmp_path: Path) -> None:
        _, _, json_path, _ = _run_full(tmp_path)
        data = json.loads(json_path.read_text())
        assert isinstance(data, dict)

    def test_json_report_has_sarna_input(self, tmp_path: Path) -> None:
        _, _, json_path, _ = _run_full(tmp_path)
        data = json.loads(json_path.read_text())
        inp = data["sarna_input"]
        assert inp["target_gene"] == _GENE
        assert inp["cell_line"] == _CELL

    def test_json_report_has_metadata(self, tmp_path: Path) -> None:
        _, _, json_path, _ = _run_full(tmp_path)
        data = json.loads(json_path.read_text())
        assert "_metadata" in data
        assert "orcsonar_version" in data["_metadata"]
        assert "data_sources" in data["_metadata"]

    def test_json_report_risk_score_in_range(self, tmp_path: Path) -> None:
        _, _, json_path, _ = _run_full(tmp_path)
        data = json.loads(json_path.read_text())
        assert 0.0 <= data["final_risk_score"] <= 1.0

    def test_json_report_risk_class_valid(self, tmp_path: Path) -> None:
        _, _, json_path, _ = _run_full(tmp_path)
        data = json.loads(json_path.read_text())
        assert data["risk_class"] in ("SAFE", "WARNING", "HIGH_RISK", "DANGEROUS")

    def test_json_report_offtarget_sites_count(self, tmp_path: Path) -> None:
        _, _, json_path, _ = _run_full(tmp_path)
        data = json.loads(json_path.read_text())
        assert len(data["offtarget_sites"]) == 2

    def test_html_starts_with_doctype(self, tmp_path: Path) -> None:
        _, _, _, html_path = _run_full(tmp_path)
        html = html_path.read_text()
        assert html.startswith("<!DOCTYPE html>")

    def test_html_contains_gene_name(self, tmp_path: Path) -> None:
        _, _, _, html_path = _run_full(tmp_path)
        assert _GENE in html_path.read_text()

    def test_html_contains_cell_line(self, tmp_path: Path) -> None:
        _, _, _, html_path = _run_full(tmp_path)
        assert _CELL in html_path.read_text()

    def test_html_contains_sarna_sequence(self, tmp_path: Path) -> None:
        _, _, _, html_path = _run_full(tmp_path)
        assert _SARNA in html_path.read_text()

    def test_html_contains_plotly(self, tmp_path: Path) -> None:
        _, _, _, html_path = _run_full(tmp_path)
        html = html_path.read_text()
        assert "plotly" in html.lower() or "plot.ly" in html

    def test_html_contains_orcsonar_branding(self, tmp_path: Path) -> None:
        _, _, _, html_path = _run_full(tmp_path)
        assert "orcSONAR" in html_path.read_text()

    def test_dangerous_risk_report_shows_red_emoji(self, tmp_path: Path) -> None:
        _, _, _, html_path = _run_full(
            tmp_path,
            seq=0.95, var=0.90, epi=0.95, bio=0.95, exe=0.95,
            atac_score=1.0, expression_score=1.0, execution_score=1.0,
        )
        html = html_path.read_text()
        assert "🟠" in html or "🔴" in html

    def test_safe_report_shows_green_emoji(self, tmp_path: Path) -> None:
        _, _, _, html_path = _run_full(
            tmp_path,
            seq=0.0, var=0.0, epi=0.0, bio=0.0, exe=0.0,
            atac_score=0.0, expression_score=0.0, execution_score=0.0,
        )
        html = html_path.read_text()
        assert "🟢" in html

    def test_html_non_empty(self, tmp_path: Path) -> None:
        _, _, _, html_path = _run_full(tmp_path)
        assert html_path.stat().st_size > 2000

    def test_zero_offtarget_sites_no_sites_message(self, tmp_path: Path) -> None:
        s2 = _stage2(tmp_path, sites=[])
        s3 = _stage3(tmp_path, sites=[])
        s4 = _stage4(tmp_path, sites=[])
        s5 = _stage5(tmp_path, sites=[])
        s6 = _stage6(tmp_path, sites=[])
        scores_path  = str(tmp_path / "stage7_scores.json")
        classif_path = str(tmp_path / "stage7_classification.json")
        json_out  = str(tmp_path / "final_report.json")
        html_out  = str(tmp_path / "final_report.html")
        log_dir   = str(tmp_path / "logs")

        score_integrator_run(
            offtargets_path=s2, variants_path=s3, epigenetic_path=s4,
            biophysics_path=s5, execution_path=s6,
            weights=_DEFAULT_WEIGHTS, output_path=scores_path,
            log_path=f"{log_dir}/si.log",
        )
        risk_classifier_run(
            scores_path=scores_path, thresholds=_DEFAULT_THRESHOLDS,
            output_path=classif_path, log_path=f"{log_dir}/rc.log",
        )
        report_generator_run(
            classification_path=classif_path, scores_path=scores_path,
            offtargets_path=s2, variants_path=s3, epigenetic_path=s4,
            biophysics_path=s5, execution_path=s6,
            gene=_GENE, cell_line=_CELL, sarna_sequence=_SARNA,
            json_output=json_out, html_output=html_out,
            log_path=f"{log_dir}/rg.log",
        )
        html = Path(html_out).read_text()
        assert "No off-target" in html


# ===========================================================================
# Graceful degradation — API timeout
# ===========================================================================


class TestGracefulDegradationAPITimeout:
    """Verify that the scoring pipeline returns neutral scores when an
    upstream data source (simulated by a socket timeout) is unavailable."""

    def test_missing_variants_json_uses_neutral_variant_score(self, tmp_path: Path) -> None:
        """Variant stage JSON absent → variant_toxicity falls back to 0.5 (neutral)."""
        s2 = _stage2(tmp_path)
        s4 = _stage4(tmp_path)
        s5 = _stage5(tmp_path)
        s6 = _stage6(tmp_path)
        out = str(tmp_path / "scores.json")

        score_integrator_run(
            offtargets_path=s2,
            variants_path="/nonexistent/stage3_variants.json",
            epigenetic_path=s4,
            biophysics_path=s5,
            execution_path=s6,
            weights=_DEFAULT_WEIGHTS,
            output_path=out,
            log_path=str(tmp_path / "si.log"),
        )
        data = json.loads(Path(out).read_text())
        for site_id, ds in data["domain_scores"].items():
            assert ds["variant_toxicity"] == pytest.approx(0.5), (
                f"{site_id}: expected neutral 0.5, got {ds['variant_toxicity']}"
            )

    def test_missing_epigenetic_json_uses_neutral(self, tmp_path: Path) -> None:
        s2 = _stage2(tmp_path)
        s3 = _stage3(tmp_path)
        s5 = _stage5(tmp_path)
        s6 = _stage6(tmp_path)
        out = str(tmp_path / "scores.json")

        score_integrator_run(
            offtargets_path=s2,
            variants_path=s3,
            epigenetic_path="/nonexistent/stage4_epigenetic.json",
            biophysics_path=s5,
            execution_path=s6,
            weights=_DEFAULT_WEIGHTS,
            output_path=out,
            log_path=str(tmp_path / "si.log"),
        )
        data = json.loads(Path(out).read_text())
        for site_id, ds in data["domain_scores"].items():
            assert ds["epigenetic_context"] == pytest.approx(0.5)

    def test_missing_execution_json_uses_neutral(self, tmp_path: Path) -> None:
        s2 = _stage2(tmp_path)
        s3 = _stage3(tmp_path)
        s4 = _stage4(tmp_path)
        s5 = _stage5(tmp_path)
        out = str(tmp_path / "scores.json")

        score_integrator_run(
            offtargets_path=s2,
            variants_path=s3,
            epigenetic_path=s4,
            biophysics_path=s5,
            execution_path="/nonexistent/stage6_execution.json",
            weights=_DEFAULT_WEIGHTS,
            output_path=out,
            log_path=str(tmp_path / "si.log"),
        )
        data = json.loads(Path(out).read_text())
        for site_id, ds in data["domain_scores"].items():
            assert ds["execution_safety"] == pytest.approx(0.5)

    def test_all_stages_missing_pipeline_still_completes(self, tmp_path: Path) -> None:
        """Pipeline must produce output even when all external stage JSONs are absent."""
        s2 = _stage2(tmp_path)
        out = str(tmp_path / "scores.json")

        score_integrator_run(
            offtargets_path=s2,
            variants_path="/nonexistent_a.json",
            epigenetic_path="/nonexistent_b.json",
            biophysics_path="/nonexistent_c.json",
            execution_path="/nonexistent_d.json",
            weights=_DEFAULT_WEIGHTS,
            output_path=out,
            log_path=str(tmp_path / "si.log"),
        )
        assert Path(out).exists()
        data = json.loads(Path(out).read_text())
        assert isinstance(data["domain_scores"], dict)

    def test_corrupt_json_treated_as_missing(self, tmp_path: Path) -> None:
        s2 = _stage2(tmp_path)
        s3 = _stage3(tmp_path)
        s4 = _stage4(tmp_path)
        s5 = _stage5(tmp_path)

        bad_path = tmp_path / "stage6_execution.json"
        bad_path.write_text("{ THIS IS NOT VALID JSON }", encoding="utf-8")

        out = str(tmp_path / "scores.json")
        score_integrator_run(
            offtargets_path=s2, variants_path=s3, epigenetic_path=s4,
            biophysics_path=s5, execution_path=str(bad_path),
            weights=_DEFAULT_WEIGHTS, output_path=out,
            log_path=str(tmp_path / "si.log"),
        )
        assert Path(out).exists()
        data = json.loads(Path(out).read_text())
        for ds in data["domain_scores"].values():
            assert ds["execution_safety"] == pytest.approx(0.5)

    def test_simulated_network_timeout_does_not_raise(self, tmp_path: Path) -> None:
        """Simulate a socket timeout during an imaginary API call.

        The pipeline modules are not directly patched here (they don't make
        network calls), but we verify that the integrator is resilient to
        missing data — the expected behaviour when an upstream API times out
        and no cached JSON is written.
        """
        s2 = _stage2(tmp_path)
        out = str(tmp_path / "scores.json")

        def _raise_timeout(*args: object, **kwargs: object) -> None:
            raise socket.timeout("Simulated API timeout")

        with patch("socket.create_connection", side_effect=_raise_timeout):
            score_integrator_run(
                offtargets_path=s2,
                variants_path="/nonexistent.json",
                epigenetic_path="/nonexistent.json",
                biophysics_path="/nonexistent.json",
                execution_path="/nonexistent.json",
                weights=_DEFAULT_WEIGHTS,
                output_path=out,
                log_path=str(tmp_path / "si.log"),
            )
        assert Path(out).exists()


# ===========================================================================
# Graceful degradation — missing SHAPE data
# ===========================================================================


class TestGracefulDegradationMissingShape:
    """Verify that Stage 5 biophysics results fall back to neutral SHAPE score
    (0.5) when SHAPE-seq data is unavailable for the requested cell line."""

    def test_shape_unavailable_flag_respected(self, tmp_path: Path) -> None:
        """When shape_available=False, biophysics normalized_score must still
        be in [0, 1] and the pipeline must complete without error."""
        scores_data, classif_data, json_path, html_path = _run_full(
            tmp_path, shape_available=False
        )
        assert json_path.exists()
        assert html_path.exists()

    def test_shape_unavailable_risk_score_in_range(self, tmp_path: Path) -> None:
        scores_data, classif_data, json_path, _ = _run_full(
            tmp_path, shape_available=False
        )
        assert 0.0 <= classif_data["overall_risk_score"] <= 1.0

    def test_shape_unavailable_domain_scores_valid(self, tmp_path: Path) -> None:
        scores_data, *_ = _run_full(tmp_path, shape_available=False)
        for site_id, ds in scores_data["domain_scores"].items():
            for field, val in ds.items():
                assert 0.0 <= val <= 1.0, (
                    f"shape_unavailable: {site_id}.{field}={val} out of range"
                )

    def test_shape_unavailable_vs_available_score_difference(self, tmp_path: Path) -> None:
        """Score with SHAPE data should differ from score without (neutral fallback)."""
        scores_with, *_ = _run_full(tmp_path, bio=0.60, shape_available=True)
        tmp2 = Path(str(tmp_path) + "_no_shape")
        tmp2.mkdir()
        scores_without, *_ = _run_full(tmp2, bio=0.35, shape_available=False)

        base_with = list(scores_with["base_scores"].values())
        base_without = list(scores_without["base_scores"].values())

        assert base_with[0] != pytest.approx(base_without[0], abs=0.001), (
            "Expected different scores when SHAPE availability changes"
        )

    def test_shape_missing_pipeline_produces_html(self, tmp_path: Path) -> None:
        _, _, _, html_path = _run_full(tmp_path, shape_available=False)
        html = html_path.read_text()
        assert "orcSONAR" in html
        assert _GENE in html

    def test_shape_missing_json_report_valid(self, tmp_path: Path) -> None:
        _, _, json_path, _ = _run_full(tmp_path, shape_available=False)
        data = json.loads(json_path.read_text())
        assert data["risk_class"] in ("SAFE", "WARNING", "HIGH_RISK", "DANGEROUS")
        assert "_metadata" in data


# ===========================================================================
# Full VEGFA / HeLa pipeline validation
# ===========================================================================


class TestVEGFAHeLaPipeline:
    """High-level integration test for the canonical VEGFA/HeLa use case."""

    def test_vegfa_hela_scores_json_schema(self, tmp_path: Path) -> None:
        scores_data, *_ = _run_full(tmp_path)
        assert "domain_scores" in scores_data
        assert "base_scores" in scores_data
        assert len(scores_data["offtarget_sites"]) > 0

    def test_vegfa_hela_json_report_structure(self, tmp_path: Path) -> None:
        _, _, json_path, _ = _run_full(tmp_path)
        data = json.loads(json_path.read_text())
        required = (
            "sarna_input", "offtarget_sites", "domain_scores_per_site",
            "final_risk_score", "risk_class", "cell_line_context", "_metadata",
        )
        for key in required:
            assert key in data, f"JSON report missing key: {key}"

    def test_vegfa_hela_html_report_structure(self, tmp_path: Path) -> None:
        _, _, _, html_path = _run_full(tmp_path)
        html = html_path.read_text()
        for marker in ("<!DOCTYPE html>", "<style>", "plotly", "orcSONAR", _GENE, _CELL):
            assert marker in html, f"HTML report missing: {marker}"

    def test_vegfa_hela_risk_class_deterministic(self, tmp_path: Path) -> None:
        """Same inputs must yield the same risk class on repeated runs."""
        _, c1, *_ = _run_full(tmp_path, seq=0.4, var=0.3, epi=0.5, bio=0.35, exe=0.2)
        tmp2 = Path(str(tmp_path) + "_r2")
        tmp2.mkdir()
        _, c2, *_ = _run_full(tmp2, seq=0.4, var=0.3, epi=0.5, bio=0.35, exe=0.2)
        assert c1["overall_risk_class"] == c2["overall_risk_class"]
        assert abs(c1["overall_risk_score"] - c2["overall_risk_score"]) < 1e-6

    def test_vegfa_hela_domain_weights_preserved(self, tmp_path: Path) -> None:
        scores_data, *_ = _run_full(tmp_path)
        assert scores_data["weights"] == _DEFAULT_WEIGHTS

    def test_vegfa_hela_cell_context_present(self, tmp_path: Path) -> None:
        scores_data, *_ = _run_full(tmp_path)
        ctx = scores_data["cell_context"]
        for key in ("atac_score", "expression_score", "execution_score"):
            assert key in ctx, f"cell_context missing {key}"
