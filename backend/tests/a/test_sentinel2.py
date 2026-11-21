"""sentinel2.py: offset handling, masking, de-duplication, no scene after the analysis date."""
from __future__ import annotations

import json
from datetime import date

import httpx
import numpy as np
import pytest
import respx

from app.geo import sentinel2
from app.geo.sentinel2 import BandInfo, SceneRef
from app.geo.sources import source

# raster:bands exactly as returned by Earth Search for B04 (CP2 probe 2026-11-21), collection sentinel-2-l2a
PRE_2022 = {"href": "https://sentinel-cogs.s3.us-west-2.amazonaws.com/x/B04.tif",      # S2A_34UCD_20180715_0_L2A, PB 02.08
            "raster:bands": [{"nodata": 0, "data_type": "uint16", "bits_per_sample": 15, "spatial_resolution": 10,
                              "scale": 0.0001, "offset": 0}]}
POST_2022 = {"href": "https://sentinel-cogs.s3.us-west-2.amazonaws.com/y/B04.tif",     # S2A_33UYU_20220714_0_L2A, PB 04.00
             "raster:bands": [{"nodata": 0, "data_type": "uint16", "bits_per_sample": 15, "spatial_resolution": 10,
                               "scale": 0.0001, "offset": -0.1}]}


def scene(offset: float, sid="S2A_TEST", acquired=date(2023, 5, 30), sensing="2023-05-30T10:06:03Z",
          baseline="05.00", platform="sentinel-2a") -> SceneRef:
    b = BandInfo(href="https://sentinel-cogs.s3.us-west-2.amazonaws.com/x.tif", scale=0.0001, offset=offset, nodata=0)
    return SceneRef(scene_id=sid, acquired=acquired, sensing=sensing, platform=platform, cloud_cover=1.0,
                    baseline=baseline, collection="sentinel-2-l2a", bands={k: b for k in sentinel2.BANDS})


C1_2023 = {"href": "https://e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com/z/B04.tif",  # PB 05.09
           "raster:bands": [{"nodata": 0, "data_type": "uint16", "spatial_resolution": 10,
                             "scale": 0.0001, "offset": -0.1}]}


def test_offset_per_collection_pre_and_post_2022():
    # sentinel-2-l2a pixels are harmonized (no +1000 DN) for every baseline -> declared offset ignored
    assert sentinel2.band_info(PRE_2022, "sentinel-2-l2a").offset == 0.0
    assert sentinel2.band_info(POST_2022, "sentinel-2-l2a").offset == 0.0
    # sentinel-2-c1-l2a keeps the PB 04.00 offset -> the item's raster:bands offset is used
    c1 = sentinel2.band_info(C1_2023, "sentinel-2-c1-l2a")
    assert c1.offset == pytest.approx(-0.1) and c1.scale == pytest.approx(0.0001) and c1.nodata == 0


def test_same_acquisition_same_ndvi_in_both_collections():
    """2023-05-10 tile 33UXU, parcel 303005_5.0323.25/7: median DNs measured on 2026-11-21 in both collections."""
    shape = (3, 3)
    inside, scl = np.ones(shape, bool), np.full(shape, 4, "uint8")
    old = scene(sentinel2.band_info(POST_2022, "sentinel-2-l2a").offset)
    c1 = scene(sentinel2.band_info(C1_2023, "sentinel-2-c1-l2a").offset)
    o, _ = sentinel2.stats_from_arrays(old, np.full(shape, 284, "uint16"), np.full(shape, 4584, "uint16"),
                                       np.full(shape, 4584, "uint16"), np.full(shape, 2000, "uint16"), scl, inside)
    n, _ = sentinel2.stats_from_arrays(c1, np.full(shape, 1284, "uint16"), np.full(shape, 5584, "uint16"),
                                       np.full(shape, 5584, "uint16"), np.full(shape, 3000, "uint16"), scl, inside)
    assert o.ndvi_median == pytest.approx(n.ndvi_median, abs=1e-4)
    assert o.ndmi_median == pytest.approx(n.ndmi_median, abs=1e-4)
    assert -1 <= o.ndvi_median <= 1 and o.ndvi_median == pytest.approx((0.4584 - 0.0284) / (0.4584 + 0.0284), abs=1e-4)


