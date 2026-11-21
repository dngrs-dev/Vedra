"""Interpret clear Sentinel-2 scenes relative to the crop and seasonal history."""
from __future__ import annotations

from datetime import date
from math import isfinite
from statistics import median
from typing import get_args

from scipy.stats import percentileofscore

from app.analytics import crops, periods, season, thresholds
from app.contracts.common import SourceStatus
from app.contracts.geo import KbwSoilCategory, VegetationData
from app.contracts.report import Metric, Signal
from app.recommendations import texts_pl as text


def _sensitive(crop: str, day: date, category: KbwSoilCategory | None) -> bool:
    if season.mode(day) == "off_season":
        return False
    schedule = periods.for_year(day.year)
    period = next((item for item in schedule if item.end >= day), None)
    if period is None:
        return False
    categories = (category,) if category else get_args(KbwSoilCategory)
    return any(isinstance(crops.threshold(crop, soil, period.idx), float) for soil in categories)


def interpret(
    veg: VegetationData | None,
    crop: str,
    analysis_date: date,
    *,
    soil_category: KbwSoilCategory | None = None,
    source_ids: list[str] | None = None,
    status: SourceStatus = SourceStatus.OK,
) -> Signal:
    missing = Signal(code="vegetation", status=SourceStatus.MISSING, summary_pl=text.VEG_UNAVAILABLE)
    if veg is None:
        return missing

    start, end = veg.current_window
    scenes = [
        scene for scene in veg.current
        if start <= scene.acquired <= min(end, analysis_date) and scene.valid_pixels > 0 and isfinite(scene.ndvi_median)
    ]
    if not scenes:
        return missing

    ids = source_ids or []
    current = median(scene.ndvi_median for scene in scenes)
    most_recent = max(scene.acquired for scene in scenes)
    metrics = [
        Metric(code="ndvi", label_pl="NDVI", value=current, source_ids=ids),
        Metric(code="veg_observation_date", label_pl=text.OBSERVATION_DATE, value=most_recent.isoformat(), source_ids=ids),
        Metric(code="clear_scenes", label_pl=text.VEG_CLEAR_SCENES, value=len(scenes), source_ids=ids),
    ]
    ndmi = [scene.ndmi_median for scene in scenes if isfinite(scene.ndmi_median)]
    if ndmi:
        metrics.append(Metric(code="ndmi", label_pl="NDMI", value=median(ndmi), source_ids=ids))

    annual = []
    for year, snapshots in veg.same_window_by_year.items():
        matching = [
            scene.ndvi_median for scene in snapshots
            if scene.acquired.year == year and scene.valid_pixels > 0 and isfinite(scene.ndvi_median)
        ]
        if year < analysis_date.year and matching:
            annual.append(median(matching))
    if not annual:
        return Signal(code="vegetation", status=SourceStatus.PARTIAL, summary_pl=text.VEG_NO_HISTORY, metrics=metrics)

    metrics.extend([
        Metric(code="veg_reference_years", label_pl=text.VEG_REFERENCE_YEARS, value=len(annual), source_ids=ids),
        Metric(code="ndvi_percentile", label_pl=text.VEG_NDVI_PERCENTILE,
               value=float(percentileofscore(annual, current, kind="mean")), source_ids=ids),
    ])
    low, high = min(annual), max(annual)
    if low == high:
        return Signal(code="vegetation", status=SourceStatus.PARTIAL, summary_pl=text.VEG_NO_VARIATION, metrics=metrics)

    # FAO GIEWS VCI definition. Clamp the display scale when current NDVI sets a new extreme.
    # https://www.fao.org/giews/earthobservation/asis/index_2.jsp?lang=en
    vci = min(100.0, max(0.0, 100 * (current - low) / (high - low)))
    metrics.append(Metric(code="vci", label_pl="VCI", value=vci, unit="%", source_ids=ids))
    limits = thresholds.load()["vegetation"]
    if not all(_sensitive(crop, day, soil_category) for day in (most_recent, analysis_date)):
        return Signal(code="vegetation", status=SourceStatus.PARTIAL, summary_pl=text.VEG_OUTSIDE_SENSITIVE_PHASE, metrics=metrics)
    summary = text.VEG_WITHIN_REFERENCE
    if vci < limits["vci_stress_below"]:
        summary = text.VEG_LOW
    elif vci > limits["vci_favorable_above"]:
        summary = text.VEG_FAVORABLE
    return Signal(code="vegetation", status=status, summary_pl=summary, metrics=metrics)
