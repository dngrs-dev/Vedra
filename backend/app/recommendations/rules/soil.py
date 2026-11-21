"""Soil retention practices supported by the assessment."""
from app.analytics.models import AnalysisContext
from app.contracts.report import Metric, Recommendation
from app.recommendations import texts_pl as text


def evaluate(ctx: AnalysisContext, risk: list[Metric]) -> list[Recommendation]:
    results = [Recommendation(
        id="retain_crop_residue", category="soil_retention", title_pl=text.RESIDUE_TITLE,
        action_pl=text.RESIDUE_ACTION, why_pl=text.RESIDUE_WHY, evidence=risk, reference_ids=["mulching"],
    )]
    # Categories I and II are identified as susceptible in the annex to Dz.U. 2019 poz. 739.
    if ctx.assessment.soil_category in {"I", "II"}:
        category = Metric(code="soil_category", label_pl=text.SOIL_CATEGORY, value=ctx.assessment.soil_category,
                          source_ids=[item.source_id for item in ctx.geo.soil.provenance])
        results.append(Recommendation(
            id="build_soil_organic_matter", category="soil_retention", title_pl=text.ORGANIC_MATTER_TITLE,
            action_pl=text.ORGANIC_MATTER_ACTION, why_pl=text.ORGANIC_MATTER_WHY,
            evidence=[*risk, category], reference_ids=["fao_organic_matter"],
        ))
    return results
