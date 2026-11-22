"""Resolve parcels using local or live EGiB data before the legacy fallbacks."""
from __future__ import annotations

from asyncio import to_thread
from datetime import timedelta
from functools import lru_cache
import json
from pathlib import Path
import re

import numpy as np
from pyproj import Transformer
from pyproj.exceptions import ProjError
from shapely import transform
from shapely.errors import ShapelyError
from shapely.geometry import Point, mapping, shape
from shapely.geometry.base import BaseGeometry

from app.api import egib_snapshot
from app.config import CONFIG_DIR
from app.contracts.errors import UpstreamUnavailable
from app.contracts.geo import GeoBundle, GeoProvider, GeoRequest
from app.contracts.parcel import Parcel
from app.core import cache, http

# GUGiK WFS capabilities and GetFeature examples at the endpoint.
WFS_URL = "https://mapy.geoportal.gov.pl/wss/service/PZGIK/EGIB/WFS/UslugaZbiorcza"
CRS_4326 = "urn:ogc:def:crs:EPSG::4326"
PARCEL_LAYER = "ms:dzialki"
FES_NAMESPACE = "http://www.opengis.net/fes/2.0"
# CONTRACTS.md §1 budgets three seconds for a normal parcel lookup.
LOOKUP_TIMEOUT_S = 3.0
# The national EGiB export is refreshed daily (config/geo_sources.yaml: egib_parquet).
CACHE_SECONDS = timedelta(days=1).total_seconds()
CACHE_NAMESPACE = "an.cadastral_wfs"
# Query a non-zero envelope at GUGiK's six-decimal WGS84 precision, then test containment.
POINT_MARGIN = 0.000001
# Full identifier syntax from GUGiK ULDK docs and PART_A_DATA_GEO.md.
PARCEL_ID = re.compile(r"[0-9]{6}_[0-9]\.[0-9]{4}\.(?:AR_[0-9]+\.)?[0-9A-Z/]+", re.IGNORECASE)


@lru_cache(maxsize=1)
def _admin_names() -> tuple[dict[str, str], dict[str, str]]:
    data = json.loads((CONFIG_DIR / "cadastral_teryt.json").read_text(encoding="utf-8"))
    return data["voivodeships"], data["counties"]


def _project(geometry: BaseGeometry, transformer: Transformer) -> BaseGeometry:
    return transform(geometry, lambda coordinates: np.column_stack(transformer.transform(*coordinates.T)))


def _parcel(props: dict, geometry: BaseGeometry, projected: BaseGeometry | None = None) -> Parcel:
    parcel_id = props["ID_DZIALKI"].strip()
    if not PARCEL_ID.fullmatch(parcel_id):
        raise ValueError("Unexpected EGiB identifier")
    if geometry.geom_type not in {"Polygon", "MultiPolygon"} or geometry.is_empty or not geometry.is_valid:
        raise ValueError("Invalid cadastral geometry")
    lon_min, lat_min, lon_max, lat_max = geometry.bounds
    if not (-180 <= lon_min < lon_max <= 180 and -90 <= lat_min < lat_max <= 90):
        raise ValueError("EGiB geometry is outside WGS84 bounds")
    if projected is None:
        projected = _project(geometry, egib_snapshot.TO_PROJECTED)
    if projected.is_empty or not projected.is_valid or projected.area <= 0:
        raise ValueError("Invalid cadastral geometry in EPSG:2180")

    teryt, region, *_ = parcel_id.split(".")
    provinces, counties = _admin_names()
    center = geometry.centroid
    return Parcel(
        parcel_id=parcel_id,
        teryt=teryt,
        voivodeship=provinces.get(teryt[:2], ""),
        county=counties.get(teryt[:4], ""),
        commune=props.get("NAZWA_GMINY") or "",
        region=props.get("NAZWA_OBREBU") or region,
        parcel_number=props.get("NUMER_DZIALKI") or parcel_id.rsplit(".", 1)[-1],
        # SI conversion from square metres to hectares, using the same precision as ULDK.
        area_ha=round(projected.area / 10_000, 4),
        geometry_wgs84=mapping(geometry),
        geometry_2180_wkt=projected.wkt,
        centroid_lat=center.y,
        centroid_lon=center.x,
    )


def _from_snapshot(record: egib_snapshot.SnapshotParcel | None) -> Parcel | None:
    if record is None:
        return None
    try:
        geometry = _project(record.geometry, egib_snapshot.TO_WGS84)
        return _parcel({
            "ID_DZIALKI": record.parcel_id,
            "NAZWA_GMINY": record.commune,
            "NAZWA_OBREBU": record.region,
            "NUMER_DZIALKI": record.number,
        }, geometry, record.geometry)
    except (ValueError, ShapelyError, ProjError):
        return None


