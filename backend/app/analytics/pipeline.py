"""Run the Part B stages in order for a single parcel analysis."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace
from datetime import date

from app.analytics import causes, crops, edo_signal, irrigation, kbw, open_meteo, periods, season
from app.analytics import soil_moisture, spi, vegetation_signal, vulnerability, water_balance, weather as weather_provider
from app.analytics.models import AnalysisContext, AnalysisRequest, WeatherData
from app.config import analysis_today
from app.contracts.common import SourceResult, SourceStatus
from app.contracts.errors import ParcelNotFound
from app.contracts.geo import GeoBundle, GeoProvider, GeoRequest, KbwSoilCategory
from app.contracts.report import Metric, Report, Signal
from app.recommendations import engine
from app.recommendations import texts_pl as text
from app.reports import builder


async def _irrigation_context(ctx: AnalysisContext) -> AnalysisContext:
    req = ctx.request
    if not req.include_irrigation or season.mode(req.analysis_date) == "off_season":
        return ctx

    start = periods.for_year(req.analysis_date.year)[0].start
    balance = await asyncio.to_thread(water_balance.run, ctx.weather.data, ctx.crop, ctx.geo.soil.data, start, req.analysis_date)
    if balance is None or balance.centre.observations[-1].day != req.analysis_date:
        return replace(ctx, irrigation=irrigation.advise(None, None, req.analysis_date))

    latest = balance.centre.observations[-1]
    forecast = None
    if req.analysis_date == analysis_today() and latest.depletion_mm < latest.raw_mm:
        forecast = await open_meteo.fetch_forecast(ctx.parcel.centroid_lat, ctx.parcel.centroid_lon)
    advice = irrigation.advise(balance, forecast.data if forecast else None, req.analysis_date)
    ids = list(dict.fromkeys(item.source_id for source in (ctx.weather, ctx.geo.soil) for item in source.provenance))
    metrics = [
        Metric(code="taw", label_pl=text.IRRIGATION_TAW, value=balance.centre.taw_mm, unit="mm", source_ids=ids),
        Metric(code="raw", label_pl=text.IRRIGATION_RAW, value=latest.raw_mm, unit="mm", source_ids=ids),
        Metric(code="depletion", label_pl=text.IRRIGATION_DEPLETION, value=latest.depletion_mm, unit="mm", source_ids=ids),
        Metric(code="stress_days", label_pl=text.IRRIGATION_STRESS_DAYS, value=balance.stress_days, source_ids=ids),
    ]
    return replace(ctx, irrigation=advice, irrigation_metrics=metrics, forecast=forecast)


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


async def run_analysis(
    req: AnalysisRequest, geo: GeoProvider, progress: Callable[[str], None],
    *, on_geo: Callable[[GeoBundle], None] | None = None,
) -> Report:
    crop = crops.load()[req.crop_code]
    progress(text.PROGRESS_PARCEL)
    parcels = await geo.find_parcels(req.parcel_id)
    parcel = next((item for item in parcels if item.parcel_id.casefold() == req.parcel_id.casefold()), None)
    if parcel is None:
        raise ParcelNotFound("No parcel matched the requested ID")

    progress(text.PROGRESS_DATA)
    weather, bundle = await asyncio.gather(
        weather_provider.fetch_weather(parcel.centroid_lat, parcel.centroid_lon, req.analysis_date),
        geo.collect(GeoRequest(parcel=parcel, analysis_date=req.analysis_date)),
    )
    if on_geo is not None:
        on_geo(bundle)
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
    context = await _irrigation_context(context)
    context = replace(context, recommendations=[*context.recommendations, *engine.irrigation_recommendations(context)])
    progress(text.PROGRESS_REPORT)
    return builder.build(context)
