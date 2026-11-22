"""Look up parcels in a locally prepared GUGiK EGiB export."""
from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from pyproj import Transformer
from shapely import from_wkb
from shapely.errors import ShapelyError
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry

logger = logging.getLogger(__name__)

# The GUGiK EGiB GeoParquet export uses PUWG 1992 (see docs/DATA_SOURCES.md §2.2).
TO_PROJECTED = Transformer.from_crs(4326, 2180, always_xy=True)
TO_WGS84 = Transformer.from_crs(2180, 4326, always_xy=True)

SCHEMA = """
CREATE TABLE parcels (
    row_id INTEGER PRIMARY KEY,
    parcel_id TEXT NOT NULL COLLATE NOCASE,
    commune TEXT,
    region TEXT,
    number TEXT,
    geometry BLOB NOT NULL
);
CREATE VIRTUAL TABLE parcel_bounds USING rtree(row_id, min_x, max_x, min_y, max_y);
CREATE TABLE sources (file_name TEXT NOT NULL, parcels INTEGER NOT NULL);
"""


@dataclass(frozen=True, slots=True)
class SnapshotParcel:
    parcel_id: str
    commune: str | None
    region: str | None
    number: str | None
    geometry: BaseGeometry


def _read(path: Path, sql: str, params: tuple, point: Point | None = None) -> SnapshotParcel | None:
    # The importer atomically installs completed databases. Open the snapshot read-only.
    uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
    result = None
    try:
        with closing(sqlite3.connect(uri, uri=True)) as db:
            for parcel_id, commune, region, number, wkb in db.execute(sql, params):
                geometry = from_wkb(wkb, on_invalid="ignore")
                if geometry is None or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
                    continue
                if geometry.is_empty or not geometry.is_valid or (point is not None and not geometry.covers(point)):
                    continue
                if result is not None:
                    return None  # An ambiguous ID or point should be resolved by the live providers.
                result = SnapshotParcel(parcel_id, commune, region, number, geometry)
    except (OSError, sqlite3.Error, ShapelyError):
        logger.warning("Nie można odczytać lokalnej kopii EGiB.", exc_info=True)
        return None
    return result


def by_id(path: Path, parcel_id: str) -> SnapshotParcel | None:
    return _read(path, """
        SELECT DISTINCT parcel_id, commune, region, number, geometry
        FROM parcels WHERE parcel_id = ?
    """, (parcel_id,))


def by_point(path: Path, lat: float, lon: float) -> SnapshotParcel | None:
    x, y = TO_PROJECTED.transform(lon, lat)
    return _read(path, """
        SELECT DISTINCT p.parcel_id, p.commune, p.region, p.number, p.geometry
        FROM parcel_bounds AS b JOIN parcels AS p USING (row_id)
        WHERE b.min_x <= ? AND b.max_x >= ? AND b.min_y <= ? AND b.max_y >= ?
    """, (x, x, y, y), Point(x, y))
