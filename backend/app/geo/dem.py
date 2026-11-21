"""DEM for the parcel + buffer on an EPSG:2180 grid (config/geo_sources.yaml `gugik_nmt_wcs`, `copernicus_dem`,
`terrain_processing`).

GUGiK NMT 1 m answers a WCS GetCoverage in ~52 s regardless of area (spike 2026-11-21), far over the 22 s budget,
so the order is:
  1. preprocessed NMT for the test parcels (data/a/nmt/, scripts/a/prefetch_nmt.py),
  2. disk cache of an earlier live NMT answer (geo.dem.nmt),
  3. live: NMT requested as a shared background task (keeps going after the deadline and fills the cache) and,
     in parallel, Copernicus DEM GLO-30; NMT is used if it arrives in time, otherwise Copernicus.
"""
from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from app.contracts.parcel import Parcel
from app.core import cache, http
from app.geo.aio import wait_shared
from app.geo import geometry
from app.geo.sources import DATA_DIR, source

NMT_DIR = DATA_DIR / "nmt"
_inflight: dict[str, asyncio.Task] = {}


@dataclass
class Dem:
    z: np.ndarray                 # float64, NaN = no data, row 0 = north
    origin: tuple[float, float]   # (x_left, y_top) EPSG:2180
    res: float                    # metres
    source: str                   # "gugik_nmt_1m" | "copernicus_dem_30m" (contract TerrainData.dem_source)
    url: str
    fetched_at: datetime
    live: bool

    def transform(self):
        from rasterio.transform import from_origin

        return from_origin(self.origin[0], self.origin[1], self.res, self.res)


def tp() -> dict:
    return source("terrain_processing")


def grid_for(parcel: Parcel) -> tuple[tuple[float, float, float, float], float]:
    """(bbox EPSG:2180 snapped to the grid, resolution): the finest of terrain_processing.nmt_resolutions_m that
    keeps the grid within max_cells."""
    cfg = tp()
    minx, miny, maxx, maxy = geometry.parcel_geom_2180(parcel).buffer(cfg["dem_buffer_m"]).bounds
    for res in cfg["nmt_resolutions_m"]:
        if math.ceil((maxx - minx) / res) * math.ceil((maxy - miny) / res) <= cfg["max_cells"]:
            break
    snap = lambda v, f: f(v / res) * res  # noqa: E731
    return (snap(minx, math.floor), snap(miny, math.floor), snap(maxx, math.ceil), snap(maxy, math.ceil)), float(res)


def _key(parcel: Parcel) -> str:
    bbox, res = grid_for(parcel)
    return cache.make_key("geo.dem.nmt", bbox=[round(v, 1) for v in bbox], res=res)


def _read_tiff(data: bytes, assume_2180: bool = True) -> tuple[np.ndarray, tuple[float, float], float]:
    from rasterio.io import MemoryFile

    with MemoryFile(data) as mf, mf.open() as ds:
        z = ds.read(1).astype("float64")
        if ds.nodata is not None:
            z[z == ds.nodata] = np.nan
        t = ds.transform
        # NMT WCS GeoTIFF carries LOCAL_CS "ETRS89 / Poland CS92" (spike) -> coordinates are EPSG:2180
        return z, (t.c, t.f), float(t.a)


def _write_tiff(z: np.ndarray, origin: tuple[float, float], res: float) -> bytes:
    from rasterio.io import MemoryFile
    from rasterio.transform import from_origin

    with MemoryFile() as mf:
        with mf.open(driver="GTiff", width=z.shape[1], height=z.shape[0], count=1, dtype="float32",
                     crs="EPSG:2180", transform=from_origin(origin[0], origin[1], res, res), nodata=np.nan,
                     compress="deflate", predictor=3) as ds:
            ds.write(z.astype("float32"), 1)
        return mf.read()


