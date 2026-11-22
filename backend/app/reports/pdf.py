"""Render a saved report as a PDF from trusted HTML and CSS templates."""
from __future__ import annotations

from base64 import b64encode
from datetime import datetime
from functools import cache
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import ANALYSIS_TIMEZONE
from app.contracts.common import Range
from app.contracts.report import Report
from app.contracts.scenario import ScenarioLevers, ScenarioReport
from app.recommendations import texts_pl as text
from app.reports.charts import monthly_risk_svg, scenario_svg

TEMPLATES = Path(__file__).with_name("templates")


def _format_value(value) -> str:
    if value is None:
        return text.PDF_MISSING
    if isinstance(value, Range):
        estimate = _format_value(value.mid)
        if value.low is not None and value.high is not None:
            return f"{estimate} ({_format_value(value.low)}-{_format_value(value.high)})"
        return estimate
    if isinstance(value, float):
        # Report formatting precision only. JSON retains the underlying values.
        return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return str(value)


def _source_time(value: datetime) -> str:
    return value.astimezone(ZoneInfo(ANALYSIS_TIMEZONE)).strftime("%Y-%m-%d %H:%M %Z")


@cache
def _environment() -> Environment:
    environment = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(default=True))
    environment.filters["display_value"] = _format_value
    environment.filters["source_time"] = _source_time
    return environment


def _data_url(data: bytes, media_type: str) -> str:
    return f"data:{media_type};base64,{b64encode(data).decode('ascii')}"


RISK_PL = {"low": "niskie", "medium": "umiarkowane", "high": "wysokie"}


def _levers_pl(levers: ScenarioLevers) -> str:
    parts = []
    if levers.retention_mm:
        parts.append(f"retencja krajobrazowa {_format_value(levers.retention_mm)} mm")
    if levers.organic_matter_pct:
        parts.append(f"próchnica +{_format_value(levers.organic_matter_pct)} p.p.")
    if levers.cover_pct:
        parts.append(f"międzyplony/mulcz na {_format_value(levers.cover_pct)}% powierzchni")
    if levers.irrigation_limit_mm:
        parts.append(f"nawadnianie do {_format_value(levers.irrigation_limit_mm)} mm w sezonie "
                     f"(dawki po {_format_value(levers.irrigation_dose_mm)} mm)")
    return ", ".join(parts) or "bez działań"


def _has_action(levers: ScenarioLevers) -> bool:
    return bool(levers.retention_mm or levers.organic_matter_pct or levers.cover_pct or levers.irrigation_limit_mm)


def render_html(report: Report, map_png: bytes | None = None, scenarios: ScenarioReport | None = None) -> str:
    chart = monthly_risk_svg(report)
    # "Co jeśli?": the farmer's own variant is shown only when at least one lever is set.
    custom = scenarios.custom if scenarios is not None and _has_action(scenarios.custom.levers) else None
    scenario_chart = scenario_svg(scenarios.baseline, custom) if scenarios is not None else None
    return _environment().get_template("report.html.j2").render(
        report=report,
        map_url=_data_url(map_png, "image/png") if map_png else None,
        chart_url=_data_url(chart.encode(), "image/svg+xml") if chart else None,
        scenarios=scenarios,
        custom=custom,
        custom_levers=_levers_pl(custom.levers) if custom else None,
        scenario_chart_url=_data_url(scenario_chart.encode(), "image/svg+xml") if scenario_chart else None,
        risk_labels=RISK_PL,
        category_labels=text.PDF_CATEGORY_LABELS,
        status_labels=text.PDF_STATUS_LABELS,
        confidence_labels=text.PDF_CONFIDENCE_LABELS,
    )


def render(report: Report, map_png: bytes | None = None, scenarios: ScenarioReport | None = None) -> bytes:
    # WeasyPrint's Pango libraries are supplied by the Docker image or local platform.
    from weasyprint import CSS, HTML

    return HTML(string=render_html(report, map_png, scenarios)).write_pdf(
        stylesheets=[CSS(filename=TEMPLATES / "report.css")])
