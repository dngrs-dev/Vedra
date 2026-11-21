import asyncio
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest

from app.analytics import open_meteo as meteo
from app.analytics.models import WeatherData, WeatherDay
from app.contracts.common import Provenance, SourceResult, SourceStatus
from app.contracts.errors import UpstreamUnavailable
from app.fakes.fake_geo import EXAMPLE_POINT
from app.recommendations.texts_pl import WEATHER_ARCHIVE_RATE_LIMITED, WEATHER_ARCHIVE_UNAVAILABLE, WEATHER_RECENT_MODEL

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
    if soil:
        for column in meteo.DAILY_SOIL_VARIABLES:
            daily[column] = [0.3] * len(days)
    return httpx.Response(200, json={"daily": daily})


@pytest.fixture(autouse=True)
def source_setup(monkeypatch):
    cache = {}
    monkeypatch.setattr(meteo.cache, "get", cache.get)
    monkeypatch.setattr(meteo.cache, "set", cache.__setitem__)
    monkeypatch.setattr(meteo, "analysis_today", lambda: TODAY)
    monkeypatch.setattr(meteo, "_archive_retry_at", 0.0)


@pytest.mark.asyncio
async def test_historical_archive_decodes_daily_values_and_caches_by_cell(monkeypatch):
    monkeypatch.setattr(meteo, "ARCHIVE_START", HISTORICAL_DAY)
    future = HISTORICAL_DAY + timedelta(days=1)
    remote = AsyncMock(return_value=_response([HISTORICAL_DAY, future], soil=True))
    monkeypatch.setattr(meteo.http, "get", remote)

    result, simultaneous = await asyncio.gather(
        meteo.fetch_weather(*EXAMPLE_POINT, HISTORICAL_DAY),
        meteo.fetch_weather(*EXAMPLE_POINT, HISTORICAL_DAY),
    )
    assert simultaneous.data == result.data
    assert result.status is SourceStatus.OK
    assert list(result.data.days) == [HISTORICAL_DAY]
    row = result.data.days[HISTORICAL_DAY]
    assert row.precipitation_mm == 0
    assert row.sunshine_h == 1.5
    assert row.daylight_h == 9
    assert row.soil_moisture_0_to_7cm == pytest.approx(0.3)
    assert result.provenance[0].live
    assert remote.call_args.args == (meteo.ARCHIVE_URL,)
    params = remote.call_args.kwargs["params"]
    assert set(params["daily"].split(",")) == set(meteo.DAILY_VARIABLES) | set(meteo.DAILY_SOIL_VARIABLES)
    assert "hourly" not in params
    assert params["end_date"] == HISTORICAL_DAY

    lat, lon = EXAMPLE_POINT
    cached = await meteo.fetch_weather(lat + 0.01, lon, HISTORICAL_DAY)
    assert cached.data == result.data
    assert cached.provenance[0].fetched_at == result.provenance[0].fetched_at
    assert cached.provenance[0].live is False
    remote.assert_awaited_once()


@pytest.mark.asyncio
async def test_archive_fetches_only_the_new_tail_and_truncates_older_reports(monkeypatch):
    first = HISTORICAL_DAY
    second = first + timedelta(days=1)
    third = second + timedelta(days=1)
    monkeypatch.setattr(meteo, "ARCHIVE_START", first)
    remote = AsyncMock(side_effect=[
        _response([first, second], soil=True),
        _response([third], soil=True),
    ])
    monkeypatch.setattr(meteo.http, "get", remote)

    await meteo.fetch_weather(*EXAMPLE_POINT, second)
    extended = await meteo.fetch_weather(*EXAMPLE_POINT, third)
    assert list(extended.data.days) == [first, second, third]
    assert [item.live for item in extended.provenance] == [False, True]
    assert remote.call_args.kwargs["params"]["start_date"] == third

    older = await meteo.fetch_weather(*EXAMPLE_POINT, first)
    assert list(older.data.days) == [first]
    assert older.provenance[0].data_period == f"{first}..{first}"
    assert older.provenance[0].live is False
    assert remote.await_count == 2


@pytest.mark.asyncio
async def test_archive_reuses_a_complete_legacy_cache_entry(monkeypatch):
    first = HISTORICAL_DAY
    monkeypatch.setattr(meteo, "ARCHIVE_START", first)
    lat, lon = (round(coord, meteo.CELL_DECIMAL_PLACES) for coord in EXAMPLE_POINT)
    record = meteo._decode(_response([first], soil=True).json(), first, first, lat, lon,
                           meteo.DAILY_VARIABLES | meteo.DAILY_SOIL_VARIABLES)
    source = Provenance(
        source_id="open_meteo_archive", name="Open-Meteo", url=meteo.ARCHIVE_URL,
        fetched_at=datetime.combine(TODAY, datetime.min.time(), tzinfo=timezone.utc),
        live=True, data_period=f"{first}..{first}", licence=meteo.LICENCE,
    )
    legacy_key = meteo.cache.make_key(meteo.CACHE_NAMESPACE, lat=lat, lon=lon, end=first)
    meteo.cache.set(legacy_key, SourceResult[WeatherData](status=SourceStatus.OK, data=record, provenance=[source]))
    remote = AsyncMock()
    monkeypatch.setattr(meteo.http, "get", remote)

    result = await meteo.fetch_weather(*EXAMPLE_POINT, first)

    assert result.status is SourceStatus.OK
    assert isinstance(result.data.days[first], WeatherDay)
    assert result.provenance[0].live is False
    migrated_key = meteo.cache.make_key(meteo.CACHE_NAMESPACE, lat=lat, lon=lon, aggregation="daily")
    assert meteo.cache.get(migrated_key).data == record
    remote.assert_not_awaited()


@pytest.mark.asyncio
async def test_rate_limit_preserves_cached_weather_and_observes_retry_after(monkeypatch):
    first = HISTORICAL_DAY
    second = first + timedelta(days=1)
    monkeypatch.setattr(meteo, "ARCHIVE_START", first)
    response = httpx.Response(429, request=httpx.Request("GET", meteo.ARCHIVE_URL), headers={"Retry-After": "60"})

    async def get(url, *, params, **_):
        if params["end_date"] == first:
            return _response([first], soil=True)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise UpstreamUnavailable("Rate limited in simulated test") from exc

    remote = AsyncMock(side_effect=get)
    monkeypatch.setattr(meteo.http, "get", remote)
    await meteo.fetch_weather(*EXAMPLE_POINT, first)
    partial = await meteo.fetch_weather(*EXAMPLE_POINT, second)
    assert partial.status is SourceStatus.PARTIAL
    assert list(partial.data.days) == [first]
    assert partial.notes_pl == [WEATHER_ARCHIVE_RATE_LIMITED]
    assert partial.provenance[0].live is False

    lat, lon = EXAMPLE_POINT
    missing = await meteo.fetch_weather(lat + 1, lon, second)
    assert missing.status is SourceStatus.MISSING
    assert missing.notes_pl == [WEATHER_ARCHIVE_RATE_LIMITED]
    cached = await meteo.fetch_weather(*EXAMPLE_POINT, first)
    assert cached.status is SourceStatus.OK
    assert remote.await_count == 2


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
