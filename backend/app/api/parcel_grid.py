"""Outlines in a WGS84 box for the map's boundary layer (frontend ParcelBoundaries), on fixed grids of cells.

Two layers, by zoom (frontend constants/map.ts):
  * obręby (zoom 15-16) from the PRG WFS - one coarse cell (0.04 x 0.06 deg) is ~1.6 s and ~100 outlines in a city
    (probe 2026-11-22, 4 x 4 km of Warsaw: 115 obręby, 344 KB GML in 1.6 s; the layer refuses application/json);
  * parcels (zoom >= 17) from the national EGiB WFS (same service as app/api/cadastral.py; probe 2026-11-22:
    ~1000 parcels / 0.8 MB / 4-6 s for one ~1 km city cell), with the EGiB GeoParquet export as the fallback.
Each cell is fetched once, simplified, rounded and cached on disk for a day. Features of neighbouring cells overlap;
the response dedupes them by id.
"""
from __future__ import annotations

import asyncio
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import timedelta

import numpy as np
import shapely
from shapely.errors import ShapelyError
from shapely.geometry import MultiPolygon, Polygon, box, mapping, shape

from app.api.cadastral import CRS_4326, PARCEL_LAYER, WFS_URL
from app.contracts.errors import UpstreamUnavailable
from app.core import cache, http
from app.geo import geometry
from app.geo.sources import source


@dataclass(frozen=True)
class Grid:
    name: str
    cell_lat: float
    cell_lon: float
    max_span_lat: float
    max_span_lon: float
    simplify_deg: float


# OUR CHOICE: ~1.1 x 1.0 km at lat 52; the frontend snaps its requests to the same grid (constants/map.ts).
PARCELS = Grid("parcels", 0.01, 0.015, 0.06, 0.09, 2.5e-6)          # ~0.25 m: invisible at zoom 19
# OUR CHOICE: ~4.4 x 4.1 km; obręby are 0.1-10 km², so one cell holds tens of them.
OBREBY = Grid("obreby", 0.04, 0.06, 0.16, 0.24, 1e-5)                # ~1 m: invisible at zoom 16
MAX_FEATURES = 6000
DECIMALS = 6
CACHE_VERSION = 2          # v2: parcel features carry area_ha
CACHE_SECONDS = timedelta(days=1).total_seconds()   # the EGiB export is refreshed daily
WFS_TIMEOUT_S = 25.0
WFS_PARALLEL = 4   # OUR CHOICE: polite to the public WFS; the frontend keeps at most 2 cells in flight per viewer

GML = "{http://www.opengis.net/gml/3.2}"
MS = "{http://mapserver.gis.umn.edu/mapserver}"

_wfs_slots = asyncio.Semaphore(WFS_PARALLEL)   # boundary cells only; parcel lookups (cadastral._fetch) never wait
_parquet_lock = asyncio.Lock()   # the parquet fallback streams row groups at full bandwidth: one at a time
_in_flight: dict[tuple[str, int, int], asyncio.Future] = {}

Cell = tuple[int, int]


class BboxTooLarge(ValueError):
    pass


def cells_for(min_lat: float, min_lon: float, max_lat: float, max_lon: float, grid: Grid = PARCELS) -> list[Cell]:
    if max_lat - min_lat > grid.max_span_lat + 1e-9 or max_lon - min_lon > grid.max_span_lon + 1e-9:
        raise BboxTooLarge(f"bbox too large for the {grid.name} boundary layer")
    i0, i1 = math.floor(min_lat / grid.cell_lat), math.ceil(max_lat / grid.cell_lat - 1e-9)
    j0, j1 = math.floor(min_lon / grid.cell_lon), math.ceil(max_lon / grid.cell_lon - 1e-9)
    return [(i, j) for i in range(i0, max(i1, i0 + 1)) for j in range(j0, max(j1, j0 + 1))]


def cell_box(cell: Cell, grid: Grid = PARCELS) -> tuple[float, float, float, float]:
    """(min_lat, min_lon, max_lat, max_lon)."""
    i, j = cell
    return (round(i * grid.cell_lat, 6), round(j * grid.cell_lon, 6),
            round((i + 1) * grid.cell_lat, 6), round((j + 1) * grid.cell_lon, 6))


def feature(fid: str, props: dict, geom_4326, simplify_deg: float = PARCELS.simplify_deg) -> dict | None:
    """Compact GeoJSON feature: simplified, coordinates rounded to DECIMALS."""
    try:
        if geom_4326.geom_type not in {"Polygon", "MultiPolygon"} or geom_4326.is_empty:
            return None
        g = shapely.simplify(geom_4326, simplify_deg, preserve_topology=True)
        g = shapely.transform(g, lambda c: np.round(c, DECIMALS))
        if g.is_empty:
            return None
    except (ShapelyError, ValueError, TypeError):
        return None
    return {"type": "Feature", "id": fid, "properties": {"id": fid, **props}, "geometry": mapping(g)}


def parcel_feature(pid: str, number: str, geom_4326, geom_2180) -> dict | None:
    """Parcel feature; area_ha from the unsimplified EPSG:2180 geometry, rounded like cadastral._parcel."""
    try:
        area_ha = round(float(geom_2180.area) / 10_000, 4)
    except (ShapelyError, ValueError, TypeError, AttributeError):
        return None
    return feature(pid, {"number": number, "area_ha": area_ha}, geom_4326)


