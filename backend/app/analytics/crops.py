"""Crop catalog and statutory climatic water balance thresholds."""
from __future__ import annotations

import csv
from functools import cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, TypeAdapter

from app.config import CONFIG_DIR
from app.contracts.geo import KbwSoilCategory

Coefficient = float | tuple[float, float]
Threshold = float | Literal["x", "-"]


class CropCoefficients(BaseModel):
    initial: Coefficient
    mid: Coefficient
    end: Coefficient
    source: str


class RootDepth(BaseModel):
    low: float
    high: float
    source: str


class DepletionFraction(BaseModel):
    value: float
    source: str


class Crop(BaseModel):
    name_pl: str
    source: str
    irrigation_profile_pl: str | None = None
    kc: CropCoefficients
    zr_m: RootDepth
    p: DepletionFraction


@cache
def load(config_dir: Path = CONFIG_DIR) -> dict[str, Crop]:
    with (config_dir / "crops.yaml").open(encoding="utf-8") as catalog:
        return TypeAdapter(dict[str, Crop]).validate_python(yaml.safe_load(catalog)["crops"])


@cache
def _thresholds() -> dict[tuple[str, str, int], Threshold]:
    thresholds: dict[tuple[str, str, int], Threshold] = {}
    with (CONFIG_DIR / "kbw_thresholds.csv").open(encoding="utf-8", newline="") as table:
        for row in csv.DictReader(table):
            key = (row["crop_code"], row["soil_category"], int(row["period_idx"]))
            if key in thresholds:
                raise ValueError(f"Duplicate KBW threshold: {key}")
            value = row["threshold_mm"]
            # The annex retains x (no yield reduction) and - (crop not recommended).
            thresholds[key] = value if value in ("x", "-") else float(value)
    return thresholds


def threshold(crop: str, category: KbwSoilCategory, period_idx: int) -> Threshold:
    """Return the annex entry for a one-based monitoring period."""
    return _thresholds()[crop, category, period_idx]
