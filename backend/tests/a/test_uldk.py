"""uldk.py: query parsing and response handling (ULDK mocked with respx; formats from the 2026-11-21 spike)."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.contracts.errors import InvalidParcelQuery, ParcelNotFound, UpstreamUnavailable
from app.geo import uldk

URL = "https://uldk.gugik.gov.pl/"
# Square 100 m x 100 m in EPSG:2180 near Inowrocław (shape made up for the test; format as returned by ULDK)
SQUARE = "SRID=2180;POLYGON((452800 548400,452900 548400,452900 548500,452800 548500,452800 548400))"


def rec(pid: str, region: str = "Jacewo", nr: str = "63/1") -> str:
    return f"{pid}|{SQUARE}|{pid}|kujawsko-pomorskie|powiat inowrocławski|Inowrocław|{region}|{nr}"


# ---------------------------------------------------------------- parse_query
@pytest.mark.parametrize("q", ["141201_1.0001.6509", "060406_2.0136.AR_5.1077/6", " 040704_2.0012.63/1 "])
def test_parse_full_id(q):
    p = uldk.parse_query(q)
    assert p.kind == "id" and p.text == q.strip()


@pytest.mark.parametrize("q,lat,lon", [("52.8,18.3", 52.8, 18.3), ("52.80 , 18.30", 52.8, 18.3), ("50;20", 50.0, 20.0)])
def test_parse_point(q, lat, lon):
    p = uldk.parse_query(q)
    assert (p.kind, p.lat, p.lon) == ("point", lat, lon)


@pytest.mark.parametrize("q", ["Krzewina 134", "Nowa Wieś 1", "Jacewo 63/1", "Krzewina  134a"])
def test_parse_region_number(q):
    assert uldk.parse_query(q).kind == "region_number"


@pytest.mark.parametrize("q", ["", "   ", "134", "Krzewina", "95.0,18.0", "52.8,190", "1412011.0001.6509"])
def test_parse_invalid(q):
    with pytest.raises(InvalidParcelQuery) as exc:
        uldk.parse_query(q)
    assert "identyfikator" in str(exc.value)  # Polish message


# ---------------------------------------------------------------- requests
@pytest.mark.asyncio
@respx.mock
async def test_get_by_id_builds_parcel():
    route = respx.get(URL).mock(return_value=httpx.Response(200, text="0\n" + rec("040704_2.0012.63/1") + "\n"))
    p = await uldk.get_by_id("040704_2.0012.63/1")
    params = route.calls.last.request.url.params
    assert params["request"] == "GetParcelById" and params["srid"] == "2180"
    assert p.parcel_id == "040704_2.0012.63/1"
    assert p.teryt == "040704_2"
    assert (p.region, p.parcel_number, p.commune) == ("Jacewo", "63/1", "Inowrocław")
    assert p.area_ha == pytest.approx(1.0)
    assert p.geometry_wgs84["type"] == "Polygon"
    assert 52.7 < p.centroid_lat < 52.9 and 18.2 < p.centroid_lon < 18.4


@pytest.mark.asyncio
@respx.mock
async def test_get_by_id_not_found():
    # ULDK appends an SQL/XML error text after "-1 brak wyników" for malformed ids (spike)
    respx.get(URL).mock(return_value=httpx.Response(200, text="-1 brak wyników\nbłędny format odpowiedzi XML"))
    with pytest.raises(ParcelNotFound):
        await uldk.get_by_id("999999_9.9999.1")


@pytest.mark.asyncio
@respx.mock
async def test_ambiguous_region_number_returns_all():
    body = "2\n" + rec("040207_5.0013.1", "Nowa Wieś", "1") + "\n" + rec("040809_2.0007.1", "Nowa Wieś", "1") + "\n"
    respx.get(URL).mock(return_value=httpx.Response(200, text=body))
    parcels = await uldk.get_by_id_or_nr("Nowa Wieś 1")
    assert [p.parcel_id for p in parcels] == ["040207_5.0013.1", "040809_2.0007.1"]


@pytest.mark.asyncio
@respx.mock
async def test_region_number_not_found():
    respx.get(URL).mock(return_value=httpx.Response(200, text="-1 brak wyników\n"))
    with pytest.raises(ParcelNotFound):
        await uldk.get_by_id_or_nr("Xyzzyqq 1")


@pytest.mark.asyncio
@respx.mock
async def test_by_xy_axis_order_and_none():
    route = respx.get(URL).mock(return_value=httpx.Response(200, text="-1 brak wyników\n"))
    assert await uldk.get_by_xy(52.8, 18.3) is None
    assert route.calls.last.request.url.params["xy"] == "18.3,52.8,4326"  # lon,lat (spike)


@pytest.mark.asyncio
@respx.mock
async def test_upstream_down_raises_upstream_unavailable(monkeypatch):
    monkeypatch.setattr("asyncio.sleep", _no_sleep)
    respx.get(URL).mock(return_value=httpx.Response(503))
    with pytest.raises(UpstreamUnavailable):
        await uldk.get_by_id("040704_2.0012.63/1")


@pytest.mark.asyncio
@respx.mock
async def test_garbage_response_is_upstream_error():
    respx.get(URL).mock(return_value=httpx.Response(200, text="<html>maintenance</html>"))
    with pytest.raises(UpstreamUnavailable):
        await uldk.get_by_id("040704_2.0012.63/1")


async def _no_sleep(_s):
    return None


@pytest.mark.asyncio
@respx.mock
async def test_one_malformed_answer_is_retried():
    good = ("0\n040704_2.0012.63/1|SRID=2180;POLYGON((452800 548400,452900 548400,452900 548500,452800 548500,"
            "452800 548400))|040704_2|kujawsko-pomorskie|powiat inowrocławski|Inowrocław|Jacewo|63/1\n")
    route = respx.get(URL).mock(side_effect=[httpx.Response(200, text="0\n040704_2.0012.63/1|SRID=2180;POLY"),
                                             httpx.Response(200, text=good)])
    p = await uldk.get_by_id("040704_2.0012.63/1")
    assert p.parcel_id == "040704_2.0012.63/1" and route.call_count == 2
