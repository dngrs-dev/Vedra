"""Fetch date-bounded weather from Open-Meteo and cache archive responses."""
from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from itertools import groupby
from math import isfinite
from statistics import mean
from time import monotonic

from app.analytics.models import Forecast, WeatherData, WeatherDay
from app.config import ANALYSIS_TIMEZONE, analysis_today
from app.contracts.common import Provenance, SourceResult, SourceStatus
from app.contracts.errors import UpstreamUnavailable
from app.core import cache, http
from app.recommendations import texts_pl as text

# Historical Weather API: https://open-meteo.com/en/docs/historical-weather-api
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
ARCHIVE_MODEL = "era5_seamless"
ARCHIVE_LAG = timedelta(days=5)
ARCHIVE_RESOLUTION = "0,25° (ERA5), 0,1° (ERA5-Land)"
SOIL_VARIABLES = (
    "soil_moisture_0_to_7cm",
    "soil_moisture_7_to_28cm",
    "soil_moisture_28_to_100cm",
)
# Forecast API: https://open-meteo.com/en/docs
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_DAYS = 7
DAILY_VARIABLES = {
    "precipitation_sum": "precipitation_mm",
    "et0_fao_evapotranspiration": "et0_mm",
    "temperature_2m_mean": "temperature_mean_c",
    "temperature_2m_max": "temperature_max_c",
    "temperature_2m_min": "temperature_min_c",
    "sunshine_duration": "sunshine_h",
    "daylight_duration": "daylight_h",
}
# The Open-Meteo APIs return daily sunshine and daylight in seconds. One hour is 3,600 SI seconds.
HOUR_VARIABLES = {"sunshine_duration", "daylight_duration"}
SECONDS_PER_HOUR = 3_600
# The baseline, cache namespace and cell precision are specified in docs/PART_B_ANALYTICS_PRODUCT.md §3.
ARCHIVE_START = date(1991, 1, 1)
CACHE_NAMESPACE = "an.openmeteo"
CELL_DECIMAL_PLACES = 1
# Use the shared HTTP client's nominal timeout. One upstream attempt per source (Part B, §3).
REQUEST_TIMEOUT_S = 10.0
# Data licence: https://open-meteo.com/en/license
LICENCE = "CC BY 4.0"


def _value(column: list | None, index: int) -> float | None:
    if column is None or index >= len(column):
        return None
    value = column[index]
    return float(value) if isinstance(value, (int, float)) and isfinite(value) else None


def _soil_means(hourly: dict, start: date, end: date) -> dict[date, dict[str, float | None]]:
    result = {}
    timestamps = hourly.get("time", [])
    for timestamp, positions in groupby(range(len(timestamps)), key=lambda idx: timestamps[idx].partition("T")[0]):
        day = date.fromisoformat(timestamp)
        if not start <= day <= end:
            continue
        indices = list(positions)
        means: dict[str, float | None] = {}
        for variable in SOIL_VARIABLES:
            values = [_value(hourly.get(variable), index) for index in indices]
            means[variable] = mean(values) if all(value is not None for value in values) else None
        result[day] = means
    return result


def _decode(payload: dict, start: date, end: date, lat: float, lon: float) -> WeatherData:
    daily = payload["daily"]
    soil_by_day = _soil_means(payload.get("hourly", {}), start, end)
    days: dict[date, WeatherDay] = {}
    for index, timestamp in enumerate(daily["time"]):
        day = date.fromisoformat(timestamp)
        if not start <= day <= end:
            continue
        fields = {}
        for variable, target in DAILY_VARIABLES.items():
            value = _value(daily.get(variable), index)
            if value is not None and variable in HOUR_VARIABLES:
                value /= SECONDS_PER_HOUR
            fields[target] = value
        soil = soil_by_day.get(day, {})
        if any(value is not None for value in (*fields.values(), *soil.values())):
            days[day] = WeatherDay(**fields, **soil)
    return WeatherData(lat, lon, dict(sorted(days.items())))


