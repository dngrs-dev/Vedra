"""Standardized Precipitation Index for complete calendar months."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy.stats import gamma, norm

from app.analytics.models import WeatherData
from app.analytics.thresholds import load
from app.contracts.common import SourceStatus
from app.contracts.report import Metric, Signal
from app.recommendations import texts_pl as text

# WMO climate normal and SPI scales selected in docs/PART_B_ANALYTICS_PRODUCT.md §3.
BASELINE = (1991, 2020)
SCALES = (1, 3)


def _accumulations(monthly_precip: pd.Series, scale: int) -> pd.Series:
    if scale < 1:
        raise ValueError("SPI scale must contain at least one month")
    index = pd.PeriodIndex(monthly_precip.index, freq="M")
    totals = pd.Series(monthly_precip.to_numpy(dtype=float), index=index)
    if totals.empty:
        return totals
    months = pd.period_range(index.min(), index.max(), freq="M")
    return totals.where(np.isfinite(totals) & (totals >= 0)).reindex(months).rolling(scale).sum()


def _reference(totals: pd.Series, month: int, baseline: tuple[int, int]) -> pd.Series:
    start, end = baseline
    return totals[(totals.index.month == month) & (totals.index.year >= start) & (totals.index.year <= end)].dropna()


def spi(monthly_precip: pd.Series, scale: int, baseline: tuple[int, int] = BASELINE) -> pd.Series:
    accumulations = _accumulations(monthly_precip, scale)
    result = pd.Series(np.nan, index=accumulations.index, name=f"spi_{scale}")
    for month, totals in accumulations.groupby(accumulations.index.month):
        reference = _reference(accumulations, month, baseline)
        positive = reference[reference > 0]
        # A two-parameter gamma fit needs variation among the positive observations.
        if positive.nunique() < 2:
            continue
        try:
            shape, _, spread = gamma.fit(positive.to_numpy(), floc=0)
        except (ValueError, RuntimeError):
            continue
        # Edwards & McKee's mixed CDF, cited in WMO-No. 1090: H(x) = q + (1 - q) G(x).
        probability_zero = float((reference == 0).mean())
        probability = probability_zero + (1 - probability_zero) * gamma.cdf(totals, shape, scale=spread)
        # Keep the normal quantile finite at the floating-point endpoints.
        result.loc[totals.index] = norm.ppf(np.clip(probability, np.nextafter(0.0, 1.0), np.nextafter(1.0, 0.0)))
    index = pd.PeriodIndex(monthly_precip.index, freq="M")
    return pd.Series(result.reindex(index).to_numpy(), index=monthly_precip.index, name=result.name)


def _monthly_precip(weather: WeatherData, analysis_date: date) -> pd.Series:
    totals: dict[pd.Period, list[float]] = defaultdict(list)
    for day, row in weather.days.items():
        if day <= analysis_date and row.precipitation_mm is not None:
            totals[pd.Period(day, freq="M")].append(row.precipitation_mm)
    return pd.Series(
        {month: sum(values) for month, values in totals.items() if month.days_in_month == len(values)}, dtype=float
    )


def _severity(value: float) -> str:
    limits = load()["spi"]
    if value <= limits["extreme_dry"]:
        return text.SPI_EXTREME
    if value <= limits["severe_dry"]:
        return text.SPI_SEVERE
    if value <= limits["moderate_dry"]:
        return text.SPI_MODERATE
    if value < 0:
        return text.SPI_MILD
    return text.SPI_ABOVE_DROUGHT_THRESHOLD


def assess(weather: WeatherData | None, analysis_date: date, source_ids: list[str]) -> Signal:
    missing = Signal(code="spi", status=SourceStatus.MISSING, summary_pl=text.SPI_UNAVAILABLE)
    if weather is None:
        return missing
    month = pd.Period(analysis_date, freq="M")
    if analysis_date + timedelta(days=1) <= month.end_time.date():
        month -= 1
    monthly = _monthly_precip(weather, analysis_date)
    if month not in monthly:
        return missing

    metrics = [Metric(code="spi_period", label_pl=text.SPI_PERIOD, value=str(month), source_ids=source_ids)]
    classes = []
    counts = []
    for scale in SCALES:
        score = spi(monthly, scale).at[month]
        if np.isfinite(score):
            sample = _reference(_accumulations(monthly, scale), month.month, BASELINE)
            counts.append(len(sample))
            metrics.extend([
                Metric(code=f"spi_{scale}", label_pl=f"SPI-{scale}", value=float(score), source_ids=source_ids),
                Metric(code=f"spi_years_{scale}", label_pl=text.SPI_REFERENCE_YEARS.format(scale=scale), value=len(sample)),
            ])
            classes.append(f"SPI-{scale}: {_severity(score)}")
    if not counts:
        return missing

    expected_years = BASELINE[1] - BASELINE[0] + 1
    complete = len(counts) == len(SCALES) and min(counts) == expected_years
    summary = ". ".join(classes) + "."
    if not complete:
        summary += f" {text.SPI_INCOMPLETE_BASELINE}"
    return Signal(code="spi", status=SourceStatus.OK if complete else SourceStatus.PARTIAL, summary_pl=summary, metrics=metrics)
