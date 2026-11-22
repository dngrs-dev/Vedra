"""Optional LLM commentary: an LLM reads the report and the scenario results and writes a short
forecast and advice for the farmer, in Polish.

Providers: Google Gemini (default, has a free tier, GEMINI_API_KEY) or Anthropic Claude
(AI_PROVIDER=anthropic, ANTHROPIC_API_KEY). The LLM only interprets numbers computed by the
backend; it never replaces them. Without a key (or when the call fails) the same structure is
filled from simple rules, so the feature always works in a demo.
"""
from __future__ import annotations

import json
import logging
import os
from collections import OrderedDict

from pydantic import BaseModel, Field

from app.config import settings
from app.contracts.report import Report
from app.contracts.scenario import AiInsight, AiStatus, ScenarioReport, ScenarioResult

logger = logging.getLogger(__name__)

RISK_PL = {"low": "niskie", "medium": "umiarkowane", "high": "wysokie"}
CACHE_SIZE = 64
_cache: OrderedDict[str, AiInsight] = OrderedDict()

SYSTEM_PROMPT = """\
You are an agronomy assistant in Vedra, a Polish tool that helps farmers keep water in the field \
and protect crops from agricultural drought (KOWR task "Zatrzymaj wodę, chroń plony").

You receive JSON computed by the backend for one parcel: the drought assessment (statutory \
climatic water balance, KBW), ten-year history, likely causes, rule-based recommendations, and \
"what if" simulations of a FAO-56 root-zone water balance for several farmer actions \
(landscape retention, more soil organic matter, cover crops/mulch, irrigation, all combined, \
and the farmer's own combination).

Write for a farmer, in plain Polish, without jargon (explain KBW or RAW in a few words if you \
use them). Base every statement on the numbers in the JSON and quote the key ones (days of water \
stress, % shortage of water for the crop, mm of water). Compare actions with the "do nothing" \
baseline and say which gives the most benefit per effort; prefer keeping water in the landscape \
and soil before irrigation, as the KOWR task does, unless the numbers clearly say otherwise. \
For the forecast, say what is likely in the coming weeks if the farmer does nothing, based on \
the current water reserve, the trend and the ten-year drought frequency; do not invent weather \
forecasts or data that is not in the JSON. Mention honestly that the simulations use model \
assumptions. Keep each field short: 1-3 sentences, lists of 2-4 items. Use only the plain \
hyphen-minus (-) as a dash, never em or en dashes."""

# Long dashes (em dash, en dash, minus sign) are shown as a plain hyphen-minus everywhere in the app.
_PLAIN_DASHES = str.maketrans({"\u2014": "-", "\u2013": "-", "\u2212": "-"})


def _plain(answer: _LlmAnswer) -> _LlmAnswer:
    return _LlmAnswer(
        headline_pl=answer.headline_pl.translate(_PLAIN_DASHES),
        forecast_pl=answer.forecast_pl.translate(_PLAIN_DASHES),
        best_action_pl=answer.best_action_pl.translate(_PLAIN_DASHES),
        reasoning_pl=[item.translate(_PLAIN_DASHES) for item in answer.reasoning_pl],
        caveats_pl=[item.translate(_PLAIN_DASHES) for item in answer.caveats_pl],
    )


class _LlmAnswer(BaseModel):
    headline_pl: str = Field(description="One-sentence verdict for the farmer.")
    forecast_pl: str = Field(description="What is likely in the coming weeks without action.")
    best_action_pl: str = Field(description="The recommended action or combination and why.")
    reasoning_pl: list[str] = Field(description="2-4 short points with the key numbers.")
    caveats_pl: list[str] = Field(description="1-3 honest limitations.")


def _n(value: float) -> str:
    """Polish decimal comma, at most one decimal place."""
    return f"{value:.1f}".rstrip("0").rstrip(".").replace(".", ",")


def _brief(item: ScenarioResult) -> dict:
    return {
        "id": item.id,
        "title": item.title_pl,
        "levers": item.levers.model_dump(),
        "available_water_mm": item.taw_mm,
        **item.outcome.model_dump(),
    }


