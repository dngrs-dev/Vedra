"""static_map.py: PNG output, hillshade, legend logic (no network: DEM fetch mocked)."""
from __future__ import annotations

import io
from datetime import datetime, timezone

import numpy as np
import pytest
from shapely.geometry import LineString, Point

from app.contracts.common import Range, SourceResult, SourceStatus
from app.contracts.geo import FlowLine, GeoBundle, HydroData, RetentionSpot, TerrainData, WaterFeature
from app.geo import dem as dem_mod
from app.geo import geometry, static_map, uldk

REC = ("040704_2.0012.63/1|SRID=2180;POLYGON((452800 548400,452900 548400,452900 548500,452800 548500,"
       "452800 548400))|x|kujawsko-pomorskie|powiat inowrocławski|Inowrocław|Jacewo|63/1").split("|")


def g4326(g):
    return geometry.to_4326(g).__geo_interface__


def bundle(with_terrain=True) -> GeoBundle:
    missing = {"status": SourceStatus.MISSING, "notes_pl": ["x"]}
    terrain = SourceResult[TerrainData](status=SourceStatus.OK, data=TerrainData(
        dem_source="gugik_nmt_1m", resolution_m=2, elevation_min_m=90, elevation_max_m=92, slope_mean_pct=1,
        slope_p90_pct=2, lowest_point=g4326(Point(452850, 548410)),
        retention_spots=[RetentionSpot(id="Z1", kind="depression", geometry=g4326(Point(452850, 548450).buffer(10)),
                                       inside_parcel=True, volume_m3=Range(mid=50.0)),
                         RetentionSpot(id="S1", kind="flow_concentration", geometry=g4326(Point(452850, 548400)),
                                       inside_parcel=True)],
        flow_lines=[FlowLine(geometry=g4326(LineString([(452850, 548480), (452850, 548380)])), upstream_area_ha=2,
                             length_m=100, crosses_parcel=True)])) if with_terrain else missing
    hydro = SourceResult[HydroData](status=SourceStatus.OK, data=HydroData(buffer_m=500, features=[
        WaterFeature(kind="ditch", geometry=g4326(LineString([(452700, 548300), (453000, 548300)]).buffer(1)),
                     distance_m=100, touches_parcel=False, source_id="bdot10k")]))
    return GeoBundle.model_validate({"soil": missing, "vegetation": missing, "terrain": terrain, "hydro": hydro,
                                     "landcover": missing, "edo": missing, "imgw": missing})


def dem() -> dem_mod.Dem:
    y, x = np.mgrid[0:300, 0:300].astype(float)
    return dem_mod.Dem(z=90 + 0.01 * x + np.sin(y / 20), origin=(452500.0, 548800.0), res=2.0,
                       source="gugik_nmt_1m", url="https://x", fetched_at=datetime.now(timezone.utc), live=False)


def test_hillshade_range_and_flat():
    hs = static_map.hillshade(dem().z, 2.0)
    assert hs.min() >= 0 and hs.max() <= 1
    flat = static_map.hillshade(np.full((10, 10), 5.0), 1.0)
    assert np.allclose(flat, np.sin(np.radians(static_map.HILLSHADE_ALTITUDE_DEG)))


@pytest.mark.parametrize("with_dem,with_terrain", [(True, True), (False, False)])
def test_render_png(with_dem, with_terrain):
    import matplotlib.image as mpimg

    png = static_map.render_png(uldk.to_parcel(REC), bundle(with_terrain), 800, dem() if with_dem else None)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert mpimg.imread(io.BytesIO(png), format="png").shape[1] == 800


@pytest.mark.asyncio
async def test_render_without_dem_does_not_fail(monkeypatch):
    async def no_dem(p, budget):
        raise dem_mod.DemNotReady("x")

    monkeypatch.setattr(dem_mod, "fetch_dem", no_dem)
    png = await static_map.render(uldk.to_parcel(REC), bundle(), 600)
    assert png[:4] == b"\x89PNG"


def test_attribution_lists_drawn_sources_only():
    b = bundle()
    assert static_map._attribution(b).startswith("Źródła: ULDK GUGiK")
