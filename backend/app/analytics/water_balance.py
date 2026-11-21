"""FAO-56 daily root-zone balance for available soil and weather observations."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from itertools import product

from app.analytics.crops import Crop
from app.analytics.models import WeatherData, WeatherDay
from app.analytics.soil_water import MM_PER_CM, RootLayer, profile_taw, root_profile
from app.contracts.geo import SoilInfo

# Open-Meteo ERA5-Land archive layer limits (cm), as used by soil_moisture.py.
LAYERS = ((0, 7, "soil_moisture_0_to_7cm"), (7, 28, "soil_moisture_7_to_28cm"), (28, 100, "soil_moisture_28_to_100cm"))
CM_PER_METRE = 100  # SI length conversion.


@dataclass(frozen=True, slots=True)
class BalanceDay:
    day: date
    depletion_mm: float
    raw_mm: float
    ks: float


@dataclass(frozen=True, slots=True)
class Scenario:
    taw_mm: float
    kc: float
    p: float
    observations: tuple[BalanceDay, ...]


@dataclass(frozen=True, slots=True)
class DailyBalance:
    centre: Scenario
    alternatives: tuple[Scenario, ...]

    @property
    def stress_days(self) -> int:
        return sum(item.ks < 1 for item in self.centre.observations)


def _initial(profile: tuple[RootLayer, ...], row: WeatherDay) -> float | None:
    if profile[-1].bottom_cm > LAYERS[-1][1]:
        return None
    depletion = 0.0
    for layer in profile:
        for top, bottom, attribute in LAYERS:
            thickness = min(layer.bottom_cm, bottom) - max(layer.top_cm, top)
            if thickness <= 0:
                continue
            water = getattr(row, attribute)
            if water is None or not 0 <= water <= 1:
                return None
            bounded = max(layer.wp.mid, min(layer.fc.mid, water))
            depletion += (layer.fc.mid - bounded) * thickness * MM_PER_CM
    return depletion


def _raw(taw: float, p: float, kc: float, et0: float | None) -> float:
    # FAO-56 chapter 8: adjust p for ETc and bound it to [0.1, 0.8], then RAW = p × TAW.
    fraction = p if et0 is None else min(0.8, max(0.1, p + 0.04 * (5 - kc * et0)))
    return fraction * taw


def _ks(depletion: float, raw: float, taw: float) -> float:
    # FAO-56 chapter 8, equation (84).
    return 1.0 if depletion <= raw else (taw - depletion) / (taw - raw)


def advance(previous: BalanceDay, scenario: Scenario, day: date, row: WeatherDay | None) -> BalanceDay | None:
    if row is None or row.precipitation_mm is None or row.et0_mm is None:
        return None
    taw = scenario.taw_mm
    raw = _raw(taw, scenario.p, scenario.kc, row.et0_mm)
    ks = _ks(previous.depletion_mm, raw, taw)
    # FAO-56 equation (85), rainfed bucket with same-day drainage above field capacity.
    depletion = min(taw, max(0.0, previous.depletion_mm + ks * scenario.kc * row.et0_mm - row.precipitation_mm))
    return BalanceDay(day, depletion, raw, ks)


def _calculate(weather: WeatherData, soil: SoilInfo, start: date, end: date, zr_m: float, kc: float, p: float) -> Scenario | None:
    profile = root_profile(soil.layers, zr_m * CM_PER_METRE)
    if profile is None or profile[-1].bottom_cm > LAYERS[-1][1]:
        return None
    taw = profile_taw(profile).mid
    scenario = Scenario(taw, kc, p, ())
    observations: list[BalanceDay] = []
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        row = weather.days.get(day)
        if observations:
            result = advance(observations[-1], scenario, day, row)
            if result is not None:
                observations.append(result)
                continue
        # Start or restart at a modelled soil-moisture observation after a missing daily input.
        observations.clear()
        if row is not None and (depletion := _initial(profile, row)) is not None:
            raw = _raw(taw, p, kc, row.et0_mm)
            observations.append(BalanceDay(day, depletion, raw, _ks(depletion, raw, taw)))
    return Scenario(taw, kc, p, tuple(observations)) if observations else None


def run(weather: WeatherData | None, crop: Crop, soil: SoilInfo | None, start: date, end: date) -> DailyBalance | None:
    if weather is None or soil is None or start > end:
        return None
    kc = crop.kc.mid
    low_kc, high_kc = kc if isinstance(kc, tuple) else (kc, kc)
    depths = (crop.zr_m.low, crop.zr_m.high)
    centre_depth = sum(depths) / len(depths)
    centre_kc = (low_kc + high_kc) / 2  # Arithmetic midpoint of the sourced Kc interval.
    centre = _calculate(weather, soil, start, end, centre_depth, centre_kc, crop.p.value)
    if centre is None:
        return None
    alternatives = []
    for depth, coefficient in dict.fromkeys(product(depths, (low_kc, high_kc))):
        if (depth, coefficient) != (centre_depth, centre_kc):
            estimate = _calculate(weather, soil, start, end, depth, coefficient, crop.p.value)
            if estimate is not None:
                alternatives.append(estimate)
    return DailyBalance(centre, tuple(alternatives))
