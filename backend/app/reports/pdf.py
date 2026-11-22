"""Render saved reports as PDF.

WeasyPrint renders the HTML and CSS templates when its native Pango libraries are present, as in the
Docker image. Elsewhere, e.g. a plain Windows Python install, the matplotlib renderer in pdf_basic
produces the same sections, so a PDF is always available.
"""
from __future__ import annotations

import logging
from base64 import b64encode
from collections.abc import Sequence
from functools import cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.contracts.report import Report
from app.recommendations import texts_pl as text
from app.reports import grouping, pdf_basic
from app.reports.charts import monthly_risk_svg
from app.reports.combined import combine
from app.reports.formatting import display_value, source_time

TEMPLATES = Path(__file__).with_name("templates")
logger = logging.getLogger(__name__)


@cache
def _environment() -> Environment:
    environment = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(default=True))
    environment.filters["display_value"] = display_value
    environment.filters["source_time"] = source_time
    environment.filters["metric_row"] = lambda metric: (metric.label_pl, grouping.metric_text(metric))
    # The rows and groups are shared with the built-in renderer, so both PDFs show the same content.
    environment.globals.update(
        texts=text,
        group_recommendations=grouping.group_recommendations,
        site_heading=grouping.site_heading,
        parcel_rows=grouping.parcel_rows,
        assessment_rows=grouping.assessment_rows,
        history_year_rows=grouping.history_year_rows,
        irrigation_rows=grouping.irrigation_rows,
        source_lines=grouping.source_lines,
        last_kbw=grouping.last_kbw,
        metric_text=grouping.metric_text,
        overview_columns=grouping.OVERVIEW_COLUMNS,
        overview_row=grouping.overview_row,
        any_varies=lambda items, varies: bool(varies) and any(map(varies, items)),
    )
    return environment


def _data_url(data: bytes, media_type: str) -> str:
    return f"data:{media_type};base64,{b64encode(data).decode('ascii')}"


def _chart_url(report: Report) -> str | None:
    chart = monthly_risk_svg(report)
    return _data_url(chart.encode(), "image/svg+xml") if chart else None


def render_many_html(items: Sequence[tuple[Report, bytes | None]]) -> str:
    """Render one HTML document.

    Several crops of one parcel share a general part and an appendix, with a part per crop between them.
    Otherwise each report is rendered whole, in the given order.
    """
    document = combine(items)
    if document is None:
        entries = [{"report": report, "map_url": _data_url(map_png, "image/png") if map_png else None,
                    "chart_url": _chart_url(report)} for report, map_png in items]
        return _environment().get_template("report.html.j2").render(entries=entries)
    return _environment().get_template("combined.html.j2").render(
        document=document,
        map_url=_data_url(document.map_png, "image/png") if document.map_png else None,
        crops=[{"part": part, "chart_url": _chart_url(part.report)} for part in document.crops],
    )


def render_html(report: Report, map_png: bytes | None = None) -> str:
    return render_many_html([(report, map_png)])


@cache
def weasyprint_available() -> bool:
    """Whether WeasyPrint and its native Pango libraries load on this host. Checked once per process."""
    try:
        import weasyprint  # noqa: F401
    except (ImportError, OSError) as exc:
        logger.warning("WeasyPrint unavailable (%s: %s). PDFs use the built-in renderer.",
                       type(exc).__name__, str(exc).splitlines()[0] if str(exc) else "")
        return False
    return True


def render_many(items: Sequence[tuple[Report, bytes | None]]) -> bytes:
    """Render several reports, for example one per selected crop, as a single PDF."""
    if not weasyprint_available():
        return pdf_basic.render_many(items)
    from weasyprint import CSS, HTML

    return HTML(string=render_many_html(items)).write_pdf(stylesheets=[CSS(filename=TEMPLATES / "report.css")])


def render(report: Report, map_png: bytes | None = None) -> bytes:
    return render_many([(report, map_png)])
