"""Run the Part B stages in order for a single parcel analysis."""
from __future__ import annotations

import asyncio
from collections.abc import Callable

from app.analytics import crops, kbw, open_meteo
from app.analytics.models import AnalysisContext, AnalysisRequest, KbwResult, WeatherData
from app.contracts.common import SourceResult
from app.contracts.errors import ParcelNotFound
from app.contracts.geo import GeoProvider, GeoRequest
from app.contracts.report import Cause, Metric, Report
from app.recommendations import texts_pl as text
from app.reports import builder


def _weather_metrics(weather: SourceResult[WeatherData], assessment: KbwResult) -> list[Metric]:
    period = assessment.period
    if period is None or assessment.kbw_mm is None or weather.data is None:
        return []

    # A numeric KBW result guarantees complete precipitation within its period (kbw.py).
    precipitation = sum(
        row.precipitation_mm for day, row in weather.data.days.items() if period.start <= day <= period.end
    )
    source_ids = [source.source_id for source in weather.provenance]
    return [
        Metric(code="precipitation", label_pl=text.PRECIPITATION_LABEL, value=precipitation, unit="mm", source_ids=source_ids),
        Metric(
            code="potential_evapotranspiration",
            label_pl=text.ETP_LABEL,
            # IUNG equation (1): ETP = precipitation - KBW (see evapotranspiration.py).
            value=precipitation - assessment.kbw_mm,
            unit="mm",
            source_ids=source_ids,
        ),
    ]


def _causes(assessment: KbwResult, metrics: list[Metric]) -> list[Cause]:
    # The sign of the physical water balance determines whether the weather inputs show a deficit.
    if assessment.kbw_mm is None or assessment.kbw_mm >= 0 or not metrics:
        return []
    return [Cause(
        code="meteorological_deficit",
        title_pl=text.WEATHER_DEFICIT_TITLE,
        explanation_pl=text.WEATHER_DEFICIT_EXPLANATION,
        evidence=metrics,
    )]


async def run_analysis(req: AnalysisRequest, geo: GeoProvider, progress: Callable[[str], None]) -> Report:
    crop = crops.load()[req.crop_code]
    progress(text.PROGRESS_PARCEL)
    parcels = await geo.find_parcels(req.parcel_id)
    parcel = next((item for item in parcels if item.parcel_id.casefold() == req.parcel_id.casefold()), None)
    if parcel is None:
        raise ParcelNotFound("No parcel matched the requested ID")

    progress(text.PROGRESS_DATA)
    weather, bundle = await asyncio.gather(
        open_meteo.fetch_weather(parcel.centroid_lat, parcel.centroid_lon, req.analysis_date),
        geo.collect(GeoRequest(parcel=parcel, analysis_date=req.analysis_date)),
    )
    soil_category = bundle.soil.data.kbw_category if bundle.soil.data is not None else None

    progress(text.PROGRESS_ASSESSMENT)
    assessment = kbw.assess(weather.data, soil_category, req.crop_code, req.analysis_date)
    history = await asyncio.to_thread(kbw.history, weather.data, soil_category, req.crop_code, req.analysis_date)

    progress(text.PROGRESS_CAUSES)
    metrics = _weather_metrics(weather, assessment)
    causes = _causes(assessment, metrics)

    progress(text.PROGRESS_REPORT)
    return builder.build(AnalysisContext(req, parcel, crop, weather, bundle, assessment, history, metrics, causes))
