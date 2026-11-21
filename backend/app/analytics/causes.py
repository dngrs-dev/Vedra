"""Rank evidence-backed drivers of an estimated parcel water deficit."""
from __future__ import annotations

from datetime import timedelta
from statistics import mean

from app.analytics import periods
from app.analytics.models import AnalysisContext, KbwResult, Period, WeatherData
from app.analytics.spi import BASELINE
from app.contracts.common import SourceResult
from app.contracts.report import Cause, Metric
from app.recommendations import texts_pl as text

# ESA WorldCover Product User Manual v2.0, table 3.
# https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/docs/WorldCover_PUM_V2.0.pdf
WORLD_COVER_CLASSES = {
    "10": "tree cover", "20": "shrubland", "30": "grassland", "40": "cropland",
    "50": "built up", "60": "bare sparse vegetation", "70": "snow and ice",
    "80": "permanent water bodies", "90": "herbaceous wetland", "95": "mangroves", "100": "moss and lichen",
}
# European Commission catalogue of natural water retention measures: tree cover, hedges, and wetlands.
# https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=celex%3A52019SC0078
RETENTION_CLASSES = {"tree cover", "shrubland", "permanent water bodies", "permanent water", "herbaceous wetland"}


def _ids(source: SourceResult) -> list[str]:
    return [item.source_id for item in source.provenance]


def _total(weather: WeatherData, period: Period, attribute: str) -> float | None:
    values = []
    for offset in range((period.end - period.start).days + 1):
        row = weather.days.get(period.start + timedelta(days=offset))
        value = getattr(row, attribute, None)
        if value is None:
            return None
        values.append(value)
    return sum(values)


def weather_metrics(weather: SourceResult[WeatherData], assessment: KbwResult) -> list[Metric]:
    if assessment.period is None or assessment.kbw_mm is None or weather.data is None:
        return []
    precipitation = _total(weather.data, assessment.period, "precipitation_mm")
    if precipitation is None:
        return []
    source_ids = _ids(weather)
    return [
        Metric(code="precipitation", label_pl=text.PRECIPITATION_LABEL, value=precipitation, unit="mm", source_ids=source_ids),
        Metric(code="potential_evapotranspiration", label_pl=text.ETP_LABEL,
               value=precipitation - assessment.kbw_mm, unit="mm", source_ids=source_ids),
    ]


def _weather_causes(ctx: AnalysisContext) -> list[Cause]:
    weather, current = ctx.weather.data, ctx.assessment.period
    if weather is None or current is None or not ctx.weather_metrics:
        return []
    earlier = [
        periods.for_year(year)[current.idx - 1]
        for year in range(BASELINE[0], min(BASELINE[1] + 1, current.start.year))
    ]
    found: list[tuple[float, Cause]] = []
    for attribute, code, title, explanation, label in (
        ("precipitation_mm", "precipitation_deficit", text.CAUSE_PRECIPITATION, text.CAUSE_PRECIPITATION_WHY, text.PRECIPITATION_LABEL),
        ("et0_mm", "evaporative_demand", text.CAUSE_ET0, text.CAUSE_ET0_WHY, text.CAUSE_ET0_LABEL),
    ):
        actual = _total(weather, current, attribute)
        sample = [value for period in earlier if (value := _total(weather, period, attribute)) is not None]
        if actual is None or not sample:
            continue
        reference = mean(sample)
        excess = reference - actual if attribute == "precipitation_mm" else actual - reference
        if excess > 0:
            ids = _ids(ctx.weather)
            found.append((excess, Cause(code=code, title_pl=title, explanation_pl=explanation, evidence=[
                Metric(code=f"{code}_actual", label_pl=label, value=actual, unit="mm", source_ids=ids),
                Metric(code=f"{code}_reference", label_pl=text.CAUSE_BASELINE, value=reference, unit="mm", source_ids=ids),
                Metric(code=f"{code}_sample_years", label_pl=text.VEG_REFERENCE_YEARS, value=len(sample)),
            ])))
    if found:
        return [cause for _, cause in sorted(found, key=lambda item: item[0], reverse=True)]
    return [Cause(code="meteorological_deficit", title_pl=text.WEATHER_DEFICIT_TITLE,
                  explanation_pl=text.WEATHER_DEFICIT_EXPLANATION, evidence=ctx.weather_metrics)]


