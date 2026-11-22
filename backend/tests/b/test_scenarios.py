from datetime import date, datetime, timedelta, timezone
from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.ai import insight
from app.analytics import crops, open_meteo, scenarios
from app.analytics.models import WeatherData, WeatherDay
from app.api import routes_analyses
from app.config import settings
from app.contracts.common import Provenance, Range, SourceResult, SourceStatus
from app.contracts.geo import SoilInfo, SoilLayer
from app.contracts.scenario import ScenarioLevers
from app.fakes.fake_geo import EXAMPLE_POINT
from app.main import app
from app.recommendations import texts_pl as text
from tests.b.test_analysis_api import ANALYSIS_DATE, TODAY, _poll, _request

# Synthetic loam: 60% sand, 20% clay, 1% SOC, so the organic-matter lever can be computed.
SOIL = SoilInfo(layers=[SoilLayer(top_cm=0, bottom_cm=200, sand_pct=Range(mid=60), clay_pct=Range(mid=20),
                                  soc_g_kg=Range(mid=10))])


def _season(start: date, end: date, wet_until: date) -> WeatherData:
    """Heavy rain every third day until `wet_until`, then a dry, hot spell."""
    days = {}
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        rain = 20.0 if day <= wet_until and offset % 3 == 0 else 0.0
        days[day] = WeatherDay(precipitation_mm=rain, et0_mm=2.0 if day <= wet_until else 5.0,
                               temperature_mean_c=18, sunshine_h=8)
    return WeatherData(*EXAMPLE_POINT, days)


def _run(levers: ScenarioLevers):
    window = scenarios.window(date(2023, 7, 31))
    weather = _season(window.start, window.end, date(2023, 5, 15))
    field = scenarios.prepare(weather, crops.load()["potatoes"], SOIL, window.start)
    return scenarios.result("x", "x", "x", weather, field, levers, window.start, window.end)


def test_window_follows_the_growing_season():
    assert scenarios.window(date(2023, 7, 31)).start == date(2023, 3, 21)
    assert scenarios.window(date(2023, 7, 31)).end == date(2023, 7, 31)
    assert scenarios.window(date(2023, 11, 5)).end == date(2023, 9, 30)
    assert scenarios.window(date(2024, 2, 1)).start == date(2023, 3, 21)


def test_every_action_reduces_drought_stress_against_the_baseline():
    base = _run(ScenarioLevers())
    assert base.outcome.stress_days > 0
    assert base.outcome.budget.losses_mm > 0  # wet spring drains water past the roots
    assert base.outcome.risk in ("medium", "high")
    assert len(base.series) == base.outcome.days

    retention = _run(ScenarioLevers(retention_mm=25))
    assert retention.outcome.budget.retained_mm > 0
    assert retention.outcome.budget.retention_release_mm > 0
    assert retention.outcome.budget.losses_mm < base.outcome.budget.losses_mm

    organic = _run(ScenarioLevers(organic_matter_pct=1))
    assert organic.taw_mm > base.taw_mm

    mulch = _run(ScenarioLevers(cover_pct=60))
    assert mulch.outcome.budget.actual_et_mm <= base.outcome.budget.actual_et_mm

    water = _run(ScenarioLevers(irrigation_limit_mm=100, irrigation_dose_mm=25))
    assert water.outcome.budget.irrigation_mm == pytest.approx(100)
    assert water.outcome.irrigation_events >= 4  # doses never exceed the current depletion

    for item in (retention, organic, mulch, water):
        assert item.outcome.stress_days <= base.outcome.stress_days
        assert item.outcome.et_deficit_pct <= base.outcome.et_deficit_pct
    assert water.outcome.stress_days < base.outcome.stress_days


def _weather_result(days: dict) -> SourceResult[WeatherData]:
    return SourceResult[WeatherData](
        status=SourceStatus.OK, data=WeatherData(*EXAMPLE_POINT, days),
        provenance=[Provenance(source_id="open_meteo_archive", name=text.OPEN_METEO_ARCHIVE_NAME,
                               url=open_meteo.ARCHIVE_URL,
                               fetched_at=datetime.combine(TODAY, datetime.min.time(), timezone.utc),
                               live=True, licence=open_meteo.LICENCE)],
    )


