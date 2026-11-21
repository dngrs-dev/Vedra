"""Water features around the parcel: BDOT10k water layers (GUGiK WMS), OSM Overpass as fallback.

Sources and method in config/geo_sources.yaml (`bdot10k_water`, `overpass`). The plan named MPHP first; MPHP
offers no vector access (HTTP 401) and BDOT10k contains the same watercourses plus drainage ditches, so BDOT10k
replaced it (CP3). BDOT10k vector endpoints are also closed, so features are derived from the rendered layers.
"""
from __future__ import annotations

import asyncio
import io
import math
import re
import time
from datetime import datetime, timezone

import numpy as np
from scipy import ndimage
from shapely.geometry import LineString, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from app.contracts.common import SourceResult, SourceStatus
from app.contracts.geo import HydroData, WaterFeature
from app.contracts.parcel import Parcel
from app.core import cache, http
from app.geo import geometry
from app.geo.sources import provenance, source

_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')
_NULLS = {"Null", ""}


# ---------------------------------------------------------------- BDOT10k (rendered layers)
def _grid(parcel_2180: BaseGeometry, buffer_m: int) -> tuple[tuple[float, float, float, float], int, int, float]:
    cfg = source("bdot10k_water")
    minx, miny, maxx, maxy = parcel_2180.buffer(buffer_m).bounds
    px = float(cfg["pixel_m"])
    px = max(px, (maxx - minx) / cfg["max_px"], (maxy - miny) / cfg["max_px"])
    w, h = max(int(np.ceil((maxx - minx) / px)), 1), max(int(np.ceil((maxy - miny) / px)), 1)
    return (minx, maxy - h * px, minx + w * px, maxy), w, h, px


async def _get_map(layer: str, bbox, w: int, h: int) -> np.ndarray:
    """Alpha mask (True = drawn) of one layer."""
    import matplotlib.image as mpimg

    cfg = source("bdot10k_water")
    minx, miny, maxx, maxy = bbox
    params = dict(SERVICE="WMS", VERSION=cfg["wms_version"], REQUEST="GetMap", LAYERS=layer, STYLES="",
                  CRS=cfg["crs"], BBOX=f"{miny},{minx},{maxy},{maxx}", WIDTH=str(w), HEIGHT=str(h),
                  FORMAT="image/png", TRANSPARENT="TRUE")
    key = cache.make_key("geo.bdot.map", **params)
    png = cache.get(key)
    if png is None:
        resp = await http.get(cfg["url"], params=params, timeout=15.0)
        if "image" not in (resp.headers.get("content-type") or ""):
            raise ValueError(f"bdot10k GetMap {layer}: {resp.text[:200]}")
        png = resp.content
        cache.set(key, png, expire_s=30 * 24 * 3600)  # BDOT10k updates are rare; monthly refresh is our choice
    img = mpimg.imread(io.BytesIO(png), format="png")
    if img.shape != (h, w, 4):
        raise ValueError(f"bdot10k GetMap {layer}: expected a transparent {w}x{h} map")
    return img[..., 3] > 0


async def _feature_info(layer: str, bbox, w: int, h: int, row: int, col: int) -> dict[str, str]:
    cfg = source("bdot10k_water")
    minx, miny, maxx, maxy = bbox
    params = dict(SERVICE="WMS", VERSION=cfg["wms_version"], REQUEST="GetFeatureInfo", LAYERS=layer,
                  QUERY_LAYERS=layer, STYLES="", CRS=cfg["crs"], BBOX=f"{miny},{minx},{maxy},{maxx}",
                  WIDTH=str(w), HEIGHT=str(h), I=str(col), J=str(row), INFO_FORMAT="text/xml")
    resp = await http.get(cfg["url"], params=params, timeout=10.0)
    text = resp.content.decode("utf-8", errors="replace")
    if "<FIELDS" not in text:
        return {}
    return {k: v for k, v in _ATTR_RE.findall(text.split("<FIELDS", 1)[1].split(">", 1)[0]) if v not in _NULLS}


def components(mask: np.ndarray, bbox, px: float) -> list[tuple[BaseGeometry, tuple[int, int]]]:
    """8-connected drawn regions -> (outline polygon in EPSG:2180, one pixel (row, col) inside it)."""
    from rasterio.features import shapes
    from rasterio.transform import from_origin

    labels, n = ndimage.label(mask, structure=np.ones((3, 3), int))
    transform = from_origin(bbox[0], bbox[3], px, px)
    out = []
    for k in range(1, n + 1):
        comp = labels == k
        polys = [shape(g) for g, v in shapes(comp.astype("uint8"), mask=comp, transform=transform) if v == 1]
        rows, cols = np.nonzero(comp)
        out.append((unary_union(polys), (int(rows[0]), int(cols[0]))))
    return out


