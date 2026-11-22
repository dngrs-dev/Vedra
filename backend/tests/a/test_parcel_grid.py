"""app/api/parcel_grid.py, GET /api/parcels/in-bbox and /obreby-in-bbox: grids, WFS answers, parquet fallback,
cell cache, obręby GML parsing."""
from __future__ import annotations

import httpx
import pytest
import respx
from shapely.geometry import Point, box

from app.api import parcel_grid
from app.core import cache
from app.geo import geometry
from app.geo.sources import source

from test_egib_parquet import URL as PARQUET_URL  # tests/a is on sys.path (rootdir prepend)
from test_egib_parquet import _serve


def _wfs_feature(pid: str, lon: float, lat: float, d: float = 0.001) -> dict:
    ring = [[lon, lat], [lon + d, lat], [lon + d, lat + d], [lon, lat + d], [lon, lat]]
    return {"type": "Feature", "properties": {"ID_DZIALKI": pid, "NUMER_DZIALKI": pid.rsplit(".", 1)[-1]},
            "geometry": {"type": "Polygon", "coordinates": [ring]}}


def test_cells_cover_the_box_on_a_fixed_grid():
    cells = parcel_grid.cells_for(52.201, 21.001, 52.219, 21.029)
    assert cells == [(5220, 1400), (5220, 1401), (5221, 1400), (5221, 1401)]
    lat0, lon0, lat1, lon1 = parcel_grid.cell_box((5220, 1400))
    assert (lat0, lon0, lat1, lon1) == (52.2, 21.0, 52.21, 21.015)
    # a box exactly on cell edges is that one cell
    assert parcel_grid.cells_for(52.2, 21.0, 52.21, 21.015) == [(5220, 1400)]
    with pytest.raises(parcel_grid.BboxTooLarge):
        parcel_grid.cells_for(52.0, 21.0, 52.5, 21.1)


def test_features_are_simplified_and_rounded():
    f = parcel_grid.feature("x.1", {"number": "1"}, box(21.0000001234, 52.0000004321, 21.001, 52.001))
    coords = f["geometry"]["coordinates"][0]
    assert all(len(str(c).split(".")[-1]) <= 6 for xy in coords for c in xy)
    assert f["id"] == "x.1" and f["properties"] == {"id": "x.1", "number": "1"}
    assert parcel_grid.feature("x.2", {}, Point(21, 52)) is None


def test_parcel_area_comes_from_the_unsimplified_2180_geometry():
    g2180 = box(452800, 548400, 452900, 548500)            # 100 m x 100 m = 1 ha
    f = parcel_grid.parcel_feature("040704_2.0012.1/1", "1/1", geometry.to_4326(g2180), g2180)
    assert f["properties"] == {"id": "040704_2.0012.1/1", "number": "1/1", "area_ha": 1.0}


def _obreby_gml(*obreby: tuple[str, str, list[tuple[float, float]]]) -> str:
    """PRG WFS answer in the shape seen 2026-11-22: GML 3.2, EPSG:2180, posList in northing easting order."""
    members = "".join(
        f"<wfs:member><ms:A06_Granice_obrebow_ewidencyjnych><ms:msGeometry>"
        f"<gml:Polygon srsName=\"urn:ogc:def:crs:EPSG::2180\"><gml:exterior><gml:LinearRing>"
        f"<gml:posList srsDimension=\"2\">{' '.join(f'{n} {e}' for e, n in ring)}</gml:posList>"
        f"</gml:LinearRing></gml:exterior></gml:Polygon></ms:msGeometry>"
        f"<ms:JPT_KOD_JE>{code}</ms:JPT_KOD_JE><ms:JPT_NAZWA_>{name}</ms:JPT_NAZWA_>"
        f"</ms:A06_Granice_obrebow_ewidencyjnych></wfs:member>"
        for code, name, ring in obreby)
    return ('<wfs:FeatureCollection xmlns:ms="http://mapserver.gis.umn.edu/mapserver" '
            'xmlns:gml="http://www.opengis.net/gml/3.2" xmlns:wfs="http://www.opengis.net/wfs/2.0">'
            f"{members}</wfs:FeatureCollection>")


JACEWO_RING = [(452700.0, 548300.0), (453400.0, 548300.0), (453400.0, 548600.0), (452700.0, 548600.0),
               (452700.0, 548300.0)]


def test_obreby_gml_is_parsed_with_northing_easting_axes():
    out = parcel_grid.parse_obreby(_obreby_gml(("040704_2.0012", "Jacewo", JACEWO_RING)))
    assert [f["id"] for f in out] == ["040704_2.0012"] and out[0]["properties"]["name"] == "Jacewo"
    lon, lat = out[0]["geometry"]["coordinates"][0][0]
    expected = geometry.to_4326(Point(452700.0, 548300.0))
    assert abs(lon - expected.x) < 1e-5 and abs(lat - expected.y) < 1e-5    # Inowrocław area, not swapped
    with pytest.raises(parcel_grid.UpstreamUnavailable):
        parcel_grid.parse_obreby("<ows:ExceptionReport xmlns:ows='http://www.opengis.net/ows/1.1'/>")


