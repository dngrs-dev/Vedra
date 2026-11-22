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
from app.recommendations import texts_pl as text
from app.reports import site_maps
from app.reports.charts import monthly_risk_svg
from app.reports.recommendation_groups import group_actions

TEMPLATES = Path(__file__).with_name("templates")


def _format_value(value) -> str:
    if value is None:
        return text.PDF_MISSING
    if isinstance(value, Range):
        estimate = _format_value(value.mid)
        if value.low is not None and value.high is not None:
            return f"{estimate} ({_format_value(value.low)}–{_format_value(value.high)})"
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


def render_html(report: Report, map_png: bytes | None = None) -> str:
    chart = monthly_risk_svg(report)
    actions = []
    for action in group_actions(report.recommendations):
        site_map, coordinates = site_maps.render(report.parcel.geometry_wgs84, action.sites)
        actions.append((action, _data_url(site_map.encode(), "image/svg+xml") if site_map else None, coordinates))
    return _environment().get_template("report.html.j2").render(
        report=report,
        actions=actions,
        map_url=_data_url(map_png, "image/png") if map_png else None,
        chart_url=_data_url(chart.encode(), "image/svg+xml") if chart else None,
        category_labels=text.PDF_CATEGORY_LABELS,
        status_labels=text.PDF_STATUS_LABELS,
        confidence_labels=text.PDF_CONFIDENCE_LABELS,
    )


def render(report: Report, map_png: bytes | None = None) -> bytes:
    # WeasyPrint's Pango libraries are supplied by the Docker image or local platform.
    from weasyprint import CSS, HTML

    return HTML(string=render_html(report, map_png)).write_pdf(stylesheets=[CSS(filename=TEMPLATES / "report.css")])
