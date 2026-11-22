"""Public JSON models for the "what if" water scenarios and the optional AI commentary."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class ScenarioLevers(BaseModel):
    """Farmer actions. Zero for every lever means "do nothing" (the baseline)."""

    # Landscape retention: water held back on or next to the field (mm over the field area).
    retention_mm: float = Field(default=0, ge=0, le=60)
    # Soil retention: extra soil organic matter in percentage points.
    organic_matter_pct: float = Field(default=0, ge=0, le=3)
    # Cover crops, residues or mulch: share of the soil surface covered (%).
    cover_pct: float = Field(default=0, ge=0, le=100)
    # Irrigation: seasonal net water limit (mm) and the net dose of one irrigation (mm).
    irrigation_limit_mm: float = Field(default=0, ge=0, le=300)
    irrigation_dose_mm: float = Field(default=25, ge=5, le=50)


RiskLevel = Literal["low", "medium", "high"]


class WaterBudget(BaseModel):
    """Root-zone water balance over the simulated window, in mm."""

    precipitation_mm: float
    irrigation_mm: float
    retention_release_mm: float
    actual_et_mm: float
    potential_et_mm: float
    losses_mm: float  # drainage below the root zone that was not held back
    retained_mm: float  # surplus caught by landscape retention
    storage_change_mm: float  # end minus start of the root-zone water store


class ScenarioOutcome(BaseModel):
    stress_days: int
    days: int
    et_deficit_pct: float  # 1 - ETa/ETc, a proxy of the yield-relevant water shortage
    min_available_pct: float  # the lowest root-zone water reserve (% of available water)
    end_available_pct: float
    irrigation_events: int
    risk: RiskLevel
    budget: WaterBudget


class ScenarioPoint(BaseModel):
    day: date
    available_pct: float


class ScenarioResult(BaseModel):
    id: str
    title_pl: str
    description_pl: str
    levers: ScenarioLevers
    taw_mm: float
    outcome: ScenarioOutcome
    series: list[ScenarioPoint] = Field(default_factory=list)


class ScenarioReport(BaseModel):
    analysis_id: str
    crop_name_pl: str
    window_start: date
    window_end: date
    window_note_pl: str
    baseline: ScenarioResult
    custom: ScenarioResult
    presets: list[ScenarioResult]
    assumptions_pl: list[str]
    kbw_note_pl: str


class AiInsight(BaseModel):
    """Commentary written by an LLM (or by rules when no LLM is configured)."""

    source: Literal["llm", "rules"]
    model: str | None = None
    headline_pl: str
    forecast_pl: str
    best_action_pl: str
    reasoning_pl: list[str]
    caveats_pl: list[str]
    note_pl: str | None = None