async def _fetch_nmt(parcel: Parcel, timeout_s: float | None = None) -> bytes:
    cfg = source("gugik_nmt_wcs")
    (minx, miny, maxx, maxy), res = grid_for(parcel)
    params = [("SERVICE", "WCS"), ("VERSION", cfg["wcs_version"]), ("REQUEST", "GetCoverage"),
              ("COVERAGEID", cfg["coverage_id"]), ("FORMAT", "image/tiff"),
              ("SUBSET", f"x({minx:.0f},{maxx:.0f})"), ("SUBSET", f"y({miny:.0f},{maxy:.0f})")]
    if res > 1:
        params.append(("SCALEFACTOR", f"{1 / res:g}"))
    resp = await http.get(cfg["url"], params=params, timeout=timeout_s or float(tp()["nmt_timeout_s"]),  # type: ignore[arg-type]
                          retries=0)
    if "tiff" not in (resp.headers.get("content-type") or ""):
        raise ValueError(f"nmt: {resp.text[:200]}")
    z, origin, got_res = _read_tiff(resp.content)
    blob = _write_tiff(z, origin, got_res)
    cache.set(_key(parcel), {"tiff": blob, "fetched_at": datetime.now(timezone.utc).isoformat()})
    return blob


def _start_nmt(parcel: Parcel) -> asyncio.Task:
    k = _key(parcel)
    task = _inflight.get(k)
    if task is None or task.done():
        task = asyncio.get_running_loop().create_task(_fetch_nmt(parcel))
        _inflight[k] = task
        task.add_done_callback(lambda t, kk=k: (_inflight.pop(kk, None), t.exception() if not t.cancelled() else None))
    return task


def _copernicus_sync(parcel: Parcel) -> dict:
    """Copernicus GLO-30 (EPSG:4326 COG tiles) -> EPSG:2180 grid of copernicus_res_m, bilinear.
    Only the window around the parcel is read (a full tile is 3600 x 3600 float32, ~52 MB)."""
    import rasterio
    from rasterio.transform import from_origin
    from rasterio.warp import Resampling, reproject
    from rasterio.windows import from_bounds

    from app.geo import raster_io

    cfg = tp()
    res = float(cfg["copernicus_res_m"])
    zone = geometry.parcel_geom_2180(parcel).buffer(cfg["dem_buffer_m"])
    minx, miny, maxx, maxy = zone.bounds
    minx, miny = math.floor(minx / res) * res, math.floor(miny / res) * res
    w, h = math.ceil((maxx - minx) / res), math.ceil((maxy - miny) / res)
    top = miny + h * res
    dst = np.full((h, w), np.nan)
    lo_lon, lo_lat, hi_lon, hi_lat = geometry.to_4326(zone).bounds
    pad = 2 * res / 111_000.0  # ~2 output cells of margin for bilinear resampling (1 deg lat ~ 111 km)
    tpl = source("copernicus_dem")["url_template"]
    with raster_io.gdal_env():
        for lat in range(math.floor(lo_lat), math.floor(hi_lat) + 1):
            for lon in range(math.floor(lo_lon), math.floor(hi_lon) + 1):
                with rasterio.open(raster_io.check_host(tpl.format(lat=lat, lon=lon))) as ds:
                    win = from_bounds(lo_lon - pad, lo_lat - pad, hi_lon + pad, hi_lat + pad, ds.transform)
                    win = win.round_offsets().round_lengths().intersection(
                        rasterio.windows.Window(0, 0, ds.width, ds.height))
                    src = ds.read(1, window=win).astype("float64")
                    part = np.full((h, w), np.nan)
                    reproject(src, part, src_transform=ds.window_transform(win), src_crs=ds.crs, src_nodata=ds.nodata,
                              dst_transform=from_origin(minx, top, res, res), dst_crs="EPSG:2180",
                              dst_nodata=np.nan, resampling=Resampling.bilinear)
                    dst = np.where(np.isnan(dst), part, dst)
    return {"tiff": _write_tiff(dst, (minx, top), res), "fetched_at": datetime.now(timezone.utc).isoformat(),
            "url": tpl.format(lat=math.floor(lo_lat), lon=math.floor(lo_lon))}


