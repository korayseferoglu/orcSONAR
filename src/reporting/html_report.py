"""Interactive HTML report generation for orcSONAR (Stage 7).

Renders a premium dark-theme report using Jinja2 templates.  Per-site
domain score radar charts are driven by Plotly.js (CDN) for in-browser
interactivity.  The generated HTML is self-contained (CSS inlined) and
suitable as input to ``pdf_report.generate_pdf_report``.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from loguru import logger

from src.core.models import DomainScores, FinalReport
from src.scoring.classifier import RiskClass, classify

_TEMPLATES_DIR: Path = Path(__file__).parent / "templates"
_ORCSONAR_VERSION: str = "0.1.0"

_DEFAULT_WEIGHTS: dict[str, float] = {
    "sequence_specificity": 0.20,
    "variant_toxicity":     0.15,
    "epigenetic_context":   0.20,
    "biophysics_structure": 0.25,
    "execution_safety":     0.20,
}

_RISK_COLORS: dict[str, str] = {
    "SAFE":      "#22c55e",
    "WARNING":   "#eab308",
    "HIGH_RISK": "#f97316",
    "DANGEROUS": "#ef4444",
}

_RISK_EMOJIS: dict[str, str] = {
    "SAFE":      "🟢",
    "WARNING":   "🟡",
    "HIGH_RISK": "🟠",
    "DANGEROUS": "🔴",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _weighted_score(scores: DomainScores) -> float:
    """Compute weighted domain composite for a single off-target site."""
    return (
        scores.sequence_specificity * _DEFAULT_WEIGHTS["sequence_specificity"]
        + scores.variant_toxicity   * _DEFAULT_WEIGHTS["variant_toxicity"]
        + scores.epigenetic_context * _DEFAULT_WEIGHTS["epigenetic_context"]
        + scores.biophysics_structure * _DEFAULT_WEIGHTS["biophysics_structure"]
        + scores.execution_safety   * _DEFAULT_WEIGHTS["execution_safety"]
    )


def _radar_chart_json(scores: DomainScores, site_risk: str) -> str:
    """Build a Plotly.js scatterpolar config as a JSON string.

    Args:
        scores: Normalised domain scores for one off-target site.
        site_risk: Risk class string used to colour the chart fill.

    Returns:
        JSON string containing ``trace``, ``layout``, and ``config`` keys.
    """
    color = _RISK_COLORS.get(site_risk, "#818cf8")
    # Parse hex to rgba components
    r_hex, g_hex, b_hex = color[1:3], color[3:5], color[5:7]
    r, g, b = int(r_hex, 16), int(g_hex, 16), int(b_hex, 16)
    fill_color = f"rgba({r},{g},{b},0.20)"

    cats = ["Sequence", "Variant", "Epigenetic", "Biophysics", "Execution"]
    vals = [
        round(scores.sequence_specificity, 4),
        round(scores.variant_toxicity, 4),
        round(scores.epigenetic_context, 4),
        round(scores.biophysics_structure, 4),
        round(scores.execution_safety, 4),
    ]

    trace = {
        "type": "scatterpolar",
        "r": vals + [vals[0]],
        "theta": cats + [cats[0]],
        "fill": "toself",
        "fillcolor": fill_color,
        "line": {"color": color, "width": 2},
        "mode": "lines+markers",
        "marker": {"color": color, "size": 5},
        "hovertemplate": "%{theta}: %{r:.3f}<extra></extra>",
    }

    layout: dict[str, Any] = {
        "polar": {
            "bgcolor": "rgba(255,255,255,0.02)",
            "radialaxis": {
                "visible": True,
                "range": [0, 1],
                "color": "#475569",
                "gridcolor": "rgba(255,255,255,0.06)",
                "tickfont": {"size": 8, "color": "#64748b"},
                "tickvals": [0.25, 0.5, 0.75, 1.0],
            },
            "angularaxis": {
                "color": "#94a3b8",
                "gridcolor": "rgba(255,255,255,0.06)",
                "tickfont": {"size": 11},
            },
        },
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"color": "#e2e8f0", "family": "Inter, system-ui, sans-serif"},
        "margin": {"t": 15, "b": 15, "l": 55, "r": 55},
        "height": 290,
        "showlegend": False,
    }

    config: dict[str, Any] = {
        "displayModeBar": False,
        "responsive": True,
        "staticPlot": False,
    }

    return json.dumps({"trace": trace, "layout": layout, "config": config})


def _build_sites(report: FinalReport) -> list[dict[str, Any]]:
    """Combine off-target site metadata with domain scores for the template.

    Args:
        report: Completed orcSONAR analysis result.

    Returns:
        List of site dicts, sorted by descending weighted score.
    """
    site_map: dict[str, Any] = {site.site_id: site for site in report.offtarget_sites}

    # A site with metadata but no score disappears from the report entirely —
    # the same class of silent loss as Bulgu-2, one layer up. Say so.
    orphans = set(site_map) - set(report.domain_scores_per_site)
    if orphans:
        logger.warning(
            f"html_report: {len(orphans)} off-target site(s) have no domain scores and "
            f"will not appear in the report, e.g. {sorted(orphans)[:3]}"
        )

    rows: list[dict[str, Any]] = []
    for site_id, scores in report.domain_scores_per_site.items():
        w_score = _weighted_score(scores)
        risk = classify(w_score)
        info = site_map.get(site_id)
        # Parse the key only when the site object is absent (reports built from
        # scores alone). site_id layout is pinned by test_site_id_layout.
        parts = site_id.split(":")

        rows.append(
            {
                "id": site_id,
                "info": info,
                "gene": info.gene if info else (parts[0] if parts else site_id),
                "transcript_id": info.transcript_id if info else (parts[1] if len(parts) > 1 else ""),
                "scores": scores,
                "weighted_score": round(w_score, 4),
                "risk_class": risk.value,
                "risk_color": _RISK_COLORS[risk.value],
                "risk_emoji": _RISK_EMOJIS[risk.value],
                "chart_json": _radar_chart_json(scores, risk.value),
            }
        )

    rows.sort(key=lambda r: r["weighted_score"], reverse=True)
    return rows


def _read_css() -> str:
    """Read and return the contents of styles.css.

    Returns:
        CSS string, or an empty string if the file is not found.
    """
    css_path = _TEMPLATES_DIR / "styles.css"
    if css_path.exists():
        return css_path.read_text(encoding="utf-8")
    logger.warning("html_report: styles.css not found — report will be unstyled")
    return ""


def _build_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
        keep_trailing_newline=True,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_html_report(
    report: FinalReport,
    output_path: str,
) -> None:
    """Render and save an interactive HTML off-target risk report.

    The output is a self-contained HTML file (CSS inlined, Plotly.js CDN)
    showing the overall risk score, per-site radar charts, and domain score
    breakdowns.

    Args:
        report: Completed orcSONAR analysis result.
        output_path: Destination path for the ``.html`` file.
    """
    env = _build_env()
    template = env.get_template("report.html")

    overall_color = _RISK_COLORS.get(report.risk_class, "#818cf8")
    overall_emoji = _RISK_EMOJIS.get(report.risk_class, "❓")

    html = template.render(
        report=report,
        styles=_read_css(),
        sites=_build_sites(report),
        overall_color=overall_color,
        overall_emoji=overall_emoji,
        risk_colors=_RISK_COLORS,
        risk_emojis=_RISK_EMOJIS,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
        version=_ORCSONAR_VERSION,
    )

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    logger.info(f"html_report: saved → {path} ({path.stat().st_size:,} bytes)")
