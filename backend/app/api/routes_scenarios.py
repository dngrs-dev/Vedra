""""What if" simulations and the optional AI commentary for a finished analysis."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, status

from app.ai import insight
from app.analytics import crops, scenarios
from app.analytics import weather as weather_provider
from app.api.deps import StoreDependency
from app.contracts.scenario import AiInsight, AiStatus, ScenarioLevers, ScenarioReport
from app.storage.db import StoredReport

router = APIRouter(prefix="/api/analyses")
ai_router = APIRouter(prefix="/api/ai")

NOT_FOUND = "Nie znaleziono analizy. Uruchom analizę działki ponownie."
NO_SOIL = "Brak danych o glebie tej działki - symulacja scenariuszy nie jest możliwa."
NO_WEATHER = "Brak danych pogodowych dla sezonu - symulacja scenariuszy nie jest możliwa."
SOM_UNSUPPORTED = ("Dla tej gleby brakuje uziarnienia lub węgla organicznego, więc wpływ próchnicy "
                   "nie został policzony (przyjęto 0).")


CONSENT_REQUIRED = ("Wymagana jest zgoda na przekazanie danych analizy do zewnętrznej usługi AI. "
                    "Bez zgody aplikacja działa dalej, ale bez komentarza AI.")


class ScenarioRequest(ScenarioLevers):
    pass


class AiInsightRequest(ScenarioLevers):
    # RODO: data goes to an external AI service only after the user agreed in the UI.
    consent: bool = False


async def _stored(store, analysis_id: str) -> StoredReport:
    saved = await asyncio.to_thread(store.by_analysis, analysis_id)
    if saved is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return saved


async def build(saved: StoredReport, analysis_id: str, levers: ScenarioLevers) -> ScenarioReport:
    report = saved.report
    crop = crops.load().get(report.crop_code)
    soil = saved.bundle.soil.data if saved.bundle is not None else None
    if crop is None or soil is None or not (soil.layers or soil.kbw_category):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, NO_SOIL)

    window = scenarios.window(report.analysis_date)
    weather = await weather_provider.fetch_weather(
        report.parcel.centroid_lat, report.parcel.centroid_lon, max(window.end, report.analysis_date))
    if weather.data is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, NO_WEATHER)
    data, et0_estimated = scenarios.with_et0(weather.data, window.start, window.end)
    field = scenarios.prepare(data, crop, soil, window.start)
    if field is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, NO_SOIL)

    def run(id_: str, title: str, description: str, chosen: ScenarioLevers, series: bool = True):
        outcome = scenarios.result(id_, title, description, data, field, chosen, window.start, window.end, series)
        if outcome is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, NO_WEATHER)
        return outcome

    def compute() -> ScenarioReport:
        baseline = run("baseline", "Bez działań", "Obecny sposób gospodarowania - punkt odniesienia.",
                       ScenarioLevers())
        custom = run("custom", "Twój wariant", "Działania wybrane suwakami.", levers)
        presets = [run(*preset, series=True) for preset in scenarios.PRESETS]
        assumptions = list(scenarios.ASSUMPTIONS_PL)
        if not scenarios.organic_matter_supported(field):
            assumptions.append(SOM_UNSUPPORTED)
        if et0_estimated:
            assumptions.append("Dane stacji nie zawierają ewapotranspiracji dobowej - przyjęto miesięczną ETP "
                               "(Doroszewski-Górski, jak w KBW) rozłożoną równo na dni miesiąca.")
        if field.typical_soil:
            assumptions.append(f"Brak profilu glebowego dla tej działki - przyjęto typową glebę kategorii "
                               f"{soil.kbw_category} (woda użyteczna w środku zakresu WOD z rozporządzenia).")
        if not field.initial_from_data:
            assumptions.append("Brak modelowej wilgotności gleby na początek okresu - przyjęto, że gleba "
                               "była nasycona do polowej pojemności wodnej (typowe po zimie).")
        return ScenarioReport(
            analysis_id=analysis_id, crop_name_pl=report.crop_name_pl,
            window_start=window.start, window_end=window.end, window_note_pl=window.note_pl,
            baseline=baseline, custom=custom, presets=presets,
            assumptions_pl=assumptions, kbw_note_pl=scenarios.KBW_NOTE_PL,
        )

    return await asyncio.to_thread(compute)


@router.post("/{analysis_id}/scenarios", summary="Symulacja scenariuszy „co jeśli” dla zakończonej analizy")
async def simulate(analysis_id: str, levers: ScenarioRequest, store: StoreDependency) -> ScenarioReport:
    saved = await _stored(store, analysis_id)
    return await build(saved, analysis_id, levers)


@router.post("/{analysis_id}/ai-insight", summary="Komentarz AI do raportu i scenariuszy")
async def ai_insight(analysis_id: str, request: AiInsightRequest, store: StoreDependency) -> AiInsight:
    if insight.status().external and not request.consent:
        raise HTTPException(status.HTTP_403_FORBIDDEN, CONSENT_REQUIRED)
    saved = await _stored(store, analysis_id)
    levers = ScenarioLevers(**request.model_dump(exclude={"consent"}))
    report = await build(saved, analysis_id, levers)
    return await insight.explain(saved.report, report)


@ai_router.get("/status", summary="Czy komentarz AI jest włączony i do jakiej usługi trafiają dane")
async def ai_status() -> AiStatus:
    return insight.status()
