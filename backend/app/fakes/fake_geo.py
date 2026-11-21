"""An offline provider for explicitly synthetic demonstrations and tests."""
from __future__ import annotations

from asyncio import to_thread
from datetime import datetime, timezone
from struct import Struct

from pyproj import Transformer
from shapely.geometry import Polygon, box, mapping

from app.contracts.common import Provenance, SourceResult, SourceStatus
from app.contracts.errors import ParcelNotFound
from app.contracts.geo import GeoBundle, GeoRequest, HydroData, SoilInfo
from app.contracts.parcel import Parcel
from app.fakes.geo_helpers import (
    PARCEL_ID,
    bundle_with_missing_sources,
    parse_query,
    render_parcel_outline,
    validate_point,
)
from app.recommendations.texts_pl import FAKE_GEO_NOTE, FAKE_GEO_SOURCE, FAKE_SOURCE_LICENCE

# Sample ID from docs/CONTRACTS.md §5.5, used only as an offline fallback.
EXAMPLE_PARCEL_ID = "141201_1.0001.6509"
EXAMPLE_DISTRICT = EXAMPLE_PARCEL_ID.rsplit(".", maxsplit=1)[0]
# The EPSG:2180 definition gives the projection origin of 52° N, 19° E.
EXAMPLE_POINT = (52.0, 19.0)
# A synthetic one-hectare square has a 50 m half-side (one hectare is 10,000 m²).
HALF_SIDE_M = 50
SQUARE_METRES_PER_HECTARE = 10_000
# docs/CONTRACTS.md §3 specifies WGS84 GeoJSON; §5.5 also requires EPSG:2180 WKT.
TO_GRID = Transformer.from_crs("EPSG:4326", "EPSG:2180", always_xy=True)
TO_WGS84 = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True)
# Encode the clicked coordinates as two IEEE 754 binary64 values (Python struct's !dd format).
POINT_ENCODING = Struct("!dd")
POINT_PARCEL_PREFIX = f"{EXAMPLE_DISTRICT}.FAKE"


def _parcel(parcel_id: str, lat: float, lon: float, region: str = FAKE_GEO_SOURCE) -> Parcel:
    x, y = TO_GRID.transform(lon, lat)
    cell = box(x - HALF_SIDE_M, y - HALF_SIDE_M, x + HALF_SIDE_M, y + HALF_SIDE_M)
    longitudes, latitudes = TO_WGS84.transform(*cell.exterior.xy)
    return Parcel(
        parcel_id=parcel_id,
        teryt=parcel_id.split(".", maxsplit=1)[0],
        voivodeship=FAKE_GEO_SOURCE,
        county=FAKE_GEO_SOURCE,
        commune=FAKE_GEO_SOURCE,
        region=region,
        parcel_number=parcel_id.rsplit(".", maxsplit=1)[-1],
        area_ha=cell.area / SQUARE_METRES_PER_HECTARE,
        geometry_wgs84=mapping(Polygon(zip(longitudes, latitudes))),
        geometry_2180_wkt=cell.wkt,
        centroid_lat=lat,
        centroid_lon=lon,
    )


class FakeGeoProvider:
    async def find_parcels(self, query: str) -> list[Parcel]:
        parsed = parse_query(query)
        if isinstance(parsed, tuple):
            parcel = await self.parcel_at_point(*parsed)
            if parcel is None:
                raise ParcelNotFound("Point outside the fake provider's projection area")
            return [parcel]
        if PARCEL_ID.fullmatch(parsed):
            if parsed.startswith(POINT_PARCEL_PREFIX):
                encoded = parsed.removeprefix(POINT_PARCEL_PREFIX)
                try:
                    coordinates = bytes.fromhex(encoded)
                except ValueError:
                    coordinates = b""
                if len(coordinates) == POINT_ENCODING.size:
                    parcel = await self.parcel_at_point(*POINT_ENCODING.unpack(coordinates))
                    if parcel is not None:
                        return [parcel]
            return [_parcel(parsed, *EXAMPLE_POINT)]
        region, number = parsed.rsplit(maxsplit=1)
        return [_parcel(f"{EXAMPLE_DISTRICT}.{number}", *EXAMPLE_POINT, region=region)]

    async def parcel_at_point(self, lat: float, lon: float) -> Parcel | None:
        validate_point(lat, lon)
        # The test geometry uses EPSG:2180, whose Polish area of use excludes the poles.
        area = TO_GRID.area_of_use
        if not (area.south <= lat <= area.north and area.west <= lon <= area.east):
            return None
        encoded = POINT_ENCODING.pack(lat, lon).hex()
        return _parcel(f"{POINT_PARCEL_PREFIX}{encoded}", lat, lon)

    async def collect(self, req: GeoRequest) -> GeoBundle:
        provenance = Provenance(
            source_id="fake_geo",
            name=FAKE_GEO_SOURCE,
            # Repository URL from the origin remote, pointing to this synthetic data recipe.
            url="https://github.com/dngrs-dev/Vedra/blob/backend/backend/app/fakes/fake_geo.py",
            fetched_at=datetime.now(timezone.utc),
            live=False,
            licence=FAKE_SOURCE_LICENCE,
            attribution_pl=FAKE_GEO_NOTE,
        )
        return bundle_with_missing_sources(
            FAKE_GEO_NOTE,
            soil=SourceResult[SoilInfo](
                status=SourceStatus.PARTIAL,
                # Category I is a contract enum value used here as the synthetic test case.
                data=SoilInfo(kbw_category="I"),
                provenance=[provenance],
                notes_pl=[FAKE_GEO_NOTE],
            ),
            hydro=SourceResult[HydroData](
                status=SourceStatus.OK,
                data=HydroData(buffer_m=req.hydro_buffer_m),
                provenance=[provenance],
                notes_pl=[FAKE_GEO_NOTE],
            ),
        )

    async def render_static_map(self, parcel: Parcel, bundle: GeoBundle, width_px: int = 1200) -> bytes:
        # Default width follows GeoProvider.render_static_map in docs/CONTRACTS.md §5.6.
        return await to_thread(render_parcel_outline, parcel, width_px)
