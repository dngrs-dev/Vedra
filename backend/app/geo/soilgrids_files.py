"""SoilGrids 2.0 texture profile at a point, read pixel by pixel from the 250 m tiles on files.isric.org.

The REST API needs 26-163 s per point (config/geo_sources.yaml `soilgrids_rest`); single pixels of the GeoTIFF tiles
behind the VRTs are read in ~1-3 s for a full profile. data/a/soilgrids_tiles.json (scripts/a/build_soilgrids_tiles.py)
says which tile of each property holds a point (the tiling differs between properties); the pixel itself is located with the tile's own georeferencing.

Sync code: runs in worker threads only (GDAL must stay off the event loop, see app/geo/dem.py fetch_dem).
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from app.geo.sources import DATA_DIR, source

INDEX_FILE = DATA_DIR / "soilgrids_tiles.json"
PROPERTIES = ("sand", "silt", "clay", "soc", "bdod")   # texture, organic carbon, bulk density
VALUES = ("Q0.05", "Q0.5", "Q0.95")


@lru_cache(maxsize=1)
def _index() -> dict:
    return json.loads(INDEX_FILE.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _to_igh():
    from pyproj import Transformer

    return Transformer.from_crs("EPSG:4326", _index()["crs_wkt"], always_xy=True)


def tile_for(prop: str, x: float, y: float) -> str | None:
    """Tile path (below the layer folder) of `prop` whose footprint contains the projected point, or None."""
    idx = _index()
    res = float(idx["res_m"])
    for name, x0, y0, w, h in idx["tiles"][prop]:
        if x0 <= x < x0 + w * res and y0 - h * res < y <= y0:
            return name
    return None


def _read_pixel(url: str, x: float, y: float) -> int | None:
    import rasterio
    from rasterio.windows import Window

    from app.geo import raster_io

    extra = source("soilgrids_files")["gdal_extra"]
    with raster_io.gdal_env(), rasterio.Env(**extra), rasterio.open(raster_io.check_host(url)) as ds:
        row, col = ds.index(x, y)
        if not (0 <= row < ds.height and 0 <= col < ds.width):
            return None                       # edge tile cropped differently in this layer
        v = int(ds.read(1, window=Window(col, row, 1, 1))[0, 0])
        return None if ds.nodata is not None and v == ds.nodata else v


def profile_raw(lat: float, lon: float, depths: list[str], workers: int | None = None
                ) -> dict[str, dict[str, dict[str, int | None]]]:
    """{property: {depth: {value: raw integer or None}}} for the point. Raises if the point is outside the index
    (outside Poland) or if any read fails."""
    x, y = _to_igh().transform(lon, lat)
    tiles = {p: tile_for(p, x, y) for p in PROPERTIES}
    if any(t is None for t in tiles.values()):
        raise ValueError(f"soilgrids_files: point {lat},{lon} outside the tile index")
    base = source("soilgrids_files")["url"]
    jobs = [(p, d, v) for p in PROPERTIES for d in depths for v in VALUES]

    def one(job):
        p, d, v = job
        return job, _read_pixel(f"{base}{p}/{p}_{d}_{v}/{tiles[p]}.tif", x, y)

    out: dict[str, dict[str, dict[str, int | None]]] = {}
    workers = workers or int(source("soilgrids_files")["read_workers"])
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="soilgrids") as ex:
        for (p, d, v), val in ex.map(one, jobs):
            out.setdefault(p, {}).setdefault(d, {})[v] = val
    return out


def as_rest_payload(raw: dict[str, dict[str, dict[str, int | None]]]) -> dict:
    """Same shape as the REST /properties/query answer, so app.geo.soilgrids.parse_layers reads both."""
    d_factor = source("soilgrids_rest")["d_factor"]
    layers = []
    for prop, by_depth in raw.items():
        depths = []
        for d, vals in by_depth.items():
            top, bottom = (int(v) for v in d.removesuffix("cm").split("-"))
            depths.append({"label": d, "range": {"top_depth": top, "bottom_depth": bottom, "unit_depth": "cm"},
                           "values": dict(vals)})
        layers.append({"name": prop, "unit_measure": {"d_factor": d_factor[prop]}, "depths": depths})
    return {"properties": {"layers": layers}}
