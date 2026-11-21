from datetime import date, timedelta
from pathlib import Path
import sqlite3
from unittest.mock import AsyncMock

import pytest

from app.analytics import imgw_weather, kbw, open_meteo, periods, weather
from app.analytics.models import WeatherData
from app.contracts.common import SourceResult, SourceStatus


@pytest.fixture
def station_archive(tmp_path: Path) -> Path:
    archive = tmp_path / "synop.sqlite"
    # Synthetic observations for archive selection and field propagation only.
    first = date(2023, 4, 1)
    with sqlite3.connect(archive) as db:
        db.executescript("""
            CREATE TABLE station (code INTEGER, name TEXT, lat REAL, lon REAL);
            CREATE TABLE observation (
                station INTEGER, day INTEGER, precipitation_mm REAL, temperature_mean_c REAL, sunshine_h REAL
            );
            CREATE TABLE input (url TEXT, fetched_at TEXT);
            INSERT INTO station VALUES (1, 'Stacja bliska', 52.3, 17.7);
            INSERT INTO station VALUES (2, 'Stacja z pełnym okresem', 52.4, 17.8);
            INSERT INTO input VALUES ('https://example.org', '2026-11-21T18:00:00+00:00');
        """)
        db.executemany(
            "INSERT INTO observation VALUES (?, ?, ?, ?, ?)",
            ((station, (first + timedelta(days=i)).toordinal(), 0, 17, sun)
             for station, sun in ((1, None), (2, 7)) for i in range(62)),
        )
    return archive


@pytest.mark.asyncio
async def test_station_fallback_assesses_the_period_and_ignores_future_days(monkeypatch, station_archive):
    end = date(2023, 5, 31)
    monkeypatch.setattr(open_meteo, "fetch_weather", AsyncMock(return_value=SourceResult[WeatherData](
        status=SourceStatus.MISSING, notes_pl=["Limit archiwum."],
    )))
    read = imgw_weather.read_weather
    monkeypatch.setattr(imgw_weather, "read_weather", lambda *args: read(*args, path=station_archive))

    selected = await weather.fetch_weather(52.3, 17.7, end)
    assert selected.status is SourceStatus.PARTIAL
    assert len(selected.data.days) == 61
    assert max(selected.data.days) == end
    assert "Stacja z pełnym okresem" in selected.provenance[0].name
    assert selected.provenance[0].source_id == imgw_weather.SOURCE_ID
    assert selected.provenance[0].live is False
    assert selected.notes_pl[0] == "Limit archiwum."
    assert selected.data.days[end].soil_moisture_0_to_7cm is None
    assert selected.data.days[end].et0_mm is None
    assert kbw.assess(selected.data, "I", "spring_cereals", end).kbw_mm is not None
    assert kbw.history(selected.data, "I", "spring_cereals", end).assessed_years == (2023,)


def test_absent_station_archive_allows_analysis_to_continue(tmp_path):
    day = date(2023, 5, 31)
    result = imgw_weather.read_weather(52.3, 17.7, day, periods.latest_completed(day), tmp_path / "absent.sqlite")
    assert result.status is SourceStatus.MISSING
