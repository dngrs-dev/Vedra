import re
from datetime import date
from hashlib import sha256
from http import HTTPStatus
from pathlib import Path
from time import monotonic, sleep
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from matplotlib.patches import Rectangle

from app.analytics import open_meteo
from app.analytics.models import WeatherData
from app.api import routes_analyses
from app.config import settings
from app.contracts.common import SourceResult, SourceStatus
from app.contracts.report import Metric, Recommendation, Report
from app.fakes.fake_geo import EXAMPLE_PARCEL_ID, FakeGeoProvider
from app.jobs.runner import ANALYSIS_TIMEOUT_S
from app.main import app
from app.recommendations import texts_pl
from app.reports import pdf, pdf_basic, site_maps
from app.reports.recommendation_groups import group_actions

SAMPLE = Path(__file__).resolve().parents[1] / "fixtures" / "sample_report.json"


def test_repeated_action_groups_keep_site_evidence_and_outside_caution():
    report = Report.model_validate_json(SAMPLE.read_bytes())
    title, instruction, why, ref = texts_pl.RETENTION_SPOT_TEXTS["depression"]
    common = Metric(code="kbw", label_pl="KBW", value=-120, unit="mm")
    first_evidence = Metric(code="retention_area", label_pl=texts_pl.RETENTION_AREA, value=20, unit="m²")
    next_evidence = first_evidence.model_copy(update={"value": 31})
    first = Recommendation(id="test-1", category="landscape_retention", title_pl=title, action_pl=instruction,
                           why_pl=why, evidence=[common, first_evidence], reference_ids=[ref],
                           geometry=report.parcel.geometry_wgs84)
    second = first.model_copy(update={"id": "test-2", "evidence": [common, next_evidence],
                                      "action_pl": f"{instruction} {texts_pl.RETENTION_OUTSIDE_PARCEL}"})
    unrelated = first.model_copy(update={"id": "test-3", "geometry": None})
    report.recommendations = [first, second, unrelated]

    grouped, separate = group_actions(report.recommendations)
    assert grouped.action_pl == instruction
    assert grouped.evidence == [common]
    assert [site.evidence for site in grouped.sites] == [[first_evidence], [next_evidence]]
    assert [site.number for site in grouped.sites] == [1, 2]
    assert grouped.sites[1].note_pl == texts_pl.RETENTION_OUTSIDE_PARCEL
    assert not separate.sites

    html = pdf.render_html(report)
    assert html.count('class="site-table small"') == 1
    assert html.count(texts_pl.RETENTION_OUTSIDE_PARCEL) == 1
    assert 'data:image/svg+xml' in html
    assert '20 m²' in html and '31 m²' in html
    assert 'Plan wizji w terenie' in html
    assert html.count('class="field-checkbox"') == 2

    report.recommendations = [second, first]
    html = pdf.render_html(report)
    plan = html.split('class="field-plan"', 1)[1].split('</section>', 1)[0]
    assert 'Miejsce 2' in plan
    assert texts_pl.RETENTION_OUTSIDE_PARCEL not in plan


def test_native_renderer_produces_a_pdf_when_pango_is_available():
    report = Report.model_validate_json(SAMPLE.read_bytes())
    try:
        from weasyprint import HTML  # noqa: F401
    except OSError as exc:
        pytest.skip(f"Native Pango unavailable: {exc}")
    assert 'Plan wizji w terenie' not in pdf.render_html(report)
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

    # A previously downloaded PDF must be regenerated in the new layout.
    old_path = settings.db_path.with_suffix(".reports") / "grouped-retention" / f"{sha256(report['report_id'].encode()).hexdigest()}.pdf"
    old_path.parent.mkdir(parents=True, exist_ok=True)
    old_path.write_bytes(b"%PDF-old-layout")
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


