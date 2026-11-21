"""Run the Part B stages in order for a single parcel analysis."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace
from datetime import date

from app.analytics import causes, crops, edo_signal, kbw, open_meteo, soil_moisture, spi, vegetation_signal, vulnerability
from app.analytics.models import AnalysisContext, AnalysisRequest, WeatherData
from app.contracts.common import SourceResult, SourceStatus
from app.contracts.errors import ParcelNotFound
from app.contracts.geo import GeoBundle, GeoProvider, GeoRequest, KbwSoilCategory
from app.contracts.report import Metric, Report, Signal
from app.recommendations import engine
from app.recommendations import texts_pl as text
from app.reports import builder


def _signals(
    weather: SourceResult[WeatherData],
    bundle: GeoBundle,
    crop: str,
    analysis_date: date,
    soil_category: KbwSoilCategory | None,
    metrics: list[Metric],
) -> list[Signal]:
    weather_summaries = {
        SourceStatus.OK: text.WEATHER_AVAILABLE,
        SourceStatus.PARTIAL: text.WEATHER_COVERAGE_INCOMPLETE,
        SourceStatus.MISSING: text.WEATHER_UNAVAILABLE,
    }
    ids = [source.source_id for source in weather.provenance]
    soil_ids = [item.source_id for item in weather.provenance if item.url == open_meteo.ARCHIVE_URL]
    return [
        Signal(code="weather", status=weather.status, summary_pl=weather_summaries[weather.status], metrics=metrics),
        spi.assess(weather.data, analysis_date, ids),
        soil_moisture.anomaly(weather.data, analysis_date, soil_ids),
        vegetation_signal.interpret(
            bundle.vegetation.data,
            crop,
            analysis_date,
            soil_category=soil_category,
            source_ids=[item.source_id for item in bundle.vegetation.provenance],
            status=bundle.vegetation.status,
        ),
        edo_signal.interpret(bundle.edo, analysis_date),
    ]


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
    metrics = causes.weather_metrics(weather, assessment)
    history, signals = await asyncio.gather(
        asyncio.to_thread(kbw.history, weather.data, soil_category, req.crop_code, req.analysis_date),
        asyncio.to_thread(_signals, weather, bundle, req.crop_code, req.analysis_date, soil_category, metrics),
    )
    historical_risk = vulnerability.assess(
        history,
        bundle.vegetation.data,
        req.analysis_date,
        weather_sources=[item.source_id for item in weather.provenance],
        vegetation_sources=[item.source_id for item in bundle.vegetation.provenance],
    )
    context = AnalysisContext(req, parcel, crop, weather, bundle, assessment, history, metrics, signals, historical_risk)

    progress(text.PROGRESS_CAUSES)
    context = replace(context, causes=causes.rank(context))
    progress(text.PROGRESS_RECOMMENDATIONS)
    context = replace(context, recommendations=engine.run(context))
    progress(text.PROGRESS_REPORT)
    return builder.build(context)