@pytest.mark.parametrize("offset,expected_ndvi", [
    (0.0, (0.41 - 0.11) / (0.41 + 0.11)),     # harmonized: reflectance = DN * 1e-4
    (-0.1, (0.31 - 0.01) / (0.31 + 0.01)),    # with BOA offset: reflectance = DN * 1e-4 - 0.1
])
def test_offset_changes_ndvi(offset, expected_ndvi):
    shape = (4, 4)
    red, nir = np.full(shape, 1100, "uint16"), np.full(shape, 4100, "uint16")
    b8a, b11 = np.full(shape, 4100, "uint16"), np.full(shape, 2100, "uint16")
    scl = np.full(shape, 4, "uint8")
    stat, n = sentinel2.stats_from_arrays(scene(offset), red, nir, b8a, b11, scl, np.ones(shape, bool))
    assert n == 16 and stat.valid_pixels == 16 and stat.valid_fraction == 1.0
    assert stat.ndvi_median == pytest.approx(expected_ndvi, abs=1e-4)


def test_masks_clouds_nodata_and_outside():
    shape = (4, 4)
    red, nir = np.full(shape, 1100, "uint16"), np.full(shape, 4100, "uint16")
    scl = np.full(shape, 4, "uint8")
    scl[0, :] = 9            # cloud high probability -> excluded (only SCL 4/5 kept)
    red[1, 0] = 0            # nodata -> excluded
    inside = np.ones(shape, bool)
    inside[3, :] = False     # outside the parcel interior
    stat, n = sentinel2.stats_from_arrays(scene(-0.1), red, nir, nir, red, scl, inside)
    assert n == 12
    assert stat.valid_pixels == 12 - 4 - 1


def test_mostly_cloudy_scene_is_none():
    shape = (10, 10)
    scl = np.full(shape, 9, "uint8")
    scl[0, :2] = 4           # 2 % clear < valid_fraction_min
    arr = np.full(shape, 2000, "uint16")
    stat, n = sentinel2.stats_from_arrays(scene(-0.1), arr, arr, arr, arr, scl, np.ones(shape, bool))
    assert stat is None and n == 100


def test_dedupe_keeps_one_per_acquisition():
    a0 = scene(0, sid="S2B_33UYU_20210714_0_L2A", baseline="03.00", sensing="2021-07-14T10:00:28Z")
    a1 = scene(-0.1, sid="S2B_33UYU_20210714_1_L2A", baseline="05.00", sensing="2021-07-14T10:00:28Z")
    other_tile = scene(-0.1, sid="S2B_34UCD_20210714_1_L2A", baseline="05.00", sensing="2021-07-14T10:00:28Z")
    later = scene(-0.1, sid="S2A_33UYU_20210716_0_L2A", sensing="2021-07-16T10:00:00Z")
    out = sentinel2.dedupe([a0, a1, other_tile, later])
    assert [s.scene_id for s in out] == ["S2A_33UYU_20210716_0_L2A", "S2B_34UCD_20210714_1_L2A"]


def test_dedupe_by_datatake_across_tiles_with_different_seconds():
    """Real case 2026-11-05: same datatake on two tiles, datetimes 10:06:00.323 and 10:05:59.384."""
    a = scene(0, sid="S2B_33UYU_20261105_0_L2A", sensing="2026-11-05T10:06:00.323000Z", baseline="05.13")
    b = scene(0, sid="S2B_34UCD_20261105_0_L2A", sensing="2026-11-05T10:05:59.384000Z", baseline="05.13")
    a = SceneRef(**{**a.__dict__, "datatake": "GS2B_20261105T100209_050484"})
    b = SceneRef(**{**b.__dict__, "datatake": "GS2B_20261105T100209_050484"})
    assert len(sentinel2.dedupe([a, b])) == 1


def test_scene_from_item_reads_datatake_without_baseline():
    item = _item("S2B_33UYU_20261105_0_L2A", "2026-11-05T10:06:00.323000Z")
    item["properties"]["s2:datatake_id"] = "GS2B_20261105T100209_050484_N05.13"
    assert sentinel2.scene_from_item(item, "sentinel-2-l2a").datatake == "GS2B_20261105T100209_050484"


def _item(sid: str, dt: str) -> dict:
    keys = source("earth_search")["assets"]
    return {"id": sid, "properties": {"datetime": dt, "platform": "sentinel-2a", "eo:cloud_cover": 5.0,
                                      "s2:processing_baseline": "05.00"},
            "assets": {keys[b]: POST_2022 for b in sentinel2.BANDS}}


async def _no_sleep(_s):
    return None