def _context(report: Report, scenarios: ScenarioReport) -> dict:
    kbw = report.assessment.kbw
    vulnerability = report.assessment.vulnerability
    return {
        "parcel": {"id": report.parcel.parcel_id, "area_ha": report.parcel.area_ha,
                   "location": ", ".join(filter(None, [report.parcel.commune, report.parcel.county,
                                                       report.parcel.voivodeship]))},
        "crop": report.crop_name_pl,
        "analysis_date": report.analysis_date.isoformat(),
        "summary": report.summary,
        "kbw": {"verdict": kbw.verdict, "explanation": kbw.explanation_pl, "kbw_mm": kbw.kbw_mm,
                "threshold_mm": kbw.threshold_mm, "distance_to_threshold_mm": kbw.distance_to_threshold_mm,
                "soil_category": kbw.soil_category},
        "history": None if vulnerability is None else {
            "summary": vulnerability.summary_pl, "years_assessed": vulnerability.years_assessed,
            "drought_years": vulnerability.drought_years},
        "causes": [{"title": c.title_pl, "explanation": c.explanation_pl} for c in report.causes],
        "recommendations": [{"title": r.title_pl, "action": r.action_pl} for r in report.recommendations],
        "irrigation_advice": None if report.irrigation is None else report.irrigation.model_dump(mode="json"),
        "simulation": {
            "window": {"start": scenarios.window_start.isoformat(), "end": scenarios.window_end.isoformat(),
                       "note": scenarios.window_note_pl},
            "baseline": _brief(scenarios.baseline),
            "presets": [_brief(item) for item in scenarios.presets],
            "farmer_combination": _brief(scenarios.custom),
            "assumptions": scenarios.assumptions_pl,
            "kbw_note": scenarios.kbw_note_pl,
        },
        "limitations": report.limitations_pl,
    }


def _key(report: Report, scenarios: ScenarioReport) -> str:
    return f"{report.report_id}:{scenarios.custom.levers.model_dump_json()}"


def rules(report: Report, scenarios: ScenarioReport, note: str | None = None) -> AiInsight:
    base = scenarios.baseline.outcome
    singles = [item for item in scenarios.presets if item.id != "combined"]
    best = max(singles, key=lambda item: (base.stress_days - item.outcome.stress_days,
                                          base.et_deficit_pct - item.outcome.et_deficit_pct), default=None)
    custom = scenarios.custom.outcome
    headline = (f"Bez działań ryzyko niedoboru wody dla uprawy jest {RISK_PL[base.risk]}: "
                f"{base.stress_days} z {base.days} dni ze stresem wodnym.")
    trend = ("zapas wody w glebie jest niski" if base.end_available_pct < 40
             else "zapas wody w glebie jest jeszcze wystarczający")
    vulnerability = report.assessment.vulnerability
    history = ""
    if vulnerability and vulnerability.years_assessed:
        history = (f" W ostatnich latach susza wystąpiła w {len(vulnerability.drought_years)} "
                   f"z {len(vulnerability.years_assessed)} ocenionych sezonów.")
    forecast = (f"Na koniec okresu {trend} ({_n(base.end_available_pct)}% wody dostępnej). "
                f"Jeśli nie spadnie większy deszcz, stres będzie narastał.{history}")
    if best is not None and best.outcome.stress_days < base.stress_days:
        action = (f"Największy pojedynczy efekt daje: {best.title_pl.lower()} - dni stresu spadają z "
                  f"{base.stress_days} do {best.outcome.stress_days}.")
    else:
        action = "Żadne pojedyncze działanie nie zmienia wyraźnie wyniku w tym okresie - warto łączyć działania."
    reasoning = [
        f"Niedobór wody dla uprawy bez działań: {_n(base.et_deficit_pct)}% potrzeb.",
        f"Twój wariant: {custom.stress_days} dni stresu, niedobór {_n(custom.et_deficit_pct)}%, "
        f"ryzyko {RISK_PL[custom.risk]}.",
    ]
    if base.budget.losses_mm > 0:
        reasoning.append(f"Poza strefę korzeni odpłynęło {_n(base.budget.losses_mm)} mm wody - to woda, "
                         f"którą retencja może zatrzymać.")
    return AiInsight(
        source="rules", headline_pl=headline, forecast_pl=forecast, best_action_pl=action,
        reasoning_pl=reasoning,
        caveats_pl=["Symulacje opierają się na założeniach modelowych, a nie na pomiarach z tej działki."],
        note_pl=note,
    )


class _Unavailable(Exception):
    """The LLM could not answer; the message (Polish) explains why to the farmer."""


# Free-tier Gemini models are sometimes overloaded (503) or rate-limited (429): try the next one.
GEMINI_RETRY_CODES = {404, 429, 500, 503, 504}
GEMINI_TIMEOUT_MS = 60_000


