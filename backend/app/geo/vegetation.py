"""VegetationData assembly: which Sentinel-2 scenes to process, in what order, within the deadline.

Work queue (PART_A_DATA_GEO.md, vegetation.py):
  1. current window [date - current_window_days, date], newest first; if it has no clear scene, the window is
     extended to current_window_max_days (those scenes jump to the front of the queue),
  2. the same ± same_window_half_days window in each of history_years previous years (newest year first),
  3. Apr-Aug of each year <= date: at most season_max_scenes least-cloudy scenes, for season_peaks.
Scenes are shared between groups (computed once). At the deadline the remaining work is dropped from the
result; reads already running finish in their threads and fill the per-scene cache for the next run.
No interpretation here (Part B decides what the numbers mean).
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from shapely.geometry import mapping

from app.contracts.common import SourceResult, SourceStatus
from app.contracts.geo import GeoRequest, SceneStat, VegetationData
from app.contracts.parcel import Parcel
from app.geo import geometry, sentinel2
from app.geo.sentinel2 import SceneRef
from app.geo.sources import provenance, source

_pool: ThreadPoolExecutor | None = None


def _executor() -> ThreadPoolExecutor:
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(max_workers=int(sentinel2.s2_params()["workers"]), thread_name_prefix="s2")
    return _pool


def shutdown_background() -> None:
    """For scripts: drop queued background scene reads so the process can exit (running reads finish)."""
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=False, cancel_futures=True)
        _pool = None


def same_day(d: date, year: int) -> date:
    """Same month/day in another year; 29 Feb -> 28 Feb in non-leap years."""
    try:
        return d.replace(year=year)
    except ValueError:
        return d.replace(year=year, day=28)


def _background_stats(scene: SceneRef, interior_geo: dict) -> None:
    try:
        sentinel2.scene_stats(scene, interior_geo)
    except Exception:  # noqa: BLE001 - background warm-up only
        pass


async def _gather_searches(bbox, req: GeoRequest):
    cfg = sentinel2.s2_params()
    d = req.analysis_date
    cur_start = d - timedelta(days=req.current_window_days)
    ext_start = d - timedelta(days=max(cfg["current_window_max_days"], req.current_window_days))
    hist_years = [d.year - k for k in range(1, req.history_years + 1)]
    season_years = [d.year - k for k in range(0, req.history_years + 1)]
    m0, m1 = cfg["season_months"]

    async def search(start, end, **kw):
        return await sentinel2.search_scenes(bbox, start, end, not_after=d, **kw)

    current_all = search(ext_start, d)
    same = [search(same_day(d, y) - timedelta(days=req.same_window_half_days),
                   same_day(d, y) + timedelta(days=req.same_window_half_days),
                   limit=cfg["same_window_max_scenes"], by_cloud=True) for y in hist_years]
    seasons = [search(date(y, m0, 1), date(y, m1 + 1, 1) - timedelta(days=1),
                      limit=cfg["season_max_scenes"], by_cloud=True) for y in season_years]
    res = await asyncio.gather(current_all, *same, *seasons)
    current = res[0]
    same_by_year = dict(zip(hist_years, res[1:1 + len(hist_years)]))
    season_by_year = {y: s for y, s in zip(season_years, res[1 + len(hist_years):]) if date(y, m0, 1) <= d}
    return cur_start, ext_start, current, same_by_year, season_by_year


async def vegetation_data(parcel: Parcel, req: GeoRequest, budget_s: float) -> SourceResult[VegetationData]:
    t0 = time.monotonic()
    deadline = t0 + budget_s
    cfg = sentinel2.s2_params()
    notes: list[str] = []
    d = req.analysis_date

    interior = geometry.parcel_geom_2180(parcel).buffer(cfg["interior_buffer_m"])
    if interior.is_empty:
        return SourceResult[VegetationData](
            status=SourceStatus.MISSING, error="interior empty after -10 m buffer",
            notes_pl=["Działka jest zbyt mała lub zbyt wąska do analizy zdjęć satelitarnych Sentinel-2 "
                      "(piksel 10 m)."], elapsed_s=round(time.monotonic() - t0, 3))
    interior_geo = mapping(interior)
    minx, miny, maxx, maxy = geometry.to_4326(geometry.parcel_geom_2180(parcel)).bounds
    bbox = (minx, miny, maxx, maxy)

    cur_start, ext_start, current_all, same_by_year, season_by_year = await asyncio.wait_for(
        _gather_searches(bbox, req), timeout=max(deadline - time.monotonic(), 0.1))
    current_30 = [s for s in current_all if s.acquired >= cur_start]
    extension = [s for s in current_all if s.acquired < cur_start]

    # ---- priority queue of unique scenes
    queue: deque[SceneRef] = deque()
    seen: set[str] = set()

    def enqueue(scenes, front=False):
        new = [s for s in scenes if s.scene_id not in seen]
        seen.update(s.scene_id for s in new)
        if front:
            queue.extendleft(reversed(new))
        else:
            queue.extend(new)

    enqueue(current_30)
    for y in sorted(same_by_year, reverse=True):
        enqueue(same_by_year[y])
    for y in sorted(season_by_year, reverse=True):
        enqueue(season_by_year[y])
    considered = set(seen) | {s.scene_id for s in extension}

    results: dict[str, SceneStat | None] = {}
    interior_px = 0
    loop = asyncio.get_running_loop()
    running: dict[asyncio.Future, SceneRef] = {}
    workers = int(cfg["workers"])
    extended = False
    errors = 0

    while queue or running:
        while queue and len(running) < workers:
            s = queue.popleft()
            running[loop.run_in_executor(_executor(), sentinel2.scene_stats, s, interior_geo)] = s
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        done, _ = await asyncio.wait(running, timeout=remaining, return_when=asyncio.FIRST_COMPLETED)
        for fut in done:
            s = running.pop(fut)
            try:
                stat, n = fut.result()
            except Exception:  # noqa: BLE001 - one unreadable scene must not stop the analysis
                errors += 1
                results[s.scene_id] = None
                continue
            results[s.scene_id] = stat
            interior_px = max(interior_px, n)
        if not extended and extension and all(s.scene_id in results for s in current_30) \
                and not any(results.get(s.scene_id) for s in current_30):
            extended = True
            enqueue(extension, front=True)
    # Unfinished work continues in the shared pool and fills the per-scene cache for the next analysis.
    for s in queue:
        _executor().submit(_background_stats, s, interior_geo)
    queue.clear()

    def clear(scenes):
        return [results[s.scene_id] for s in scenes if results.get(s.scene_id) is not None]

    def complete(scenes):
        return all(s.scene_id in results for s in scenes)

    window_scenes = current_30 + (extension if extended else [])
    current = sorted(clear(window_scenes), key=lambda x: x.acquired, reverse=True)
    window = (ext_start if extended else cur_start, d)
    # Years in which the archive has no scene at all for the window are left out (not "no clear scene").
    no_archive = sorted({y for y, sc in same_by_year.items() if not sc} & {y for y, sc in season_by_year.items() if not sc})
    same_window = {y: sorted(clear(sc), key=lambda x: x.acquired)
                   for y, sc in same_by_year.items() if sc and complete(sc)}
    peaks: dict[int, SceneStat | None] = {}
    for y, sc in season_by_year.items():
        if sc and complete(sc):
            c = clear(sc)
            peaks[y] = max(c, key=lambda x: x.ndvi_median) if c else None

    processed = len(results)
    total = len(seen)
    status = SourceStatus.OK
    if processed < total:
        status = SourceStatus.PARTIAL
        notes.append(f"Przeanalizowano {processed} z {total} scen Sentinel-2 w dostępnym czasie; "
                     "pozostałe sceny są przetwarzane w tle i zostaną uwzględnione przy kolejnej analizie.")
    if interior_px and interior_px < cfg["min_interior_pixels"]:
        status = SourceStatus.PARTIAL
        notes.append(f"Mała działka: tylko {interior_px} pikseli Sentinel-2 (10 m) we wnętrzu działki; "
                     "wskaźniki roślinności są mniej wiarygodne.")
    if complete(window_scenes) and not current:
        status = SourceStatus.PARTIAL
        notes.append(f"Brak bezchmurnych zdjęć Sentinel-2 działki od {window[0].isoformat()} "
                     f"do {window[1].isoformat()}.")
    elif extended and current:
        notes.append(f"W ostatnich {req.current_window_days} dniach brak bezchmurnych zdjęć; okno bieżące "
                     f"rozszerzono do {(window[1] - window[0]).days} dni.")
    if errors:
        notes.append(f"{errors} scen Sentinel-2 nie udało się odczytać.")
    if no_archive:
        notes.append("Brak zdjęć Sentinel-2 L2A w archiwum dla lat: " + ", ".join(map(str, no_archive))
                     + "; porównanie wieloletnie obejmuje krótszy okres.")

    dates = [r.acquired for r in results.values() if r is not None]
    data = VegetationData(
        interior_pixels=interior_px,
        current=current,
        current_window=window,
        same_window_by_year=same_window,
        season_peaks=peaks,
        scenes_considered=len(considered),
        scenes_processed=processed,
    )
    cols = source("earth_search")["collections"]
    prov = [provenance("earth_search", f"{source('earth_search')['url']}/collections/{cols['primary']}",
                       data_period=f"{min(dates).isoformat()}..{max(dates).isoformat()}" if dates else None,
                       resolution="10 m")]
    return SourceResult[VegetationData](status=status, data=data, provenance=prov, notes_pl=notes,
                                        error=f"{errors} scene reads failed" if errors else None,
                                        elapsed_s=round(time.monotonic() - t0, 3))