@pytest.mark.asyncio
@respx.mock
async def test_search_never_returns_scene_after_analysis_date(monkeypatch):
    """Planetary Computer down -> Earth Search fallback; the request and the result are clipped to the date."""
    monkeypatch.setattr("asyncio.sleep", _no_sleep)
    respx.get(source("planetary_computer")["url"] + "/search").mock(return_value=httpx.Response(503))
    url = source("earth_search")["url"] + "/search"
    items = [_item("S2A_after", "2023-06-02T10:00:00Z"), _item("S2A_same_day", "2023-05-31T10:00:00Z"),
             _item("S2A_before", "2023-05-20T10:00:00Z")]
    route = respx.get(url).mock(return_value=httpx.Response(200, json={"features": items, "links": []}))
    out = await sentinel2.search_scenes((18.0, 52.0, 18.1, 52.1), date(2023, 5, 1), date(2023, 6, 30),
                                        not_after=date(2023, 5, 31))
    assert {s.scene_id for s in out} == {"S2A_same_day", "S2A_before"}
    params = route.calls.last.request.url.params
    assert params["datetime"].endswith("2023-05-31T23:59:59Z")          # request itself is clipped
    assert json.loads(params["query"]) == {"eo:cloud_cover": {"lt": 60}}


@pytest.mark.asyncio
async def test_search_window_entirely_after_date_is_empty():
    assert await sentinel2.search_scenes((18, 52, 18.1, 52.1), date(2023, 6, 1), date(2023, 6, 30),
                                         not_after=date(2023, 5, 31)) == []


# Planetary Computer items as returned 2026-11-21 (no raster:bands; baseline decides the offset)
def _pc_item(sid: str, dt: str, baseline: str, datatake: str) -> dict:
    href = "https://sentinel2l2a01.blob.core.windows.net/sentinel2-l2/34/U/CD/x/" + sid
    return {"id": sid, "properties": {"datetime": dt, "platform": "Sentinel-2A", "eo:cloud_cover": 1.0,
                                      "s2:processing_baseline": baseline, "s2:datatake_id": datatake},
            "assets": {b: {"href": f"{href}_{b}.tif"} for b in sentinel2.BANDS}}


@pytest.mark.asyncio
@respx.mock
async def test_planetary_computer_offset_by_baseline_dedupe_and_signing():
    pc = source("planetary_computer")
    items = [
        _pc_item("S2A_MSIL2A_20220731T095041_R079_T34UCD_20240717T075305", "2022-07-31T09:50:41Z", "05.10",
                 "GS2A_20220731T095041_037113_N05.10"),
        _pc_item("S2A_MSIL2A_20220731T095041_R079_T34UCD_20220801T095553", "2022-07-31T09:50:41Z", "04.00",
                 "GS2A_20220731T095041_037113_N04.00"),
        _pc_item("S2A_MSIL2A_20170730T100031_R122_T34UCD_20210210T164236", "2017-07-30T10:00:31Z", "02.12",
                 "GS2A_20170730T100031_011010_N02.12"),
    ]
    respx.get(pc["url"] + "/search").mock(return_value=httpx.Response(200, json={"features": items, "links": []}))
    tok = respx.get(pc["token_url"]).mock(return_value=httpx.Response(
        200, json={"token": "st=x&sig=y", "msft:expiry": "2099-01-01T00:00:00Z"}))
    out = await sentinel2.search_scenes((18.0, 52.0, 18.1, 52.1), date(2016, 1, 1), date(2022, 12, 31),
                                        not_after=date(2022, 12, 31))
    assert [s.scene_id for s in out] == [items[0]["id"], items[2]["id"]]     # reprocessed PB 05.10 kept
    new, old = out
    assert new.provider == old.provider == "planetary_computer"
    assert new.bands["B04"].offset == -0.1 and old.bands["B04"].offset == 0.0   # MTD_MSIL2A.xml BOA_ADD_OFFSET
    assert new.bands["B04"].scale == 0.0001 and new.bands["SCL"].nodata == 0
    assert sentinel2.signed_href(new, "B04").endswith("_B04.tif?st=x&sig=y")
    await sentinel2.pc_token()
    assert tok.call_count == 1                                                  # token cached until expiry
    from app.geo import raster_io
    assert raster_io.check_host(sentinel2.signed_href(new, "SCL")).startswith("/vsicurl/https://sentinel2l2a01")


def test_same_reflectance_from_both_baselines():
    """PB 04.00+ DN carry +1000: DN 1284 (offset) and 284 (no offset) are the same red reflectance."""
    a = sentinel2.band_info({"href": "h"}, "sentinel-2-l2a", "planetary_computer", "05.09")
    b = sentinel2.band_info({"href": "h"}, "sentinel-2-l2a", "planetary_computer", "03.00")
    assert np.isclose(sentinel2.reflectance(np.array([1284]), a), sentinel2.reflectance(np.array([284]), b)).all()
