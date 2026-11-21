"""RealGeoProvider: query routing, collect() never raises, deadline respected (network mocked)."""
from __future__ import annotations

import asyncio
import time
from datetime import date

import pytest

from app.contracts.common import SourceResult, SourceStatus
from app.contracts.errors import InvalidParcelQuery, ParcelNotFound
from app.contracts.geo import GeoBundle, GeoRequest, SoilInfo
from app.geo import provider as provider_mod
from app.geo import soil, uldk
from app.geo.provider import RealGeoProvider

REC = ("040704_2.0012.63/1|SRID=2180;POLYGON((452800 548400,452900 548400,452900 548500,452800 548500,"
       "452800 548400))|x|kujawsko-pomorskie|powiat inowrocławski|Inowrocław|Jacewo|63/1").split("|")


@pytest.fixture
def parcel():
    return uldk.to_parcel(REC)


@pytest.fixture(autouse=True)
def _offline_sources(monkeypatch):
    """collect() must not touch the network in these tests: stub every implemented non-soil source."""
    from app.geo import vegetation

    async def veg(p, req, budget):
        return SourceResult(status=SourceStatus.MISSING, notes_pl=["stub"])

    monkeypatch.setattr(vegetation, "vegetation_data", veg)
    from app.geo import edo, imgw

    async def edo_stub(lat, lon, d):
        return SourceResult(status=SourceStatus.MISSING, notes_pl=["stub"])

    async def imgw_stub(p, d):
        return SourceResult(status=SourceStatus.MISSING, notes_pl=["stub"])

    monkeypatch.setattr(edo, "edo_signal", edo_stub)
    monkeypatch.setattr(imgw, "imgw_context", imgw_stub)
    from app.geo import hydro, landcover

    async def two_arg_stub(p, buffer_m):
        return SourceResult(status=SourceStatus.MISSING, notes_pl=["stub"])

    monkeypatch.setattr(hydro, "water_features", two_arg_stub)
    monkeypatch.setattr(landcover, "landcover", two_arg_stub)


@pytest.mark.asyncio
async def test_find_parcels_routes_query_types(monkeypatch, parcel):
    seen = []

    async def by_id(pid):
        seen.append(("id", pid)); return parcel

    async def by_nr(text):
        seen.append(("nr", text)); return [parcel, parcel]

    async def by_xy(lat, lon):
        seen.append(("xy", lat, lon)); return None

    monkeypatch.setattr(uldk, "get_by_id", by_id)
    monkeypatch.setattr(uldk, "get_by_id_or_nr", by_nr)
    monkeypatch.setattr(uldk, "get_by_xy", by_xy)
    p = RealGeoProvider()
    assert len(await p.find_parcels("040704_2.0012.63/1")) == 1
    assert len(await p.find_parcels("Nowa Wieś 1")) == 2
    with pytest.raises(ParcelNotFound):
        await p.find_parcels("52.8, 18.3")
    with pytest.raises(InvalidParcelQuery):
        await p.find_parcels("???")
    assert seen == [("id", "040704_2.0012.63/1"), ("nr", "Nowa Wieś 1"), ("xy", 52.8, 18.3)]


@pytest.mark.asyncio
async def test_parcel_at_point_validates_bounds():
    with pytest.raises(InvalidParcelQuery):
        await RealGeoProvider().parcel_at_point(91, 18)


@pytest.mark.asyncio
async def test_collect_never_raises(monkeypatch, parcel):
    async def boom(p, budget):
        raise RuntimeError("network down")

    monkeypatch.setattr(soil, "soil_info", boom)
    b = await RealGeoProvider().collect(GeoRequest(parcel=parcel, analysis_date=date(2023, 5, 31)))
    assert isinstance(b, GeoBundle)
    assert b.soil.status == SourceStatus.MISSING and "network down" in b.soil.error and b.soil.notes_pl
    for name in GeoBundle.model_fields:
        res = getattr(b, name)
        assert res.notes_pl, name                      # every non-ok source explains itself in Polish
        assert res.elapsed_s is not None, name


@pytest.mark.asyncio
async def test_collect_respects_deadline(monkeypatch, parcel):
    async def slow(p, budget):
        await asyncio.sleep(10)

    monkeypatch.setattr(soil, "soil_info", slow)
    t = time.monotonic()
    b = await RealGeoProvider().collect(GeoRequest(parcel=parcel, analysis_date=date(2023, 5, 31), deadline_s=0.5))
    assert time.monotonic() - t < 0.5 + 0.5          # CONTRACTS.md: deadline + 0.5 s
    assert b.soil.status == SourceStatus.MISSING and "deadline" in b.soil.error


@pytest.mark.asyncio
async def test_collect_passes_budget_below_deadline(monkeypatch, parcel):
    got = {}

    async def fake(p, budget):
        got["budget"] = budget
        return SourceResult[SoilInfo](status=SourceStatus.OK, data=SoilInfo(kbw_category="II"))

    monkeypatch.setattr(soil, "soil_info", fake)
    b = await RealGeoProvider().collect(GeoRequest(parcel=parcel, analysis_date=date(2023, 5, 31), deadline_s=5))
    assert b.soil.data.kbw_category == "II"
    assert got["budget"] <= 5 - provider_mod._INNER_MARGIN_S + 0.01