def test_several_crops_share_one_combined_pdf(monkeypatch):
    # Several crops selected for one parcel yield one analysis each and a single combined PDF.
    analysis_date = date(2026, 11, 21)
    monkeypatch.setattr(routes_analyses, "analysis_today", lambda: analysis_date)
    monkeypatch.setattr(settings, "geo_provider", "fake")
    monkeypatch.setattr(open_meteo, "fetch_weather", AsyncMock(return_value=SourceResult[WeatherData](
        status=SourceStatus.MISSING
    )))
    map_builder = AsyncMock(return_value=b"\x89PNG-map")
    monkeypatch.setattr(FakeGeoProvider, "render_static_map", map_builder)
    combined_calls = []

    def render_many(items):
        combined_calls.append([report.crop_code for report, _ in items])
        html = pdf.render_many_html(items)
        # General part, one part per crop and the appendix, each part after the first from a new page.
        assert html.count('<article class="report') == len(items) + 2
        assert html.count("next-report") == len(items) + 1
        assert html.count('class="visual map"') == 1
        assert html.count("<h2>Źródła danych</h2>") == 1
        for report, map_png in items:
            assert report.crop_name_pl in html
            assert map_png == b"\x89PNG-map"
        return b"%PDF-combined"

    monkeypatch.setattr(pdf, "render_many", render_many)
    crops = ["winter_cereals", "grain_maize", "potatoes"]
    with TestClient(app) as client:
        ids = []
        for crop in crops:
            submitted = client.post("/api/analyses", json={"parcel_id": EXAMPLE_PARCEL_ID, "crop_code": crop,
                                                           "analysis_date": analysis_date.isoformat()})
            assert submitted.status_code == HTTPStatus.ACCEPTED
            ids.append(submitted.json()["analysis_id"])
        deadline = monotonic() + ANALYSIS_TIMEOUT_S
        pending = set(ids)
        while pending and monotonic() < deadline:
            pending = {item for item in pending
                       if client.get(f"/api/analyses/{item}").json()["status"] not in {"done", "error"}}
            sleep(0.01)  # Schedule the background tasks between test polls.
        assert not pending

        query = "&".join(f"analysis_id={item}" for item in ids)
        first = client.get(f"/api/analyses/report.pdf?{query}")
        second = client.get(f"/api/analyses/report.pdf?{query}&analysis_id={ids[0]}")
        unknown = client.get(f"/api/analyses/report.pdf?{query}&analysis_id=missing")
        empty = client.get("/api/analyses/report.pdf")
        single = client.get(f"/api/analyses/{ids[0]}")

    assert first.status_code == second.status_code == HTTPStatus.OK
    assert first.headers["content-type"] == "application/pdf"
    assert first.content == second.content == b"%PDF-combined"
    assert combined_calls == [crops]
    # One parcel, so its map is rendered once for all crops.
    map_builder.assert_awaited_once()
    assert unknown.status_code == HTTPStatus.NOT_FOUND
    assert empty.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert single.json()["status"] == "done"


