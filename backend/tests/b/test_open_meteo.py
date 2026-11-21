from datetime import date, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest

from app.analytics import open_meteo as meteo
from app.contracts.common import SourceStatus
from app.contracts.errors import UpstreamUnavailable
from app.fakes.fake_geo import EXAMPLE_POINT
from app.recommendations.texts_pl import WEATHER_ARCHIVE_UNAVAILABLE, WEATHER_RECENT_MODEL

# Historical example date from docs/TEAM_SPLIT.md §7 and the contest date in backend/README.md.
HISTORICAL_DAY = date(2023, 5, 31)
TODAY = date(2026, 11, 21)


def _response(days: list[date], *, soil: bool = False) -> httpx.Response:
    day_labels = [day.isoformat() for day in days]
    # Values are synthetic CP1 test inputs. The column names come from Open-Meteo's API docs.
    daily = {
        "time": day_labels,
        "precipitation_sum": [0] * len(days),
        "et0_fao_evapotranspiration": [0.64] * len(days),
        "temperature_2m_mean": [5.2] * len(days),
        "temperature_2m_max": [8.6] * len(days),
        "temperature_2m_min": [1.7] * len(days),
        "sunshine_duration": [5_400] * len(days),
        "daylight_duration": [32_400] * len(days),
    }
    data = {"daily": daily}
    if soil:
        data["hourly"] = {"time": [f"{day}T{hour:02}:00" for day in day_labels for hour in range(24)]}
        for column in meteo.SOIL_VARIABLES:
            data["hourly"][column] = [0.2, 0.4] * (len(days) * 12)
    return httpx.Response(200, json=data)


@pytest.fixture(autouse=True)
def source_setup(monkeypatch):
    cache = {}
    monkeypatch.setattr(meteo.cache, "get", cache.get)
    monkeypatch.setattr(meteo.cache, "set", cache.__setitem__)
    monkeypatch.setattr(meteo, "analysis_today", lambda: TODAY)


@pytest.mark.asyncio
async def test_historical_archive_decodes_daily_values_and_caches_by_cell(monkeypatch):
    monkeypatch.setattr(meteo, "ARCHIVE_START", HISTORICAL_DAY)
    future = HISTORICAL_DAY + timedelta(days=1)
    remote = AsyncMock(return_value=_response([HISTORICAL_DAY, future], soil=True))
    monkeypatch.setattr(meteo.http, "get", remote)

    result = await meteo.fetch_weather(*EXAMPLE_POINT, HISTORICAL_DAY)
    assert result.status is SourceStatus.OK
    assert list(result.data.days) == [HISTORICAL_DAY]
    row = result.data.days[HISTORICAL_DAY]
    assert row.precipitation_mm == 0
    assert row.sunshine_h == 1.5
    assert row.daylight_h == 9
    assert row.soil_moisture_0_to_7cm == pytest.approx(0.3)
    assert result.provenance[0].live
    assert remote.call_args.args == (meteo.ARCHIVE_URL,)
    assert remote.call_args.kwargs["params"]["hourly"] == ",".join(meteo.SOIL_VARIABLES)
    assert remote.call_args.kwargs["params"]["end_date"] == HISTORICAL_DAY

    lat, lon = EXAMPLE_POINT
    cached = await meteo.fetch_weather(lat + 0.01, lon, HISTORICAL_DAY)
    assert cached.data == result.data
    assert cached.provenance[0].fetched_at == result.provenance[0].fetched_at
    assert cached.provenance[0].live is False
    remote.assert_awaited_once()


@pytest.mark.asyncio
async def test_recent_weather_survives_archive_failure_without_future_dates(monkeypatch):
    analysis_date = TODAY - timedelta(days=1)
    recent_start = TODAY - meteo.ARCHIVE_LAG + timedelta(days=1)
    days = [recent_start + timedelta(days=offset) for offset in range((TODAY - recent_start).days + 1)]

    async def get(url, **_):
        if url == meteo.ARCHIVE_URL:
            raise UpstreamUnavailable("Rate limited in simulated test")
        return _response(days)

    remote = AsyncMock(side_effect=get)
    monkeypatch.setattr(meteo.http, "get", remote)
    result = await meteo.fetch_weather(*EXAMPLE_POINT, analysis_date)

    assert result.status is SourceStatus.PARTIAL
    assert max(result.data.days) == analysis_date
    assert result.data.days[analysis_date].soil_moisture_0_to_7cm is None
    assert result.notes_pl == [WEATHER_ARCHIVE_UNAVAILABLE, WEATHER_RECENT_MODEL]
    assert result.provenance[0].url == meteo.FORECAST_URL
    forecast = next(call for call in remote.await_args_list if call.args == (meteo.FORECAST_URL,))
    assert forecast.kwargs["params"]["past_days"] == (TODAY - recent_start).days


@pytest.mark.asyncio
async def test_forecast_limits_the_response_to_its_documented_horizon(monkeypatch):
    days = [TODAY + timedelta(days=offset) for offset in range(-1, meteo.FORECAST_DAYS + 1)]
    remote = AsyncMock(return_value=_response(days))
    monkeypatch.setattr(meteo.http, "get", remote)
    result = await meteo.fetch_forecast(*EXAMPLE_POINT)

    assert result.status is SourceStatus.OK
    assert list(result.data.days) == days[1:-1]
    assert remote.call_args.kwargs["params"]["forecast_days"] == meteo.FORECAST_DAYS
