"""Part A - data & geo. Public entry point: RealGeoProvider.

Exported lazily: app.core.http imports app.geo.hosts, and an eager import of the provider here would make
that import pull in modules which themselves import app.core.http (circular import).
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any


def _use_wheel_data() -> None:
    """Point PROJ/GDAL at the data bundled with the installed rasterio wheel, before rasterio is imported.

    A system GDAL/PostGIS install can export PROJ_LIB / GDAL_DATA pointing at an older proj.db (dev machine
    2026-11-21: "proj.db ... DATABASE.LAYOUT.VERSION.MINOR = 2 whereas a number >= 6 is expected"); once
    PROJ_LIB is set, the rasterio wheel does not override it. Located with find_spec, without importing rasterio.
    """
    spec = importlib.util.find_spec("rasterio")
    if spec is None or not spec.origin:
        return
    base = Path(spec.origin).parent
    if (base / "proj_data").is_dir():
        os.environ["PROJ_DATA"] = os.environ["PROJ_LIB"] = str(base / "proj_data")
    if (base / "gdal_data").is_dir():
        os.environ["GDAL_DATA"] = str(base / "gdal_data")


_use_wheel_data()

if TYPE_CHECKING:
    from app.geo.provider import RealGeoProvider

__all__ = ["RealGeoProvider"]


def __getattr__(name: str) -> Any:
    if name == "RealGeoProvider":
        from app.geo.provider import RealGeoProvider

        return RealGeoProvider
    raise AttributeError(name)