def _finished_analysis(client: TestClient) -> str:
    started = client.post("/api/analyses", json=_request())
    assert started.status_code == HTTPStatus.ACCEPTED
    job = _poll(client, started.json()["analysis_id"])
    assert job["status"] == "done"
    return started.json()["analysis_id"]


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(routes_analyses, "analysis_today", lambda: TODAY)
    monkeypatch.setattr(settings, "geo_provider", "fake")
    weather = _season(date(2023, 1, 1), ANALYSIS_DATE, date(2023, 4, 30))
    monkeypatch.setattr(open_meteo, "fetch_weather", AsyncMock(return_value=_weather_result(weather.days)))
    insight._cache.clear()
    with TestClient(app) as client:
        yield client


def test_scenario_api_compares_presets_with_the_baseline(api):
    analysis_id = _finished_analysis(api)
    response = api.post(f"/api/analyses/{analysis_id}/scenarios",
                        json={"retention_mm": 10, "irrigation_limit_mm": 50})
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["window_start"] == "2023-03-21"
    assert body["window_end"] == ANALYSIS_DATE.isoformat()
    assert [item["id"] for item in body["presets"]] == ["retention", "organic_matter", "cover", "irrigation", "combined"]
    assert body["custom"]["levers"]["retention_mm"] == 10
    assert body["baseline"]["series"]
    assert body["custom"]["outcome"]["stress_days"] <= body["baseline"]["outcome"]["stress_days"]

    assert api.post("/api/analyses/missing/scenarios", json={}).status_code == HTTPStatus.NOT_FOUND
    invalid = api.post(f"/api/analyses/{analysis_id}/scenarios", json={"cover_pct": 150})
    assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_ai_insight_falls_back_to_rules_without_a_model(api, monkeypatch):
    monkeypatch.setattr(settings, "ai_enabled", False)
    analysis_id = _finished_analysis(api)
    response = api.post(f"/api/analyses/{analysis_id}/ai-insight", json={})
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["source"] == "rules"
    assert body["headline_pl"] and body["best_action_pl"] and body["reasoning_pl"]
    assert "wyłączona" in body["note_pl"]


ANSWER = ('{"headline_pl": "Ryzyko jest wysokie.", "forecast_pl": "Zapas wody maleje.", '
          '"best_action_pl": "Zatrzymaj wodę.", "reasoning_pl": ["a", "b"], "caveats_pl": ["c"]}')


def test_ai_insight_uses_gemini_by_default(api, monkeypatch):
    from google import genai
    generate = AsyncMock(return_value=SimpleNamespace(text=ANSWER))
    created = {}

    def client(api_key, **_):
        created["key"] = api_key
        return SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))

    monkeypatch.setattr(genai, "Client", client)
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")

    analysis_id = _finished_analysis(api)
    body = api.post(f"/api/analyses/{analysis_id}/ai-insight", json={"cover_pct": 40, "consent": True}).json()
    assert body["source"] == "llm"
    assert body["model"] == settings.gemini_model
    assert body["best_action_pl"] == "Zatrzymaj wodę."
    assert created["key"] == "test-key"
    kwargs = generate.await_args.kwargs
    assert kwargs["model"] == settings.gemini_model
    assert kwargs["config"].response_mime_type == "application/json"
    assert '"farmer_combination"' in kwargs["contents"]

    api.post(f"/api/analyses/{analysis_id}/ai-insight", json={"cover_pct": 40, "consent": True})
    assert generate.await_count == 1


def test_gemini_switches_to_the_fallback_model_when_overloaded(api, monkeypatch):
    from google import genai
    from google.genai import errors
    busy = errors.ServerError(503, {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}})
    generate = AsyncMock(side_effect=[busy, SimpleNamespace(text=ANSWER)])
    monkeypatch.setattr(genai, "Client", lambda **_: SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate))))
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")

    analysis_id = _finished_analysis(api)
    body = api.post(f"/api/analyses/{analysis_id}/ai-insight", json={"consent": True}).json()
    assert body["source"] == "llm"
    assert body["model"] == settings.gemini_fallback_model
    assert [call.kwargs["model"] for call in generate.await_args_list] == [settings.gemini_model,
                                                                          settings.gemini_fallback_model]


