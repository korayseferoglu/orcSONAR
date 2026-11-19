"""Unit tests for src/reporting/ — JSON, HTML and PDF report generation."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.core.models import (
    DomainScores,
    FinalReport,
    GenomicRegion,
    OffTargetSite,
    SarnaInput,
)
from src.reporting.html_report import (
    _build_sites,
    _radar_chart_json,
    _read_css,
    _weighted_score,
    generate_html_report,
)
from src.reporting.json_report import _build_payload, save_json_report
from src.reporting.pdf_report import generate_pdf_report

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_REGION = GenomicRegion(chrom="chr1", start=10_000, end=10_100, strand="+")


def _make_input(gene: str = "VEGFA", cell: str = "HeLa") -> SarnaInput:
    return SarnaInput(sequence="GCAACCAUAGCCUCGGCCGC", target_gene=gene, cell_line=cell)


def _make_domain(
    seq: float = 0.1,
    var: float = 0.2,
    epi: float = 0.3,
    bio: float = 0.4,
    exc: float = 0.15,
) -> DomainScores:
    return DomainScores(
        sequence_specificity=seq,
        variant_toxicity=var,
        epigenetic_context=epi,
        biophysics_structure=bio,
        execution_safety=exc,
    )


def _make_site(gene: str = "BRCA1", tid: str = "ENST00000001") -> OffTargetSite:
    return OffTargetSite(
        gene=gene,
        transcript_id=tid,
        region=_REGION,
        seed_match_type="perfect",
        mismatches=0,
        alignment_score=1.0,
    )


def _make_report(
    *,
    risk_score: float = 0.45,
    risk_class: str = "WARNING",
    n_sites: int = 2,
) -> FinalReport:
    sites = [_make_site(f"GENE{i}", f"ENST{i:08d}") for i in range(n_sites)]
    # Key off the model's own site_id rather than a hand-written literal, so the
    # scores cannot be keyed differently from the sites they describe — which is
    # the failure this file's join tests are meant to detect (AUDIT.md Bulgu-2).
    domain_map = {
        site.site_id: _make_domain(
            seq=0.1 * (i + 1),
            var=0.2,
            epi=0.3,
            bio=0.4,
            exc=0.1,
        )
        for i, site in enumerate(sites)
    }
    return FinalReport(
        sarna_input=_make_input(),
        offtarget_sites=sites,
        domain_scores_per_site=domain_map,
        final_risk_score=risk_score,
        risk_class=risk_class,  # type: ignore[arg-type]
        cell_line_context="Chromatin is moderately accessible in HeLa.",
    )


# ===========================================================================
# json_report.py
# ===========================================================================


class TestBuildPayload:
    def test_metadata_present(self) -> None:
        data = _build_payload(_make_report())
        assert "_metadata" in data

    def test_version_in_metadata(self) -> None:
        data = _build_payload(_make_report())
        assert "orcsonar_version" in data["_metadata"]

    def test_generated_at_is_iso_string(self) -> None:
        data = _build_payload(_make_report())
        ts: str = data["_metadata"]["generated_at"]
        assert "T" in ts  # ISO 8601 contains T separator

    def test_data_sources_list_non_empty(self) -> None:
        data = _build_payload(_make_report())
        sources = data["_metadata"]["data_sources"]
        assert isinstance(sources, list)
        assert len(sources) > 10

    def test_risk_thresholds_keys(self) -> None:
        data = _build_payload(_make_report())
        thresholds = data["_metadata"]["risk_thresholds"]
        assert set(thresholds.keys()) == {"SAFE", "WARNING", "HIGH_RISK", "DANGEROUS"}

    def test_domain_weights_sum_to_one(self) -> None:
        data = _build_payload(_make_report())
        weights = data["_metadata"]["domain_weights"]
        assert abs(sum(weights.values()) - 1.0) < 1e-9

    def test_report_fields_preserved(self) -> None:
        report = _make_report(risk_score=0.72, risk_class="HIGH_RISK")
        data = _build_payload(report)
        assert data["final_risk_score"] == pytest.approx(0.72)
        assert data["risk_class"] == "HIGH_RISK"

    def test_sarna_input_preserved(self) -> None:
        data = _build_payload(_make_report())
        inp = data["sarna_input"]
        assert inp["target_gene"] == "VEGFA"
        assert inp["cell_line"] == "HeLa"

    def test_domain_scores_per_site_in_output(self) -> None:
        data = _build_payload(_make_report(n_sites=3))
        assert len(data["domain_scores_per_site"]) == 3


class TestSaveJsonReport:
    def test_file_created(self, tmp_path: Path) -> None:
        out = str(tmp_path / "report.json")
        save_json_report(_make_report(), out)
        assert Path(out).exists()

    def test_file_is_valid_json(self, tmp_path: Path) -> None:
        out = str(tmp_path / "report.json")
        save_json_report(_make_report(), out)
        data = json.loads(Path(out).read_text())
        assert isinstance(data, dict)

    def test_parent_dirs_created(self, tmp_path: Path) -> None:
        out = str(tmp_path / "a" / "b" / "c" / "report.json")
        save_json_report(_make_report(), out)
        assert Path(out).exists()

    def test_file_contains_metadata(self, tmp_path: Path) -> None:
        out = str(tmp_path / "report.json")
        save_json_report(_make_report(), out)
        data = json.loads(Path(out).read_text())
        assert "_metadata" in data

    def test_non_ascii_preserved(self, tmp_path: Path) -> None:
        report = _make_report()
        out = str(tmp_path / "report.json")
        save_json_report(report, out)
        raw = Path(out).read_text(encoding="utf-8")
        assert "HeLa" in raw

    def test_indent_formatting(self, tmp_path: Path) -> None:
        out = str(tmp_path / "report.json")
        save_json_report(_make_report(), out)
        raw = Path(out).read_text()
        # Pretty-printed JSON has newlines and 2-space indent
        assert "\n" in raw
        assert "  " in raw

    def test_zero_sites_report(self, tmp_path: Path) -> None:
        report = FinalReport(
            sarna_input=_make_input(),
            offtarget_sites=[],
            domain_scores_per_site={},
            final_risk_score=0.0,
            risk_class="SAFE",
            cell_line_context="",
        )
        out = str(tmp_path / "empty.json")
        save_json_report(report, out)
        data = json.loads(Path(out).read_text())
        assert data["offtarget_sites"] == []


# ===========================================================================
# html_report.py — internal helpers
# ===========================================================================


class TestWeightedScore:
    def test_zero_scores_give_zero(self) -> None:
        ds = DomainScores(
            sequence_specificity=0.0,
            variant_toxicity=0.0,
            epigenetic_context=0.0,
            biophysics_structure=0.0,
            execution_safety=0.0,
        )
        assert _weighted_score(ds) == pytest.approx(0.0)

    def test_all_one_gives_one(self) -> None:
        ds = DomainScores(
            sequence_specificity=1.0,
            variant_toxicity=1.0,
            epigenetic_context=1.0,
            biophysics_structure=1.0,
            execution_safety=1.0,
        )
        assert _weighted_score(ds) == pytest.approx(1.0)

    def test_only_biophysics_gives_025(self) -> None:
        ds = DomainScores(
            sequence_specificity=0.0,
            variant_toxicity=0.0,
            epigenetic_context=0.0,
            biophysics_structure=1.0,
            execution_safety=0.0,
        )
        assert _weighted_score(ds) == pytest.approx(0.25)


class TestRadarChartJson:
    def test_returns_valid_json(self) -> None:
        ds = _make_domain()
        json_str = _radar_chart_json(ds, "WARNING")
        parsed = json.loads(json_str)
        assert "trace" in parsed
        assert "layout" in parsed
        assert "config" in parsed

    def test_trace_type_is_scatterpolar(self) -> None:
        ds = _make_domain()
        parsed = json.loads(_radar_chart_json(ds, "SAFE"))
        assert parsed["trace"]["type"] == "scatterpolar"

    def test_r_values_match_domain_scores(self) -> None:
        ds = _make_domain(seq=0.1, var=0.2, epi=0.3, bio=0.4, exc=0.5)
        parsed = json.loads(_radar_chart_json(ds, "SAFE"))
        r = parsed["trace"]["r"]
        assert r[0] == pytest.approx(0.1)
        assert r[1] == pytest.approx(0.2)
        assert r[2] == pytest.approx(0.3)
        assert r[3] == pytest.approx(0.4)
        assert r[4] == pytest.approx(0.5)
        assert r[5] == pytest.approx(r[0])  # polygon closed

    def test_five_theta_categories(self) -> None:
        parsed = json.loads(_radar_chart_json(_make_domain(), "SAFE"))
        # 5 categories + 1 closing = 6
        assert len(parsed["trace"]["theta"]) == 6

    def test_dangerous_uses_red_color(self) -> None:
        parsed = json.loads(_radar_chart_json(_make_domain(), "DANGEROUS"))
        assert "ef4444" in parsed["trace"]["line"]["color"].lower()

    def test_safe_uses_green_color(self) -> None:
        parsed = json.loads(_radar_chart_json(_make_domain(), "SAFE"))
        assert "22c55e" in parsed["trace"]["line"]["color"].lower()

    def test_display_mode_bar_false(self) -> None:
        parsed = json.loads(_radar_chart_json(_make_domain(), "SAFE"))
        assert parsed["config"]["displayModeBar"] is False


class TestBuildSites:
    def test_returns_list(self) -> None:
        result = _build_sites(_make_report(n_sites=2))
        assert isinstance(result, list)

    def test_length_matches_domain_scores(self) -> None:
        report = _make_report(n_sites=3)
        assert len(_build_sites(report)) == 3

    def test_sorted_by_score_descending(self) -> None:
        report = _make_report(n_sites=3)
        sites = _build_sites(report)
        scores = [s["weighted_score"] for s in sites]
        assert scores == sorted(scores, reverse=True)

    def test_site_has_required_keys(self) -> None:
        sites = _build_sites(_make_report(n_sites=1))
        s = sites[0]
        for key in ("id", "scores", "weighted_score", "risk_class", "risk_color", "risk_emoji", "chart_json"):
            assert key in s

    def test_chart_json_is_valid_json(self) -> None:
        sites = _build_sites(_make_report(n_sites=1))
        parsed = json.loads(sites[0]["chart_json"])
        assert "trace" in parsed

    def test_empty_report_returns_empty_list(self) -> None:
        report = FinalReport(
            sarna_input=_make_input(),
            offtarget_sites=[],
            domain_scores_per_site={},
            final_risk_score=0.0,
            risk_class="SAFE",
            cell_line_context="",
        )
        assert _build_sites(report) == []

    def test_info_populated_when_offtarget_site_exists(self) -> None:
        report = _make_report(n_sites=2)
        sites = _build_sites(report)
        # At least one site should have info populated (gene:transcript matches)
        assert any(s["info"] is not None for s in sites)

    def test_risk_class_reflects_weighted_score(self) -> None:
        # Domain scores near zero → SAFE
        report = FinalReport(
            sarna_input=_make_input(),
            offtarget_sites=[],
            domain_scores_per_site={
                "FAKEGENE:ENST001": DomainScores(
                    sequence_specificity=0.0,
                    variant_toxicity=0.0,
                    epigenetic_context=0.0,
                    biophysics_structure=0.0,
                    execution_safety=0.0,
                )
            },
            final_risk_score=0.0,
            risk_class="SAFE",
            cell_line_context="",
        )
        sites = _build_sites(report)
        assert sites[0]["risk_class"] == "SAFE"


class TestReadCss:
    def test_returns_string(self) -> None:
        css = _read_css()
        assert isinstance(css, str)

    def test_css_non_empty_when_file_exists(self) -> None:
        css = _read_css()
        # styles.css exists in the package
        assert len(css) > 100

    def test_css_contains_root_variables(self) -> None:
        css = _read_css()
        assert ":root" in css

    def test_css_contains_risk_colors(self) -> None:
        css = _read_css()
        assert "--safe" in css
        assert "--dangerous" in css


# ===========================================================================
# html_report.py — generate_html_report
# ===========================================================================


class TestGenerateHtmlReport:
    def test_file_created(self, tmp_path: Path) -> None:
        out = str(tmp_path / "report.html")
        generate_html_report(_make_report(), out)
        assert Path(out).exists()

    def test_file_non_empty(self, tmp_path: Path) -> None:
        out = str(tmp_path / "report.html")
        generate_html_report(_make_report(), out)
        assert Path(out).stat().st_size > 1000

    def test_parent_dirs_created(self, tmp_path: Path) -> None:
        out = str(tmp_path / "sub" / "dir" / "report.html")
        generate_html_report(_make_report(), out)
        assert Path(out).exists()

    def test_contains_orcsonar_title(self, tmp_path: Path) -> None:
        out = str(tmp_path / "report.html")
        generate_html_report(_make_report(), out)
        html = Path(out).read_text()
        assert "orcSONAR" in html

    def test_contains_gene_name(self, tmp_path: Path) -> None:
        out = str(tmp_path / "report.html")
        generate_html_report(_make_report(), out)
        html = Path(out).read_text()
        assert "VEGFA" in html

    def test_contains_cell_line(self, tmp_path: Path) -> None:
        out = str(tmp_path / "report.html")
        generate_html_report(_make_report(), out)
        html = Path(out).read_text()
        assert "HeLa" in html

    def test_contains_sarna_sequence(self, tmp_path: Path) -> None:
        out = str(tmp_path / "report.html")
        generate_html_report(_make_report(), out)
        html = Path(out).read_text()
        assert "GCAACCAUAGCCUCGGCCGC" in html

    def test_contains_risk_score(self, tmp_path: Path) -> None:
        out = str(tmp_path / "report.html")
        generate_html_report(_make_report(risk_score=0.456), out)
        html = Path(out).read_text()
        assert "0.456" in html

    def test_risk_class_displayed(self, tmp_path: Path) -> None:
        out = str(tmp_path / "report.html")
        generate_html_report(_make_report(risk_class="HIGH_RISK", risk_score=0.7), out)
        html = Path(out).read_text()
        assert "HIGH" in html

    def test_plotly_script_tag_present(self, tmp_path: Path) -> None:
        out = str(tmp_path / "report.html")
        generate_html_report(_make_report(), out)
        html = Path(out).read_text()
        assert "plot.ly" in html or "plotly" in html.lower()

    def test_radar_div_per_site(self, tmp_path: Path) -> None:
        out = str(tmp_path / "report.html")
        generate_html_report(_make_report(n_sites=3), out)
        html = Path(out).read_text()
        radar_ids = re.findall(r'id="radar-\d+"', html)
        assert len(radar_ids) >= 3

    def test_css_inlined(self, tmp_path: Path) -> None:
        out = str(tmp_path / "report.html")
        generate_html_report(_make_report(), out)
        html = Path(out).read_text()
        assert "<style>" in html
        assert ":root" in html  # from styles.css

    def test_html5_doctype(self, tmp_path: Path) -> None:
        out = str(tmp_path / "report.html")
        generate_html_report(_make_report(), out)
        html = Path(out).read_text()
        assert html.startswith("<!DOCTYPE html>")

    def test_safe_risk_shows_safe_emoji(self, tmp_path: Path) -> None:
        out = str(tmp_path / "report.html")
        generate_html_report(_make_report(risk_score=0.1, risk_class="SAFE"), out)
        html = Path(out).read_text()
        assert "🟢" in html

    def test_dangerous_risk_shows_red_emoji(self, tmp_path: Path) -> None:
        out = str(tmp_path / "report.html")
        generate_html_report(_make_report(risk_score=0.9, risk_class="DANGEROUS"), out)
        html = Path(out).read_text()
        assert "🔴" in html

    def test_empty_sites_shows_no_sites_message(self, tmp_path: Path) -> None:
        report = FinalReport(
            sarna_input=_make_input(),
            offtarget_sites=[],
            domain_scores_per_site={},
            final_risk_score=0.0,
            risk_class="SAFE",
            cell_line_context="No active chromatin detected.",
        )
        out = str(tmp_path / "empty.html")
        generate_html_report(report, out)
        html = Path(out).read_text()
        assert "No off-target" in html

    def test_footer_contains_data_sources(self, tmp_path: Path) -> None:
        out = str(tmp_path / "report.html")
        generate_html_report(_make_report(), out)
        html = Path(out).read_text()
        assert "COSMIC" in html
        assert "ENCODE" in html

    def test_version_in_output(self, tmp_path: Path) -> None:
        out = str(tmp_path / "report.html")
        generate_html_report(_make_report(), out)
        html = Path(out).read_text()
        assert "0.1.0" in html


# ===========================================================================
# pdf_report.py — generate_pdf_report
# ===========================================================================


class TestGeneratePdfReport:
    def test_pdf_file_created(self, tmp_path: Path) -> None:
        html_path = str(tmp_path / "report.html")
        pdf_path = str(tmp_path / "report.pdf")
        generate_html_report(_make_report(), html_path)
        generate_pdf_report(html_path, pdf_path)
        assert Path(pdf_path).exists()

    def test_pdf_non_empty(self, tmp_path: Path) -> None:
        html_path = str(tmp_path / "report.html")
        pdf_path = str(tmp_path / "report.pdf")
        generate_html_report(_make_report(), html_path)
        generate_pdf_report(html_path, pdf_path)
        assert Path(pdf_path).stat().st_size > 500

    def test_pdf_starts_with_pdf_magic(self, tmp_path: Path) -> None:
        html_path = str(tmp_path / "report.html")
        pdf_path = str(tmp_path / "report.pdf")
        generate_html_report(_make_report(), html_path)
        generate_pdf_report(html_path, pdf_path)
        with open(pdf_path, "rb") as f:
            magic = f.read(5)
        assert magic == b"%PDF-"

    def test_parent_dirs_created(self, tmp_path: Path) -> None:
        html_path = str(tmp_path / "report.html")
        pdf_path = str(tmp_path / "sub" / "out.pdf")
        generate_html_report(_make_report(), html_path)
        generate_pdf_report(html_path, pdf_path)
        assert Path(pdf_path).exists()

    def test_missing_html_raises_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="HTML source not found"):
            generate_pdf_report(str(tmp_path / "nonexistent.html"), str(tmp_path / "out.pdf"))

    def test_output_different_from_html(self, tmp_path: Path) -> None:
        html_path = str(tmp_path / "report.html")
        pdf_path = str(tmp_path / "report.pdf")
        generate_html_report(_make_report(), html_path)
        generate_pdf_report(html_path, pdf_path)
        html_size = Path(html_path).stat().st_size
        pdf_size = Path(pdf_path).stat().st_size
        assert html_size != pdf_size

    def test_zero_sites_report_generates_pdf(self, tmp_path: Path) -> None:
        report = FinalReport(
            sarna_input=_make_input(),
            offtarget_sites=[],
            domain_scores_per_site={},
            final_risk_score=0.0,
            risk_class="SAFE",
            cell_line_context="",
        )
        html_path = str(tmp_path / "empty.html")
        pdf_path = str(tmp_path / "empty.pdf")
        generate_html_report(report, html_path)
        generate_pdf_report(html_path, pdf_path)
        assert Path(pdf_path).stat().st_size > 500


# ===========================================================================
# Integration — full pipeline JSON → HTML → PDF
# ===========================================================================


class TestReportingIntegration:
    def test_full_pipeline_creates_all_three_files(self, tmp_path: Path) -> None:
        report = _make_report(n_sites=3, risk_score=0.72, risk_class="HIGH_RISK")

        json_path = str(tmp_path / "report.json")
        html_path = str(tmp_path / "report.html")
        pdf_path  = str(tmp_path / "report.pdf")

        save_json_report(report, json_path)
        generate_html_report(report, html_path)
        generate_pdf_report(html_path, pdf_path)

        assert Path(json_path).exists()
        assert Path(html_path).exists()
        assert Path(pdf_path).exists()

    def test_json_and_html_share_same_risk_score(self, tmp_path: Path) -> None:
        report = _make_report(risk_score=0.654, risk_class="HIGH_RISK")

        json_path = str(tmp_path / "report.json")
        html_path = str(tmp_path / "report.html")

        save_json_report(report, json_path)
        generate_html_report(report, html_path)

        json_data = json.loads(Path(json_path).read_text())
        html_text = Path(html_path).read_text()

        assert json_data["final_risk_score"] == pytest.approx(0.654)
        assert "0.654" in html_text

    def test_dangerous_report_pipeline(self, tmp_path: Path) -> None:
        report = FinalReport(
            sarna_input=_make_input("TP53", "HeLa"),
            offtarget_sites=[_make_site("BRCA1", "ENST00000001")],
            domain_scores_per_site={
                "BRCA1:ENST00000001": DomainScores(
                    sequence_specificity=0.95,
                    variant_toxicity=0.90,
                    epigenetic_context=0.85,
                    biophysics_structure=0.92,
                    execution_safety=0.88,
                )
            },
            final_risk_score=0.91,
            risk_class="DANGEROUS",
            cell_line_context="High ATAC signal and active transcription detected.",
        )

        html_path = str(tmp_path / "dangerous.html")
        pdf_path  = str(tmp_path / "dangerous.pdf")

        generate_html_report(report, html_path)
        generate_pdf_report(html_path, pdf_path)

        html = Path(html_path).read_text()
        assert "DANGEROUS" in html
        assert "🔴" in html
        assert "TP53" in html
        assert "BRCA1" in html
        assert Path(pdf_path).stat().st_size > 500


class TestUnassessedRunRenders:
    """A run that classified nothing must render as unassessed, not as 0.000/SAFE.

    Audit 2026-11-19, Bulgu 12. The JSON side is pinned in
    ``test_risk_classifier.py``; this covers the Jinja template, which is the
    fragile half — ``report.risk_class|lower`` on ``None`` renders the string
    "none" rather than raising, so a missing guard here fails silently and
    looks like a styling bug instead of a false verdict.
    """

    def test_html_says_not_assessed_and_omits_a_score(self, tmp_path: Path) -> None:
        report = FinalReport(
            sarna_input=_make_input(),
            offtarget_sites=[],
            domain_scores_per_site={},
            final_risk_score=None,
            risk_class=None,
            cell_line_context="No off-target sites were classified.",
        )
        out = str(tmp_path / "report.html")
        generate_html_report(report, out)

        html = Path(out).read_text(encoding="utf-8")
        assert "NOT ASSESSED" in html
        assert "0.000" not in html
        assert ">SAFE<" not in html
        assert "c-none" not in html, "the |lower filter rendered None as a CSS class"

    def test_json_round_trips_an_unassessed_report(self, tmp_path: Path) -> None:
        report = FinalReport(
            sarna_input=_make_input(),
            offtarget_sites=[],
            domain_scores_per_site={},
            final_risk_score=None,
            risk_class=None,
            cell_line_context="No off-target sites were classified.",
        )
        out = str(tmp_path / "report.json")
        save_json_report(report, out)

        payload = json.loads(Path(out).read_text(encoding="utf-8"))
        assert payload["risk_class"] is None
        assert payload["final_risk_score"] is None
