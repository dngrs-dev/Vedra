"""Parcel model. Frozen after T0."""
from __future__ import annotations

from pydantic import BaseModel


class Parcel(BaseModel):
    parcel_id: str  # full ULDK id, e.g. "141201_1.0001.6509"
    teryt: str
    voivodeship: str
    county: str
    commune: str
    region: str  # obreb (name or number)
    parcel_number: str
    area_ha: float
    geometry_wgs84: dict  # GeoJSON Polygon or MultiPolygon, EPSG:4326
    geometry_2180_wkt: str  # same geometry, EPSG:2180 (PUWG 1992)
    centroid_lat: float
    centroid_lon: float
