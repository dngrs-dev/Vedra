"""Optional irrigation timing and net dose from the FAO-56 balance."""
from datetime import date, timedelta

from app.analytics.models import Forecast
from app.analytics.water_balance import BalanceDay, DailyBalance, Scenario, advance
from app.contracts.common import Range
from app.contracts.report import IrrigationAdvice
from app.recommendations import texts_pl as text


def _project(scenario: Scenario, forecast: Forecast | None, analysis_date: date) -> dict[date, BalanceDay]:
    current = scenario.observations[-1]
    points = {current.day: current}
    if forecast is None or current.day != analysis_date:
        return points
    for day in sorted(forecast.days):
        if day <= analysis_date:
            continue
        if day != current.day + timedelta(days=1):
            break
        next_day = advance(current, scenario, day, forecast.days[day])
        if next_day is None:
            break
        points[day] = current = next_day
    return points


def advise(balance: DailyBalance | None, forecast: Forecast | None, analysis_date: date) -> IrrigationAdvice:
    if balance is None or balance.centre.observations[-1].day != analysis_date:
        return IrrigationAdvice(justified=None, why_pl=text.IRRIGATION_MISSING_BALANCE)
    points = _project(balance.centre, forecast, analysis_date)
    limit = next((item for item in points.values() if item.depletion_mm >= item.raw_mm), None)
    if limit is None:
        return IrrigationAdvice(justified=False, why_pl=text.IRRIGATION_BELOW_RAW)
    doses = [limit.depletion_mm]
    for scenario in balance.alternatives:
        projected = _project(scenario, forecast, analysis_date).get(limit.day)
        if projected is not None:
            doses.append(projected.depletion_mm)
    # FAO-56 chapter 8: refill to field capacity without exceeding root-zone depletion.
    dose = Range(low=min(doses), mid=limit.depletion_mm, high=max(doses)) if len(doses) > 1 else Range(mid=limit.depletion_mm)
    explanation = text.IRRIGATION_REACHED_RAW if limit.day == analysis_date else text.IRRIGATION_PROJECTED_RAW
    return IrrigationAdvice(justified=True, why_pl=explanation, suggested_date=limit.day, net_dose_mm=dose)
