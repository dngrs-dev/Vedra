"""Apply the statutory crop thresholds to the prototype's climatic water balance."""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import date, timedelta

from app.analytics import crops, periods, season
from app.analytics.evapotranspiration import etp_period
from app.analytics.models import KbwHistory, KbwResult, Period, WeatherData
from app.config import years_before
from app.contracts.geo import KbwSoilCategory
from app.recommendations import texts_pl as text


def _period_balance(
    weather: WeatherData | None, soil_category: KbwSoilCategory | None, crop: str, period: Period
) -> KbwResult:
    if soil_category is None:
        return KbwResult("unavailable", text.KBW_SOIL_MISSING, period)

    threshold = crops.threshold(crop, soil_category, period.idx)
    if threshold == "x":
        return KbwResult("not_applicable", text.KBW_NOT_APPLICABLE, period, soil_category, threshold_mm=threshold)
    if threshold == "-":
        return KbwResult("not_recommended", text.KBW_NOT_RECOMMENDED, period, soil_category, threshold_mm=threshold)

    base = KbwResult("unavailable", text.KBW_WEATHER_MISSING, period, soil_category, threshold_mm=threshold)
    if weather is None:
        return base

    rows = [
        weather.days.get(period.start + timedelta(days=offset))
        for offset in range((period.end - period.start).days + 1)
    ]
    if any(row is None or row.precipitation_mm is None for row in rows):
        return base

    # IUNG, Susza rolnicza w Polsce, equation (1): KBW = precipitation minus ETP.
    precipitation = sum(row.precipitation_mm for row in rows)
    et0 = sum(row.et0_mm for row in rows) if all(row.et0_mm is not None for row in rows) else None
    et0_balance = None if et0 is None else precipitation - et0
    etp = etp_period(weather, period.start, period.end)
    if etp is None:
        return replace(base, kbw_et0_mm=et0_balance)

    balance = precipitation - etp
    distance = balance - threshold
    # Art. 3(2)(10) of the crop insurance act (Dz.U. 2019 poz. 477) specifies strictly below.
    # https://eli.gov.pl/api/acts/DU/2019/477/text/I/D20190477.pdf
    drought = distance < 0
    near = distance == 0 or (
        et0_balance is not None and min(balance, et0_balance) <= threshold <= max(balance, et0_balance)
    )
    explanation = text.KBW_DROUGHT if drought else text.KBW_NO_DROUGHT
    if near:
        explanation = f"{explanation} {text.KBW_NEAR_THRESHOLD}"
    return KbwResult(
        "drought" if drought else "no_drought",
        explanation,
        period,
        soil_category,
        balance,
        et0_balance,
        threshold,
        distance,
        near,
    )


def assess(
    weather: WeatherData | None, soil_category: KbwSoilCategory | None, crop: str, analysis_date: date
) -> KbwResult:
    if season.mode(analysis_date) == "off_season":
        return KbwResult("off_season", text.KBW_OFF_SEASON, soil_category=soil_category)
    period = periods.latest_completed(analysis_date)
    if period is None:
        first_end = periods.for_year(analysis_date.year)[0].end.strftime("%d.%m.%Y")
        explanation = text.KBW_NO_COMPLETED_PERIOD.format(first_period_end=first_end)
        return KbwResult("unavailable", explanation, soil_category=soil_category)
    return _period_balance(weather, soil_category, crop, period)


def history(
    weather: WeatherData | None,
    soil_category: KbwSoilCategory | None,
    crop: str,
    analysis_date: date,
    years: int = 10,  # Ten-year history specified in docs/PART_B_ANALYTICS_PRODUCT.md §3.
) -> KbwHistory:
    cutoff = years_before(analysis_date, years)
    results = tuple(
        _period_balance(weather, soil_category, crop, period)
        for year in range(cutoff.year, analysis_date.year + 1)
        for period in periods.for_year(year)
        if cutoff < period.end <= analysis_date
    )
    assessed_years: set[int] = set()
    drought_years: set[int] = set()
    assessed_months: Counter[int] = Counter()
    drought_months: Counter[int] = Counter()
    for result in results:
        if result.verdict in ("drought", "no_drought") and result.period is not None:
            end = result.period.end
            assessed_years.add(end.year)
            assessed_months[end.month] += 1
            if result.verdict == "drought":
                drought_years.add(end.year)
                drought_months[end.month] += 1
    risk = {month: drought_months[month] / count for month, count in sorted(assessed_months.items())}
    return KbwHistory(results, tuple(sorted(assessed_years)), tuple(sorted(drought_years)), risk)
