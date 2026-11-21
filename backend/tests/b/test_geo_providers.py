import json
from datetime import date, timedelta
from struct import unpack

import pytest

from app.api.deps import get_geo_provider
from app.config import settings
from app.contracts.common import SourceStatus
from app.contracts.errors import InvalidParcelQuery, ParcelNotFound
from app.contracts.geo import GeoBundle, GeoRequest
from app.fakes.fake_geo import EXAMPLE_PARCEL_ID, FakeGeoProvider
from app.fakes.fixture_geo import FixtureGeoProvider
from app.recommendations.texts_pl import FAKE_GEO_NOTE, GEO_FIXTURE_UNAVAILABLE

# Example historical analysis date from docs/TEAM_SPLIT.md §7.
ANALYSIS_DATE = date(2023, 5, 31)


def test_geo_provider_selection(monkeypatch):
    monkeypatch.setattr(settings, "geo_provider", "fake")
    assert isinstance(get_geo_provider(), FakeGeoProvider)
    monkeypatch.setattr(settings, "geo_provider", "fixtures")
    assert isinstance(get_geo_provider(), FixtureGeoProvider)


@pytest.mark.asyncio
async def test_fake_source_statuses_and_provenance():
    provider = FakeGeoProvider()
    parcel, = await provider.find_parcels(EXAMPLE_PARCEL_ID)
    bundle = await provider.collect(GeoRequest(parcel=parcel, analysis_date=ANALYSIS_DATE))
    results = [getattr(bundle, field) for field in GeoBundle.model_fields]

    assert {result.status for result in results} == set(SourceStatus)
    assert all(result.notes_pl == [FAKE_GEO_NOTE] for result in results)
    assert all(result.provenance and not result.provenance[0].live for result in results if result.data)


@pytest.mark.asyncio
async def test_fake_point_round_trips_through_parcel_id(tmp_path, monkeypatch):
    monkeypatch.setenv("MPLCONFIGDIR", str(tmp_path))
    provider = FakeGeoProvider()
    # The query example comes from backend/README.md §1. The offset is one eighth of a degree.
    base, = await provider.find_parcels("Krzewina 134")
    lat, lon = base.centroid_lat + 0.125, base.centroid_lon
    clicked = await provider.parcel_at_point(lat, lon)
    assert clicked is not None
    by_id, = await FakeGeoProvider().find_parcels(clicked.parcel_id)
    assert by_id == clicked

    bundle = await provider.collect(GeoRequest(parcel=clicked, analysis_date=ANALYSIS_DATE))
    # Request a small image to check the width override in GeoProvider.render_static_map.
    width = 320
    png = await provider.render_static_map(clicked, bundle, width_px=width)
    # The PNG specification puts the image dimensions in the first IHDR chunk.
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert unpack(">I", png[16:20])[0] == width


@pytest.mark.asyncio
async def test_fixture_provider_reads_exact_date_and_looks_up_parcels(tmp_path):
    # Include a slash in the synthetic parcel number to test CONTRACTS.md §4 sanitization.
    parcel_id = f"{EXAMPLE_PARCEL_ID}/1"
    fake = FakeGeoProvider()
    parcel, = await fake.find_parcels(parcel_id)
    request = GeoRequest(parcel=parcel, analysis_date=ANALYSIS_DATE)
    expected = await fake.collect(request)
    snapshot = {"parcel": parcel.model_dump(mode="json"), "bundle": expected.model_dump(mode="json")}
    path = tmp_path / f"{EXAMPLE_PARCEL_ID}-1__{ANALYSIS_DATE}.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")

    provider = FixtureGeoProvider(tmp_path)
    by_id, = await provider.find_parcels(parcel_id)
    by_name, = await provider.find_parcels(f"{parcel.region} {parcel.parcel_number}")
    at_point = await provider.parcel_at_point(parcel.centroid_lat, parcel.centroid_lon)
    assert by_id == by_name == at_point
    assert await provider.collect(request) == expected

    earlier = request.model_copy(update={"analysis_date": ANALYSIS_DATE - timedelta(days=1)})
    unavailable = await provider.collect(earlier)
    for field in GeoBundle.model_fields:
        result = getattr(unavailable, field)
        assert result.status is SourceStatus.MISSING
        assert result.notes_pl == [GEO_FIXTURE_UNAVAILABLE]

    with pytest.raises(InvalidParcelQuery):
        await provider.find_parcels("")
    with pytest.raises(ParcelNotFound):
        await provider.find_parcels(EXAMPLE_PARCEL_ID)