def test_gemini_without_a_key_explains_the_fallback(api, monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", None)
    analysis_id = _finished_analysis(api)
    body = api.post(f"/api/analyses/{analysis_id}/ai-insight", json={}).json()
    assert body["source"] == "rules"
    assert "GEMINI_API_KEY" in body["note_pl"]


def test_ai_insight_uses_claude_structured_output(api, monkeypatch):
    answer = ANSWER
    response = SimpleNamespace(stop_reason="end_turn", model="claude-opus-5-5",
                               content=[SimpleNamespace(type="text", text=answer)])
    create = AsyncMock(return_value=response)
    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    import anthropic
    monkeypatch.setattr(anthropic, "AsyncAnthropic", lambda: client)
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "anthropic")

    analysis_id = _finished_analysis(api)
    body = api.post(f"/api/analyses/{analysis_id}/ai-insight", json={"cover_pct": 40}).json()
    assert body["source"] == "llm"
    assert body["model"] == "claude-opus-5-5"
    assert body["best_action_pl"] == "Zatrzymaj wodę."
    kwargs = create.await_args.kwargs
    assert kwargs["model"] == settings.anthropic_model
    assert kwargs["output_config"]["format"]["type"] == "json_schema"
    assert '"farmer_combination"' in kwargs["messages"][0]["content"]

    # The same question is answered from the cache.
    api.post(f"/api/analyses/{analysis_id}/ai-insight", json={"cover_pct": 40})
    assert create.await_count == 1


def test_claude_without_credentials_explains_the_fallback(api, monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "anthropic")
    analysis_id = _finished_analysis(api)
    body = api.post(f"/api/analyses/{analysis_id}/ai-insight", json={}).json()
    assert body["source"] == "rules"
    assert "ANTHROPIC_API_KEY" in body["note_pl"]


def test_station_weather_without_et0_gets_a_monthly_estimate():
    start, end = date(2023, 5, 1), date(2023, 5, 31)
    days = {start + timedelta(days=i): WeatherDay(precipitation_mm=0, temperature_mean_c=15, sunshine_h=8)
            for i in range((end - start).days + 1)}
    weather, filled = scenarios.with_et0(WeatherData(*EXAMPLE_POINT, days), start, end)
    assert filled
    values = {row.et0_mm for row in weather.days.values()}
    assert len(values) == 1 and next(iter(values)) > 0
    field = scenarios.prepare(weather, crops.load()["potatoes"], SOIL, start)
    assert scenarios.result("x", "x", "x", weather, field, ScenarioLevers(), start, end).outcome.days == 31


def test_external_ai_needs_consent_and_reports_its_status(api, monkeypatch):
    from google import genai
    generate = AsyncMock(return_value=SimpleNamespace(text=ANSWER))
    monkeypatch.setattr(genai, "Client", lambda **_: SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate))))
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")

    status = api.get("/api/ai/status").json()
    assert status == {"enabled": True, "provider": "gemini", "provider_name": "Google Gemini",
                      "model": settings.gemini_model, "external": True}

    analysis_id = _finished_analysis(api)
    refused = api.post(f"/api/analyses/{analysis_id}/ai-insight", json={})
    assert refused.status_code == HTTPStatus.FORBIDDEN
    assert "zgoda" in refused.json()["detail"].lower()
    assert generate.await_count == 0  # nothing left the server

    agreed = api.post(f"/api/analyses/{analysis_id}/ai-insight", json={"consent": True})
    assert agreed.status_code == HTTPStatus.OK
    assert agreed.json()["source"] == "llm"


