"""Real GeoProvider. Signatures frozen at T0; Part A implements the bodies."""
from __future__ import annotations

from app.contracts.geo import GeoBundle, GeoRequest
from app.contracts.parcel import Parcel


class RealGeoProvider:
    async def find_parcels(self, query: str) -> list[Parcel]:
        raise NotImplementedError

    async def parcel_at_point(self, lat: float, lon: float) -> Parcel | None:
        raise NotImplementedError

    async def collect(self, req: GeoRequest) -> GeoBundle:
        raise NotImplementedError

    async def render_static_map(self, parcel: Parcel, bundle: GeoBundle, width_px: int = 1200) -> bytes:
        raise NotImplementedError
