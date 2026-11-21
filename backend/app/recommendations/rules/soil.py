"""Soil retention practices supported by the assessment."""
from app.analytics.models import AnalysisContext
from app.analytics.soil_water import GRAMS_PER_KG_PER_PERCENT, SOC_TO_SOM, what_if_som
from app.analytics.water_balance import CM_PER_METRE
from app.contracts.report import Metric, Recommendation
from app.recommendations import texts_pl as text

# Minasny & McBratney (2018) analyze a sensitivity scenario adding 10 g SOC/kg.
# https://doi.org/10.1111/ejss.12475. Conversion to SOM uses the factor cited in soil_water.py.
SOC_SCENARIO_G_KG = 10


def evaluate(ctx: AnalysisContext, risk: list[Metric]) -> list[Recommendation]:
    results = [Recommendation(
        id="retain_crop_residue", category="soil_retention", title_pl=text.RESIDUE_TITLE,
        action_pl=text.RESIDUE_ACTION, why_pl=text.RESIDUE_WHY, evidence=risk, reference_ids=["mulching"],
    )]
    # Categories I and II are identified as susceptible in the annex to Dz.U. 2019 poz. 739.
    if ctx.assessment.soil_category in {"I", "II"}:
        category = Metric(code="soil_category", label_pl=text.SOIL_CATEGORY, value=ctx.assessment.soil_category,
                          source_ids=[item.source_id for item in ctx.geo.soil.provenance])
        evidence = [*risk, category]
        references = ["fao_organic_matter"]
        data = ctx.geo.soil.data
        if data is not None:
            roots = ctx.crop.zr_m
            depth_cm = (roots.low + roots.high) / 2 * CM_PER_METRE  # Midpoint of the sourced root-depth range.
            increment = SOC_SCENARIO_G_KG / GRAMS_PER_KG_PER_PERCENT * SOC_TO_SOM
            change = what_if_som(data.layers, increment, depth_cm)
            if change is not None:
                evidence.extend([
                    Metric(code="som_increase", label_pl=text.SOM_SCENARIO_INCREMENT, value=increment, unit=text.PERCENTAGE_POINTS),
                    Metric(code="som_delta_taw", label_pl=text.SOM_SCENARIO_CHANGE, value=change.mid, unit="mm",
                           source_ids=[item.source_id for item in ctx.geo.soil.provenance]),
                ])
                references.extend(["saxton_rawls", "som_scenario"])
        results.append(Recommendation(
            id="build_soil_organic_matter", category="soil_retention", title_pl=text.ORGANIC_MATTER_TITLE,
            action_pl=text.ORGANIC_MATTER_ACTION, why_pl=text.ORGANIC_MATTER_WHY,
            evidence=evidence, reference_ids=references,
        ))
    return results
