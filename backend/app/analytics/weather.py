"""Choose the best available, internally consistent weather series for KBW."""
from __future__ import annotations

import asyncio
from datetime import date, timedelta

from app.analytics import imgw_weather, open_meteo, periods
from app.analytics.evapotranspiration import etp_period
from app.analytics.models import Period, WeatherData
from app.contracts.common import SourceResult, SourceStatus
from app.recommendations import texts_pl as text


def _covers_period(weather: WeatherData | None, period: Period) -> bool:
    if weather is None:
        return False
    for offset in range((period.end - period.start).days + 1):
        row = weather.days.get(period.start + timedelta(days=offset))
        if row is None or row.precipitation_mm is None:
            return False
    return etp_period(weather, period.start, period.end) is not None


async def fetch_weather(lat: float, lon: float, analysis_date: date) -> SourceResult[WeatherData]:
    modeled = await open_meteo.fetch_weather(lat, lon, analysis_date)
    if modeled.status is SourceStatus.OK:
        return modeled
    period = periods.latest_completed(analysis_date) or periods.for_year(analysis_date.year - 1)[-1]
    if _covers_period(modeled.data, period):
        return modeled
    observed = await asyncio.to_thread(imgw_weather.read_weather, lat, lon, analysis_date, period)
    if observed.data is None:
        return modeled
    if modeled.data is not None and not _covers_period(observed.data, period):
        if len(modeled.data.days) >= len(observed.data.days):
            return modeled
    # Keep one source for the KBW series. Mixing precipitation from models and stations
    # across dates would change the meaning of the ten-year risk comparison.
    archive_notes = [note for note in modeled.notes_pl if note != text.WEATHER_RECENT_MODEL]
    return observed.model_copy(update={"notes_pl": [*archive_notes, *observed.notes_pl]})
