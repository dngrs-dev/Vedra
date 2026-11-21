from datetime import date, timedelta

import pytest

from app.analytics import kbw, periods
from app.analytics.evapotranspiration import daylight_hours, etp_monthly, etp_period
from app.analytics.models import WeatherData, WeatherDay
from app.fakes.fake_geo import EXAMPLE_POINT

# Example historical year/date from docs/TEAM_SPLIT.md §7.
YEAR = 2023


def test_latest_completed_period_uses_annex_dates_inclusively():
    schedule = periods.for_year(YEAR)
    # Annex to Dz.U. 2019 poz. 739, table header: first and last statutory dates.
    assert len(schedule) == 14
    assert schedule[0].start == date(YEAR, 3, 21)
    assert schedule[-1].end == date(YEAR, 9, 30)
    for previous, completed in zip(schedule, schedule[1:]):
        assert periods.latest_completed(completed.end - timedelta(days=1)) == previous
        assert periods.latest_completed(completed.end) == completed
    assert periods.latest_completed(schedule[0].end - timedelta(days=1)) is None


def test_monthly_etp_and_daylight_use_the_published_equations():
    # Formula evaluation with synthetic inputs, using Doroszewski et al. (2014), eq. (2).
    assert etp_monthly(0, 0, 12) == pytest.approx(19.6)
    assert etp_monthly(20, 220, 10.9) == pytest.approx(69.07971478849177)
    # FAO-56, Chapter 3, Example 9: 11.7 hours on 3 September at latitude 20° S.
    assert round(daylight_hours(-20, date(YEAR, 9, 3)), 1) == 11.7


def test_etp_prorates_a_month_without_using_later_values():
    # Identical synthetic May days give an exactly reproducible test for the approximation.
    start = date(YEAR, 5, 1)
    weather = WeatherData(*EXAMPLE_POINT, {
        start + timedelta(days=offset): WeatherDay(temperature_mean_c=20, sunshine_h=5, daylight_h=15)
        for offset in range(31)
    })
    period_start = start.replace(day=11)
    period_end = start.replace(day=20)
    weather.days[period_end + timedelta(days=1)] = WeatherDay(temperature_mean_c=40, sunshine_h=8)
    expected = etp_monthly(20, 5 * 31, 15) * 10 / 31
    assert etp_period(weather, period_start, period_end) == pytest.approx(expected)
    del weather.days[period_start]
    assert etp_period(weather, period_start, period_end) is None


def test_kbw_keeps_the_statute_markers_and_rejects_incomplete_periods():
    assert kbw.assess(None, "I", "winter_cereals", date(YEAR, 11, 21)).verdict == "off_season"
    assert kbw.assess(None, "I", "winter_cereals", date(YEAR, 5, 19)).period is None
    assert kbw.assess(None, "I", "winter_cereals", date(YEAR, 8, 20)).threshold_mm == "x"
    assert kbw.assess(None, "I", "sugar_beet", date(YEAR, 5, 20)).threshold_mm == "-"
    assert kbw.assess(None, None, "winter_cereals", date(YEAR, 5, 20)).verdict == "unavailable"
    assert kbw.assess(None, "I", "winter_cereals", date(YEAR, 5, 20)).verdict == "unavailable"


def test_history_and_threshold_comparison_use_the_completed_window(monkeypatch):
    # The winter cereal thresholds in the annex for I, windows 1 and 2, are -129 and -132 mm.
    # Use rain-free synthetic days and fixed estimators to exercise both sides of the threshold.
    first, second, *_ = periods.for_year(YEAR)
    days = {
        first.start + timedelta(days=offset): WeatherDay(precipitation_mm=0, et0_mm=1)
        for offset in range((second.end - first.start).days + 1)
    }
    weather = WeatherData(*EXAMPLE_POINT, days)
    monkeypatch.setattr(kbw, "etp_period", lambda *_: 130)
    assessed = kbw.assess(weather, "I", "winter_cereals", first.end)
    assert assessed.verdict == "drought"
    assert assessed.kbw_mm == -130
    assert assessed.kbw_et0_mm == -((first.end - first.start).days + 1)
    assert assessed.distance_to_threshold_mm == -1
    assert assessed.near_threshold is True

    history = kbw.history(weather, "I", "winter_cereals", second.end)
    assert history.assessed_years == history.drought_years == (YEAR,)
    assert history.risk_by_month == {5: 0.5}
    assert history.periods[-1].period == second

    monkeypatch.setattr(kbw, "etp_period", lambda *_: 129)
    at_threshold = kbw.assess(weather, "I", "winter_cereals", first.end)
    assert at_threshold.verdict == "no_drought"
    assert at_threshold.near_threshold is True
