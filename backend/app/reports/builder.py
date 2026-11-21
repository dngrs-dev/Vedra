"""Build the public report from an analysis context."""
from __future__ import annotations

from dataclasses import asdict
from uuid import uuid4

from app.analytics.models import AnalysisContext
from app.contracts.common import Provenance, SourceStatus
from app.contracts.geo import GeoBundle
from app.contracts.report import Assessment, IrrigationAdvice, KbwAssessment, MapLayer, Reference, Report, Signal, Vulnerability
from app.recommendations import texts_pl as text

# The primary ETP and KBW equations are documented in docs/METHODOLOGY.md.
IUNG_KBW_URL = "https://iung.pl/images/wyd/Susza%20rolnicza%20w%20Polsce.pdf"


def _sources(ctx: AnalysisContext) -> tuple[list[Provenance], list[str]]:
    sources = [ctx.weather, *(getattr(ctx.geo, field) for field in GeoBundle.model_fields)]
    records: dict[str, Provenance] = {}
    limitations = [text.KBW_ESTIMATE_NOTE]
    for source in sources:
        limitations.extend(source.notes_pl)
        for item in source.provenance:
            records.setdefault(item.model_dump_json(), item)
    return list(records.values()), list(dict.fromkeys(limitations))


def _vulnerability(ctx: AnalysisContext) -> Vulnerability:
    history = ctx.history
    summary = text.HISTORY_UNAVAILABLE
    if history.assessed_years:
        summary = text.HISTORY_SUMMARY.format(drought=len(history.drought_years), assessed=len(history.assessed_years))
    return Vulnerability(
        summary_pl=summary,
        years_assessed=list(history.assessed_years),
        drought_years=list(history.drought_years),
    )


def build(ctx: AnalysisContext) -> Report:
    sources, limitations = _sources(ctx)
    weather_summaries = {
        SourceStatus.OK: text.WEATHER_AVAILABLE,
        SourceStatus.PARTIAL: text.WEATHER_COVERAGE_INCOMPLETE,
        SourceStatus.MISSING: text.WEATHER_UNAVAILABLE,
    }
    signal = Signal(
        code="weather",
        status=ctx.weather.status,
        summary_pl=weather_summaries[ctx.weather.status],
        metrics=ctx.weather_metrics,
    )
    irrigation = IrrigationAdvice(justified=None, why_pl=text.IRRIGATION_UNAVAILABLE) if ctx.request.include_irrigation else None
    return Report(
        report_id=str(uuid4()),
        parcel=ctx.parcel,
        crop_code=ctx.request.crop_code,
        crop_name_pl=ctx.crop.name_pl,
        analysis_date=ctx.request.analysis_date,
        summary=ctx.assessment.explanation_pl,
        assessment=Assessment(
            kbw=KbwAssessment.model_validate(asdict(ctx.assessment)),
            signals=[signal],
            vulnerability=_vulnerability(ctx),
        ),
        causes=ctx.causes,
        map_layers=[MapLayer(id="parcel", name_pl=text.PARCEL_LAYER_NAME, geojson=ctx.parcel.geometry_wgs84)],
        irrigation=irrigation,
        limitations_pl=limitations,
        data_sources=sources,
        references=[
            Reference(id="kbw_regulation", title_pl=text.KBW_REGULATION_TITLE, url=ctx.crop.source),
            Reference(id="iung_kbw", title_pl=text.IUNG_KBW_TITLE, url=IUNG_KBW_URL),
        ],
    )
