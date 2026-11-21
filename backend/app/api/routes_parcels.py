"""Parcel lookup endpoints using the configured geo provider."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import GeoDependency
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