def _cop_key(parcel: Parcel) -> str:
    return cache.make_key("geo.dem.cop", wkt=parcel.geometry_2180_wkt, buffer=tp()["dem_buffer_m"])


async def _fetch_copernicus(parcel: Parcel) -> dict:
    rec = await asyncio.to_thread(_copernicus_sync, parcel)
    cache.set(_cop_key(parcel), rec)  # a fixed product
    return rec


def _start_copernicus(parcel: Parcel) -> asyncio.Task:
    k = _cop_key(parcel)
    task = _inflight.get(k)
    if task is None or task.done():
        task = asyncio.get_running_loop().create_task(_fetch_copernicus(parcel))
        _inflight[k] = task
        task.add_done_callback(lambda t, kk=k: (_inflight.pop(kk, None), t.exception() if not t.cancelled() else None))
    return task


def _cop_dem(rec: dict, live: bool) -> Dem:
    z, origin, res = _read_tiff(rec["tiff"])
    return Dem(z=z, origin=origin, res=res, source="copernicus_dem_30m", url=rec["url"],
               fetched_at=datetime.fromisoformat(rec["fetched_at"]), live=live)


class DemNotReady(Exception):
    """Neither DEM arrived within the budget; both requests continue in the background."""


def _from_blob(blob: bytes, fetched_at: datetime, live: bool) -> Dem:
    z, origin, res = _read_tiff(blob)
    return Dem(z=z, origin=origin, res=res, source="gugik_nmt_1m", url=source("gugik_nmt_wcs")["url"],
               fetched_at=fetched_at, live=live)


def preprocessed_path(parcel: Parcel):
    return NMT_DIR / f"{parcel.parcel_id.replace('/', '-')}.tif"


async def fetch_dem(parcel: Parcel, budget_s: float) -> tuple[Dem, list[str]]:
    """DEM + Polish notes. Raises if no DEM at all could be obtained."""
    notes: list[str] = []
    path = preprocessed_path(parcel)
    if path.exists():
        mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        return _from_blob(path.read_bytes(), mtime, live=False), notes
    hit = cache.get(_key(parcel))
    if hit is not None:
        return _from_blob(hit["tiff"], datetime.fromisoformat(hit["fetched_at"]), live=True), notes
    t0 = time.monotonic()
    nmt = _start_nmt(parcel)
    cop_hit = cache.get(_cop_key(parcel))
    cop = None if cop_hit is not None else _start_copernicus(parcel)
    try:
        blob = await wait_shared(nmt, timeout=max(budget_s - float(tp()["copernicus_reserve_s"]), 0.1))
        return _from_blob(blob, datetime.now(timezone.utc), live=True), notes
    except Exception:  # noqa: BLE001 - timeout or NMT error: use Copernicus
        pass
    try:
        rec = cop_hit or await wait_shared(cop, timeout=max(budget_s - (time.monotonic() - t0), 0.1))
    except asyncio.TimeoutError as exc:
        raise DemNotReady("no DEM within the budget") from exc
    notes.append("Ukształtowanie terenu oceniono na modelu Copernicus DEM (30 m), bo numeryczny model terenu GUGiK "
                 "(1 m) nie odpowiedział w wyznaczonym czasie; drobne zagłębienia i bruzdy nie są widoczne. "
                 "Copernicus DEM jest modelem powierzchni (uwzględnia drzewa i zabudowę), więc część wykrytych "
                 "zagłębień może wynikać z zadrzewień. Model GUGiK jest pobierany w tle i zostanie użyty przy "
                 "kolejnej analizie tej działki.")
    return _cop_dem(rec, live=cop_hit is None), notes


async def prefetch_nmt(parcel: Parcel, timeout_s: float = 400.0) -> bytes:
    """For scripts/a/prefetch_nmt.py: wait for the NMT answer. 400 s (our choice) - a 9 ha parcel + 200 m
    exceeded the 120 s runtime limit on the dev link (2026-11-21)."""
    return await _fetch_nmt(parcel, timeout_s)

