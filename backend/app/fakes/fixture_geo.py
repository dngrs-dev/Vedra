"""Offline access to date-specific snapshots recorded by Part A."""
from __future__ import annotations

from asyncio import to_thread
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ValidationError
from shapely.geometry import Point, shape

from app.contracts.errors import ParcelNotFound
from app.contracts.geo import GeoBundle, GeoRequest
from app.contracts.parcel import Parcel
from app.fakes.geo_helpers import (
    PARCEL_ID,
    bundle_with_missing_sources,
    parse_query,
    render_parcel_outline,
    validate_point,
)
from app.recommendations.texts_pl import GEO_FIXTURE_UNAVAILABLE

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "geo"


class _Snapshot(BaseModel):
    parcel: Parcel
    bundle: GeoBundle


def _read(path: Path) -> _Snapshot:
    return _Snapshot.model_validate_json(path.read_bytes())


def _fixture_name(parcel_id: str, analysis_date: date) -> str:
    # The filename and the slash replacement are defined in docs/CONTRACTS.md §4.
    return f"{parcel_id.replace('/', '-')}__{analysis_date.isoformat()}.json"


class FixtureGeoProvider:
    def __init__(self, directory: Path = FIXTURES_DIR):
        self.directory = directory

    def _parcels(self) -> list[Parcel]:
        parcels: dict[str, Parcel] = {}
        for path in sorted(self.directory.glob("*.json"), reverse=True):
            try:
                parcel = _read(path).parcel
            except (OSError, ValidationError):
                continue
            parcels.setdefault(parcel.parcel_id.casefold(), parcel)
        return list(parcels.values())

    async def find_parcels(self, query: str) -> list[Parcel]:
        parsed = parse_query(query)
        if isinstance(parsed, tuple):
            parcel = await self.parcel_at_point(*parsed)
            matches = [parcel] if parcel is not None else []
        else:
            parcels = await to_thread(self._parcels)
            if PARCEL_ID.fullmatch(parsed):
                matches = [parcel for parcel in parcels if parcel.parcel_id.casefold() == parsed.casefold()]
            else:
                region, number = parsed.rsplit(maxsplit=1)
                matches = [
                    parcel
                    for parcel in parcels
                    if parcel.region.casefold() == region.casefold()
                    and parcel.parcel_number.casefold() == number.casefold()
                ]
        if not matches:
            raise ParcelNotFound("No parcel matched the recorded snapshots")
        return matches

    async def parcel_at_point(self, lat: float, lon: float) -> Parcel | None:
        validate_point(lat, lon)
        point = Point(lon, lat)
        parcels = await to_thread(self._parcels)
        return next((parcel for parcel in parcels if shape(parcel.geometry_wgs84).covers(point)), None)

    async def collect(self, req: GeoRequest) -> GeoBundle:
        if not PARCEL_ID.fullmatch(req.parcel.parcel_id):
            return bundle_with_missing_sources(GEO_FIXTURE_UNAVAILABLE, error="Invalid parcel ID in fixture request")
        path = self.directory / _fixture_name(req.parcel.parcel_id, req.analysis_date)
        try:
            snapshot = await to_thread(_read, path)
        except (OSError, ValidationError) as exc:
            return bundle_with_missing_sources(
                GEO_FIXTURE_UNAVAILABLE, error=f"Fixture read failed: {type(exc).__name__}"
            )
        if snapshot.parcel.parcel_id != req.parcel.parcel_id:
            return bundle_with_missing_sources(
                GEO_FIXTURE_UNAVAILABLE, error="Fixture parcel ID does not match the request"
            )
        return snapshot.bundle

    async def render_static_map(self, parcel: Parcel, bundle: GeoBundle, width_px: int = 1200) -> bytes:
        # Default width follows GeoProvider.render_static_map in docs/CONTRACTS.md §5.6.
        return await to_thread(render_parcel_outline, parcel, width_px)
