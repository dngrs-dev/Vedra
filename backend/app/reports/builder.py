"""Build the public report from an analysis context."""
from __future__ import annotations

from dataclasses import asdict
from uuid import uuid4

from app.analytics import uncertainty
from app.analytics.models import AnalysisContext
from app.contracts.common import Provenance
from app.contracts.geo import GeoBundle
from app.contracts.report import Assessment, IrrigationAdvice, KbwAssessment, MapLayer, Reference, Report
from app.recommendations import texts_pl as text

# The primary ETP and KBW equations are documented in docs/METHODOLOGY.md.
IUNG_KBW_URL = "https://iung.pl/images/wyd/Susza%20rolnicza%20w%20Polsce.pdf"


def _sources(ctx: AnalysisContext) -> list[Provenance]:
    sources = [ctx.weather, *(getattr(ctx.geo, field) for field in GeoBundle.model_fields)]
    records: dict[str, Provenance] = {}
    for source in sources:
        for item in source.provenance:
            records.setdefault(item.model_dump_json(), item)
    return list(records.values())


def build(ctx: AnalysisContext) -> Report:
    confidence, limitations = uncertainty.assess(ctx)
    off_season = ctx.assessment.verdict == "off_season"
    irrigation = None
    if ctx.request.include_irrigation:
        explanation = text.IRRIGATION_OFF_SEASON if off_season else text.IRRIGATION_UNAVAILABLE
        irrigation = IrrigationAdvice(justified=None, why_pl=explanation)
    return Report(
        report_id=str(uuid4()),
        parcel=ctx.parcel,
        crop_code=ctx.request.crop_code,
        crop_name_pl=ctx.crop.name_pl,
        analysis_date=ctx.request.analysis_date,
        summary=ctx.assessment.explanation_pl,
        assessment=Assessment(
            kbw=KbwAssessment.model_validate(asdict(ctx.assessment)),
            confidence=confidence,
            signals=ctx.signals,
            vulnerability=ctx.vulnerability,
        ),
        causes=ctx.causes,
        map_layers=[MapLayer(id="parcel", name_pl=text.PARCEL_LAYER_NAME, geojson=ctx.parcel.geometry_wgs84)],
        irrigation=irrigation,
        limitations_pl=limitations,
        data_sources=_sources(ctx),
        references=[
            Reference(id="kbw_regulation", title_pl=text.KBW_REGULATION_TITLE, url=ctx.crop.source),
            Reference(id="iung_kbw", title_pl=text.IUNG_KBW_TITLE, url=IUNG_KBW_URL),
            # Sources for the report's SPI and satellite interpretation (docs/METHODOLOGY.md).
            Reference(id="wmo_spi", title_pl=text.SPI_REFERENCE_TITLE,
                      url="https://www.droughtmanagement.info/literature/WMO_standardized_precipitation_index_user_guide_en_2012.pdf"),
            Reference(id="polsa_vegetation", title_pl=text.POLSA_REFERENCE_TITLE,
                      url="https://polsa.gov.pl/aktywnosci/obserwacja-ziemi/dane-satelitarne/"),
        ],
    )