def test_without_a_key_no_consent_is_needed(api, monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", None)
    assert api.get("/api/ai/status").json()["external"] is False
    analysis_id = _finished_analysis(api)
    assert api.post(f"/api/analyses/{analysis_id}/ai-insight", json={}).json()["source"] == "rules"


def test_pdf_can_include_the_what_if_section(api, monkeypatch):
    from app.reports import pdf
    calls = []

    def render(report, map_png, scenarios=None):
        calls.append(scenarios)
        return b"%PDF-test"

    monkeypatch.setattr(pdf, "render", render)
    analysis_id = _finished_analysis(api)

    plain = api.get(f"/api/analyses/{analysis_id}/report.pdf")
    assert plain.status_code == HTTPStatus.OK and calls[-1] is None

    with_scenarios = api.get(f"/api/analyses/{analysis_id}/report.pdf",
                             params={"scenarios": "true", "cover_pct": 60, "irrigation_limit_mm": 80})
    assert with_scenarios.status_code == HTTPStatus.OK
    included = calls[-1]
    assert included is not None
    assert included.custom.levers.cover_pct == 60 and included.custom.levers.irrigation_limit_mm == 80

    # The plain PDF is cached; the scenario one depends on the sliders and is rendered each time.
    api.get(f"/api/analyses/{analysis_id}/report.pdf", params={"scenarios": "true"})
    assert len(calls) == 3


def test_builtin_pdf_renderer_prints_the_what_if_section(api):
    """Without WeasyPrint (plain Windows Python) the built-in renderer prints the same "Co jeśli?" section."""
    import asyncio
    import re

    from app.api.routes_scenarios import build
    from app.reports import pdf_basic
    from app.storage.db import ReportStore

    analysis_id = _finished_analysis(api)
    saved = ReportStore(settings.db_path).by_analysis(analysis_id)
    with_action = asyncio.run(build(saved, analysis_id, ScenarioLevers(cover_pct=60)))

    def document(scenario_report):
        figures = list(pdf_basic.pages([(saved.report, None)], scenario_report))
        content = re.sub(r"\s+", " ", " ".join(item.get_text() for figure in figures for item in figure.texts))
        return content, sum(len(axis.images) for figure in figures for axis in figure.axes)

    content, images = document(with_action)
    assert "Co jeśli? Symulacja działań" in content
    assert "Twój wariant: międzyplony/mulcz na 60% powierzchni" in content
    assert "Wszystkie działania razem" in content and "Założenia modelu" in content
    assert "Dni ze stresem wodnym" in content and "Bilans wody (mm)" in content
    plain, plain_images = document(None)
    assert "Co jeśli?" not in plain
    assert images == plain_images + 1  # the soil water reserve chart
    assert pdf_basic.render(saved.report, None, with_action).startswith(b"%PDF-")


def test_pdf_html_shows_the_farmer_variant_only_when_an_action_is_set(api):
    import asyncio
    from app.api.routes_scenarios import build
    from app.reports import pdf
    from app.storage.db import ReportStore

    analysis_id = _finished_analysis(api)
    saved = ReportStore(settings.db_path).by_analysis(analysis_id)
    with_action = asyncio.run(build(saved, analysis_id, ScenarioLevers(cover_pct=60)))
    html = pdf.render_html(saved.report, None, with_action)
    assert "Co jeśli? Symulacja działań" in html
    assert "Twój wariant: międzyplony/mulcz na 60% powierzchni" in html
    assert "Wszystkie działania razem" in html and "data:image/svg+xml" in html

    nothing = asyncio.run(build(saved, analysis_id, ScenarioLevers()))
    assert "Twój wariant" not in pdf.render_html(saved.report, None, nothing)
    assert "Co jeśli?" not in pdf.render_html(saved.report, None, None)


def test_ai_answers_use_plain_hyphens(api, monkeypatch):
    from google import genai
    dashed = ANSWER.replace("Zatrzymaj wodę.", "Zatrzymaj wodę \u2014 retencja \u2013 mulcz, \u22125 dni.")
    generate = AsyncMock(return_value=SimpleNamespace(text=dashed))
    monkeypatch.setattr(genai, "Client", lambda **_: SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate))))
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    analysis_id = _finished_analysis(api)
    body = api.post(f"/api/analyses/{analysis_id}/ai-insight", json={"consent": True}).json()
    assert body["best_action_pl"] == "Zatrzymaj wodę - retencja - mulcz, -5 dni."
