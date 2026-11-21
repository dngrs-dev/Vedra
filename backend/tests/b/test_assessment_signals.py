from datetime import date

import pandas as pd
import pytest

from app.analytics import edo_signal, season, soil_moisture, spi, vegetation_signal
from app.analytics.models import WeatherData, WeatherDay
from app.contracts.common import SourceResult, SourceStatus
from app.contracts.geo import EdoData, SceneStat, VegetationData
from app.fakes.fake_geo import EXAMPLE_POINT
from app.recommendations import texts_pl as text

# Historical date used in docs/TEAM_SPLIT.md §7. The test observations are synthetic.
ANALYSIS_DATE = date(2023, 5, 31)


def test_spi_uses_calendar_months_and_zero_mass():
    baseline = pd.period_range("1991-05", "2020-05", freq="12M").asfreq("M", how="start")
    reference = pd.Series([float(idx) for idx in range(len(baseline))], index=baseline)
    score = spi.spi(reference, 1)
    assert score.iloc[0] == pytest.approx(-1.8339146358159146)
    assert score.iloc[0] < score.iloc[-1]
    assert spi.spi(reference, 3).isna().all()


def test_soil_percentile_uses_matching_calendar_days_and_never_reads_a_future_day():
    years = range(ANALYSIS_DATE.year - soil_moisture.HISTORY_YEARS, ANALYSIS_DATE.year)
    days = {
        date(year, 5, 31): WeatherDay(soil_moisture_0_to_7cm=0.3, soil_moisture_7_to_28cm=0.3, soil_moisture_28_to_100cm=0.3)
        for year in years
    }
    days[ANALYSIS_DATE] = WeatherDay(soil_moisture_0_to_7cm=0.1, soil_moisture_7_to_28cm=0.3, soil_moisture_28_to_100cm=0.4)
    days[date(2023, 6, 1)] = WeatherDay(soil_moisture_0_to_7cm=0.4)
    result = soil_moisture.anomaly(WeatherData(*EXAMPLE_POINT, days), ANALYSIS_DATE)
    values = {item.code: item.value for item in result.metrics}
    assert result.status == SourceStatus.OK
    assert result.summary_pl == text.SOIL_MOISTURE_LOW
    assert values["soil_observation_date"] == ANALYSIS_DATE.isoformat()
    assert values["soil_percentile_0_to_7cm"] == 0
    assert values["soil_percentile_7_to_28cm"] == 50
    assert values["soil_percentile_28_to_100cm"] == 100


def _scene(day: date, ndvi: float) -> SceneStat:
    return SceneStat(scene_id=f"test-{day}", acquired=day, ndvi_median=ndvi, ndmi_median=0.1,
                     valid_pixels=1, valid_fraction=1)


def test_vegetation_uses_current_and_prior_matching_scenes_with_crop_context():
    veg = VegetationData(
        interior_pixels=1,
        current=[_scene(ANALYSIS_DATE, 0.35), _scene(date(2023, 6, 1), 0.9)],
        current_window=(date(2023, 5, 20), date(2023, 6, 1)),
        same_window_by_year={2021: [_scene(date(2021, 5, 31), 0.4)], 2022: [_scene(date(2022, 5, 31), 0.8)]},
        season_peaks={},
        scenes_considered=2,
        scenes_processed=2,
    )
    active = vegetation_signal.interpret(veg, "winter_cereals", ANALYSIS_DATE)
    assert active.status == SourceStatus.OK
    assert active.summary_pl == text.VEG_LOW
    assert {item.code: item.value for item in active.metrics}["vci"] == 0

    # The annex uses x for the first periods of grain maize. The same NDVI has a different meaning.
    early = vegetation_signal.interpret(veg, "grain_maize", date(2023, 5, 31))
    assert early.status == SourceStatus.PARTIAL
    assert early.summary_pl == text.VEG_OUTSIDE_SENSITIVE_PHASE


def test_edo_reads_the_official_legend_and_rejects_future_data():
    data = EdoData(date_used=ANALYSIS_DATE, cdi_class="Warning", cdi_value=2)
    result = SourceResult[EdoData](status=SourceStatus.OK, data=data)

    signal = edo_signal.interpret(result, ANALYSIS_DATE)
    assert signal.summary_pl == text.CDI_SUMMARY.format(label=text.CDI_WARNING)
    assert edo_signal.interpret(result, date(2023, 5, 30)).status == SourceStatus.MISSING


def test_season_includes_both_published_boundary_dates():
    # Boundary dates from the annex to Dz.U. 2019 poz. 739.
    assert season.mode(date(2023, 3, 20)) == "off_season"
    assert season.mode(date(2023, 3, 21)) == "in_season"
    assert season.mode(date(2023, 9, 30)) == "in_season"
    assert season.mode(date(2023, 10, 1)) == "off_season"