# ---------------------------------------------------------------- parcels
async def _parcels_from_wfs(cell: Cell) -> list[dict]:
    min_lat, min_lon, max_lat, max_lon = cell_box(cell, PARCELS)
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
            g = shape(f["geometry"])
            item = parcel_feature(pid, props.get("NUMER_DZIALKI") or pid.rsplit(".", 1)[-1], g, geometry.to_2180(g))
        except (KeyError, TypeError, AttributeError, ValueError, ShapelyError):
            continue
        if item:
            out.append(item)
    return out


async def _parcels_from_parquet(cell: Cell) -> list[dict]:
    from shapely import wkb

    from app.geo import egib_parquet

    min_lat, min_lon, max_lat, max_lon = cell_box(cell, PARCELS)
    area = geometry.to_2180(box(min_lon, min_lat, max_lon, max_lat))
    async with _parquet_lock:
        rows = await egib_parquet.in_bbox(*area.bounds)
    out = []
    for pid, number, geom in rows:
        g = wkb.loads(geom)
        item = parcel_feature(pid, number, geometry.to_4326(g), g)
        if item:
            out.append(item)
    return out


async def _load_parcels(cell: Cell) -> list[dict]:
    try:
        return await _parcels_from_wfs(cell)
    except UpstreamUnavailable as wfs_exc:
        try:
            return await _parcels_from_parquet(cell)
        except UpstreamUnavailable as pq_exc:
            raise UpstreamUnavailable(f"{wfs_exc}; parquet fallback: {pq_exc}") from pq_exc


# ---------------------------------------------------------------- obręby
def _ring(pos_list: str) -> list[tuple[float, float]]:
    """gml:posList (EPSG:2180, northing easting - config prg_wfs.envelope_axis_order) -> [(easting, northing)]."""
    v = [float(t) for t in pos_list.split()]
    return [(v[k + 1], v[k]) for k in range(0, len(v) - 1, 2)]


def parse_obreby(gml: str) -> list[dict]:
    """Obręb features (EPSG:4326, simplified) from a PRG WFS GetFeature answer."""
    root = ET.fromstring(gml)
    if root.tag.endswith("ExceptionReport"):
        raise UpstreamUnavailable("prg_wfs: exception report")
    out = []
    for member in root.iter("{http://www.opengis.net/wfs/2.0}member"):
        code = member.findtext(f".//{MS}JPT_KOD_JE")
        name = member.findtext(f".//{MS}JPT_NAZWA_") or ""
        geom_el = member.find(f".//{MS}msGeometry")
        if not code or geom_el is None:
            continue
        polys = []
        for poly in geom_el.iter(f"{GML}Polygon"):
            ext = poly.find(f"{GML}exterior//{GML}posList")
            if ext is None or not ext.text:
                continue
            holes = [_ring(h.text) for h in poly.findall(f"{GML}interior//{GML}posList") if h.text]
            try:
                polys.append(Polygon(_ring(ext.text), holes))
            except (ShapelyError, ValueError):
                continue
        if not polys:
            continue
        g2180 = polys[0] if len(polys) == 1 else MultiPolygon(polys)
        item = feature(code.strip(), {"name": name.strip()}, geometry.to_4326(g2180), OBREBY.simplify_deg)
        if item:
            out.append(item)
    return out


async def _load_obreby(cell: Cell) -> list[dict]:
    cfg = source("prg_wfs")
    min_lat, min_lon, max_lat, max_lon = cell_box(cell, OBREBY)
    async with _wfs_slots:
        resp = await http.get(cfg["url"], timeout=WFS_TIMEOUT_S, retries=1, params={
            "SERVICE": "WFS", "REQUEST": "GetFeature", "VERSION": "2.0.0", "TYPENAMES": cfg["layers"]["obreby"],
            "BBOX": f"{min_lat},{min_lon},{max_lat},{max_lon},{CRS_4326}"})
    try:
        return await asyncio.to_thread(parse_obreby, resp.text)
    except ET.ParseError as exc:
        raise UpstreamUnavailable(f"prg_wfs: unparsable answer for cell {cell}: {exc!r}") from exc


# ---------------------------------------------------------------- cells
_LOADERS = {PARCELS.name: _load_parcels, OBREBY.name: _load_obreby}


async def _load(grid: Grid, cell: Cell) -> list[dict]:
    key = cache.make_key(f"an.{grid.name}_cells", v=CACHE_VERSION, cell=list(cell), lat=grid.cell_lat,
                         lon=grid.cell_lon)
    hit = cache.get(key)
    if isinstance(hit, list):
        return hit
    features = await _LOADERS[grid.name](cell)
    cache.set(key, features, expire_s=CACHE_SECONDS)
    return features


async def cell_features(cell: Cell, grid: Grid = PARCELS) -> list[dict]:
    """Features of one cell; concurrent requests for the same cell share one upstream fetch."""
    k = (grid.name, *cell)
    running = _in_flight.get(k)
    if running is None:
        running = asyncio.ensure_future(_load(grid, cell))
        _in_flight[k] = running
        running.add_done_callback(lambda _f: _in_flight.pop(k, None))
    return await asyncio.shield(running)


async def features_in_bbox(min_lat: float, min_lon: float, max_lat: float, max_lon: float,
                           grid: Grid = PARCELS) -> dict:
    """GeoJSON FeatureCollection (+ `truncated`) of the features in the grid cells covering the box."""
    cells = cells_for(min_lat, min_lon, max_lat, max_lon, grid)
    results = await asyncio.gather(*(cell_features(c, grid) for c in cells), return_exceptions=True)
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


async def parcels_in_bbox(min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> dict:
    return await features_in_bbox(min_lat, min_lon, max_lat, max_lon, PARCELS)


async def obreby_in_bbox(min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> dict:
    return await features_in_bbox(min_lat, min_lon, max_lat, max_lon, OBREBY)
