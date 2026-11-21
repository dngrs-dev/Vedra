from datetime import date
from http import HTTPStatus
from pathlib import Path
from time import monotonic, sleep
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.analytics import open_meteo
from app.analytics.models import WeatherData
from app.api import routes_analyses
from app.config import settings
from app.contracts.common import SourceResult, SourceStatus
from app.contracts.report import Report
from app.fakes.fake_geo import EXAMPLE_PARCEL_ID, FakeGeoProvider
from app.jobs.runner import ANALYSIS_TIMEOUT_S
from app.main import app
from app.reports import pdf

SAMPLE = Path(__file__).resolve().parents[1] / "fixtures" / "sample_report.json"


def test_native_renderer_produces_a_pdf_when_pango_is_available():
    report = Report.model_validate_json(SAMPLE.read_bytes())
    try:
        from weasyprint import HTML  # noqa: F401
    except OSError as exc:
        pytest.skip(f"Native Pango unavailable: {exc}")
    assert pdf.render(report).startswith(b"%PDF-")


def test_saved_report_survives_restart_and_pdf_is_cached_without_map(monkeypatch):
    # Contest date from backend/README.md. Weather and the map failure are simulated.
    analysis_date = date(2026, 11, 21)
    monkeypatch.setattr(routes_analyses, "analysis_today", lambda: analysis_date)
    monkeypatch.setattr(settings, "geo_provider", "fake")
    monkeypatch.setattr(open_meteo, "fetch_weather", AsyncMock(return_value=SourceResult[WeatherData](
        status=SourceStatus.MISSING
    )))
    map_builder = AsyncMock(side_effect=RuntimeError("Simulated map outage"))
    monkeypatch.setattr(FakeGeoProvider, "render_static_map", map_builder)
    pdf_calls = []

    def render(report, map_png):
        pdf_calls.append((report.report_id, map_png))
        return b"%PDF-test"

    monkeypatch.setattr(pdf, "render", render)
    with TestClient(app) as client:
        submitted = client.post("/api/analyses", json={"parcel_id": EXAMPLE_PARCEL_ID, "crop_code": "winter_cereals",
                                                       "analysis_date": analysis_date.isoformat()})
        assert submitted.status_code == HTTPStatus.ACCEPTED
        analysis_id = submitted.json()["analysis_id"]
        deadline = monotonic() + ANALYSIS_TIMEOUT_S
        while monotonic() < deadline:
            response = client.get(f"/api/analyses/{analysis_id}")
            if response.json()["status"] in {"done", "error"}:
                break
            sleep(0.01)  # Schedule the background task between test polls.
        assert response.json()["status"] == "done"
        report = response.json()["report"]

    with TestClient(app) as client:
        assert client.get(f"/api/reports/{report['report_id']}").json() == report
        assert client.get(f"/api/analyses/{analysis_id}").json()["report"] == report
        first = client.get(f"/api/analyses/{analysis_id}/report.pdf")
        second = client.get(f"/api/analyses/{analysis_id}/report.pdf")

    assert first.status_code == second.status_code == HTTPStatus.OK
    assert first.headers["content-type"] == "application/pdf"
    assert first.content == second.content == b"%PDF-test"
    assert pdf_calls == [(report["report_id"], None)]
    map_builder.assert_awaited_once()
