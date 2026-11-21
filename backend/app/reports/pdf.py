"""Render a saved report as a PDF from trusted HTML and CSS templates."""
from __future__ import annotations

from base64 import b64encode
from collections.abc import Sequence
from datetime import datetime
from functools import cache
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import ANALYSIS_TIMEZONE
from app.contracts.common import Range
from app.contracts.report import Report
from app.recommendations import texts_pl as text
from app.reports.charts import monthly_risk_svg

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


def _entry(report: Report, map_png: bytes | None) -> dict:
    chart = monthly_risk_svg(report)
    return {
        "report": report,
        "map_url": _data_url(map_png, "image/png") if map_png else None,
        "chart_url": _data_url(chart.encode(), "image/svg+xml") if chart else None,
    }


def render_many_html(items: Sequence[tuple[Report, bytes | None]]) -> str:
    """Render one HTML document with a section for each report, in the given order."""
    return _environment().get_template("report.html.j2").render(
        entries=[_entry(report, map_png) for report, map_png in items],
        category_labels=text.PDF_CATEGORY_LABELS,
        status_labels=text.PDF_STATUS_LABELS,
        confidence_labels=text.PDF_CONFIDENCE_LABELS,
    )


def render_html(report: Report, map_png: bytes | None = None) -> str:
    return render_many_html([(report, map_png)])


def _write_pdf(html: str) -> bytes:
    # WeasyPrint's Pango libraries are supplied by the Docker image or local platform.
    from weasyprint import CSS, HTML

    return HTML(string=html).write_pdf(stylesheets=[CSS(filename=TEMPLATES / "report.css")])


def render(report: Report, map_png: bytes | None = None) -> bytes:
    return _write_pdf(render_html(report, map_png))


def render_many(items: Sequence[tuple[Report, bytes | None]]) -> bytes:
    """Render several reports, for example one per selected crop, as a single PDF."""
    return _write_pdf(render_many_html(items))