def _nearest_pixel(comp_geom: BaseGeometry, parcel_2180: BaseGeometry, bbox, px: float) -> tuple[int, int]:
    from shapely.ops import nearest_points

    p = nearest_points(comp_geom, parcel_2180)[0]
    p = comp_geom.representative_point() if not comp_geom.buffer(px / 4).contains(p) else p
    col = int((p.x - bbox[0]) / px)
    row = int((bbox[3] - p.y) / px)
    return row, col


async def bdot10k_features(parcel: Parcel, buffer_m: int) -> tuple[list[WaterFeature], float]:
    cfg = source("bdot10k_water")
    g = geometry.parcel_geom_2180(parcel)
    zone = g.buffer(buffer_m)
    bbox, w, h, px = _grid(g, buffer_m)
    layers = list(cfg["layers"])
    masks = await asyncio.gather(*(_get_map(L, bbox, w, h) for L in layers))
    found: list[tuple[str, BaseGeometry, float]] = []
    # rasterio.features.shapes is GDAL: off the event loop (see app/geo/dem.py fetch_dem)
    comps = await asyncio.to_thread(lambda: [components(m, bbox, px) for m in masks])
    for layer, layer_comps in zip(layers, comps):
        for comp, _ in layer_comps:
            if comp.is_empty or not comp.intersects(zone):
                continue
            found.append((layer, comp, comp.distance(g)))
    found.sort(key=lambda t: t[2])
    # attributes (kind for WPow, x_kod, name) for the nearest features, capped
    targets = found[: int(cfg["max_feature_info"])]
    infos = await asyncio.gather(*(_feature_info(L, bbox, w, h, *_nearest_pixel(c, g, bbox, px))
                                   for L, c, _ in targets), return_exceptions=True)
    features = []
    for i, (layer, comp, dist) in enumerate(found):
        info = infos[i] if i < len(infos) and isinstance(infos[i], dict) else {}
        kind = cfg["layers"][layer]
        if kind == "by_rodzaj":
            kind = cfg["wpow_rodzaj_kind"].get(info.get("rodzaj", ""), "other")
        clipped = comp.intersection(zone).simplify(px, preserve_topology=True)
        features.append(WaterFeature(
            kind=kind, name=info.get(cfg["name_attribute"]),
            geometry=geometry.to_4326(clipped).__geo_interface__,
            distance_m=round(dist, 1) if dist > px else 0.0,
            touches_parcel=dist <= px,
            source_id="bdot10k",
        ))
    return features, px


# ---------------------------------------------------------------- OSM Overpass (fallback)
def _osm_kind(tags: dict) -> str:
    ww, nat = tags.get("waterway"), tags.get("natural")
    if ww in ("ditch", "drain"):
        return "ditch"
    if ww in ("stream", "river", "canal"):
        return ww
    if nat == "wetland":
        return "wetland"
    if nat == "water":
        return "pond" if tags.get("water") == "pond" else "lake" if tags.get("water") == "lake" else "other"
    return "other"


def osm_features_from_payload(payload: dict, parcel_2180: BaseGeometry, buffer_m: int) -> list[WaterFeature]:
    zone = parcel_2180.buffer(buffer_m)
    out = []
    for el in payload.get("elements", []):
        pts = [(p["lon"], p["lat"]) for p in el.get("geometry") or []]
        if len(pts) < 2:
            continue
        line = LineString(pts)
        geom4326 = Polygon(pts) if len(pts) >= 4 and pts[0] == pts[-1] and "natural" in el.get("tags", {}) else line
        g2180 = geometry.to_2180(geom4326)
        if not g2180.intersects(zone):
            continue
        dist = g2180.distance(parcel_2180)
        tags = el.get("tags", {})
        out.append(WaterFeature(kind=_osm_kind(tags), name=tags.get("name"),
                                geometry=geometry.to_4326(g2180.intersection(zone)).__geo_interface__,
                                distance_m=round(dist, 1), touches_parcel=dist == 0.0, source_id="osm"))
    return sorted(out, key=lambda f: f.distance_m)


