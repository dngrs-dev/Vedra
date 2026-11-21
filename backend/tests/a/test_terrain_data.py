"""terrain.terrain_data: contract assembly on a synthetic DEM (fetch mocked)."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest
from shapely.geometry import LineString, shape

from app.contracts.common import SourceStatus
from app.contracts.geo import HydroData, WaterFeature
from app.geo import dem as dem_mod
from app.geo import geometry, terrain, uldk

# parcel 200 m x 200 m in EPSG:2180, DEM covers it + 100 m on every side at 2 m
X0, Y0 = 452800.0, 548400.0
REC = (f"040704_2.0012.63/1|SRID=2180;POLYGON(({X0} {Y0},{X0 + 200} {Y0},{X0 + 200} {Y0 + 200},{X0} {Y0 + 200},"
       f"{X0} {Y0}))|x|kujawsko-pomorskie|powiat inowrocławski|Inowrocław|Jacewo|63/1").split("|")


def synthetic_dem(source="gugik_nmt_1m") -> dem_mod.Dem:
    res = 2.0
    n = 200                                   # 400 m
    rows, cols = np.mgrid[0:n, 0:n].astype(float)
    z = 100.0 + 0.02 * rows * res             # slopes up towards north (row 0 = north is highest)
    z = z[::-1].copy()
    cy, cx = 100, 100                         # bowl in the parcel centre, radius 20 m, depth 1 m
    r2 = ((rows - cy) * res) ** 2 + ((cols - cx) * res) ** 2
    z -= np.where(r2 < 20 ** 2, 1.0 * (1 - r2 / 20 ** 2), 0.0)
    return dem_mod.Dem(z=z, origin=(X0 - 100, Y0 + 300), res=res, source=source, url="https://x",
                       fetched_at=datetime(2026, 11, 21, tzinfo=timezone.utc), live=False)


@pytest.fixture
def parcel():
    return uldk.to_parcel(REC)


def hydro_with_ditch() -> HydroData:
    ditch = LineString([(X0 + 50, Y0 - 50), (X0 + 50, Y0 + 50)]).buffer(1)      # crosses the south boundary
    return HydroData(buffer_m=500, features=[WaterFeature(kind="ditch", geometry=geometry.to_4326(ditch).__geo_interface__,
                                                          distance_m=0, touches_parcel=True, source_id="bdot10k")])


@pytest.mark.asyncio
async def test_terrain_data_assembly(parcel, monkeypatch):
    async def fake_fetch(p, budget):
        return synthetic_dem(), []

    monkeypatch.setattr(dem_mod, "fetch_dem", fake_fetch)
    res = await terrain.terrain_data(parcel, hydro_with_ditch(), budget_s=20)
    d = res.data
    assert res.status == SourceStatus.OK and d.dem_source == "gugik_nmt_1m" and d.resolution_m == 2.0
    assert d.elevation_min_m < d.elevation_max_m and d.slope_mean_pct > 0
    deps = [s for s in d.retention_spots if s.kind == "depression"]
    assert len(deps) == 1 and deps[0].inside_parcel and deps[0].max_depth_m > 0.5
    # paraboloid pi R^2 h / 2 = 628 m3, minus what the regional slope does not hold back
    assert 100 < deps[0].volume_m3.mid < 700 and deps[0].volume_m3.low is None
    assert any(s.kind == "ditch_outlet" for s in d.retention_spots)
    assert all(s.geometry["type"] in ("Point", "Polygon", "MultiPolygon") for s in d.retention_spots)
    lon, lat = shape(d.lowest_point).coords[0]
    assert 18 < lon < 19 and 52 < lat < 53                       # geometries are EPSG:4326
    assert res.provenance[0].source_id == "gugik_nmt_wcs"


@pytest.mark.asyncio
async def test_copernicus_is_partial_with_note(parcel, monkeypatch):
    async def fake_fetch(p, budget):
        return synthetic_dem("copernicus_dem_30m"), ["note"]

    monkeypatch.setattr(dem_mod, "fetch_dem", fake_fetch)
    res = await terrain.terrain_data(parcel, None, budget_s=20)
    assert res.status == SourceStatus.PARTIAL and res.provenance[0].source_id == "copernicus_dem"
    assert any("rowach" in n for n in res.notes_pl)


def test_grid_for_respects_max_cells(parcel):
    (minx, miny, maxx, maxy), res = dem_mod.grid_for(parcel)
    assert res == 2.0 and (maxx - minx) / res * (maxy - miny) / res <= dem_mod.tp()["max_cells"]
