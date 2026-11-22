"""Monthly Doroszewski-Górski potential evapotranspiration estimates."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from math import acos, pi, radians, sin, tan
from statistics import mean

from app.analytics.models import WeatherData


def etp_monthly(t: float, h: float, f: float) -> float:
    """Return monthly ETP in mm from mean °C, sunshine hours and mid-month daylight hours."""
    # Doroszewski et al. (2014), Susza rolnicza w Polsce, equation (2), p. 15.
    # https://iung.pl/images/wyd/Susza%20rolnicza%20w%20Polsce.pdf
    return -89.6 + 0.0621 * t**2 + 0.00448 * h**1.66 + 9.1 * f


def daylight_hours(latitude: float, day: date) -> float:
    # FAO-56, equations (24), (25) and (34), with the arccos domain at polar latitudes.
    # https://www.fao.org/4/x0490e/x0490e07.htm
    declination = 0.409 * sin(2 * pi * day.timetuple().tm_yday / 365 - 1.39)
    sunset_angle = acos(max(-1.0, min(1.0, -tan(radians(latitude)) * tan(declination))))
    return 24 * sunset_angle / pi


def etp_period(weather: WeatherData, start: date, end: date) -> float | None:
    """Prorate monthly ETP over inclusive dates, using observations through end."""
    if start > end:
        raise ValueError("ETP period starts after it ends")

    total = 0.0
    one_day = timedelta(days=1)
    month_start = start.replace(day=1)
    while month_start <= end:
        month_days = monthrange(month_start.year, month_start.month)[1]
        month_end = month_start.replace(day=month_days)
        available_end = min(end, month_end)
        count = (available_end - month_start).days + 1
        temperatures: list[float] = []
        sunshine: list[float] = []
        for offset in range(count):
            row = weather.days.get(month_start + offset * one_day)
            if row is None or row.temperature_mean_c is None or row.sunshine_h is None:
                return None
            temperatures.append(row.temperature_mean_c)
            sunshine.append(row.sunshine_h)

        # FAO-56, Annex 2 table 2.7 uses the 15th for representative monthly daylight.
        mid_month = month_start.replace(day=15)
        middle = weather.days.get(mid_month) if mid_month <= end else None
        daylight = middle.daylight_h if middle and middle.daylight_h is not None else daylight_hours(
            weather.latitude, mid_month
        )
        # See docs/METHODOLOGY.md: extrapolate the observed month's prefix, then prorate its ETP.
        monthly_etp = etp_monthly(mean(temperatures), sum(sunshine) * month_days / count, daylight)
        overlap_days = (available_end - max(start, month_start)).days + 1
        total += monthly_etp * overlap_days / month_days
        month_start = month_end + one_day

    return total
