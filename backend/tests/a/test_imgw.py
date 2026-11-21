"""imgw.py: historical dates, nearest station, drought-warning filter (network mocked; payload shapes from 2026-11-21)."""
from __future__ import annotations

from datetime import date, datetime, timezone

import httpx
import pytest
import respx

from app.contracts.common import SourceStatus
from app.geo import imgw, uldk
from app.geo.sources import source

REC = ("100206_2.0008.273/23|SRID=2180;POLYGON((523300 480000,523400 480000,523400 480100,523300 480100,"
       "523300 480000))|x|łódzkie|powiat kutnowski|Kutno|r|273/23").split("|")
STATIONS = {"12360": {"id_stacji": "12360", "stacja": "Płock", "lat": 52.588, "lon": 19.726},
            "12295": {"id_stacji": "12295", "stacja": "Białystok", "lat": 53.107, "lon": 23.162}}
SYNOP = [{"id_stacji": "12295", "stacja": "Białystok", "data_pomiaru": "2026-11-21", "godzina_pomiaru": "15",
          "temperatura": "1.9", "wilgotnosc_wzgledna": "82.2", "suma_opadu": "0"},
         {"id_stacji": "12360", "stacja": "Płock", "data_pomiaru": "2026-11-21", "godzina_pomiaru": "15",
          "temperatura": "1.9", "wilgotnosc_wzgledna": "79.8", "suma_opadu": "0"},
         {"id_stacji": "12001", "stacja": "Platforma", "data_pomiaru": "2026-11-21", "godzina_pomiaru": "15"}]
WARN = [{"numer": "21", "zdarzenie": "Susza hydrologiczna", "stopień": "-1", "data_od": "2026-04-17 08:46:51",
         "data_do": "9999-12-31 23:59:59",
         "obszary": [{"wojewodztwo": "łódzkie", "opis": "łódzkie, Warta górna z Liswartą, susza hydrologiczna"},
                     {"wojewodztwo": "opolskie", "opis": "opolskie, Warta górna z Liswartą, susza hydrologiczna"}]},
        {"numer": "5", "zdarzenie": "Wezbranie z przekroczeniem stanów ostrzegawczych", "stopień": "1",
         "data_od": "2026-11-20 10:00:00", "data_do": "2026-11-22 10:00:00",
         "obszary": [{"wojewodztwo": "łódzkie", "opis": "łódzkie, x"}]}]


@pytest.fixture
def parcel():
    return uldk.to_parcel(REC)


@pytest.fixture(autouse=True)
def _stations(monkeypatch):
    monkeypatch.setattr(imgw, "stations", lambda: STATIONS)


@pytest.mark.asyncio
async def test_historical_date_is_missing_with_required_note(parcel):
    res = await imgw.imgw_context(parcel, date(2018, 7, 10))
    assert res.status == SourceStatus.MISSING and res.data is None
    assert res.notes_pl[0].startswith(imgw.HISTORICAL_NOTE_PL)


def test_nearest_observation():
    obs = imgw.nearest_observation(SYNOP, 52.25, 19.36)   # Kutno
    assert obs.station_name == "Płock" and 30 < obs.distance_km < 60
    assert obs.observed_at == datetime(2026, 11, 21, 15, tzinfo=timezone.utc)
    assert obs.relative_humidity_pct == 79.8 and obs.precipitation_mm == 0.0


def test_observation_selection_ignores_invalid_and_future_dates():
    today = date(2026, 11, 21)
    invalid = dict(SYNOP[1], data_pomiaru=None)
    future_polish_day = dict(SYNOP[1], godzina_pomiaru="23")
    obs = imgw.nearest_observation([invalid, future_polish_day, SYNOP[0]], 52.25, 19.36, today)
    assert obs.station_id == "12295"


def test_drought_warnings_filtered_by_voivodeship_and_phenomenon():
    w = imgw.drought_warnings(WARN, "łódzkie")
    assert len(w) == 1 and w[0].number == "21" and w[0].area_pl.startswith("łódzkie")
    assert w[0].valid_from == datetime(2026, 4, 17, 8, 46, 51) and w[0].valid_to is None   # 9999-12-31 = open
    assert imgw.drought_warnings(WARN, "pomorskie") == []


def test_warning_selection_ignores_expired_and_future_alerts(parcel):
    future = dict(WARN[0], data_od="2026-11-22 08:00:00")
    expired = dict(WARN[0], data_do="2026-11-20 08:00:00")
    assert imgw.drought_warnings([future, expired], parcel.voivodeship, date(2026, 11, 21)) == []


@pytest.mark.asyncio
@respx.mock
async def test_today_path(parcel, monkeypatch):
    monkeypatch.setattr(imgw, "today_warsaw", lambda: date(2026, 11, 21))
    respx.get(source("imgw")["synop_url"]).mock(return_value=httpx.Response(200, json=SYNOP))
    respx.get(source("imgw")["warnings_hydro_url"]).mock(return_value=httpx.Response(200, json=WARN))
    res = await imgw.imgw_context(parcel, date(2026, 11, 21))
    assert res.status == SourceStatus.OK
    assert res.data.nearest_synop.station_id == "12360" and len(res.data.drought_warnings) == 1
    assert len(res.provenance) == 2 and all(p.attribution_pl for p in res.provenance)


@pytest.mark.asyncio
@respx.mock
async def test_today_one_endpoint_down_is_partial(parcel, monkeypatch):
    monkeypatch.setattr("asyncio.sleep", _no_sleep)
    monkeypatch.setattr(imgw, "today_warsaw", lambda: date(2026, 11, 21))
    respx.get(source("imgw")["synop_url"]).mock(return_value=httpx.Response(503))
    respx.get(source("imgw")["warnings_hydro_url"]).mock(return_value=httpx.Response(200, json=WARN))
    res = await imgw.imgw_context(parcel, date(2026, 11, 21))
    assert res.status == SourceStatus.PARTIAL and res.data.nearest_synop is None and res.error


async def _no_sleep(_s):
    return None
