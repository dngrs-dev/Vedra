"""Internal input and output types for weather and climatic water balance."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.analytics.crops import Crop, Threshold
from app.contracts.common import SourceResult
from app.contracts.geo import GeoBundle, KbwSoilCategory
from app.contracts.parcel import Parcel
from app.contracts.report import Cause, Metric

KbwVerdict = Literal["drought", "no_drought", "not_applicable", "not_recommended", "off_season", "unavailable"]


@dataclass(frozen=True, slots=True)
class WeatherDay:
    precipitation_mm: float | None = None
    et0_mm: float | None = None
    temperature_mean_c: float | None = None
    temperature_max_c: float | None = None
    temperature_min_c: float | None = None
    sunshine_h: float | None = None
    daylight_h: float | None = None
    soil_moisture_0_to_7cm: float | None = None
    soil_moisture_7_to_28cm: float | None = None
    soil_moisture_28_to_100cm: float | None = None


@dataclass(frozen=True, slots=True)
class WeatherData:
    latitude: float
    longitude: float
    days: dict[date, WeatherDay] = field(default_factory=dict)


Forecast = WeatherData


@dataclass(frozen=True, slots=True)
class Period:
    idx: int
    start: date
    end: date


@dataclass(frozen=True, slots=True)
class KbwResult:
    verdict: KbwVerdict
    explanation_pl: str
    period: Period | None = None
    soil_category: KbwSoilCategory | None = None
    kbw_mm: float | None = None
    kbw_et0_mm: float | None = None
    threshold_mm: Threshold | None = None
    distance_to_threshold_mm: float | None = None
    near_threshold: bool | None = None


@dataclass(frozen=True, slots=True)
class KbwHistory:
    periods: tuple[KbwResult, ...]
    assessed_years: tuple[int, ...]
    drought_years: tuple[int, ...]
    risk_by_month: dict[int, float]


class AnalysisRequest(BaseModel):
    # README.md §4 requires the parcel identifier and crop code in submitted requests.
    parcel_id: str = Field(min_length=1)
    crop_code: str = Field(min_length=1)
    analysis_date: date
    include_irrigation: bool = False


@dataclass(frozen=True, slots=True)
class AnalysisContext:
    request: AnalysisRequest
    parcel: Parcel
    crop: Crop
    weather: SourceResult[WeatherData]
    geo: GeoBundle
    assessment: KbwResult
    history: KbwHistory
    weather_metrics: list[Metric]
    causes: list[Cause]
