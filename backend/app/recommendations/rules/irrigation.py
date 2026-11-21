"""Present irrigation advice backed by a computed daily water balance."""
from app.analytics.models import AnalysisContext
from app.contracts.report import Metric, Recommendation
from app.recommendations import texts_pl as text


def evaluate(ctx: AnalysisContext) -> list[Recommendation]:
    irrigation = ctx.irrigation
    if irrigation is None or irrigation.justified is not True or irrigation.net_dose_mm is None:
        return []
    evidence = [Metric(code="net_irrigation_dose", label_pl=text.IRRIGATION_NET_DOSE,
                       value=irrigation.net_dose_mm, unit="mm")]
    if irrigation.suggested_date is not None:
        evidence.append(Metric(code="irrigation_date", label_pl=text.IRRIGATION_DATE,
                               value=irrigation.suggested_date.isoformat()))
    return [Recommendation(
        id="consider_irrigation", category="irrigation", title_pl=text.IRRIGATION_TITLE,
        action_pl=text.IRRIGATION_ACTION, why_pl=irrigation.why_pl, evidence=evidence,
        reference_ids=["fao_water_balance"],
    )]
