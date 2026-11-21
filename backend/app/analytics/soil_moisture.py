"""Calendar-day soil moisture percentiles from the ERA5-Land layers."""
from __future__ import annotations

from datetime import date
from math import isfinite

from scipy.stats import percentileofscore

from app.analytics.models import WeatherData
from app.analytics.thresholds import load
from app.contracts.common import SourceStatus
from app.contracts.report import Metric, Signal
from app.recommendations import texts_pl as text

# Open-Meteo Historical Weather API soil moisture layers in cm, backed by ERA5-Land.
LAYERS = {"0_to_7cm": "0–7", "7_to_28cm": "7–28", "28_to_100cm": "28–100"}
# Same date in the preceding ten years, docs/PART_B_ANALYTICS_PRODUCT.md §3.
HISTORY_YEARS = 10


def anomaly(weather: WeatherData | None, analysis_date: date, source_ids: list[str] | None = None) -> Signal:
    missing = Signal(code="soil_moisture", status=SourceStatus.MISSING, summary_pl=text.SOIL_MOISTURE_UNAVAILABLE)
    if weather is None:
        return missing
    available = [
        day for day, row in weather.days.items()
        if day <= analysis_date and any(getattr(row, f"soil_moisture_{layer}") is not None for layer in LAYERS)
    ]
    if not available:
        return missing

    current_day = max(available)
    current = weather.days[current_day]
    historical = [
        row for day, row in weather.days.items()
        if current_day.year - HISTORY_YEARS <= day.year < current_day.year
        and (day.month, day.day) == (current_day.month, current_day.day)
    ]
    ids = source_ids or []
    metrics = [Metric(code="soil_observation_date", label_pl=text.OBSERVATION_DATE, value=current_day.isoformat(), source_ids=ids)]
    counts = []
    percentiles = []
    for layer, depth in LAYERS.items():
        field = f"soil_moisture_{layer}"
        value = getattr(current, field)
        sample = [item for row in historical if (item := getattr(row, field)) is not None and isfinite(item)]
        if value is None or not isfinite(value) or not sample:
            continue
        percentile = float(percentileofscore(sample, value, kind="mean"))
        counts.append(len(sample))
        percentiles.append(percentile)
        metrics.extend([
            Metric(code=f"soil_percentile_{layer}", label_pl=text.SOIL_PERCENTILE.format(depth=depth), value=percentile, source_ids=ids),
            Metric(code=f"soil_sample_{layer}", label_pl=text.SOIL_REFERENCE_YEARS.format(depth=depth), value=len(sample)),
        ])
    if not counts:
        return missing

    dry = min(percentiles) < load()["soil_moisture"]["dry_percentile"]
    summary = text.SOIL_MOISTURE_LOW if dry else text.SOIL_MOISTURE_ABOVE_LOW
    if current_day != analysis_date:
        summary += f" {text.SOIL_MOISTURE_LAST_DATE.format(date=current_day.isoformat())}"
    complete = current_day == analysis_date and len(counts) == len(LAYERS) and min(counts) == HISTORY_YEARS
    return Signal(code="soil_moisture", status=SourceStatus.OK if complete else SourceStatus.PARTIAL, summary_pl=summary, metrics=metrics)
