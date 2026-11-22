import sqlite3
from contextlib import closing
from unittest.mock import AsyncMock

import httpx
import pytest
from shapely import from_wkt

from app.api import cadastral, egib_snapshot
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


@pytest.mark.asyncio
async def test_local_snapshot_resolves_by_point_and_id_without_network(monkeypatch, tmp_path):
    path = tmp_path / "egib.sqlite"
    source = FakeGeoProvider()
    (parcel,) = await source.find_parcels(PARCEL_ID)
    polygon = from_wkt(parcel.geometry_2180_wkt)
    min_x, min_y, max_x, max_y = polygon.bounds
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript(egib_snapshot.SCHEMA)
        row = (PARCEL_ID, parcel.commune, parcel.region, parcel.parcel_number, polygon.wkb)
        ident = db.execute("INSERT INTO parcels VALUES (NULL, ?, ?, ?, ?, ?)", row).lastrowid
        db.execute("INSERT INTO parcel_bounds VALUES (?, ?, ?, ?, ?)", (ident, min_x, max_x, min_y, max_y))

    remote = AsyncMock(side_effect=AssertionError("A covered parcel should be resolved locally"))
    monkeypatch.setattr(cadastral.http, "get", remote)
    legacy = AsyncMock(spec=FakeGeoProvider)
    provider = cadastral.CadastralProvider(legacy, snapshot_path=path)
    selected = await provider.parcel_at_point(parcel.centroid_lat, parcel.centroid_lon)

    assert selected is not None
    assert selected.parcel_id == PARCEL_ID
    assert selected.geometry_2180_wkt == parcel.geometry_2180_wkt
    assert await provider.find_parcels(PARCEL_ID) == [selected]
    remote.assert_not_awaited()
    legacy.find_parcels.assert_not_awaited()
    legacy.parcel_at_point.assert_not_awaited()


@pytest.mark.asyncio
async def test_local_snapshot_miss_preserves_live_fallback(monkeypatch, tmp_path):
    path = tmp_path / "egib.sqlite"
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript(egib_snapshot.SCHEMA)
        # No regional export has been installed for the requested TERYT.
    remote = AsyncMock(side_effect=UpstreamUnavailable("Simulated WFS outage"))
    monkeypatch.setattr(cadastral.http, "get", remote)
    legacy = FakeGeoProvider()
    provider = cadastral.CadastralProvider(legacy, snapshot_path=path)

    assert await provider.find_parcels(PARCEL_ID) == await legacy.find_parcels(PARCEL_ID)
    assert await provider.parcel_at_point(*POINT) == await legacy.parcel_at_point(*POINT)
    assert remote.await_count == 2
