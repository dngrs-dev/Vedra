"""Shared building blocks of the A<->B contract. Frozen after T0."""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class SourceStatus(str, Enum):
    OK = "ok"
    PARTIAL = "partial"
    MISSING = "missing"


class Provenance(BaseModel):
    source_id: str  # stable id, e.g. "uldk", "sentinel2_earth_search"
    name: str  # display name, e.g. "ULDK GUGiK"
    url: str  # endpoint or dataset URL actually used
    fetched_at: datetime  # UTC
    live: bool  # True = fetched during this analysis; False = preprocessed file
    data_period: str | None = None  # e.g. "2016-05-01..2026-05-31" or "2021"
    resolution: str | None = None  # e.g. "10 m", "0.1 deg", "1:5000"
    licence: str  # e.g. "CC BY 4.0"
    attribution_pl: str | None = None  # exact attribution text required by the provider


class SourceResult(BaseModel, Generic[T]):
    status: SourceStatus
    data: T | None = None
    provenance: list[Provenance] = Field(default_factory=list)
    notes_pl: list[str] = Field(default_factory=list)  # user-facing limitations (Polish)
    error: str | None = None  # technical detail for logs (English)
    elapsed_s: float | None = None


class Range(BaseModel):
    """A value with optional uncertainty bounds (e.g. SoilGrids Q0.05 / Q0.5 / Q0.95)."""

    low: float | None = None
    mid: float
    high: float | None = None


class DateWindow(BaseModel):
    start: date
    end: date
