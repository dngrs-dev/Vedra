"""Parcel outlines in a WGS84 box for the map's boundary layer (frontend ParcelBoundaries).

The box is split into fixed grid cells (CELL_LAT x CELL_LON, ~1.1 km). Each cell is fetched once from the national
EGiB WFS (same service as app/api/cadastral.py; probe 2026-11-22: ~1000 parcels / 0.8 MB / 4-6 s for one city cell),
with the EGiB GeoParquet export as the fallback (app/geo/egib_parquet.in_bbox), then simplified, rounded and cached
on disk for a day. Features of neighbouring cells overlap; the response dedupes them by parcel id.
"""
from __future__ import annotations

import asyncio
import math
from datetime import timedelta

import numpy as np
import shapely
from shapely.errors import ShapelyError
from shapely.geometry import box, mapping, shape

from app.api.cadastral import CRS_4326, PARCEL_LAYER, WFS_URL
from app.contracts.errors import UpstreamUnavailable
from app.core import cache, http

# OUR CHOICE: ~1.1 km x 1.0 km at lat 52; the frontend snaps its requests to the same grid (constants/map.ts).
CELL_LAT = 0.01
CELL_LON = 0.015
# OUR CHOICE: a zoom-15 viewport on a large screen is ~0.03 x 0.06 deg; anything much bigger is refused.
MAX_SPAN_LAT = 0.06
MAX_SPAN_LON = 0.09
MAX_FEATURES = 4000
# ~0.25 m: invisible at zoom 19 (0.2 m/px), cuts the vertex count of digitised arcs.
SIMPLIFY_DEG = 2.5e-6
DECIMALS = 6
CACHE_NAMESPACE = "an.parcel_cells"
CACHE_SECONDS = timedelta(days=1).total_seconds()   # the EGiB export is refreshed daily
WFS_TIMEOUT_S = 25.0
WFS_PARALLEL = 4   # OUR CHOICE: polite to the public WFS; one viewport is ~6-12 cells

_wfs_slots = asyncio.Semaphore(WFS_PARALLEL)
_parquet_lock = asyncio.Lock()   # the parquet fallback streams row groups at full bandwidth: one at a time
_in_flight: dict[tuple[int, int], asyncio.Future] = {}

Cell = tuple[int, int]


class BboxTooLarge(ValueError):
    pass


