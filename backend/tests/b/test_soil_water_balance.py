from datetime import date, timedelta

import pytest

from app.analytics import crops, irrigation, soil_water, water_balance
from app.analytics.models import WeatherData, WeatherDay
from app.contracts.common import Range
from app.contracts.geo import SoilInfo, SoilLayer
from app.fakes.fake_geo import EXAMPLE_POINT


def test_taw_uses_layer_thickness_and_requires_full_coverage():
    # Synthetic layers with 0.20 m³/m³ of available water over a 50 cm root zone.
    layers = [SoilLayer(top_cm=0, bottom_cm=60, theta_fc=Range(low=0.28, mid=0.30, high=0.32),
                        theta_wp=Range(low=0.08, mid=0.10, high=0.12))]
    water = soil_water.taw_mm(layers, 50)
    assert water.mid == pytest.approx(100)
    assert water.low == pytest.approx(80)
    assert water.high == pytest.approx(120)
    assert soil_water.taw_mm(layers, 70) is None


def test_organic_matter_scenario_requires_texture_and_carbon():
    # Synthetic texture used to exercise Saxton & Rawls (2006), table 1.
    layer = SoilLayer(top_cm=0, bottom_cm=60, sand_pct=Range(mid=60), clay_pct=Range(mid=20), soc_g_kg=Range(mid=10))
    assert soil_water.taw_mm([layer], 50).mid > 0
    assert soil_water.what_if_som([layer], 0, 50).mid == 0
    assert soil_water.what_if_som([layer], soil_water.SOC_TO_SOM, 50).mid > 0
    assert soil_water.what_if_som([layer.model_copy(update={"soc_g_kg": None})], soil_water.SOC_TO_SOM, 50) is None


def test_irrigation_uses_consecutive_forecast_days_after_the_analysis_date():
    # Use the team example date and a synthetic profile at 30 mm initial depletion.
    analysis_date = date(2023, 5, 31)
    next_day = analysis_date + timedelta(days=1)
    soil = SoilInfo(layers=[SoilLayer(top_cm=0, bottom_cm=60, theta_fc=Range(mid=0.30), theta_wp=Range(mid=0.10))])
    current = WeatherDay(precipitation_mm=0, et0_mm=5, soil_moisture_0_to_7cm=0.24,
                         soil_moisture_7_to_28cm=0.24, soil_moisture_28_to_100cm=0.24)
    weather = WeatherData(*EXAMPLE_POINT, {analysis_date: current})
    crop = crops.load()["potatoes"]
    balance = water_balance.run(weather, crop, soil, analysis_date, analysis_date)
    assert balance.centre.observations[-1].depletion_mm == pytest.approx(30)
    assert irrigation.advise(balance, None, analysis_date).justified is False

    forecast = WeatherData(*EXAMPLE_POINT, {next_day: WeatherDay(precipitation_mm=0, et0_mm=5)})
    advice = irrigation.advise(balance, forecast, analysis_date)
    assert advice.justified is True
    assert advice.suggested_date == next_day
    assert advice.net_dose_mm.low <= advice.net_dose_mm.mid <= advice.net_dose_mm.high
