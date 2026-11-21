"""Sentinel-2 L2A: STAC search on Earth Search and per-scene NDVI/NDMI statistics for a parcel interior.

Collections, asset keys, search parameters and the offset/duplicate behaviour are recorded in
config/geo_sources.yaml `earth_search` (spike + CP2 probe 2026-11-21).
"""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from functools import lru_cache
from datetime import date
from typing import Any

import numpy as np

from app.contracts.errors import UpstreamUnavailable
from app.contracts.geo import SceneStat
from app.core import cache, http
from app.geo.sources import BACKEND, source

BANDS = ("B04", "B08", "B8A", "B11", "SCL")
MAX_PAGES = 10  # safety cap on STAC pagination (10 x 100 items); our choice


def s2_params() -> dict[str, Any]:
    return source("sentinel2_processing")


@dataclass(frozen=True)
class BandInfo:
    href: str
    scale: float
    offset: float
    nodata: float | None


@dataclass(frozen=True)
class SceneRef:
    scene_id: str
    acquired: date
    sensing: str          # ISO datetime of the acquisition
    platform: str
    cloud_cover: float | None
    baseline: str | None
    collection: str
    bands: dict[str, BandInfo]


def band_info(asset: dict, collection: str) -> BandInfo:
    """Scale/offset/nodata from the item's raster:bands. For collections whose pixels are harmonized to the
    pre-PB-04.00 scale (sentinel-2-l2a) the declared offset is NOT applied - see geo_sources.yaml offset_note."""
    rb = (asset.get("raster:bands") or [{}])[0]
    offset = float(rb.get("offset", 0.0))
    if collection in source("earth_search")["harmonized_collections"]:
        offset = 0.0
    return BandInfo(href=asset["href"], scale=float(rb.get("scale", 1.0)), offset=offset, nodata=rb.get("nodata"))


def scene_from_item(item: dict, collection: str) -> SceneRef | None:
    keys = source("earth_search")["assets"]
    assets = item.get("assets", {})
    if any(keys[b] not in assets for b in BANDS):
        return None
    p = item["properties"]
    return SceneRef(
        scene_id=item["id"],
        acquired=date.fromisoformat(p["datetime"][:10]),
        sensing=p["datetime"],
        platform=p.get("platform", ""),
        cloud_cover=p.get("eo:cloud_cover"),
        baseline=p.get("s2:processing_baseline"),
        collection=collection,
        bands={b: band_info(assets[keys[b]], collection) for b in BANDS},
    )


def dedupe(scenes: list[SceneRef]) -> list[SceneRef]:
    """One scene per acquisition (platform + sensing minute); keeps the higher processing baseline / id."""
    best: dict[tuple[str, str], SceneRef] = {}
    for s in scenes:
        k = (s.platform, s.sensing[:16])
        cur = best.get(k)
        if cur is None or ((s.baseline or ""), s.scene_id) > ((cur.baseline or ""), cur.scene_id):
            best[k] = s
    return sorted(best.values(), key=lambda s: s.sensing, reverse=True)


async def _search(collection: str, bbox: tuple[float, float, float, float], start: date, end: date,
                  limit: int | None, by_cloud: bool) -> list[dict]:
    cfg = source("earth_search")
    params: dict[str, Any] = {
        "collections": collection,
        "bbox": ",".join(f"{v:.6f}" for v in bbox),
        "datetime": f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z",
        "limit": str(min(limit or 100, 100)),
        cfg["search"]["query_param"]: json.dumps({"eo:cloud_cover": {"lt": cfg["search"]["max_cloud_cover_pct"]}}),
    }
    if by_cloud:
        params[cfg["search"]["sortby_param"]] = "+properties.eo:cloud_cover"
    key = cache.make_key("geo.s2.search", **params)
    hit = cache.get(key)
    if hit is not None:
        return hit
    items: list[dict] = []
    url: str | None = cfg["url"] + "/search"
    query: dict | None = params
    for _ in range(MAX_PAGES):
        resp = await http.get(url, params=query, timeout=15.0)  # type: ignore[arg-type]
        page = resp.json()
        items.extend(page.get("features", []))
        if limit is not None and len(items) >= limit:
            items = items[:limit]
            break
        nxt = next((ln["href"] for ln in page.get("links", []) if ln.get("rel") == "next"), None)
        if not nxt:
            break
        url, query = nxt, None
    # The archive for past dates does not change; the newest days may still receive scenes.
    expire = None if (date.today() - end).days > 7 else 3600
    cache.set(key, items, expire_s=expire)
    return items


