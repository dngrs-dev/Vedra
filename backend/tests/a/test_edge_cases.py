"""CP4 edge cases (offline): multipolygon parcel, parcel < 0.2 ha, date in 2016, every source down.

Forest / water / built-up parcels need the real services; they are checked live by scripts/a/check_edge_cases.py
(real parcels in tests/a/data/edge_parcels.json) and their recorded bundles are validated in test_edge_bundles below.
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import LineString, Point, shape

from app.contracts.common import SourceStatus
from app.contracts.errors import UpstreamUnavailable
from app.contracts.geo import GeoBundle, GeoRequest, SceneStat, WaterFeature
from app.geo import dem as dem_mod
from app.geo import geometry, hydro, static_map, terrain, uldk, vegetation
from app.geo.provider import RealGeoProvider

from tests.a.test_vegetation import install, ref

DATA = Path(__file__).parent / "data"

# two 200 m x 200 m parts 200 m apart (EPSG:2180)
X0, Y0 = 452800.0, 548400.0


def _sq(x, y, s):
    return f"(({x} {y},{x + s} {y},{x + s} {y + s},{x} {y + s},{x} {y}))"


MULTI = (f"x_1.0001.1|SRID=2180;MULTIPOLYGON({_sq(X0, Y0, 200)},{_sq(X0 + 400, Y0, 200)})"
         "|x|kujawsko-pomorskie|powiat inowrocławski|Inowrocław|Jacewo|1").split("|")
SMALL = (f"x_1.0001.2|SRID=2180;POLYGON{_sq(X0, Y0, 40)}"                         # 0.16 ha
         "|x|kujawsko-pomorskie|powiat inowrocławski|Inowrocław|Jacewo|2").split("|")


def two_bowl_dem() -> dem_mod.Dem:
    """2 m DEM over both parts + 100 m, tilted, with a 1 m deep bowl (r = 20 m) in the centre of each part."""
    res, x_left, y_top = 2.0, X0 - 100, Y0 + 300
    rows, cols = np.mgrid[0:250, 0:450].astype(float)
    x, y = x_left + (cols + 0.5) * res, y_top - (rows + 0.5) * res
    z = 100.0 + 0.01 * (y - Y0)
    for cx in (X0 + 100, X0 + 500):
        r2 = (x - cx) ** 2 + (y - (Y0 + 100)) ** 2
        z -= np.where(r2 < 400, 1.0 * (1 - r2 / 400), 0.0)
    return dem_mod.Dem(z=z, origin=(x_left, y_top), res=res, source="gugik_nmt_1m", url="https://x",
                       fetched_at=datetime(2026, 11, 21, tzinfo=timezone.utc), live=False)


# ------------------------------------------------------------------------------------------------ multipolygon
def test_multipolygon_parcel_geometry_and_sampling():
    p = uldk.to_parcel(MULTI)
    g = geometry.parcel_geom_2180(p)
    assert p.geometry_wgs84["type"] == "MultiPolygon" and abs(p.area_ha - 8.0) < 0.01
    lat, lon = geometry.query_point(p)
    assert g.buffer(1).contains(geometry.to_2180(Point(lon, lat)))   # never the centroid between the parts
    pts = geometry.sample_points(g, 9)
    assert len(pts) == 9 and all(g.contains(q) for q in pts)
    assert {int(q.x > X0 + 300) for q in pts} == {0, 1}                 # both parts are sampled


@pytest.mark.asyncio
async def test_multipolygon_terrain_finds_a_depression_in_each_part(monkeypatch):
    async def fake_fetch(p, budget):
        return two_bowl_dem(), []

    monkeypatch.setattr(dem_mod, "fetch_dem", fake_fetch)
    p = uldk.to_parcel(MULTI)
    res = await terrain.terrain_data(p, None, budget_s=20)
    deps = [s for s in res.data.retention_spots if s.kind == "depression"]
    assert res.status == SourceStatus.OK and len(deps) == 2 and all(s.inside_parcel for s in deps)


def test_multipolygon_ditch_crossings_and_static_map():
    from tests.a.test_static_map import bundle

    p = uldk.to_parcel(MULTI)
    g = geometry.parcel_geom_2180(p)
    ditch = WaterFeature(kind="ditch", geometry=geometry.to_4326(
        LineString([(X0 + 500, Y0 - 50), (X0 + 500, Y0 + 50)])).__geo_interface__,
        distance_m=0, touches_parcel=True, source_id="bdot10k")
    assert hydro.count_ditch_crossings([ditch], g) == 1                 # crosses the second part only
    png = static_map.render_png(p, bundle(), 800, two_bowl_dem())
    assert png[:4] == b"\x89PNG"


@pytest.mark.asyncio
async def test_multipolygon_vegetation(monkeypatch):
    day = date(2023, 5, 31)
    install(monkeypatch, [ref(day - timedelta(days=3))])
    p = uldk.to_parcel(MULTI)
    res = await vegetation.vegetation_data(p, GeoRequest(parcel=p, analysis_date=day), budget_s=5)
    assert res.status == SourceStatus.OK and len(res.data.current) == 1


# ------------------------------------------------------------------------------------------------ < 0.2 ha
@pytest.mark.asyncio
async def test_small_parcel_vegetation_is_partial_with_few_pixels(monkeypatch):
    """40 m x 40 m: the -10 m interior is 20 m x 20 m = 4 Sentinel-2 pixels (< min_interior_pixels)."""
    day = date(2023, 5, 31)
    install(monkeypatch, [ref(day - timedelta(days=3))])

    def stats(s, interior):
        assert abs(shape(interior).area - 400) < 1
        return SceneStat(scene_id=s.scene_id, acquired=s.acquired, ndvi_median=0.6, ndmi_median=0.1,
                         valid_pixels=4, valid_fraction=1.0), 4

    monkeypatch.setattr(vegetation.sentinel2, "scene_stats", stats)
    p = uldk.to_parcel(SMALL)
    res = await vegetation.vegetation_data(p, GeoRequest(parcel=p, analysis_date=day), budget_s=5)
    assert res.status == SourceStatus.PARTIAL and res.data.interior_pixels == 4
    assert any(n.startswith("Mała działka: tylko 4 pikseli") for n in res.notes_pl)


@pytest.mark.asyncio
async def test_small_parcel_soil_points_and_terrain(monkeypatch):
    p = uldk.to_parcel(SMALL)
    g = geometry.parcel_geom_2180(p)
    assert 1 <= len(geometry.sample_points(g, 9)) <= 9 and all(g.contains(q) for q in geometry.sample_points(g, 9))

    async def fake_fetch(parcel, budget):
        return two_bowl_dem(), []

    monkeypatch.setattr(dem_mod, "fetch_dem", fake_fetch)
    res = await terrain.terrain_data(p, None, budget_s=20)
    assert res.status == SourceStatus.OK and res.data.elevation_min_m <= res.data.elevation_max_m


# ------------------------------------------------------------------------------------------------ date in 2016
@pytest.mark.asyncio
async def test_2016_date_has_no_history_years_and_says_so(monkeypatch):
    """Sentinel-2 L2A starts in 2016 in the archive: no same-window years before 2016, never an exception."""
    from app.geo import uldk as u
    from tests.a.test_vegetation import REC

    day = date(2016, 12, 15)
    install(monkeypatch, [ref(date(2016, 11, 28)), ref(date(2016, 12, 8))])
    p = u.to_parcel(REC)
    res = await vegetation.vegetation_data(p, GeoRequest(parcel=p, analysis_date=day), budget_s=5)
    d = res.data
    assert res.status == SourceStatus.OK and [s.acquired for s in d.current] == [date(2016, 12, 8), date(2016, 11, 28)]
    assert d.same_window_by_year == {} and d.season_peaks == {}
    assert any("Brak zdjęć Sentinel-2 L2A w archiwum dla lat: 2006" in n and "2015" in n for n in res.notes_pl)


# ------------------------------------------------------------------------------------------------ all sources down
@pytest.mark.asyncio
async def test_every_source_down_still_gives_a_valid_bundle(monkeypatch):
    import rasterio

    from app.core import http
    from app.geo import soilgrids

    async def down(url, *a, **kw):
        raise UpstreamUnavailable("mocked: all upstreams down")

    def raster_down(*a, **kw):
        raise rasterio.errors.RasterioIOError("mocked: all upstreams down")

    monkeypatch.setattr(http, "get", down)
    monkeypatch.setattr(rasterio, "open", raster_down)
    monkeypatch.setattr(soilgrids, "_preprocessed", lambda lat, lon: None)
    monkeypatch.setattr(dem_mod, "preprocessed_path", lambda parcel: Path("/nonexistent/none.tif"))
    p = uldk.to_parcel(MULTI)
    today = datetime.now(timezone.utc).date()                     # today: the IMGW path is exercised too
    t = time.monotonic()
    bundle = await RealGeoProvider().collect(GeoRequest(parcel=p, analysis_date=today, deadline_s=6))
    assert time.monotonic() - t <= 6 + 0.5
    GeoBundle.model_validate(bundle.model_dump(mode="json"))
    for name, res in bundle:
        assert res.status != SourceStatus.OK, name
        assert res.notes_pl, name                                 # B shows these notes in the report
    assert bundle.hydro.status == SourceStatus.MISSING
    assert any("nie oznacza to braku wód" in n for n in bundle.hydro.notes_pl)


# ------------------------------------------------------------------------------------------------ live-recorded
EDGE_BUNDLES = sorted((DATA / "edge_bundles").glob("*.json"))


@pytest.mark.parametrize("path", EDGE_BUNDLES, ids=[p.stem for p in EDGE_BUNDLES])
def test_edge_bundles(path):
    """Bundles recorded by scripts/a/check_edge_cases.py for real forest / water / built-up / huge parcels."""
    rec = json.loads(path.read_text(encoding="utf-8"))
    bundle = GeoBundle.model_validate(rec["bundle"])
    for name, res in bundle:
        if res.status != SourceStatus.OK:
            assert res.notes_pl or res.error, name
        if res.data is not None:
            assert res.provenance, name