def cells_for(min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> list[Cell]:
    if max_lat - min_lat > MAX_SPAN_LAT + 1e-9 or max_lon - min_lon > MAX_SPAN_LON + 1e-9:
        raise BboxTooLarge("bbox too large for the parcel boundary layer")
    i0, i1 = math.floor(min_lat / CELL_LAT), math.ceil(max_lat / CELL_LAT - 1e-9)
    j0, j1 = math.floor(min_lon / CELL_LON), math.ceil(max_lon / CELL_LON - 1e-9)
    return [(i, j) for i in range(i0, max(i1, i0 + 1)) for j in range(j0, max(j1, j0 + 1))]


def cell_box(cell: Cell) -> tuple[float, float, float, float]:
    """(min_lat, min_lon, max_lat, max_lon)."""
    i, j = cell
    return (round(i * CELL_LAT, 6), round(j * CELL_LON, 6), round((i + 1) * CELL_LAT, 6), round((j + 1) * CELL_LON, 6))


def feature(pid: str, number: str, geom_4326) -> dict | None:
    """Compact GeoJSON feature: simplified, coordinates rounded to DECIMALS."""
    try:
        if geom_4326.geom_type not in {"Polygon", "MultiPolygon"} or geom_4326.is_empty:
            return None
        g = shapely.simplify(geom_4326, SIMPLIFY_DEG, preserve_topology=True)
        g = shapely.transform(g, lambda c: np.round(c, DECIMALS))
        if g.is_empty:
            return None
    except (ShapelyError, ValueError, TypeError):
        return None
    return {"type": "Feature", "id": pid, "properties": {"id": pid, "number": number}, "geometry": mapping(g)}


async def _from_wfs(cell: Cell) -> list[dict]:
    min_lat, min_lon, max_lat, max_lon = cell_box(cell)
    async with _wfs_slots:
        # WFS 2.0 EPSG:4326 BBOX is latitude/longitude order; GeoJSON coordinates are longitude/latitude.
        resp = await http.get(WFS_URL, timeout=WFS_TIMEOUT_S, retries=1, params={
            "service": "WFS", "version": "2.0.0", "request": "GetFeature", "typenames": PARCEL_LAYER,
            "srsName": CRS_4326, "outputFormat": "application/json",
            "bbox": f"{min_lat},{min_lon},{max_lat},{max_lon},{CRS_4326}"})
    try:
        payload = resp.json()
        raw = payload["features"]
        if payload.get("type") != "FeatureCollection" or not isinstance(raw, list):
            raise ValueError("not a FeatureCollection")
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise UpstreamUnavailable(f"egib_wfs: unexpected answer for cell {cell}: {exc!r}") from exc
    out = []
    for f in raw:
        try:
            props = f["properties"]
            pid = props["ID_DZIALKI"].strip()
            item = feature(pid, props.get("NUMER_DZIALKI") or pid.rsplit(".", 1)[-1], shape(f["geometry"]))
        except (KeyError, TypeError, AttributeError, ValueError, ShapelyError):
            continue
        if item:
            out.append(item)
    return out


async def _from_parquet(cell: Cell) -> list[dict]:
    from shapely import wkb

    from app.geo import egib_parquet, geometry

    min_lat, min_lon, max_lat, max_lon = cell_box(cell)
    area = geometry.to_2180(box(min_lon, min_lat, max_lon, max_lat))
    async with _parquet_lock:
        rows = await egib_parquet.in_bbox(*area.bounds)
    out = []
    for pid, number, geom in rows:
        item = feature(pid, number, geometry.to_4326(wkb.loads(geom)))
        if item:
            out.append(item)
    return out


async def _load(cell: Cell) -> list[dict]:
    key = cache.make_key(CACHE_NAMESPACE, cell=list(cell), lat=CELL_LAT, lon=CELL_LON)
    hit = cache.get(key)
    if isinstance(hit, list):
        return hit
    try:
        features = await _from_wfs(cell)
    except UpstreamUnavailable as wfs_exc:
        try:
            features = await _from_parquet(cell)
        except UpstreamUnavailable as pq_exc:
            raise UpstreamUnavailable(f"{wfs_exc}; parquet fallback: {pq_exc}") from pq_exc
    cache.set(key, features, expire_s=CACHE_SECONDS)
    return features


async def cell_features(cell: Cell) -> list[dict]:
    """Features of one cell; concurrent requests for the same cell share one upstream fetch."""
    running = _in_flight.get(cell)
    if running is None:
        running = asyncio.ensure_future(_load(cell))
        _in_flight[cell] = running
        running.add_done_callback(lambda _f: _in_flight.pop(cell, None))
    return await asyncio.shield(running)


async def parcels_in_bbox(min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> dict:
    """GeoJSON FeatureCollection (+ `truncated`) of the parcels in the grid cells covering the box."""
    cells = cells_for(min_lat, min_lon, max_lat, max_lon)
    results = await asyncio.gather(*(cell_features(c) for c in cells), return_exceptions=True)
    if all(isinstance(r, BaseException) for r in results):
        first = results[0]
        raise first if isinstance(first, UpstreamUnavailable) else UpstreamUnavailable(repr(first))
    seen: dict[str, dict] = {}
    for r in results:
        if isinstance(r, BaseException):
            continue
        for f in r:
            seen.setdefault(f["id"], f)
    features = list(seen.values())
    truncated = len(features) > MAX_FEATURES or any(isinstance(r, BaseException) for r in results)
    return {"type": "FeatureCollection", "features": features[:MAX_FEATURES], "truncated": truncated}
