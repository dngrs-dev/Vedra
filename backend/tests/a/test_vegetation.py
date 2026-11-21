"""vegetation.py: work queue, window extension, history assembly, deadline (scene reads mocked)."""
from __future__ import annotations

import time
from datetime import date, timedelta

import pytest

from app.contracts.common import SourceStatus
from app.contracts.geo import GeoRequest, SceneStat
from app.geo import sentinel2, uldk, vegetation
from app.geo.sentinel2 import BandInfo, SceneRef

REC = ("040704_2.0012.63/1|SRID=2180;POLYGON((452800 548400,452900 548400,452900 548500,452800 548500,"
       "452800 548400))|x|kujawsko-pomorskie|powiat inowrocławski|Inowrocław|Jacewo|63/1").split("|")
DAY = date(2023, 5, 31)


def ref(d: date) -> SceneRef:
    b = BandInfo(href="https://sentinel-cogs.s3.us-west-2.amazonaws.com/x.tif", scale=1e-4, offset=-0.1, nodata=0)
    return SceneRef(scene_id=f"S2_{d.isoformat()}", acquired=d, sensing=f"{d.isoformat()}T10:00:00Z",
                    platform="sentinel-2a", cloud_cover=1.0, baseline="05.00", collection="sentinel-2-l2a",
                    bands={k: b for k in sentinel2.BANDS})


@pytest.fixture
def parcel():
    return uldk.to_parcel(REC)


def install(monkeypatch, scenes_by_window, clear=lambda d: True, ndvi=lambda d: 0.5 + d.month / 100, delay=0.0):
    async def search(bbox, start, end, *, not_after, limit=None, by_cloud=False):
        end = min(end, not_after)
        out = [s for s in scenes_by_window if start <= s.acquired <= end]
        return sorted(out, key=lambda s: s.acquired, reverse=True)[:limit] if limit else out

    def stats(s, interior):
        if delay:
            time.sleep(delay)
        if not clear(s.acquired):
            return None, 99
        return SceneStat(scene_id=s.scene_id, acquired=s.acquired, ndvi_median=ndvi(s.acquired), ndmi_median=0.1,
                         valid_pixels=99, valid_fraction=1.0), 99

    monkeypatch.setattr(sentinel2, "search_scenes", search)
    monkeypatch.setattr(sentinel2, "scene_stats", stats)


@pytest.mark.asyncio
async def test_assembly_current_history_peaks(monkeypatch, parcel):
    scenes = [ref(DAY - timedelta(days=k)) for k in (2, 12, 25)]                       # current window
    scenes += [ref(date(2022, 5, 28)), ref(date(2022, 6, 5)), ref(date(2022, 7, 20))]  # 2022: window + season
    install(monkeypatch, scenes)
    res = await vegetation.vegetation_data(parcel, GeoRequest(parcel=parcel, analysis_date=DAY), budget_s=10)
    d = res.data
    assert res.status == SourceStatus.OK
    assert [s.acquired for s in d.current] == [DAY - timedelta(days=k) for k in (2, 12, 25)]   # newest first
    assert d.current_window == (DAY - timedelta(days=30), DAY)
    assert [s.acquired for s in d.same_window_by_year[2022]] == [date(2022, 5, 28), date(2022, 6, 5)]
    assert d.season_peaks[2022].acquired == date(2022, 7, 20)                                  # max NDVI Apr-Aug
    assert d.season_peaks[2023].acquired == DAY - timedelta(days=2)
    assert 2014 not in d.same_window_by_year and any("Brak zdjęć Sentinel-2 L2A" in n for n in res.notes_pl)
    assert d.interior_pixels == 99 and res.provenance


@pytest.mark.asyncio
async def test_no_scene_after_analysis_date(monkeypatch, parcel):
    scenes = [ref(DAY - timedelta(days=3)), ref(DAY), ref(DAY + timedelta(days=1)), ref(date(2023, 7, 1))]
    install(monkeypatch, scenes)
    d = (await vegetation.vegetation_data(parcel, GeoRequest(parcel=parcel, analysis_date=DAY), budget_s=10)).data
    every = d.current + [s for v in d.same_window_by_year.values() for s in v] + \
        [s for s in d.season_peaks.values() if s]
    assert every and max(s.acquired for s in every) <= DAY