async def _ask_gemini(prompt: str) -> tuple[_LlmAnswer, str]:
    """Google Gemini (has a free tier). Key from GEMINI_API_KEY."""
    try:
        from google import genai
        from google.genai import errors, types
    except ImportError as exc:
        raise _Unavailable("Brak pakietu google-genai na serwerze") from exc
    key = settings.gemini_api_key or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise _Unavailable("Model AI nie jest skonfigurowany (brak GEMINI_API_KEY)")

    client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS))
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=_LlmAnswer,
    )
    models = list(dict.fromkeys([settings.gemini_model, settings.gemini_fallback_model]))
    reason = "Model AI zwrócił błąd"
    for model in models:
        try:
            response = await client.aio.models.generate_content(model=model, contents=prompt, config=config)
        except errors.APIError as exc:
            logger.warning("Gemini %s failed with status %s: %s", model, exc.code, exc.message)
            if exc.code in (401, 403):
                raise _Unavailable("Klucz GEMINI_API_KEY jest nieprawidłowy lub nie ma dostępu do modelu") from exc
            if exc.code == 400:
                raise _Unavailable(f"Gemini odrzucił zapytanie (400: {exc.message})") from exc
            if exc.code not in GEMINI_RETRY_CODES:
                raise _Unavailable(f"Model AI zwrócił błąd ({exc.code})") from exc
            reason = {429: "Wyczerpano darmowy limit zapytań Gemini - spróbuj za chwilę",
                      404: f"Model {model} jest niedostępny (sprawdź GEMINI_MODEL)"}.get(
                exc.code, "Modele Gemini są teraz przeciążone - spróbuj za chwilę")
            continue
        except Exception as exc:  # network errors and timeouts come from the SDK's HTTP client
            logger.warning("Gemini %s failed: %s", model, type(exc).__name__)
            reason = "Brak połączenia z modelem AI lub przekroczono czas odpowiedzi"
            continue
        try:
            return _LlmAnswer.model_validate_json(response.text or ""), model
        except ValueError:
            logger.warning("Gemini %s returned invalid JSON", model)
            reason = "Odpowiedź modelu AI miała zły format"
    raise _Unavailable(reason)


async def _ask_claude(prompt: str) -> tuple[_LlmAnswer, str]:
    """Anthropic Claude (paid). Key from ANTHROPIC_API_KEY."""
    try:
        import anthropic
    except ImportError as exc:
        raise _Unavailable("Brak pakietu anthropic na serwerze") from exc
    try:
        response = await anthropic.AsyncAnthropic().beta.messages.create(
            model=settings.anthropic_model,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": _schema()}},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError as exc:
        raise _Unavailable("Model AI nie jest skonfigurowany (brak lub błędny ANTHROPIC_API_KEY)") from exc
    except anthropic.RateLimitError as exc:
        raise _Unavailable("Limit zapytań do modelu AI został przekroczony") from exc
    except anthropic.APIStatusError as exc:
        logger.warning("Claude insight failed with status %s", exc.status_code)
        raise _Unavailable("Model AI zwrócił błąd") from exc
    except anthropic.APIConnectionError as exc:
        raise _Unavailable("Brak połączenia z modelem AI") from exc
    except anthropic.AnthropicError as exc:
        raise _Unavailable("Model AI jest niedostępny lub nieskonfigurowany (sprawdź ANTHROPIC_API_KEY)") from exc
    except TypeError as exc:
        # The SDK raises TypeError before sending when no credential can be resolved.
        if "authentication" not in str(exc):
            raise
        raise _Unavailable("Model AI nie jest skonfigurowany (brak ANTHROPIC_API_KEY)") from exc

    if response.stop_reason == "refusal":
        raise _Unavailable("Model AI odmówił odpowiedzi")
    if response.stop_reason == "max_tokens":
        raise _Unavailable("Odpowiedź modelu AI była niepełna")
    text = next((block.text for block in response.content if block.type == "text"), None)
    try:
        return _LlmAnswer.model_validate_json(text or ""), response.model
    except ValueError as exc:
        raise _Unavailable("Odpowiedź modelu AI miała zły format") from exc


PROVIDERS = {"gemini": _ask_gemini, "anthropic": _ask_claude}


async def explain(report: Report, scenarios: ScenarioReport) -> AiInsight:
    key = f"{settings.ai_provider}:{_key(report, scenarios)}"
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    if not settings.ai_enabled:
        return rules(report, scenarios, "Analiza AI jest wyłączona w konfiguracji - pokazano podsumowanie z reguł.")

    prompt = json.dumps(_context(report, scenarios), ensure_ascii=False)
    try:
        answer, model = await PROVIDERS[settings.ai_provider](prompt)
    except _Unavailable as exc:
        return rules(report, scenarios, f"{exc} - pokazano podsumowanie z reguł.")

    insight = AiInsight(source="llm", model=model, **_plain(answer).model_dump())
    _cache[key] = insight
    if len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)
    return insight


def _schema() -> dict:
    schema = _LlmAnswer.model_json_schema()
    schema["additionalProperties"] = False
    return schema


PROVIDER_LABELS = {"gemini": "Google Gemini", "anthropic": "Anthropic Claude"}


def status() -> AiStatus:
    if settings.ai_provider == "gemini":
        model = settings.gemini_model
        configured = bool(settings.gemini_api_key or os.environ.get("GOOGLE_API_KEY"))
    else:
        model = settings.anthropic_model
        configured = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    return AiStatus(enabled=settings.ai_enabled, provider=settings.ai_provider,
                    provider_name=PROVIDER_LABELS[settings.ai_provider], model=model,
                    external=settings.ai_enabled and configured)
