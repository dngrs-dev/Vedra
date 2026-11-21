"""Loads Part A configuration (config/geo_sources.yaml, config/soil_categories.yaml) and builds Provenance."""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.contracts.common import Provenance

BACKEND = Path(__file__).resolve().parents[2]
CONFIG_DIR = BACKEND / "config"
DATA_DIR = BACKEND / "data" / "a"


@lru_cache(maxsize=None)
def _load(name: str) -> dict[str, Any]:
    return yaml.safe_load((CONFIG_DIR / name).read_text(encoding="utf-8"))


def source(name: str) -> dict[str, Any]:
    """One entry of config/geo_sources.yaml."""
    return _load("geo_sources.yaml")[name]


def soil_categories() -> dict[str, Any]:
    return _load("soil_categories.yaml")


def provenance(name: str, url: str, *, live: bool = True, fetched_at: datetime | None = None,
               data_period: str | None = None, resolution: str | None = None) -> Provenance:
    entry = source(name)
    return Provenance(
        source_id=name,
        name=entry["name"],
        url=url,
        fetched_at=fetched_at or datetime.now(timezone.utc),
        live=live,
        data_period=data_period,
        resolution=resolution or entry.get("resolution"),
        # Licence text: provider licence if recorded, else what the service itself declares.
        licence=entry.get("licence") or entry.get("licence_declared") or "unknown (see docs/DATA_SOURCES.md)",
        attribution_pl=entry.get("attribution_pl"),
    )
