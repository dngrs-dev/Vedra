"""Run evidence-gated recommendations in the agreed stage order."""
from app.analytics.models import AnalysisContext
from app.analytics.season import mode
from app.contracts.report import Metric, Recommendation
from app.recommendations import texts_pl as text
from app.recommendations.rules import agrotech, irrigation, landscape, off_season, soil


def _risk_evidence(ctx: AnalysisContext, outside: bool) -> list[Metric]:
    weather_ids = [item.source_id for item in ctx.weather.provenance]
    if not outside and ctx.assessment.kbw_mm is not None and ctx.assessment.kbw_mm < 0:
        return [Metric(code="kbw", label_pl=text.KBW_LABEL, value=ctx.assessment.kbw_mm, unit="mm", source_ids=weather_ids)]
    if outside and ctx.history.drought_years:
        return [Metric(code="historical_drought_years", label_pl=text.RETENTION_HISTORY_YEARS,
                       value=len(ctx.history.drought_years), source_ids=weather_ids)]
    # Categories I/II are susceptible to drought according to the annex to Dz.U. 2019 poz. 739.
    if ctx.assessment.soil_category in {"I", "II"}:
        return [Metric(code="soil_category", label_pl=text.SOIL_CATEGORY, value=ctx.assessment.soil_category,
                       source_ids=[item.source_id for item in ctx.geo.soil.provenance])]
    return []


def run(ctx: AnalysisContext) -> list[Recommendation]:
    outside = mode(ctx.request.analysis_date) == "off_season"
    risk = _risk_evidence(ctx, outside)
    results: list[Recommendation] = []
    if risk:
        results.extend(landscape.evaluate(ctx, risk))
        if outside:
            results.append(off_season.evaluate(risk))
        results.extend(soil.evaluate(ctx, risk))
        results.extend(agrotech.evaluate(ctx, risk))
    if not outside and ctx.request.include_irrigation:
        results.extend(irrigation.evaluate(ctx))
    return results
