"""Agrotechnical options linked to crop and evidence of water loss."""
from app.analytics.models import AnalysisContext
from app.contracts.report import Metric, Recommendation
from app.recommendations import texts_pl as text

# The FAO guidance applies catch crops to gaps between crops. The catalog's perennial
# categories may retain the same plants through winter, so omit the between-crop rule for them.
# https://www.fao.org/conservation-agriculture/in-practice/soil-organic-cover/en
PERENNIAL_CROPS = {"fruit_trees", "fruit_bushes", "hops", "strawberries"}


def evaluate(ctx: AnalysisContext, risk: list[Metric]) -> list[Recommendation]:
    results = []
    if ctx.request.crop_code not in PERENNIAL_CROPS:
        results.append(Recommendation(
            id="plan_cover_crop", category="agrotechnics", title_pl=text.COVER_CROP_TITLE,
            action_pl=text.COVER_CROP_ACTION, why_pl=text.COVER_CROP_WHY,
            evidence=[*risk, Metric(code="crop", label_pl=text.RECOMMENDATION_CROP, value=ctx.crop.name_pl)],
            reference_ids=["cover_crops"],
        ))
    runoff = next((item for item in ctx.causes if item.code == "surface_runoff"), None)
    # FAO conservation agriculture recommends testing reduced disturbance with permanent cover.
    if runoff is not None or ctx.assessment.soil_category in {"I", "II"}:
        results.append(Recommendation(
            id="trial_less_tillage", category="agrotechnics", title_pl=text.TILLAGE_TITLE,
            action_pl=text.TILLAGE_ACTION, why_pl=text.TILLAGE_WHY,
            evidence=[*risk, *(runoff.evidence if runoff else [])], reference_ids=["fao_conservation"],
        ))
    return results