async def osm_features(parcel: Parcel, buffer_m: int) -> list[WaterFeature]:
    cfg = source("overpass")
    g = geometry.parcel_geom_2180(parcel)
    lat, lon = parcel.centroid_lat, parcel.centroid_lon
    x, y = geometry.lonlat_to_2180(lon, lat)
    minx, miny, maxx, maxy = g.buffer(buffer_m).bounds
    # A radius derived from area misses the ends of long fields and separate parts of a multipolygon.
    radius = math.ceil(max(math.hypot(x - cx, y - cy) for cx in (minx, maxx) for cy in (miny, maxy)))
    ww = "|".join(cfg["tags"]["waterway"])
    nat = "|".join(cfg["tags"]["natural"])
    q = (f'[out:json][timeout:20];(way(around:{radius},{lat},{lon})[waterway~"^({ww})$"];'
         f'way(around:{radius},{lat},{lon})[natural~"^({nat})$"];);out geom;')
    last: Exception | None = None
    for url in [cfg["url"], *cfg.get("mirrors", [])]:
        try:
            resp = await http.get(url, params={"data": q}, timeout=20.0, retries=0)
            return osm_features_from_payload(resp.json(), g, buffer_m)
        except Exception as exc:  # noqa: BLE001 - try the next mirror
            last = exc
    raise last or RuntimeError("overpass: no endpoint")


# ---------------------------------------------------------------- assembly
def hydro_from_features(features: list[WaterFeature], parcel_2180: BaseGeometry, buffer_m: int,
                        ditch_crossings: int) -> HydroData:
    return HydroData(buffer_m=buffer_m, features=features,
                     nearest_water_m=min((f.distance_m for f in features), default=None),
                     ditches_crossing_boundary=ditch_crossings)


def count_ditch_crossings(features: list[WaterFeature], parcel_2180: BaseGeometry) -> int:
    boundary = parcel_2180.boundary
    n = 0
    for f in features:
        if f.kind == "ditch" and geometry.to_2180(shape(f.geometry)).buffer(0.5).intersects(boundary):
            n += 1
    return n


async def water_features(parcel: Parcel, buffer_m: int) -> SourceResult[HydroData]:
    t0 = time.monotonic()
    g = geometry.parcel_geom_2180(parcel)
    notes: list[str] = []
    try:
        # the derived features are cached like the BDOT10k maps they come from (30 days, our choice)
        key = cache.make_key("geo.bdot.features", parcel=parcel.geometry_2180_wkt, buffer=buffer_m)
        hit = cache.get(key)
        live = hit is None
        if live:
            feats, px = await bdot10k_features(parcel, buffer_m)
            hit = {"features": [f.model_dump(mode="json") for f in feats], "px": px,
                   "fetched_at": datetime.now(timezone.utc).isoformat()}
            cache.set(key, hit, expire_s=30 * 24 * 3600)
        feats = [WaterFeature.model_validate(f) for f in hit["features"]]
        px = hit["px"]
        prov = [provenance("bdot10k_water", source("bdot10k_water")["url"], live=live, fetched_at=datetime.fromisoformat(
            hit["fetched_at"]), resolution=f"1:10 000, odczyt co {px:g} m")]
        notes.append(f"Cieki, rowy i wody powierzchniowe odczytano z warstw BDOT10k (siatka {px:g} m); odległości "
                     "mogą być zaniżone o połowę szerokości symbolu na mapie.")
        status = SourceStatus.OK
        error = None
    except Exception as exc:  # noqa: BLE001 - fall back to OSM
        error = f"bdot10k: {type(exc).__name__}: {exc}"
        try:
            feats = await osm_features(parcel, buffer_m)
        except Exception as exc2:  # noqa: BLE001
            return SourceResult[HydroData](
                status=SourceStatus.MISSING, error=f"{error}; osm: {type(exc2).__name__}: {exc2}",
                notes_pl=["Dane o ciekach i rowach w otoczeniu działki są chwilowo niedostępne (BDOT10k, "
                          "OpenStreetMap); nie oznacza to braku wód w pobliżu."],
                elapsed_s=round(time.monotonic() - t0, 3))
        prov = [provenance("overpass", source("overpass")["url"])]
        notes.append("Dane o wodach pochodzą z OpenStreetMap (BDOT10k niedostępne); rowy melioracyjne mogą być "
                     "niekompletne.")
        status = SourceStatus.PARTIAL
    data = hydro_from_features(feats, g, buffer_m, count_ditch_crossings(feats, g))
    if not feats:
        notes.append(f"W promieniu {buffer_m} m od działki nie znaleziono cieków, rowów ani wód powierzchniowych.")
    return SourceResult[HydroData](status=status, data=data, provenance=prov, notes_pl=notes, error=error,
                                   elapsed_s=round(time.monotonic() - t0, 3))