@pytest.mark.asyncio
async def test_window_extended_to_60_days_when_no_clear_scene(monkeypatch, parcel):
    scenes = [ref(DAY - timedelta(days=5)), ref(DAY - timedelta(days=45))]
    install(monkeypatch, scenes, clear=lambda d: d < DAY - timedelta(days=30))
    res = await vegetation.vegetation_data(parcel, GeoRequest(parcel=parcel, analysis_date=DAY), budget_s=10)
    assert res.data.current_window == (DAY - timedelta(days=60), DAY)
    assert [s.acquired for s in res.data.current] == [DAY - timedelta(days=45)]
    assert any("rozszerzono" in n for n in res.notes_pl)


@pytest.mark.asyncio
async def test_no_clear_scene_is_partial_with_note(monkeypatch, parcel):
    install(monkeypatch, [ref(DAY - timedelta(days=5))], clear=lambda d: False)
    res = await vegetation.vegetation_data(parcel, GeoRequest(parcel=parcel, analysis_date=DAY), budget_s=10)
    assert res.status == SourceStatus.PARTIAL and res.data.current == []
    assert any("Brak bezchmurnych" in n for n in res.notes_pl)


@pytest.mark.asyncio
async def test_deadline_gives_partial(monkeypatch, parcel):
    scenes = [ref(DAY - timedelta(days=k)) for k in range(1, 30)]
    install(monkeypatch, scenes, delay=0.2)
    t = time.monotonic()
    res = await vegetation.vegetation_data(parcel, GeoRequest(parcel=parcel, analysis_date=DAY), budget_s=0.3)
    assert time.monotonic() - t < 1.0
    assert res.status == SourceStatus.PARTIAL
    assert res.data.scenes_processed < res.data.scenes_considered
    assert any(n.startswith("Przeanalizowano") for n in res.notes_pl)
    vegetation.shutdown_background()


@pytest.mark.asyncio
async def test_too_small_parcel_is_missing(monkeypatch):
    tiny = ("x_1.0001.1|SRID=2180;POLYGON((452800 548400,452815 548400,452815 548415,452800 548415,452800 548400))"
            "|x|v|c|g|r|1").split("|")
    install(monkeypatch, [])
    res = await vegetation.vegetation_data(uldk.to_parcel(tiny), GeoRequest(parcel=uldk.to_parcel(tiny),
                                                                             analysis_date=DAY), budget_s=5)
    assert res.status == SourceStatus.MISSING and "zbyt mała" in res.notes_pl[0]


@pytest.mark.asyncio
async def test_leftover_background_work_does_not_starve_next_analysis(monkeypatch, parcel):
    """Regression (2026-11-21): with one shared pool, every analysis after the first processed 0 scenes."""
    slow_day = date(2023, 5, 31)
    fast_day = date(2022, 5, 31)
    slow = [ref(slow_day - timedelta(days=k)) for k in range(1, 29)]
    fast = [ref(fast_day - timedelta(days=k)) for k in range(1, 6)]

    async def search(bbox, start, end, *, not_after, limit=None, by_cloud=False):
        out = [s for s in slow + fast if start <= s.acquired <= min(end, not_after)]
        return out[:limit] if limit else out

    def stats(s, interior):
        if s.acquired.year == 2023:
            time.sleep(1.0)      # first analysis: slow reads, most of them left to the background
        return SceneStat(scene_id=s.scene_id, acquired=s.acquired, ndvi_median=0.5, ndmi_median=0.1,
                         valid_pixels=99, valid_fraction=1.0), 99

    monkeypatch.setattr(sentinel2, "search_scenes", search)
    monkeypatch.setattr(sentinel2, "scene_stats", stats)
    first = await vegetation.vegetation_data(parcel, GeoRequest(parcel=parcel, analysis_date=slow_day), budget_s=0.3)
    assert first.status == SourceStatus.PARTIAL
    second = await vegetation.vegetation_data(parcel, GeoRequest(parcel=parcel, analysis_date=fast_day, history_years=0),
                                              budget_s=2.0)
    assert second.data.scenes_processed == second.data.scenes_considered == len(fast)
    vegetation.shutdown_background()