def _land_cover_cause(ctx: AnalysisContext) -> Cause | None:
    cover = ctx.geo.landcover.data
    if cover is None or "worldcover" not in cover.dataset.casefold():
        return None
    shares = {}
    for label, value in cover.shares_buffer.items():
        normalized = " ".join(label.casefold().replace("_", " ").replace("-", " ").replace("/", " ").split())
        shares[WORLD_COVER_CLASSES.get(normalized, normalized)] = value
    known = set(WORLD_COVER_CLASSES.values()) | RETENTION_CLASSES
    if not shares or shares.keys() - known or sum(shares.values()) <= 0:
        return None
    mapped = sum(value for label, value in shares.items() if label in RETENTION_CLASSES)
    if mapped > 0:
        return None
    ids = _ids(ctx.geo.landcover)
    return Cause(code="limited_landscape_retention", title_pl=text.CAUSE_LAND_COVER,
                 explanation_pl=text.CAUSE_LAND_COVER_WHY, evidence=[
                     Metric(code="retaining_land_cover_share", label_pl=text.CAUSE_RETAINING_SHARE,
                            value=mapped * 100, unit="%", source_ids=ids),
                     Metric(code="land_cover_buffer", label_pl=text.CAUSE_LAND_COVER_BUFFER,
                            value=cover.buffer_m, unit="m", source_ids=ids),
                 ])


def rank(ctx: AnalysisContext) -> list[Cause]:
    if ctx.assessment.kbw_mm is None or ctx.assessment.kbw_mm >= 0:
        return []
    # Order quantified weather differences first, then local soil, terrain, land cover, and crop context.
    causes = _weather_causes(ctx)
    soil = ctx.geo.soil.data
    # The annex to Dz.U. 2019 poz. 739 calls categories I and II susceptible to drought.
    if soil and soil.kbw_category in {"I", "II"}:
        ids = _ids(ctx.geo.soil)
        evidence = [Metric(code="soil_kbw_category", label_pl=text.SOIL_CATEGORY, value=soil.kbw_category, source_ids=ids)]
        if soil.wod_mm is not None:
            evidence.append(Metric(code="wod", label_pl=text.SOIL_AVAILABLE_WATER, value=soil.wod_mm, unit="mm", source_ids=ids))
        causes.append(Cause(code="low_soil_retention", title_pl=text.CAUSE_SOIL, explanation_pl=text.CAUSE_SOIL_WHY, evidence=evidence))

    terrain = ctx.geo.terrain.data
    if terrain is not None:
        crossing = [line for line in terrain.flow_lines if line.crosses_parcel]
        if crossing:
            ids = _ids(ctx.geo.terrain)
            causes.append(Cause(code="surface_runoff", title_pl=text.CAUSE_RUNOFF, explanation_pl=text.CAUSE_RUNOFF_WHY, evidence=[
                Metric(code="crossing_flow_lines", label_pl=text.CAUSE_FLOW_LINES, value=len(crossing), source_ids=ids),
                Metric(code="flow_area", label_pl=text.CAUSE_FLOW_AREA,
                       value=max(line.upstream_area_ha for line in crossing), unit="ha", source_ids=ids),
            ]))

    land_cover = _land_cover_cause(ctx)
    if land_cover is not None:
        causes.append(land_cover)

    mid = ctx.crop.kc.mid
    low = mid[0] if isinstance(mid, tuple) else mid
    # FAO-56 equation (58): ETc = Kc * ET0. Kc > 1 implies higher demand than the reference crop.
    if low > 1:
        causes.append(Cause(code="crop_water_demand", title_pl=text.CAUSE_CROP, explanation_pl=text.CAUSE_CROP_WHY, evidence=[
            Metric(code="kc_mid_lower", label_pl=text.CAUSE_CROP_KC, value=low),
            Metric(code="crop_profile", label_pl=text.CAUSE_CROP_PROFILE, value=ctx.crop.irrigation_profile_pl or ctx.crop.name_pl),
        ]))
    return causes