async def _fetch(
    url: str, *, lat: float, lon: float, start: date, end: date, query: dict, archive: bool = False
) -> SourceResult[WeatherData]:
    started = monotonic()
    unavailable = text.WEATHER_ARCHIVE_UNAVAILABLE if archive else text.WEATHER_FORECAST_UNAVAILABLE
    params = {"latitude": lat, "longitude": lon, "timezone": ANALYSIS_TIMEZONE, "daily": ",".join(DAILY_VARIABLES)}
    params.update(query)
    try:
        response = await http.get(url, params=params, timeout=REQUEST_TIMEOUT_S, retries=0)
        stamp = datetime.now(timezone.utc)
        data = await asyncio.to_thread(lambda: _decode(response.json(), start, end, lat, lon))
    except (UpstreamUnavailable, KeyError, ValueError, TypeError, AttributeError) as exc:
        return SourceResult[WeatherData](
            status=SourceStatus.MISSING, notes_pl=[unavailable], error=str(exc), elapsed_s=monotonic() - started
        )
    if not data.days:
        return SourceResult[WeatherData](
            status=SourceStatus.MISSING, notes_pl=[unavailable], elapsed_s=monotonic() - started
        )

    fields = (*DAILY_VARIABLES.values(), *SOIL_VARIABLES) if archive else tuple(DAILY_VARIABLES.values())
    complete = len(data.days) == (end - start).days + 1 and all(
        getattr(row, field) is not None for row in data.days.values() for field in fields
    )
    provenance = Provenance(
        source_id="open_meteo_archive" if archive else "open_meteo_forecast",
        name=text.OPEN_METEO_ARCHIVE_NAME if archive else text.OPEN_METEO_FORECAST_NAME,
        url=url,
        fetched_at=stamp,
        live=True,
        data_period=f"{min(data.days).isoformat()}..{max(data.days).isoformat()}",
        resolution=ARCHIVE_RESOLUTION if archive else None,
        licence=LICENCE,
        attribution_pl=text.OPEN_METEO_ATTRIBUTION,
    )
    return SourceResult[WeatherData](
        status=SourceStatus.OK if complete else SourceStatus.PARTIAL,
        data=data,
        provenance=[provenance],
        notes_pl=[] if complete else [text.WEATHER_COVERAGE_INCOMPLETE],
        elapsed_s=monotonic() - started,
    )


async def _archive(lat: float, lon: float, end: date) -> SourceResult[WeatherData]:
    started = monotonic()
    key = cache.make_key(CACHE_NAMESPACE, lat=lat, lon=lon, end=end)
    cached = await asyncio.to_thread(cache.get, key)
    if isinstance(cached, SourceResult) and cached.data is not None:
        return cached.model_copy(update={
            "provenance": [item.model_copy(update={"live": False}) for item in cached.provenance],
            "elapsed_s": monotonic() - started,
        })

    result = await _fetch(
        ARCHIVE_URL,
        lat=lat,
        lon=lon,
        start=ARCHIVE_START,
        end=end,
        query={"start_date": ARCHIVE_START, "end_date": end, "models": ARCHIVE_MODEL, "hourly": ",".join(SOIL_VARIABLES)},
        archive=True,
    )
    if result.status is SourceStatus.OK:
        await asyncio.to_thread(cache.set, key, result)
    return result


async def fetch_weather(lat: float, lon: float, analysis_date: date) -> SourceResult[WeatherData]:
    today = analysis_today()
    end = min(today, analysis_date)
    if end < ARCHIVE_START:
        return SourceResult[WeatherData](status=SourceStatus.MISSING, notes_pl=[text.WEATHER_BEFORE_ARCHIVE])

    lat, lon = round(lat, CELL_DECIMAL_PLACES), round(lon, CELL_DECIMAL_PLACES)
    archive_end = min(end, today - ARCHIVE_LAG)
    if archive_end == end:
        return await _archive(lat, lon, end)

    recent_start = archive_end + timedelta(days=1)
    archive, recent = await asyncio.gather(
        _archive(lat, lon, archive_end),
        _fetch(
            FORECAST_URL,
            lat=lat,
            lon=lon,
            start=recent_start,
            end=end,
            # The forecast endpoint requires at least one forecast day when using past_days.
            query={"past_days": (today - recent_start).days, "forecast_days": 1},
        ),
    )
    days = dict(archive.data.days) if archive.data is not None else {}
    notes = [*archive.notes_pl, *recent.notes_pl]
    if recent.data is not None:
        days.update(recent.data.days)
        notes.append(text.WEATHER_RECENT_MODEL)
    return SourceResult[WeatherData](
        status=SourceStatus.PARTIAL if days else SourceStatus.MISSING,
        data=WeatherData(lat, lon, days) if days else None,
        provenance=[*archive.provenance, *recent.provenance],
        notes_pl=list(dict.fromkeys(notes)),
        error=archive.error or recent.error,
        elapsed_s=max(archive.elapsed_s or 0, recent.elapsed_s or 0),
    )


async def fetch_forecast(lat: float, lon: float) -> SourceResult[Forecast]:
    today = analysis_today()
    return await _fetch(
        FORECAST_URL,
        lat=lat,
        lon=lon,
        start=today,
        end=today + timedelta(days=FORECAST_DAYS - 1),
        query={"forecast_days": FORECAST_DAYS},
    )