async def search_scenes(bbox_wgs84: tuple[float, float, float, float], start: date, end: date, *,
                        not_after: date, limit: int | None = None, by_cloud: bool = False) -> list[SceneRef]:
    """Scenes intersecting bbox in [start, end], never after `not_after` (the analysis date)."""
    end = min(end, not_after)
    if start > end:
        return []
    cols = source("earth_search")["collections"]
    last_exc: Exception | None = None
    for collection in (cols["primary"], cols["fallback"]):
        try:
            items = await _search(collection, bbox_wgs84, start, end, limit, by_cloud)
        except UpstreamUnavailable as exc:
            last_exc = exc
            continue
        scenes = [s for s in (scene_from_item(i, collection) for i in items) if s is not None]
        return dedupe([s for s in scenes if start <= s.acquired <= not_after])
    raise last_exc or UpstreamUnavailable("earth search: no collection answered")


# ---------------------------------------------------------------- per-scene statistics (sync, thread pool)
def reflectance(dn: np.ndarray, b: BandInfo) -> np.ndarray:
    return dn.astype("float64") * b.scale + b.offset


def stats_from_arrays(scene: SceneRef, red, nir, nir08, swir16, scl, inside) -> tuple[SceneStat | None, int]:
    """Pure function (unit-tested): masks, reflectance, NDVI/NDMI medians."""
    cfg = s2_params()
    n_inside = int(inside.sum())
    if n_inside == 0:
        return None, 0
    keep = np.isin(scl, cfg["scl_keep_classes"]) & inside
    for arr, b in ((red, scene.bands["B04"]), (nir, scene.bands["B08"]),
                   (nir08, scene.bands["B8A"]), (swir16, scene.bands["B11"])):
        if b.nodata is not None:
            keep &= arr != b.nodata
    r, n = reflectance(red, scene.bands["B04"]), reflectance(nir, scene.bands["B08"])
    n8, s16 = reflectance(nir08, scene.bands["B8A"]), reflectance(swir16, scene.bands["B11"])
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = (n - r) / (n + r)
        ndmi = (n8 - s16) / (n8 + s16)
    keep &= np.isfinite(ndvi) & np.isfinite(ndmi)
    valid = int(keep.sum())
    frac = valid / n_inside
    if frac < cfg["valid_fraction_min"]:
        return None, n_inside
    return SceneStat(scene_id=scene.scene_id, acquired=scene.acquired,
                     ndvi_median=round(float(np.median(ndvi[keep])), 4),
                     ndmi_median=round(float(np.median(ndmi[keep])), 4),
                     valid_pixels=valid, valid_fraction=round(frac, 4)), n_inside


def stats_key(scene_id: str, interior_2180: dict) -> str:
    """Key of one scene x parcel-interior result (preprocessed file and disk cache)."""
    geom = json.dumps(interior_2180, sort_keys=True)
    return f"{scene_id}|{hashlib.sha1(geom.encode()).hexdigest()[:16]}"


@lru_cache(maxsize=1)
def _preprocessed() -> dict[str, list]:
    path = BACKEND / s2_params()["preprocessed_stats_file"]
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


# Every result computed in this process (used by scripts/a/prefetch_s2.py to write the preprocessed file).
computed: dict[str, list] = {}
_computed_lock = threading.Lock()


def _decode(value: list) -> tuple[SceneStat | None, int]:
    stat, n = value
    return (SceneStat.model_validate(stat) if stat else None), int(n)


def scene_stats(scene: SceneRef, interior_2180: dict) -> tuple[SceneStat | None, int]:
    """Reads SCL first (skips the other bands when the parcel is mostly cloudy), then B04/B08/B8A/B11 on the
    10 m grid. Returns (stat or None, interior pixel count).
    Lookup order: preprocessed file (data/a) -> disk cache (geo.s2.scene, permanent) -> COG reads."""
    from app.geo import raster_io  # GDAL import only in worker paths

    skey = stats_key(scene.scene_id, interior_2180)
    pre = _preprocessed().get(skey)
    if pre is not None:
        return _decode(pre)
    ckey = cache.make_key("geo.s2.scene", key=skey)
    hit = cache.get(ckey)
    if hit is not None:
        with _computed_lock:
            computed[skey] = hit
        return _decode(hit)
    cfg = s2_params()
    res = cfg["grid_m"]
    with raster_io.gdal_env():
        scl = raster_io.read_window(scene.bands["SCL"].href, interior_2180, "EPSG:2180", out_res=res)
        inside = scl.inside
        n_inside = int(inside.sum())
        clear = np.isin(scl.data, cfg["scl_keep_classes"]) & inside
        if n_inside == 0 or clear.sum() / n_inside < cfg["valid_fraction_min"]:
            result: tuple[SceneStat | None, int] = (None, n_inside)
        else:
            arrs = {b: raster_io.read_window(scene.bands[b].href, interior_2180, "EPSG:2180", out_res=res).data
                    for b in ("B04", "B08", "B8A", "B11")}
            result = stats_from_arrays(scene, arrs["B04"], arrs["B08"], arrs["B8A"], arrs["B11"], scl.data, inside)
    value = [result[0].model_dump(mode="json") if result[0] else None, result[1]]
    cache.set(ckey, value)
    with _computed_lock:
        computed[skey] = value
    return result
