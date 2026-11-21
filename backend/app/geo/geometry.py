"""CRS transforms and sampling helpers (private to Part A)."""
from __future__ import annotations

import math

from pyproj import Transformer
import shapely
from shapely import wkt
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry

from app.contracts.parcel import Parcel

_TO_2180 = Transformer.from_crs(4326, 2180, always_xy=True)
_TO_4326 = Transformer.from_crs(2180, 4326, always_xy=True)


def to_2180(geom: BaseGeometry) -> BaseGeometry:
    return shapely.transform(geom, _TO_2180.transform, interleaved=False)


def to_4326(geom: BaseGeometry) -> BaseGeometry:
    return shapely.transform(geom, _TO_4326.transform, interleaved=False)


def lonlat_to_2180(lon: float, lat: float) -> tuple[float, float]:
    return _TO_2180.transform(lon, lat)


def parse_ewkt(text: str) -> tuple[int | None, BaseGeometry]:
    """'SRID=2180;POLYGON((...))' -> (2180, geometry). Plain WKT -> (None, geometry)."""
    srid = None
    if text.upper().startswith("SRID="):
        head, text = text.split(";", 1)
        srid = int(head.split("=", 1)[1])
    return srid, wkt.loads(text)


def parcel_geom_2180(parcel: Parcel) -> BaseGeometry:
    return wkt.loads(parcel.geometry_2180_wkt)


def query_point(parcel: Parcel) -> tuple[float, float]:
    """(lat, lon) used for point services (SoilGrids). Centroid if inside the parcel, else a point
    guaranteed inside. Rounded to 5 decimals (~1 m) so cache keys and preprocessed files match."""
    g = parcel_geom_2180(parcel)
    p = g.centroid if g.contains(g.centroid) else g.representative_point()
    lon, lat = _TO_4326.transform(p.x, p.y)
    return round(lat, 5), round(lon, 5)


def sample_points(geom_2180: BaseGeometry, n: int) -> list[Point]:
    """Up to n points inside the polygon (EPSG:2180) on a regular grid over its bounding box.
    Always contains at least one point (representative_point) for non-empty geometries."""
    pts: list[Point] = []
    if geom_2180.is_empty:
        return pts
    minx, miny, maxx, maxy = geom_2180.bounds
    k = max(2, math.ceil(math.sqrt(n * 2)))  # denser grid than n, then keep the inside points
    for i in range(k):
        for j in range(k):
            p = Point(minx + (i + 0.5) * (maxx - minx) / k, miny + (j + 0.5) * (maxy - miny) / k)
            if geom_2180.contains(p):
                pts.append(p)
    if len(pts) > n:  # thin out evenly
        step = len(pts) / n
        pts = [pts[int(i * step)] for i in range(n)]
    if not pts:
        pts = [geom_2180.representative_point()]
    return pts
