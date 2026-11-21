"""hydro.py and landcover.py (network mocked; payload shapes from the CP3 probe 2026-11-21)."""
from __future__ import annotations

import io
from collections import Counter
from datetime import date

import httpx
import numpy as np
import pytest
import respx

from app.contracts.common import SourceStatus
from app.geo import geometry, hydro, landcover, uldk
from app.geo.sources import source

# 100 m x 100 m parcel in EPSG:2180
REC = ("040704_2.0012.63/1|SRID=2180;POLYGON((452800 548400,452900 548400,452900 548500,452800 548500,"
       "452800 548400))|x|kujawsko-pomorskie|powiat inowrocławski|Inowrocław|Jacewo|63/1").split("|")
BDOT = source("bdot10k_water")["url"]


@pytest.fixture
def parcel():
    return uldk.to_parcel(REC)


def png(mask: np.ndarray) -> bytes:
    import matplotlib.image as mpimg

    rgba = np.zeros(mask.shape + (4,), "float32")
    rgba[mask] = (0, 0, 1, 1)
    buf = io.BytesIO()
    mpimg.imsave(buf, rgba, format="png")
    return buf.getvalue()


def feature_info(x_kod: str, rodzaj: str = "Null", nazwa: str = "Null") -> str:
    return ('<?xml version="1.0" encoding="UTF-8"?><FeatureInfoResponse xmlns="http://www.esri.com/wms">'
            f'<FIELDS OBJECTID="1" x_kod="{x_kod}" rodzaj="{rodzaj}" nazwa="{nazwa}" Shape="Polyline"></FIELDS>'
            '</FeatureInfoResponse>')


# ---------------------------------------------------------------- components
def test_components_two_blobs_with_coordinates():
    mask = np.zeros((10, 10), bool)
    mask[1, 1:4] = True          # blob 1
    mask[7:9, 7:9] = True        # blob 2
    comps = hydro.components(mask, (1000.0, 2000.0, 1020.0, 2020.0), 2.0)
    assert len(comps) == 2
    b = sorted(c.bounds for c, _ in comps)
    assert b[0] == (1002.0, 2016.0, 1008.0, 2018.0)          # row 1 -> y 2016..2018, cols 1..3 -> x 1002..1008


# ---------------------------------------------------------------- BDOT10k path
def _bdot_router(layer_masks: dict[str, np.ndarray], infos: dict[str, str]):
    def handler(request: httpx.Request) -> httpx.Response:
        q = request.url.params
        layer = q["LAYERS"]
        if q["REQUEST"] == "GetMap":
            w, h = int(q["WIDTH"]), int(q["HEIGHT"])
            m = layer_masks.get(layer)
            mask = np.zeros((h, w), bool) if m is None else m(h, w)
            return httpx.Response(200, content=png(mask), headers={"content-type": "image/png"})
        return httpx.Response(200, text=infos.get(layer, "<FeatureInfoResponse/>"))
    return handler


