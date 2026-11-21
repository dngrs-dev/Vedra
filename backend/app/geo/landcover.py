"""ESA WorldCover 2021 v200 class shares in the parcel and in a ring around it (config/geo_sources.yaml `worldcover`).

Class names are taken from the `legend` tag embedded in each COG ("10  Tree cover\\n20  Shrubland..."), so they
are exactly the WorldCover legend. shares_buffer = the ring parcel.buffer(buffer_m) minus the parcel (the parcel
itself is in shares_parcel). Shares are pixel counts; at 10 m (1/12000 deg) the change of pixel area over a
few km is far below 0.1 %, so no area weighting is applied.
"""
from __future__ import annotations

import asyncio
import math
import re
import time
from collections import Counter

import numpy as np
from shapely.geometry import mapping

from app.contracts.common import SourceResult, SourceStatus
from app.contracts.geo import LandCoverData
from app.contracts.parcel import Parcel
from app.core import cache
from app.geo import geometry
from app.geo.sources import provenance, source

DATASET = "ESA WorldCover 2021 v200"
_LEGEND_RE = re.compile(r"^\s*(\d+)\s+(.+?)\s*$", re.M)


def tiles_for(bounds_4326: tuple[float, float, float, float]) -> list[str]:
    """3x3 degree tiles named by their SW corner (e.g. N51E018) covering the bounds (Poland: N/E only)."""
    minx, miny, maxx, maxy = bounds_4326
    out = []
    for lat in range(3 * math.floor(miny / 3), 3 * math.floor(maxy / 3) + 1, 3):
        for lon in range(3 * math.floor(minx / 3), 3 * math.floor(maxx / 3) + 1, 3):
            out.append(f"N{lat:02d}E{lon:03d}")
    return out


def parse_legend(tag: str) -> dict[int, str]:
    return {int(code): name for code, name in _LEGEND_RE.findall(tag or "")}


def _counts(href: str, zone_2180: dict, parcel_2180: dict) -> tuple[Counter, Counter, dict[int, str]]:
    """Sync (thread): pixel counts per class in the parcel and in the ring, plus the tile's legend."""
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.warp import transform_geom

    from app.geo import raster_io

    with raster_io.gdal_env():
        wr = raster_io.read_window(href, zone_2180, "EPSG:2180")
        with rasterio.open(raster_io.check_host(href)) as ds:
            legend = parse_legend(ds.tags().get("legend", ""))
    in_parcel = ~geometry_mask([transform_geom("EPSG:2180", wr.crs, parcel_2180)], out_shape=wr.data.shape,
                               transform=wr.transform)
    valid = wr.data != (wr.nodata if wr.nodata is not None else 0)
    ring = wr.inside & ~in_parcel & valid
    par = in_parcel & valid
    return (Counter(dict(zip(*np.unique(wr.data[par], return_counts=True)))),
            Counter(dict(zip(*np.unique(wr.data[ring], return_counts=True)))), legend)


def _shares(counts: Counter, legend: dict[int, str]) -> dict[str, float]:
    total = sum(counts.values())
    if not total:
        return {}
    shares = {legend.get(int(k), f"klasa {int(k)}"): round(v / total, 4)
              for k, v in sorted(counts.items(), key=lambda kv: -kv[1])}
    return {k: v for k, v in shares.items() if v > 0}   # classes below 0.005 % would only add noise


async def landcover(parcel: Parcel, buffer_m: int) -> SourceResult[LandCoverData]:
    t0 = time.monotonic()
    g = geometry.parcel_geom_2180(parcel)
    zone = g.buffer(buffer_m)
    key = cache.make_key("geo.worldcover", parcel=parcel.geometry_2180_wkt, buffer=buffer_m)
    hit = cache.get(key)
    if hit is None:
        tpl = source("worldcover")["url_template"]
        tiles = tiles_for(geometry.to_4326(zone).bounds)
        results = await asyncio.gather(*(asyncio.to_thread(_counts, tpl.format(tile=t), mapping(zone), mapping(g))
                                         for t in tiles))
        par, ring, legend = Counter(), Counter(), {}
        for p, r, leg in results:
            par.update(p)
            ring.update(r)
            legend.update(leg)
        hit = {"parcel": _shares(par, legend), "ring": _shares(ring, legend), "tiles": tiles}
        cache.set(key, hit)  # the 2021 map is a fixed product
    data = LandCoverData(dataset=DATASET, buffer_m=buffer_m, shares_parcel=hit["parcel"], shares_buffer=hit["ring"])
    notes = []
    if not hit["parcel"]:
        notes.append("Mapa pokrycia terenu ESA WorldCover nie zawiera danych dla obszaru działki.")
    return SourceResult[LandCoverData](
        status=SourceStatus.OK if hit["parcel"] else SourceStatus.PARTIAL, data=data,
        provenance=[provenance("worldcover", source("worldcover")["url_template"].format(tile=",".join(hit["tiles"])),
                               data_period="2021", resolution="10 m")],
        notes_pl=notes, elapsed_s=round(time.monotonic() - t0, 3))
