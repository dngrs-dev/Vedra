"""Terrain analysis on a DEM grid - pure numpy / heapq, no GPL code (pysheds and richdem are GPL-3.0).

Methods (cited):
- Depression filling: Priority-Flood, Barnes R., Lehman C., Mulla D. (2014) "Priority-flood: An optimal
  depression-filling and watershed-labeling algorithm for digital elevation models", Computers & Geosciences 62,
  117-127. The "+epsilon" variant from the same paper is used only for flow routing (no flats).
- Flow directions: D8, O'Callaghan J.F., Mark D.M. (1984) "The extraction of drainage networks from digital
  elevation data", Computer Vision, Graphics, and Image Processing 28, 323-344.
- Topographic wetness index: TWI = ln(a / tan beta), Beven K.J., Kirkby M.J. (1979) Hydrological Sciences Bulletin
  24(1), 43-69; a = specific catchment area (upslope area per unit contour width = area / cell size).
Grids are row-major, row 0 = north, square cells of `res` metres. NaN = no data.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass

import numpy as np
from scipy import ndimage

# D8 neighbour offsets (drow, dcol) and their distance factors
_OFFS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
_DIST = np.array([np.sqrt(2), 1, np.sqrt(2), 1, 1, np.sqrt(2), 1, np.sqrt(2)])


def slope_pct(z: np.ndarray, res: float) -> np.ndarray:
    """Slope in percent (rise/run * 100) from central differences (numpy.gradient)."""
    gy, gx = np.gradient(z, res)
    return np.hypot(gx, gy) * 100.0


def priority_flood(z: np.ndarray, epsilon: float = 0.0) -> np.ndarray:
    """Filled DEM (Barnes et al. 2014). epsilon > 0 gives the +epsilon variant (strictly draining surface).
    Edge cells and cells next to NaN are seeds (water leaves the grid there)."""
    rows, cols = z.shape
    filled = z.astype("float64").copy()
    nodata = np.isnan(filled)
    closed = nodata.copy()
    heap: list[tuple[float, int, int]] = []
    edge = np.zeros_like(closed)
    edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
    edge |= ndimage.binary_dilation(nodata, structure=np.ones((3, 3))) & ~nodata
    for r, c in zip(*np.nonzero(edge & ~nodata)):
        heapq.heappush(heap, (filled[r, c], int(r), int(c)))
        closed[r, c] = True
    while heap:
        h, r, c = heapq.heappop(heap)
        for dr, dc in _OFFS:
            rr, cc = r + dr, c + dc
            if 0 <= rr < rows and 0 <= cc < cols and not closed[rr, cc]:
                closed[rr, cc] = True
                floor = h + epsilon
                if filled[rr, cc] < floor:
                    filled[rr, cc] = floor
                heapq.heappush(heap, (filled[rr, cc], rr, cc))
    return filled


@dataclass
class Depression:
    cells: np.ndarray        # bool mask
    area_m2: float
    volume_m3: float
    max_depth_m: float
    deepest: tuple[int, int]


def depressions(z: np.ndarray, filled: np.ndarray, res: float, min_area_m2: float,
                min_depth_m: float = 0.0) -> list[Depression]:
    """Connected regions of filled - z > min_depth_m with area >= min_area_m2; volume = sum(depth) * cell area."""
    depth = np.nan_to_num(filled - z, nan=0.0)
    wet = depth > min_depth_m
    labels, n = ndimage.label(wet, structure=np.ones((3, 3), int))
    cell = res * res
    out = []
    for k in range(1, n + 1):
        m = labels == k
        area = float(m.sum()) * cell
        if area < min_area_m2:
            continue
        d = np.where(m, depth, 0.0)
        idx = np.unravel_index(int(np.argmax(d)), d.shape)
        out.append(Depression(cells=m, area_m2=area, volume_m3=float(d.sum()) * cell, max_depth_m=float(d.max()),
                              deepest=(int(idx[0]), int(idx[1]))))
    return sorted(out, key=lambda x: -x.volume_m3)


def d8(filled_eps: np.ndarray) -> np.ndarray:
    """Index 0..7 of the steepest downslope neighbour (into _OFFS), -1 where none (outlet / no data)."""
    rows, cols = filled_eps.shape
    pad = np.pad(filled_eps, 1, constant_values=np.nan)
    best = np.full((rows, cols), -1, int)
    best_drop = np.zeros((rows, cols))
    for k, (dr, dc) in enumerate(_OFFS):
        nb = pad[1 + dr:1 + dr + rows, 1 + dc:1 + dc + cols]
        drop = (filled_eps - nb) / _DIST[k]
        better = np.nan_to_num(drop, nan=-np.inf) > best_drop
        best[better] = k
        best_drop[better] = drop[better]
    best[np.isnan(filled_eps)] = -1
    return best


def flow_accumulation(dirs: np.ndarray, filled_eps: np.ndarray) -> np.ndarray:
    """Number of cells draining through each cell (itself included), processing cells from high to low."""
    rows, cols = dirs.shape
    acc = np.where(np.isnan(filled_eps), 0.0, 1.0)
    order = np.argsort(np.nan_to_num(filled_eps, nan=-np.inf), axis=None)[::-1]
    dr = np.array([o[0] for o in _OFFS])
    dc = np.array([o[1] for o in _OFFS])
    flat_dirs = dirs.ravel()
    for idx in order:
        k = flat_dirs[idx]
        if k < 0:
            continue
        r, c = divmod(int(idx), cols)
        rr, cc = r + dr[k], c + dc[k]
        if 0 <= rr < rows and 0 <= cc < cols:
            acc[rr, cc] += acc[r, c]
    return acc


def twi(acc: np.ndarray, slope_percent: np.ndarray, res: float) -> np.ndarray:
    """ln(a / tan beta), a = acc * res^2 / res (specific catchment area); tan beta = slope_pct / 100.
    Cells with zero slope are NaN (index undefined)."""
    tan_b = slope_percent / 100.0
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.log((acc * res) / tan_b)
    out[~np.isfinite(out)] = np.nan
    return out


def trace_lines(acc: np.ndarray, dirs: np.ndarray, res: float, min_upstream_ha: float) -> list[list[tuple[int, int]]]:
    """Channel cells = acc * cell area >= min_upstream_ha. Each line starts at a channel head (no channel cell
    flows into it) and follows D8 until it leaves the grid, reaches an outlet, or joins an already traced line."""
    rows, cols = acc.shape
    channel = acc * res * res / 10_000.0 >= min_upstream_ha
    inflow = np.zeros_like(channel)
    for r, c in zip(*np.nonzero(channel)):
        k = dirs[r, c]
        if k >= 0:
            rr, cc = r + _OFFS[k][0], c + _OFFS[k][1]
            if 0 <= rr < rows and 0 <= cc < cols:
                inflow[rr, cc] = True
    heads = channel & ~inflow
    visited = np.zeros_like(channel)
    lines = []
    for r, c in sorted(zip(*np.nonzero(heads)), key=lambda rc: acc[rc]):
        line = [(int(r), int(c))]
        visited[r, c] = True
        while True:
            k = dirs[r, c]
            if k < 0:
                break
            r, c = r + _OFFS[k][0], c + _OFFS[k][1]
            if not (0 <= r < rows and 0 <= c < cols):
                break
            line.append((int(r), int(c)))
            if visited[r, c]:
                break
            visited[r, c] = True
        if len(line) >= 2:
            lines.append(line)
    return lines


# ---------------------------------------------------------------- assembly into the contract (TerrainData)
def _cell_xy(dem, r: int, c: int) -> tuple[float, float]:
    return dem.origin[0] + (c + 0.5) * dem.res, dem.origin[1] - (r + 0.5) * dem.res


def analyse(dem, parcel_2180, ditch_geoms_2180: list) -> "TerrainData":  # noqa: F821 - contract type below
    """Sync (run in a thread). All thresholds from config/geo_sources.yaml terrain_processing."""
    from rasterio.features import geometry_mask, shapes
    from shapely.geometry import LineString, Point, mapping, shape
    from shapely.ops import unary_union

    from app.contracts.common import Range
    from app.contracts.geo import FlowLine, RetentionSpot, TerrainData
    from app.geo import geometry
    from app.geo.dem import tp

    cfg = tp()
    z, res = dem.z, dem.res
    tr = dem.transform()
    in_parcel = ~geometry_mask([mapping(parcel_2180)], out_shape=z.shape, transform=tr) & ~np.isnan(z)
    if not in_parcel.any():
        raise ValueError("terrain: parcel does not overlap the DEM")
    slope = slope_pct(z, res)
    filled = priority_flood(z)
    fe = priority_flood(z, epsilon=1e-4)   # +epsilon variant only for routing (Barnes et al. 2014)
    dirs = d8(fe)
    acc = flow_accumulation(dirs, fe)
    tw = twi(acc, slope, res)

    def ha(a_cells: float) -> float:
        return round(float(a_cells) * res * res / 10_000.0, 3)

    def to_geo(g):
        return geometry.to_4326(g).__geo_interface__

    spots: list = []
    # depressions
    deps = depressions(z, filled, res, cfg["depression_min_area_m2"], cfg["depression_min_depth_m"])
    for k, d in enumerate(deps[: cfg["max_retention_spots"]], 1):
        poly = unary_union([shape(g) for g, v in shapes(d.cells.astype("uint8"), mask=d.cells, transform=tr) if v == 1])
        spots.append(RetentionSpot(
            id=f"Z{k}", kind="depression", geometry=to_geo(poly.simplify(res / 2)),
            inside_parcel=bool(poly.intersects(parcel_2180)), volume_m3=Range(mid=round(d.volume_m3, 1)),
            area_m2=round(d.area_m2, 1), max_depth_m=round(d.max_depth_m, 2), upstream_area_ha=ha(acc[d.deepest])))
    # flow lines + where they leave the parcel
    lines = trace_lines(acc, dirs, res, cfg["flow_min_upstream_ha"])
    flow_lines, exits = [], []
    for ln in lines:
        inside = [bool(in_parcel[r, c]) for r, c in ln]
        if not any(inside):
            continue
        xy = [_cell_xy(dem, r, c) for r, c in ln]
        geom = LineString(xy)
        flow_lines.append((acc[ln[-1]], FlowLine(geometry=to_geo(geom), upstream_area_ha=ha(acc[ln[-1]]),
                                                 length_m=round(geom.length, 1), crosses_parcel=True)))
        for i in range(len(ln) - 1):
            if inside[i] and not inside[i + 1]:
                exits.append((acc[ln[i]], Point(xy[i])))
                break
    flow_lines.sort(key=lambda t: -t[0])
    exits.sort(key=lambda t: -t[0])
    for k, (a, p) in enumerate(exits[: cfg["max_retention_spots"]], 1):
        spots.append(RetentionSpot(id=f"S{k}", kind="flow_concentration", geometry=to_geo(p), inside_parcel=True,
                                   upstream_area_ha=ha(a)))
    # ditch outlets: ditches crossing the parcel boundary, lowest crossing first
    outlets = []
    for g in ditch_geoms_2180:
        cross = g.intersection(parcel_2180.boundary.buffer(res))
        if cross.is_empty:
            continue
        p = cross.representative_point()
        c, r = int((p.x - dem.origin[0]) / res), int((dem.origin[1] - p.y) / res)
        if 0 <= r < z.shape[0] and 0 <= c < z.shape[1] and not np.isnan(z[r, c]):
            outlets.append((z[r, c], acc[r, c], p))
    outlets.sort(key=lambda t: t[0])
    for k, (_, a, p) in enumerate(outlets[: cfg["max_retention_spots"]], 1):
        spots.append(RetentionSpot(id=f"R{k}", kind="ditch_outlet", geometry=to_geo(p), inside_parcel=True,
                                   upstream_area_ha=ha(a)))

    zp = np.where(in_parcel, z, np.nan)
    low = np.unravel_index(int(np.nanargmin(zp)), z.shape)
    sp = slope[in_parcel & ~np.isnan(slope)]
    twp = tw[in_parcel & ~np.isnan(tw)]
    return TerrainData(
        dem_source=dem.source, resolution_m=res,
        elevation_min_m=round(float(np.nanmin(zp)), 2), elevation_max_m=round(float(np.nanmax(zp)), 2),
        slope_mean_pct=round(float(sp.mean()), 2) if sp.size else 0.0,
        slope_p90_pct=round(float(np.percentile(sp, 90)), 2) if sp.size else 0.0,
        twi_p90=round(float(np.percentile(twp, 90)), 2) if twp.size else None,
        lowest_point=to_geo(Point(_cell_xy(dem, *low))),
        retention_spots=spots,
        flow_lines=[f for _, f in flow_lines[: cfg["max_flow_lines"]]],
    )


async def terrain_data(parcel, hydro_data, budget_s: float):
    """SourceResult[TerrainData]. hydro_data gives the ditches for ditch_outlet spots: HydroData, None, or an
    awaitable of SourceResult[HydroData] (the provider's running hydro task) - the DEM is fetched while it runs."""
    import asyncio
    import inspect
    import time

    from shapely.geometry import shape

    from app.contracts.common import SourceResult, SourceStatus
    from app.contracts.geo import TerrainData
    from app.geo import dem as dem_mod
    from app.geo import geometry
    from app.geo.sources import provenance, source

    t0 = time.monotonic()
    try:
        return await _terrain_data(parcel, hydro_data, budget_s, t0)
    except dem_mod.DemNotReady as exc:
        return SourceResult[TerrainData](
            status=SourceStatus.MISSING, error=f"terrain: {exc}", elapsed_s=round(time.monotonic() - t0, 3),
            notes_pl=["Model terenu nie został pobrany w wyznaczonym czasie; pobieranie trwa w tle i ukształtowanie "
                      "terenu będzie dostępne przy kolejnej analizie tej działki."])


async def _terrain_data(parcel, hydro_data, budget_s: float, t0: float):
    import asyncio
    import inspect
    import time

    from shapely.geometry import shape

    from app.contracts.common import SourceResult, SourceStatus
    from app.contracts.geo import TerrainData
    from app.geo import dem as dem_mod
    from app.geo import geometry
    from app.geo.sources import provenance

    # Time kept for the analysis itself, from the size of the NMT grid (the larger of the two DEM grids);
    # the rest of the budget may be spent waiting for the DEM (config terrain_processing).
    cfg = dem_mod.tp()
    (minx, miny, maxx, maxy), res = dem_mod.grid_for(parcel)
    reserve = float(cfg["analysis_reserve_min_s"]) + (maxx - minx) * (maxy - miny) / res ** 2 * float(cfg["analysis_s_per_cell"])
    dem_budget = max(budget_s - reserve, 0.5)
    if inspect.isawaitable(hydro_data):
        (dem, notes), hydro_res = await asyncio.gather(dem_mod.fetch_dem(parcel, dem_budget),
                                                       asyncio.shield(hydro_data))
        hydro_data = hydro_res.data
    else:
        dem, notes = await dem_mod.fetch_dem(parcel, dem_budget)
    ditches = [geometry.to_2180(shape(f.geometry)) for f in (hydro_data.features if hydro_data else [])
               if f.kind == "ditch"]
    # The analysis is deterministic for one DEM (source, fetch time, grid) and one set of ditches: cache it, so a
    # warm analysis does not spend ~3 s on a 250k-cell grid again.
    from app.core import cache

    key = cache.make_key("geo.terrain", parcel=parcel.geometry_2180_wkt, dem=dem.source, res=dem.res,
                         fetched=dem.fetched_at.isoformat(), origin=list(dem.origin), ditches=[d.wkt for d in ditches])
    hit = cache.get(key)
    if hit is not None:
        data = TerrainData.model_validate(hit)
    else:
        data = await asyncio.to_thread(analyse, dem, geometry.parcel_geom_2180(parcel), ditches)
        cache.set(key, data.model_dump(mode="json"), expire_s=30 * 24 * 3600)   # OUR CHOICE, as for BDOT10k
    if hydro_data is None:
        notes.append("Brak danych o rowach - miejsca odpływu rowami nie zostały wskazane.")
    name = "gugik_nmt_wcs" if dem.source == "gugik_nmt_1m" else "copernicus_dem"
    prov = [provenance(name, dem.url, live=dem.live, fetched_at=dem.fetched_at, resolution=f"{dem.res:g} m")]
    status = SourceStatus.OK if dem.source == "gugik_nmt_1m" else SourceStatus.PARTIAL
    if dem.source == "gugik_nmt_1m" and dem.res > 1:
        notes.append(f"Numeryczny model terenu GUGiK (1 m) przeliczono na siatkę {dem.res:g} m ze względu na "
                     "wielkość obszaru analizy.")
    return SourceResult[TerrainData](status=status, data=data, provenance=prov, notes_pl=notes,
                                     elapsed_s=round(time.monotonic() - t0, 3))
