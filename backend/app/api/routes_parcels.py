"""Parcel lookup endpoints using the configured geo provider."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.api import parcel_grid
from app.api.deps import GeoDependency
from app.config import settings
from app.contracts.errors import ParcelNotFound, UpstreamUnavailable
from app.contracts.parcel import Parcel
from app.recommendations import texts_pl as text

router = APIRouter(prefix="/api/parcels")
# WGS84 geographical coordinate bounds, RFC 7946 §§3.1.1, 5.2 and 5.3.
Latitude = Annotated[float, Query(ge=-90, le=90)]
Longitude = Annotated[float, Query(ge=-180, le=180)]


@router.get("/search", summary=text.PARCEL_SEARCH_SUMMARY)
async def search_parcels(q: Annotated[str, Query(min_length=1)], geo: GeoDependency) -> list[Parcel]:
    try:
        matches = await geo.find_parcels(q)
    except NotImplementedError as exc:
        raise UpstreamUnavailable("Geo provider is not ready") from exc
    if not matches:
        raise ParcelNotFound("Parcel search returned no matches")
    return matches


@router.get("/by-point", summary=text.PARCEL_POINT_SUMMARY)
async def parcel_at_point(lat: Latitude, lon: Longitude, geo: GeoDependency) -> Parcel:
    try:
        parcel = await geo.parcel_at_point(lat, lon)
    except NotImplementedError as exc:
        raise UpstreamUnavailable("Geo provider is not ready") from exc
    if parcel is None:
        raise ParcelNotFound("No parcel at the requested point")
    return parcel


_EMPTY = {"type": "FeatureCollection", "features": [], "truncated": False}


def _check_box(min_lat: float, min_lon: float, max_lat: float, max_lon: float, grid: parcel_grid.Grid) -> None:
    if min_lat >= max_lat or min_lon >= max_lon:
        raise HTTPException(status_code=422, detail="min_lat/min_lon must be below max_lat/max_lon")
    try:
        parcel_grid.cells_for(min_lat, min_lon, max_lat, max_lon, grid)
    except parcel_grid.BboxTooLarge as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/in-bbox", summary="Parcel outlines in a WGS84 box (map boundary layer, zoom >= 17)")
async def parcels_in_bbox(min_lat: Latitude, min_lon: Longitude, max_lat: Latitude, max_lon: Longitude) -> dict:
    """GeoJSON FeatureCollection of the parcels in the grid cells covering the box, plus `truncated`."""
    _check_box(min_lat, min_lon, max_lat, max_lon, parcel_grid.PARCELS)
    if settings.geo_provider != "real":   # fake / fixture runs stay offline: no boundary layer
        return _EMPTY
    return await parcel_grid.parcels_in_bbox(min_lat, min_lon, max_lat, max_lon)


@router.get("/obreby-in-bbox", summary="Obręb outlines in a WGS84 box (map boundary layer, zoom 15-16)")
async def obreby_in_bbox(min_lat: Latitude, min_lon: Longitude, max_lat: Latitude, max_lon: Longitude) -> dict:
    """GeoJSON FeatureCollection of the obręby (cadastral precincts) in the grid cells covering the box."""
    _check_box(min_lat, min_lon, max_lat, max_lon, parcel_grid.OBREBY)
    if settings.geo_provider != "real":
        return _EMPTY
    return await parcel_grid.obreby_in_bbox(min_lat, min_lon, max_lat, max_lon)
