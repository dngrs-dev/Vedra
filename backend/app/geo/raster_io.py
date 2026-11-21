"""GDAL environment and windowed COG reads over HTTPS (/vsicurl/), restricted to GEO_HOSTS.

GDAL reads do not go through app.core.http, so the host allowlist is enforced here (CONTRACTS.md 5.7).
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from urllib.parse import urlparse

import numpy as np


# PROJ/GDAL data directories are set in app/geo/__init__.py before rasterio is imported.

import rasterio  # noqa: E402
from rasterio.features import geometry_mask  # noqa: E402
from rasterio.warp import transform_geom  # noqa: E402
from rasterio.windows import Window, from_bounds  # noqa: E402

from app.core.http import HostNotAllowed  # noqa: E402
from app.geo.hosts import GEO_HOSTS  # noqa: E402

# GDAL options from PART_A_DATA_GEO.md (raster_io.gdal_env); VSI cache size is our choice (64 MB).
GDAL_OPTIONS = dict(
    GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
    CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.vrt",
    GDAL_HTTP_MULTIRANGE="YES",
    GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES",
    AWS_NO_SIGN_REQUEST="YES",
    VSI_CACHE="TRUE",
    VSI_CACHE_SIZE=str(64 * 1024 * 1024),
    # 60 s: one 1024x1024 deflate tile of a 10 m S2 band is ~1.4 MB; at ~140 KB/s per stream (dev machine,
    # 2026-11-21) a 20 s timeout truncated reads ("got 790006 bytes, expected 1424297").
    GDAL_HTTP_TIMEOUT="60",
    GDAL_HTTP_MAX_RETRY="2",
    GDAL_HTTP_RETRY_DELAY="0.5",
)


@contextmanager
def gdal_env():
    with rasterio.Env(**GDAL_OPTIONS):
        yield


def check_host(href: str) -> str:
    """Returns the GDAL path for an https href; raises HostNotAllowed if the host is not in GEO_HOSTS."""
    u = urlparse(href)
    if u.scheme != "https" or (u.hostname or "") not in GEO_HOSTS:
        raise HostNotAllowed(u.hostname or href)
    return "/vsicurl/" + href


@dataclass
class WindowRead:
    data: np.ndarray            # 2-D array of raw values (dtype of the file)
    inside: np.ndarray          # bool mask: pixel centre inside the geometry
    transform: rasterio.Affine
    crs: rasterio.crs.CRS
    nodata: float | None
    res: float


def read_window(href: str, geom: dict, geom_crs: str, out_res: float | None = None) -> WindowRead:
    """Reads band 1 of a COG over the bounding box of `geom` (GeoJSON-like dict in `geom_crs`).

    out_res: resample to this pixel size (dataset CRS units) - e.g. 20 m Sentinel-2 bands onto the 10 m grid
    (nearest neighbour). Call inside gdal_env() from a worker thread.
    """
    path = check_host(href)
    with rasterio.open(path) as ds:
        g = transform_geom(geom_crs, ds.crs, geom)
        xs = [c[0] for c in _coords(g)]
        ys = [c[1] for c in _coords(g)]
        res = out_res or ds.res[0]
        # snap the window to the target grid so 10 m and 20 m bands align
        left = np.floor(min(xs) / res) * res
        bottom = np.floor(min(ys) / res) * res
        right = np.ceil(max(xs) / res) * res
        top = np.ceil(max(ys) / res) * res
        width, height = max(int(round((right - left) / res)), 1), max(int(round((top - bottom) / res)), 1)
        win: Window = from_bounds(left, bottom, right, top, transform=ds.transform)
        data = ds.read(1, window=win, out_shape=(height, width), boundless=True, fill_value=ds.nodata or 0,
                       resampling=rasterio.enums.Resampling.nearest)
        transform = rasterio.transform.from_origin(left, top, res, res)
        inside = ~geometry_mask([g], out_shape=(height, width), transform=transform, all_touched=False)
        return WindowRead(data=data, inside=inside, transform=transform, crs=ds.crs, nodata=ds.nodata, res=res)


def _coords(g: dict):
    t = g["type"]
    if t == "Polygon":
        for ring in g["coordinates"]:
            yield from ring
    elif t == "MultiPolygon":
        for poly in g["coordinates"]:
            for ring in poly:
                yield from ring
    elif t == "Point":
        yield g["coordinates"]
    else:
        raise ValueError(f"unsupported geometry type {t}")
