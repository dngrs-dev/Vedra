"""soil_map.py, soilgrids.py, soil.py (network mocked; recorded payloads from the 2026-11-21 spike)."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.contracts.common import Range, SourceStatus
from app.contracts.geo import SoilLayer
from app.contracts.parcel import Parcel
from app.geo import soil, soil_map, soilgrids, uldk
from app.geo.sources import source

from pathlib import Path

DATA = Path(__file__).parent / "data"

SG_PAYLOAD = json.loads((DATA / "soilgrids_18.55_53.05.json").read_text(encoding="utf-8"))
MAP_URL = source("soil_map")["url"]


def feature_xml(podloze1: str, podloze2: str = "Null", kompleks: str = "1", date: str = "2000-11-01") -> str:
    """Shape of a real FeatureInfoResponse (spike 2026-11-21), fewer attributes."""
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<FeatureInfoResponse xmlns="http://www.esri.com/wms">'
            f'<FIELDS SYS_ID="1" KOMPLEKS="{kompleks}" TYPPODTYP="D" PODLOZE1="{podloze1}" PODLOZE2="{podloze2}" '
            'PODLOZE3="Null" PODLOZE4="Null" PODLOZE5="Null" GATUNEKMADY1="Null" GATUNEKREDZINY1="Null" '
            f'RODZAJGLEBYORGANICZNEJ1="Null" ZRODLO="Mgr5000" AKTUALNOSC_NR="{date}" UWAGI="Null" '
            'Shape="Polygon"></FIELDS></FeatureInfoResponse>')


NO_FEATURE = '<?xml version="1.0" encoding="UTF-8"?><FeatureInfoResponse xmlns="http://www.esri.com/wms"></FeatureInfoResponse>'


@pytest.fixture
def parcel() -> Parcel:
    rec = ("040704_2.0012.63/1|SRID=2180;POLYGON((452800 548400,452900 548400,452900 548500,452800 548500,"
           "452800 548400))|x|kujawsko-pomorskie|powiat inowrocławski|Inowrocław|Jacewo|63/1")
    return uldk.to_parcel(rec.split("|"))


def sg_result(layers=None, live=False):
    return soilgrids.SoilGridsResult(layers if layers is not None else soilgrids.parse_layers(SG_PAYLOAD),
                                     datetime(2026, 11, 21, tzinfo=timezone.utc), live, source("soilgrids_rest")["url"])


# ---------------------------------------------------------------- category tables (Dz.U. 2019 poz. 739)
@pytest.mark.parametrize("codes,cat", [
    (["pl", "plp", "ps", "psp"], "I"),
    (["pgl", "pglp", "pgm", "pgmp"], "II"),
    (["gl", "glp", "płg", "płz", "płp"], "III"),
    (["gs", "gsp", "gc", "gcp", "płi", "i", "ip"], "IV"),
])
def test_category_from_soil_type(codes, cat):
    for c in codes:
        assert soil.category_from_soil_type(c) == cat
        assert soil.category_from_soil_type(c.upper()) == cat


@pytest.mark.parametrize("code", ["li", "l", "c", "bc", "", None])
def test_codes_outside_regulation_have_no_category(code):
    assert soil.category_from_soil_type(code) is None


@pytest.mark.parametrize("mm,cat", [(0, "I"), (127.4, "I"), (127.5, "II"), (169.95, "II"), (170, "III"),
                                    (202.5, "III"), (202.6, "IV")])
def test_category_from_wod(mm, cat):
    assert soil.category_from_wod(mm) == cat


# ---------------------------------------------------------------- SoilGrids
def test_parse_layers_units():
    layers = soilgrids.parse_layers(SG_PAYLOAD)
    assert [(L.top_cm, L.bottom_cm) for L in layers] == [(0, 5), (5, 15), (15, 30), (30, 60), (60, 100), (100, 200)]
    top = layers[0]
    # raw Q0.5 at 0-5 cm: sand 710 g/kg, bdod 122 cg/cm3, wv0033 378, wv1500 76 (recorded payload)
    assert top.sand_pct.mid == pytest.approx(71.0)
    assert top.bulk_density_g_cm3.mid == pytest.approx(1.22)
    assert top.theta_fc.mid == pytest.approx(0.378)
    assert top.theta_wp.mid == pytest.approx(0.076)
    assert top.theta_fc.low <= top.theta_fc.mid <= top.theta_fc.high


def test_wod_mm_hand_computed():
    def L(t, b, fc, wp):
        return SoilLayer(top_cm=t, bottom_cm=b, theta_fc=Range(low=fc - 0.05, mid=fc, high=fc + 0.05),
                         theta_wp=Range(low=wp - 0.02, mid=wp, high=wp + 0.02))
    w = soilgrids.wod_mm([L(0, 50, 0.30, 0.10), L(50, 200, 0.35, 0.15)], depth_cm=100)
    assert w.mid == pytest.approx(0.2 * 500 + 0.2 * 500)          # 200 mm
    assert w.low == pytest.approx(0.17 * 500 + 0.17 * 500)        # fc.low - wp.low (co-monotonic)
    assert w.high == pytest.approx(0.23 * 500 + 0.23 * 500)       # fc.high - wp.high
    assert w.low <= w.mid <= w.high


def test_wod_incomplete_profile_is_none():
    layer = SoilLayer(top_cm=0, bottom_cm=30, theta_fc=Range(mid=0.3), theta_wp=Range(mid=0.1))
    assert soilgrids.wod_mm([layer], depth_cm=100) is None


@pytest.mark.asyncio
async def test_soilgrids_budget_exceeded_continues_in_background(monkeypatch):
    calls = 0

    async def slow_fetch(lat, lon):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.3)
        return {"lat": lat, "lon": lon, "fetched_at": "2026-11-21T00:00:00+00:00", "response": SG_PAYLOAD}

    monkeypatch.setattr(soilgrids, "_fetch_and_cache", slow_fetch)
    monkeypatch.setattr(soilgrids, "_preprocessed", lambda lat, lon: None)
    assert await soilgrids.soil_layers(52.1, 18.1, budget_s=0.05) is None   # budget too short
    res = await soilgrids.soil_layers(52.1, 18.1, budget_s=2.0)              # joins the running request
    assert res is not None and len(res.layers) == 6 and res.live
    assert calls == 1


# ---------------------------------------------------------------- soil map
def test_parse_feature_info():
    hit = soil_map.parse_feature_info(feature_xml("pgl", "gl", kompleks="4"))
    assert hit.texture_layers == ["pgl", "gl"] and hit.primary_code == "pgl"
    assert hit.complex == "4" and hit.currency_date == "2000-11-01"
    assert soil_map.parse_feature_info(NO_FEATURE) is None


@pytest.mark.asyncio
@respx.mock
async def test_dominant_soil_type_majority(parcel):
    answers = iter([feature_xml("pgl")] * 6 + [feature_xml("gl")] * 20)
    respx.get(MAP_URL).mock(side_effect=lambda req: httpx.Response(200, text=next(answers)))
    dom = await soil_map.dominant_soil_type(parcel)
    assert dom.code == "pgl" and dom.points_sampled >= 5
    assert 0 < dom.share < 1


# ---------------------------------------------------------------- soil_info
@pytest.mark.asyncio
@respx.mock
async def test_soil_info_ok_from_map(parcel, monkeypatch):
    respx.get(MAP_URL).mock(return_value=httpx.Response(200, text=feature_xml("pgl", "gl")))

    async def layers(lat, lon, budget_s):
        return sg_result()

    monkeypatch.setattr(soilgrids, "soil_layers", layers)
    res = await soil.soil_info(parcel, budget_s=5)
    assert res.status == SourceStatus.OK
    assert (res.data.kbw_category, res.data.category_source) == ("II", "soil_map")
    assert res.data.soil_type_name_pl == "piasek gliniasty lekki"
    assert len(res.data.layers) == 6 and res.data.wod_mm is not None
    assert {p.source_id for p in res.provenance} == {"soil_map", "soilgrids_rest"}


@pytest.mark.asyncio
@respx.mock
async def test_soil_info_code_outside_regulation_uses_wod(parcel, monkeypatch):
    respx.get(MAP_URL).mock(return_value=httpx.Response(200, text=feature_xml("li")))

    async def layers(lat, lon, budget_s):
        return sg_result()

    monkeypatch.setattr(soilgrids, "soil_layers", layers)
    res = await soil.soil_info(parcel, budget_s=5)
    assert res.data.category_source == "soilgrids_wod"
    assert res.data.kbw_category == soil.category_from_wod(res.data.wod_mm.mid)
    assert any("WOD" in n for n in res.notes_pl)


@pytest.mark.asyncio
@respx.mock
async def test_soil_info_soilgrids_late_is_partial(parcel, monkeypatch):
    respx.get(MAP_URL).mock(return_value=httpx.Response(200, text=feature_xml("ps")))

    async def layers(lat, lon, budget_s):
        return None

    monkeypatch.setattr(soilgrids, "soil_layers", layers)
    res = await soil.soil_info(parcel, budget_s=5)
    assert res.status == SourceStatus.PARTIAL and res.data.kbw_category == "I" and res.data.layers == []
    assert any("w tle" in n for n in res.notes_pl)


@pytest.mark.asyncio
@respx.mock
async def test_soil_info_everything_down_is_missing(parcel, monkeypatch):
    monkeypatch.setattr("asyncio.sleep", _no_sleep)
    respx.get(MAP_URL).mock(return_value=httpx.Response(500))

    async def layers(lat, lon, budget_s):
        raise RuntimeError("504")

    monkeypatch.setattr(soilgrids, "soil_layers", layers)
    res = await soil.soil_info(parcel, budget_s=5)
    assert res.status == SourceStatus.MISSING and res.data is None
    assert res.error and res.notes_pl


async def _no_sleep(_s):
    return None