def _page_count(document: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page\b(?!s)", document))


def _grouped_retention_report() -> Report:
    """Two retention sites of one action (the second outside the parcel) and an unrelated action."""
    report = Report.model_validate_json(SAMPLE.read_bytes())
    title, instruction, why, ref = texts_pl.RETENTION_SPOT_TEXTS["depression"]
    common = Metric(code="kbw", label_pl="KBW", value=-120, unit="mm")
    area = Metric(code="retention_area", label_pl=texts_pl.RETENTION_AREA, value=20, unit="m²")
    first = Recommendation(id="test-1", category="landscape_retention", title_pl=title, action_pl=instruction,
                           why_pl=why, evidence=[common, area], reference_ids=[ref],
                           geometry=report.parcel.geometry_wgs84)
    second = first.model_copy(update={"id": "test-2", "evidence": [common, area.model_copy(update={"value": 31})],
                                      "action_pl": f"{instruction} {texts_pl.RETENTION_OUTSIDE_PARCEL}"})
    report.recommendations = [first, second, first.model_copy(update={"id": "test-3", "geometry": None})]
    return report


def test_builtin_renderer_prints_site_maps_site_table_and_field_plan():
    """Without WeasyPrint (a plain Windows Python) the PDF keeps main's grouped actions, as the HTML report."""
    report = _grouped_retention_report()
    assert pdf_basic.render(report).startswith(b"%PDF-")
    figures = list(pdf_basic.pages([(report, None)]))
    document = re.sub(r"\s+", " ", " ".join(item.get_text() for figure in figures for item in figure.texts))

    assert document.count("Plan wizji w terenie") == 1
    assert "Od czego zacząć:" in document and "Miejsca do sprawdzenia: 2." in document
    assert document.count("Przesłanki i uwagi") == 1 and "Sprawdzone" in document
    assert "20 m²" in document and "31 m²" in document
    # The outside-parcel caution stays with its site; the field plan starts at the site without it.
    assert document.count(texts_pl.RETENTION_OUTSIDE_PARCEL) == 1

    grouped = group_actions(report.recommendations)[0]
    png, coordinates = site_maps.render_png(report.parcel.geometry_wgs84, grouped.sites)
    _, svg_coordinates = site_maps.render(report.parcel.geometry_wgs84, grouped.sites)
    assert png.startswith(b"\x89PNG") and coordinates == svg_coordinates and len(coordinates) == 2
    assert all(value in document for value in coordinates.values())
    # The site map is embedded as an image and each mapped retention site has a box to tick.
    assert any(axis.images for figure in figures for axis in figure.axes)
    boxes = [artist for figure in figures for artist in figure.artists if isinstance(artist, Rectangle)
             and abs(artist.get_width() * pdf_basic.PAGE_W - 3 * pdf_basic.MM) < 0.01]
    assert len(boxes) == 2


def test_builtin_renderer_needs_no_native_libraries():
    # Used when WeasyPrint's Pango libraries are missing, e.g. a plain Windows Python install.
    report = Report.model_validate_json(SAMPLE.read_bytes())
    other = report.model_copy(update={"report_id": "other", "crop_name_pl": "Kukurydza na ziarno"})
    single = pdf_basic.render(report)
    combined = pdf_basic.render_many([(report, None), (other, None)])
    assert single.startswith(b"%PDF-") and combined.startswith(b"%PDF-")
    # The general part, each crop and the appendix start on a new page; shared content is not repeated.
    assert _page_count(combined) >= 4 and _page_count(single) >= 1

    page_texts = [" ".join(item.get_text() for item in figure.texts)
                  for figure in pdf_basic.pages([(report, None), (other, None)])]
    document = " ".join(page_texts)
    assert document.count("Źródła danych") == 1
    assert document.count("Położenie działki") == 1
    assert any("UPRAWA 1 Z 2" in page and report.crop_name_pl in page for page in page_texts)
    assert any("UPRAWA 2 Z 2" in page and "Kukurydza na ziarno" in page for page in page_texts)


def test_pdf_endpoints_fall_back_to_builtin_renderer(monkeypatch):
    analysis_date = date(2026, 11, 21)
    monkeypatch.setattr(routes_analyses, "analysis_today", lambda: analysis_date)
    monkeypatch.setattr(settings, "geo_provider", "fake")
    monkeypatch.setattr(open_meteo, "fetch_weather", AsyncMock(return_value=SourceResult[WeatherData](
        status=SourceStatus.MISSING
    )))
    monkeypatch.setattr(FakeGeoProvider, "render_static_map", AsyncMock(return_value=None))
    monkeypatch.setattr(pdf, "weasyprint_available", lambda: False)
    with TestClient(app) as client:
        ids = [client.post("/api/analyses", json={"parcel_id": EXAMPLE_PARCEL_ID, "crop_code": crop,
                                                  "analysis_date": analysis_date.isoformat()}).json()["analysis_id"]
               for crop in ("winter_cereals", "potatoes")]
        deadline = monotonic() + ANALYSIS_TIMEOUT_S
        while monotonic() < deadline and any(
            client.get(f"/api/analyses/{item}").json()["status"] not in {"done", "error"} for item in ids
        ):
            sleep(0.01)  # Schedule the background tasks between test polls.
        single = client.get(f"/api/analyses/{ids[0]}/report.pdf")
        combined = client.get(f"/api/analyses/report.pdf?analysis_id={ids[0]}&analysis_id={ids[1]}")

    assert single.status_code == combined.status_code == HTTPStatus.OK
    assert single.content.startswith(b"%PDF-") and combined.content.startswith(b"%PDF-")
    assert _page_count(combined.content) > _page_count(single.content)