@pytest.mark.asyncio
@respx.mock
async def test_bdot_ditch_crossing_and_pond(parcel):
    def ditch(h, w):              # vertical line through the image centre -> crosses the parcel
        m = np.zeros((h, w), bool)
        m[:, w // 2] = True
        return m

    def pond(h, w):               # small blob near the top edge of the 500 m buffer, beside the ditch
        m = np.zeros((h, w), bool)    # (image corners are outside the rounded buffer and are dropped)
        m[20:30, w // 2 + 20:w // 2 + 30] = True
        return m

    respx.get(BDOT).mock(side_effect=_bdot_router(
        {"row": ditch, "WPow": pond},
        {"row": feature_info("SWRM02"), "WPow": feature_info("PTWP03", rodzaj="wody stojące", nazwa="Staw X")}))
    res = await hydro.water_features(parcel, 500)
    d = res.data
    assert res.status == SourceStatus.OK and res.provenance[0].source_id == "bdot10k_water"
    kinds = {f.kind: f for f in d.features}
    assert kinds["ditch"].touches_parcel and kinds["ditch"].distance_m == 0.0
    assert kinds["pond"].name == "Staw X" and kinds["pond"].distance_m > 300
    assert d.ditches_crossing_boundary == 1 and d.nearest_water_m == 0.0
    assert all(f.source_id == "bdot10k" for f in d.features)


@pytest.mark.asyncio
@respx.mock
async def test_bdot_nothing_found_is_ok_with_note(parcel):
    respx.get(BDOT).mock(side_effect=_bdot_router({}, {}))
    res = await hydro.water_features(parcel, 500)
    assert res.status == SourceStatus.OK and res.data.features == [] and res.data.nearest_water_m is None
    assert any("nie znaleziono" in n for n in res.notes_pl)


# ---------------------------------------------------------------- OSM fallback
def _osm_payload(parcel) -> dict:
    g = geometry.parcel_geom_2180(parcel)
    lon0, lat0 = geometry.to_4326(g).centroid.x, geometry.to_4326(g).centroid.y
    return {"elements": [
        {"type": "way", "tags": {"waterway": "ditch"},
         "geometry": [{"lat": lat0 - 0.002, "lon": lon0}, {"lat": lat0 + 0.002, "lon": lon0}]},
        {"type": "way", "tags": {"natural": "water", "water": "pond", "name": "Staw"},
         "geometry": [{"lat": lat0 + 0.003, "lon": lon0 + 0.003}, {"lat": lat0 + 0.003, "lon": lon0 + 0.0035},
                      {"lat": lat0 + 0.0035, "lon": lon0 + 0.0035}, {"lat": lat0 + 0.003, "lon": lon0 + 0.003}]},
    ]}


def test_osm_payload_to_features(parcel):
    feats = hydro.osm_features_from_payload(_osm_payload(parcel), geometry.parcel_geom_2180(parcel), 500)
    assert [f.kind for f in feats] == ["ditch", "pond"]
    assert feats[0].touches_parcel and feats[1].name == "Staw" and feats[1].distance_m > 100
    assert {f.source_id for f in feats} == {"osm"}


@pytest.mark.asyncio
@respx.mock
async def test_fallback_to_osm_when_bdot_fails(parcel, monkeypatch):
    monkeypatch.setattr("asyncio.sleep", _no_sleep)
    respx.get(BDOT).mock(return_value=httpx.Response(503))
    respx.get(source("overpass")["url"]).mock(return_value=httpx.Response(200, json=_osm_payload(parcel)))
    res = await hydro.water_features(parcel, 500)
    assert res.status == SourceStatus.PARTIAL and res.provenance[0].source_id == "overpass"
    assert res.data.ditches_crossing_boundary == 1 and "bdot10k" in res.error


@pytest.mark.asyncio
@respx.mock
async def test_both_down_is_missing_and_never_claims_no_water(parcel, monkeypatch):
    monkeypatch.setattr("asyncio.sleep", _no_sleep)
    respx.get(BDOT).mock(return_value=httpx.Response(503))
    for url in [source("overpass")["url"], *source("overpass")["mirrors"]]:
        respx.get(url).mock(return_value=httpx.Response(504))
    res = await hydro.water_features(parcel, 500)
    assert res.status == SourceStatus.MISSING and res.data is None
    assert "nie oznacza to braku wód" in res.notes_pl[0]


async def _no_sleep(_s):
    return None


# ---------------------------------------------------------------- land cover
# legend tag exactly as embedded in ESA_WorldCover_10m_2021_v200_N51E018_Map.tif (read 2026-11-21)
LEGEND_TAG = ("10  Tree cover\n20  Shrubland\n30  Grassland\n40  Cropland\n50  Built-up\n60  Bare/sparse vegetation\n"
              "70  Snow and ice\n80  Permanent water bodies\n90  Herbaceous wetland\n95  Mangroves\n100  Moss and lichen")


def test_parse_legend():
    leg = landcover.parse_legend(LEGEND_TAG)
    assert leg[40] == "Cropland" and leg[60] == "Bare/sparse vegetation" and leg[100] == "Moss and lichen"
    assert len(leg) == 11


@pytest.mark.parametrize("bounds,tiles", [
    ((18.29, 52.79, 18.31, 52.81), ["N51E018"]),
    ((20.99, 53.99, 21.01, 54.01), ["N51E018", "N51E021", "N54E018", "N54E021"]),
])
def test_tiles_for(bounds, tiles):
    assert sorted(landcover.tiles_for(bounds)) == tiles


@pytest.mark.asyncio
async def test_landcover_sums_tiles_and_drops_zero_shares(parcel, monkeypatch):
    leg = landcover.parse_legend(LEGEND_TAG)

    def counts(href, zone, par):
        return Counter({40: 90, 30: 10}), Counter({40: 50, 10: 49, 60: 1, 80: 0}), leg

    monkeypatch.setattr(landcover, "_counts", counts)
    monkeypatch.setattr(landcover, "tiles_for", lambda b: ["N51E018", "N51E021"])
    res = await landcover.landcover(parcel, 500)
    d = res.data
    assert d.dataset == "ESA WorldCover 2021 v200" and d.buffer_m == 500
    assert d.shares_parcel == {"Cropland": 0.9, "Grassland": 0.1}
    assert d.shares_buffer == {"Cropland": 0.5, "Tree cover": 0.49, "Bare/sparse vegetation": 0.01}
    assert res.status == SourceStatus.OK and res.provenance[0].data_period == "2021"


@pytest.mark.asyncio
async def test_landcover_requires_the_end_of_the_observation_year(parcel, monkeypatch):
    leg = landcover.parse_legend(LEGEND_TAG)
    reads = []

    def counts(href, zone, par):
        reads.append(href)
        return Counter({40: 1}), Counter({40: 1}), leg

    monkeypatch.setattr(landcover, "_counts", counts)
    monkeypatch.setattr(landcover, "tiles_for", lambda b: ["N51E018"])
    old = await landcover.landcover(parcel, 500, date(2021, 12, 30))
    assert old.status == SourceStatus.MISSING and old.data is None
    assert "2021-12-31" in old.notes_pl[0] and not reads
    covered = await landcover.landcover(parcel, 500, date(2021, 12, 31))
    assert covered.status == SourceStatus.OK and len(reads) == 1
