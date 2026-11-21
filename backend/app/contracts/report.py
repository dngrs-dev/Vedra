"""Public JSON models shared with the frontend."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.contracts.common import DateWindow, Provenance, Range, SourceStatus
from app.contracts.geo import KbwSoilCategory
from app.contracts.parcel import Parcel

KbwVerdict = Literal[
    "drought", "no_drought", "not_applicable", "not_recommended", "off_season", "unavailable"
]
KbwThreshold = float | Literal["x", "-"]


class Metric(BaseModel):
    code: str
    label_pl: str
    value: float | int | str | Range | None
    unit: str | None = None
    source_ids: list[str] = Field(default_factory=list)


class Signal(BaseModel):
    code: str
    status: SourceStatus
    summary_pl: str
    metrics: list[Metric] = Field(default_factory=list)


class KbwAssessment(BaseModel):
    verdict: KbwVerdict
    explanation_pl: str
    period: DateWindow | None = None
    soil_category: KbwSoilCategory | None = None
    kbw_mm: float | None = None
    kbw_et0_mm: float | None = None
    threshold_mm: KbwThreshold | None = None
    distance_to_threshold_mm: float | None = None
    near_threshold: bool | None = None


class Vulnerability(BaseModel):
    summary_pl: str
    years_assessed: list[int] = Field(default_factory=list)
    drought_years: list[int] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)


class Assessment(BaseModel):
    kbw: KbwAssessment
    confidence: Literal["low", "medium", "high"] | None = None
    signals: list[Signal] = Field(default_factory=list)
    vulnerability: Vulnerability | None = None


class Cause(BaseModel):
    code: str
    title_pl: str
    explanation_pl: str
    # docs/PART_B_ANALYTICS_PRODUCT.md §3 requires evidence for each ranked cause.
    evidence: list[Metric] = Field(min_length=1)


class Recommendation(BaseModel):
    id: str
    category: Literal["landscape_retention", "soil_retention", "agrotechnics", "irrigation"]
    title_pl: str
    action_pl: str
    why_pl: str
    # docs/PART_B_ANALYTICS_PRODUCT.md §§3 and 5 require evidence and a reference per recommendation.
    evidence: list[Metric] = Field(min_length=1)
    reference_ids: list[str] = Field(min_length=1)
    geometry: dict | None = None  # GeoJSON in WGS84, consistent with docs/CONTRACTS.md §3.


class MapLayer(BaseModel):
    id: str
    name_pl: str
    geojson: dict  # WGS84 GeoJSON, consistent with docs/CONTRACTS.md §3.


class IrrigationAdvice(BaseModel):
    justified: bool | None
    why_pl: str
    suggested_date: date | None = None
    net_dose_mm: Range | None = None


class Reference(BaseModel):
    id: str
    title_pl: str
    url: str


class Report(BaseModel):
    report_id: str
    parcel: Parcel
    crop_code: str
    crop_name_pl: str
    analysis_date: date
    summary: str
    assessment: Assessment
    causes: list[Cause] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    map_layers: list[MapLayer] = Field(default_factory=list)
    irrigation: IrrigationAdvice | None = None
    limitations_pl: list[str] = Field(default_factory=list)
    data_sources: list[Provenance] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
