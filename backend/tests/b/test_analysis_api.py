from datetime import date, datetime, timedelta, timezone
from http import HTTPStatus
from time import monotonic, sleep
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.analytics import open_meteo, periods
from app.analytics.models import WeatherData, WeatherDay
from app.api import routes_analyses
from app.api.deps import get_geo_provider
from app.config import settings
from app.contracts.common import Provenance, SourceResult, SourceStatus
from app.contracts.errors import UpstreamUnavailable
from app.contracts.report import Report
from app.fakes.fake_geo import EXAMPLE_PARCEL_ID, EXAMPLE_POINT, FakeGeoProvider
from app.jobs.runner import ANALYSIS_TIMEOUT_S
from app.main import app
from app.recommendations import texts_pl as text

# Historical example date from docs/TEAM_SPLIT.md §7 and the contest date from backend/README.md.
ANALYSIS_DATE = date(2023, 5, 31)
TODAY = date(2026, 11, 21)


def _request(parcel_id: str = EXAMPLE_PARCEL_ID) -> dict:
    return {
        "parcel_id": parcel_id,
        "crop_code": "winter_cereals",
        "analysis_date": ANALYSIS_DATE.isoformat(),
        "include_irrigation": True,
    }


def _poll(client: TestClient, analysis_id: str) -> dict:
    deadline = monotonic() + ANALYSIS_TIMEOUT_S
    while monotonic() < deadline:
        response = client.get(f"/api/analyses/{analysis_id}")
        assert response.status_code == HTTPStatus.OK
        job = response.json()
        if job["status"] in ("done", "error"):
            return job
        # Give the in-process event loop a scheduling turn between test polls.
        sleep(0.01)
    raise AssertionError("Analysis did not finish within the CP1 run budget")


def test_can_analyze_the_parcel_returned_by_map_click(monkeypatch):
    monkeypatch.setattr(routes_analyses, "analysis_today", lambda: TODAY)
    monkeypatch.setattr(settings, "geo_provider", "fake")
    period = periods.latest_completed(ANALYSIS_DATE)
    # Synthetic observations for this regression: consistent sunshine and zero rain.
    start = period.start.replace(day=1)
    days = {
        start + timedelta(days=offset): WeatherDay(precipitation_mm=0, et0_mm=1, temperature_mean_c=20, sunshine_h=7)
        for offset in range((period.end - start).days + 1)
    }
    # The source metadata uses the archive identity and fixtures from Open-Meteo and the contest date.
    weather = SourceResult[WeatherData](
        status=SourceStatus.OK,
        data=WeatherData(*EXAMPLE_POINT, days),
        provenance=[Provenance(
            source_id="open_meteo_archive",
            name=text.OPEN_METEO_ARCHIVE_NAME,
            url=open_meteo.ARCHIVE_URL,
            fetched_at=datetime.combine(TODAY, datetime.min.time(), timezone.utc),
            live=True,
            licence=open_meteo.LICENCE,
        )],
    )
    fetch = AsyncMock(return_value=weather)
    monkeypatch.setattr(open_meteo, "fetch_weather", fetch)

    with TestClient(app) as client:
        lat, lon = EXAMPLE_POINT
        found = client.get("/api/parcels/by-point", params={"lat": lat, "lon": lon})
        assert found.status_code == HTTPStatus.OK
        parcel_id = found.json()["parcel_id"]
        assert client.get("/api/parcels/search", params={"q": parcel_id}).json() == [found.json()]

        started = client.post("/api/analyses", json=_request(parcel_id))
        assert started.status_code == HTTPStatus.ACCEPTED
        job = _poll(client, started.json()["analysis_id"])

    assert job["status"] == "done"
    assert job["progress"] == [
        text.PROGRESS_QUEUED,
        text.PROGRESS_PARCEL,
        text.PROGRESS_DATA,
        text.PROGRESS_ASSESSMENT,
        text.PROGRESS_CAUSES,
        text.PROGRESS_REPORT,
        text.PROGRESS_DONE,
    ]
    report = Report.model_validate(job["report"])
    assert report.parcel.parcel_id == parcel_id
    assert report.assessment.kbw.verdict == "drought"
    assert {item.code for item in report.assessment.signals} == {"weather", "spi", "soil_moisture", "vegetation", "edo"}
    assert report.assessment.confidence == "low"
    assert report.causes[0].evidence[0].value == 0
    assert report.assessment.vulnerability.drought_years == [ANALYSIS_DATE.year]
    assert report.irrigation.why_pl == text.IRRIGATION_UNAVAILABLE
    assert {source.source_id for source in report.data_sources} == {"open_meteo_archive", "fake_geo"}
    fetch.assert_awaited_once_with(lat, lon, ANALYSIS_DATE)


def test_missing_weather_still_yields_a_report(monkeypatch):
    monkeypatch.setattr(routes_analyses, "analysis_today", lambda: TODAY)
    monkeypatch.setattr(settings, "geo_provider", "fake")
    fetch = AsyncMock(return_value=SourceResult[WeatherData](
        status=SourceStatus.MISSING, notes_pl=[text.WEATHER_ARCHIVE_UNAVAILABLE], error="HTTP 429"
    ))
    monkeypatch.setattr(open_meteo, "fetch_weather", fetch)

    with TestClient(app) as client:
        started = client.post("/api/analyses", json=_request())
        job = _poll(client, started.json()["analysis_id"])

    assert job["status"] == "done"
    report = Report.model_validate(job["report"])
    assert report.assessment.kbw.verdict == "unavailable"
    assert text.WEATHER_ARCHIVE_UNAVAILABLE in report.limitations_pl
    assert report.causes == []


def test_reports_polish_errors_for_invalid_requests_and_missing_resources(monkeypatch):
    monkeypatch.setattr(routes_analyses, "analysis_today", lambda: TODAY)
    monkeypatch.setattr(settings, "geo_provider", "fake")

    with TestClient(app) as client:
        invalid = client.get("/api/parcels/search", params={"q": "?"})
        assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert invalid.json()["detail"] == text.PARCEL_QUERY_INVALID

        unknown = client.get("/api/analyses/unknown")
        assert unknown.status_code == HTTPStatus.NOT_FOUND
        assert unknown.json()["detail"] == text.ANALYSIS_NOT_FOUND

        future = client.post("/api/analyses", json={**_request(), "analysis_date": (TODAY + timedelta(days=1)).isoformat()})
        assert future.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert future.json()["detail"] == text.ANALYSIS_DATE_RANGE


def test_geo_outage_returns_service_unavailable(monkeypatch):
    class OfflineGeoProvider(FakeGeoProvider):
        async def find_parcels(self, query):
            raise UpstreamUnavailable("Simulated upstream outage")

    monkeypatch.setitem(app.dependency_overrides, get_geo_provider, OfflineGeoProvider)
    with TestClient(app) as client:
        response = client.get("/api/parcels/search", params={"q": EXAMPLE_PARCEL_ID})

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json()["detail"] == text.GEO_SERVICE_UNAVAILABLE