@pytest.mark.asyncio
async def test_obreby_endpoint_uses_the_coarse_grid():
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(source("prg_wfs")["url"]).mock(
            return_value=httpx.Response(200, text=_obreby_gml(("040704_2.0012", "Jacewo", JACEWO_RING))))
        out = await parcel_grid.obreby_in_bbox(52.79, 18.25, 52.80, 18.26)
    assert [f["id"] for f in out["features"]] == ["040704_2.0012"]
    assert route.call_count == 1
    assert route.calls[0].request.url.params["BBOX"].startswith("52.76,18.24,52.8,18.3,")
    with pytest.raises(parcel_grid.BboxTooLarge):
        parcel_grid.cells_for(52.0, 18.0, 52.5, 18.5, parcel_grid.OBREBY)


@pytest.mark.asyncio
async def test_wfs_cells_are_deduped_and_cached(monkeypatch):
    store: dict = {}
    monkeypatch.setattr(cache, "get", store.get)
    monkeypatch.setattr(cache, "set", lambda k, v, expire_s=None: store.__setitem__(k, v))
    with respx.mock(assert_all_called=False) as mock:
        # one parcel straddles the two cells and is returned for both
        route = mock.get(parcel_grid.WFS_URL).mock(return_value=httpx.Response(200, json={
            "type": "FeatureCollection",
            "features": [_wfs_feature("146501_8.0101.12/3", 21.0145, 52.205), _wfs_feature("bad", 21.0, 52.0) | {
                "geometry": None}]}))
        out = await parcel_grid.parcels_in_bbox(52.201, 21.001, 52.209, 21.02)
        assert [f["id"] for f in out["features"]] == ["146501_8.0101.12/3"] and out["truncated"] is False
        assert out["features"][0]["properties"]["area_ha"] > 0
        assert route.call_count == 2
        bbox = route.calls[0].request.url.params["bbox"]
        assert bbox.startswith("52.2,21.0,52.21,21.015,")   # latitude/longitude order (WFS 2.0, EPSG:4326)
        await parcel_grid.parcels_in_bbox(52.201, 21.001, 52.209, 21.02)
        assert route.call_count == 2   # second request: both cells from the cache


@pytest.mark.asyncio
async def test_wfs_down_falls_back_to_the_parquet_export():
    # the test export's first row group: 5 squares of 100 m from (452800, 548400) in EPSG:2180
    sw = geometry.to_4326(Point(452850.0, 548450.0))
    with respx.mock(assert_all_called=False) as mock:
        mock.get(parcel_grid.WFS_URL).mock(return_value=httpx.Response(503))
        mock.get(PARQUET_URL).mock(side_effect=_serve)
        mock.get(source("prg_wfs")["url"]).mock(return_value=httpx.Response(503))
        out = await parcel_grid.parcels_in_bbox(sw.y - 0.0005, sw.x - 0.0005, sw.y + 0.0005, sw.x + 0.0005)
    ids = {f["id"] for f in out["features"]}
    assert "040704_2.0012.0/1" in ids and all(i.startswith("040704_2.0012.") for i in ids)
    assert out["features"][0]["geometry"]["type"] == "Polygon"


@pytest.mark.asyncio
async def test_everything_down_is_upstream_unavailable(monkeypatch):
    async def _no_sleep(_s):
        return None

    monkeypatch.setattr("asyncio.sleep", _no_sleep)
    with respx.mock(assert_all_called=False) as mock:
        mock.get(parcel_grid.WFS_URL).mock(return_value=httpx.Response(503))
        mock.get(PARQUET_URL).mock(return_value=httpx.Response(503))
        with pytest.raises(parcel_grid.UpstreamUnavailable):
            await parcel_grid.parcels_in_bbox(52.201, 21.001, 52.209, 21.009)


def test_route_validates_the_box(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    async def fake(*box_):
        return {"type": "FeatureCollection", "features": [], "truncated": False, "box": list(box_)}

    monkeypatch.setattr(parcel_grid, "parcels_in_bbox", fake)
    monkeypatch.setattr("app.api.routes_parcels.settings.geo_provider", "real")
    with TestClient(app) as client:
        ok = client.get("/api/parcels/in-bbox", params={"min_lat": 52.2, "min_lon": 21.0, "max_lat": 52.21,
                                                        "max_lon": 21.015})
        assert ok.status_code == 200 and ok.json()["box"] == [52.2, 21.0, 52.21, 21.015]
        huge = client.get("/api/parcels/in-bbox", params={"min_lat": 50, "min_lon": 19, "max_lat": 52,
                                                          "max_lon": 21})
        assert huge.status_code == 422
        flipped = client.get("/api/parcels/in-bbox", params={"min_lat": 52.21, "min_lon": 21.0, "max_lat": 52.2,
                                                             "max_lon": 21.015})
        assert flipped.status_code == 422
        monkeypatch.setattr(parcel_grid, "obreby_in_bbox", fake)
        coarse = client.get("/api/parcels/obreby-in-bbox", params={"min_lat": 52.2, "min_lon": 21.0,
                                                                   "max_lat": 52.32, "max_lon": 21.18})
        assert coarse.status_code == 200      # too large for parcels, fine for the obręby grid
        assert client.get("/api/parcels/in-bbox", params={"min_lat": 52.2, "min_lon": 21.0, "max_lat": 52.32,
                                                          "max_lon": 21.18}).status_code == 422
