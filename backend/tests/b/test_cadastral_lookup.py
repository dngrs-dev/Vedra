from unittest.mock import AsyncMock

import httpx
import pytest

from app.api import cadastral
from app.contracts.errors import UpstreamUnavailable
from app.fakes.fake_geo import FakeGeoProvider

# Identifier and WGS84 point used to verify the national EGiB WFS on 2026-11-21.
PARCEL_ID = "142513_2.0024.15/2"
POINT = (51.450377, 21.053372)


@pytest.fixture(autouse=True)
def cache_only_in_test(monkeypatch):
    entries = {}
    monkeypatch.setattr(cadastral.cache, "get", entries.get)
    monkeypatch.setattr(cadastral.cache, "set", lambda key, value, *, expire_s: entries.__setitem__(key, value))


@pytest.mark.asyncio
async def test_wfs_click_geometry_is_reused_when_analysis_resolves_its_id(monkeypatch):
    # Small synthetic polygon around the actual test point, in GeoJSON longitude/latitude order.
    geometry = {"type": "Polygon", "coordinates": [[
        [21.05, 51.45], [21.06, 51.45], [21.06, 51.46], [21.05, 51.46], [21.05, 51.45],
    ]]}
    feature = {"properties": {"ID_DZIALKI": PARCEL_ID, "NAZWA_GMINY": "ZAKRZEW"}, "geometry": geometry}
    remote = AsyncMock(return_value=httpx.Response(200, json={
        "type": "FeatureCollection", "features": [feature],
    }))
    monkeypatch.setattr(cadastral.http, "get", remote)
    legacy = AsyncMock(spec=FakeGeoProvider)
    provider = cadastral.CadastralProvider(legacy)

    selected = await provider.parcel_at_point(*POINT)
    assert selected.parcel_id == PARCEL_ID
    assert selected.county == "powiat radomski"
    assert selected.voivodeship == "mazowieckie"
    assert selected.area_ha > 0
    assert selected.geometry_2180_wkt.startswith("POLYGON")
    assert await provider.parcel_at_point(*POINT) == selected
    assert await provider.find_parcels(PARCEL_ID) == [selected]
    assert remote.call_args.args == (cadastral.WFS_URL,)
    assert remote.call_args.kwargs["params"]["bbox"].endswith(cadastral.CRS_4326)
    remote.assert_awaited_once()
    legacy.find_parcels.assert_not_awaited()
    legacy.parcel_at_point.assert_not_awaited()


@pytest.mark.asyncio
async def test_wfs_unavailability_keeps_existing_provider_as_fallback(monkeypatch):
    monkeypatch.setattr(cadastral.http, "get", AsyncMock(side_effect=UpstreamUnavailable("Simulated WFS outage")))
    legacy = FakeGeoProvider()
    provider = cadastral.CadastralProvider(legacy)
    expected = await legacy.find_parcels(PARCEL_ID)

    assert await provider.find_parcels(PARCEL_ID) == expected
    assert await provider.parcel_at_point(*POINT) == await legacy.parcel_at_point(*POINT)