async def _fetch(params: dict[str, str]) -> list[Parcel]:
    try:
        response = await http.get(WFS_URL, timeout=LOOKUP_TIMEOUT_S, retries=0, params={
            "service": "WFS", "version": "2.0.0", "request": "GetFeature",
            "typenames": PARCEL_LAYER, "srsName": CRS_4326, "outputFormat": "application/json", **params,
        })
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
            return []
        features = payload["features"]
        if not isinstance(features, list):
            return []
    except (UpstreamUnavailable, ValueError, KeyError, TypeError):
        return []

    parcels = []
    for feature in features:
        try:
            parcels.append(_parcel(feature["properties"], shape(feature["geometry"])))
        except (KeyError, ValueError, TypeError, AttributeError, OSError, ShapelyError, ProjError):
            continue  # Ignore invalid individual records and leave unresolved lookups to the fallback.
    return parcels


def _id_key(parcel_id: str) -> str:
    return cache.make_key(CACHE_NAMESPACE, parcel_id=parcel_id.casefold())


def _remember(parcel: Parcel) -> Parcel:
    cache.set(_id_key(parcel.parcel_id), parcel, expire_s=CACHE_SECONDS)
    return parcel


class CadastralProvider:
    def __init__(self, fallback: GeoProvider, *, snapshot_path: Path | None = None) -> None:
        self._fallback = fallback
        self._snapshot_path = snapshot_path

    async def find_parcels(self, query: str) -> list[Parcel]:
        parcel_id = query.strip()
        if not PARCEL_ID.fullmatch(parcel_id):
            return await self._fallback.find_parcels(query)
        if self._snapshot_path is not None:
            parcel = _from_snapshot(await to_thread(egib_snapshot.by_id, self._snapshot_path, parcel_id))
            if parcel is not None:
                return [parcel]
        cached = cache.get(_id_key(parcel_id))
        if isinstance(cached, Parcel):
            return [cached]

        # OGC FES 2.0 filter. Only syntactically valid IDs reach this request.
        filter_xml = (
            f'<fes:Filter xmlns:fes="{FES_NAMESPACE}"><fes:PropertyIsEqualTo>'
            f"<fes:ValueReference>ID_DZIALKI</fes:ValueReference><fes:Literal>{parcel_id.upper()}</fes:Literal>"
            "</fes:PropertyIsEqualTo></fes:Filter>"
        )
        matches = await _fetch({"filter": filter_xml})
        for parcel in matches:
            if parcel.parcel_id.casefold() == parcel_id.casefold():
                return [_remember(parcel)]
        result = await self._fallback.find_parcels(parcel_id)
        for parcel in result:
            if parcel.parcel_id.casefold() == parcel_id.casefold():
                _remember(parcel)
        return result

    async def parcel_at_point(self, lat: float, lon: float) -> Parcel | None:
        if self._snapshot_path is not None:
            parcel = _from_snapshot(await to_thread(egib_snapshot.by_point, self._snapshot_path, lat, lon))
            if parcel is not None:
                return parcel
        point_key = cache.make_key(CACHE_NAMESPACE, lat=lat, lon=lon)
        saved_id = cache.get(point_key)
        if isinstance(saved_id, str):
            cached = cache.get(_id_key(saved_id))
            if isinstance(cached, Parcel):
                return cached

        point = Point(lon, lat)
        # WFS 2.0 requests EPSG:4326 BBOX in latitude/longitude order. GeoJSON responses use longitude/latitude.
        bbox = f"{lat - POINT_MARGIN},{lon - POINT_MARGIN},{lat + POINT_MARGIN},{lon + POINT_MARGIN},{CRS_4326}"
        matches = [parcel for parcel in await _fetch({"bbox": bbox}) if shape(parcel.geometry_wgs84).covers(point)]
        parcel = matches[0] if len(matches) == 1 else await self._fallback.parcel_at_point(lat, lon)
        if parcel is not None:
            _remember(parcel)
            cache.set(point_key, parcel.parcel_id, expire_s=CACHE_SECONDS)
        return parcel

    async def collect(self, req: GeoRequest) -> GeoBundle:
        return await self._fallback.collect(req)

    async def render_static_map(self, parcel: Parcel, bundle: GeoBundle, width_px: int = 1200) -> bytes:
        return await self._fallback.render_static_map(parcel, bundle, width_px=width_px)
