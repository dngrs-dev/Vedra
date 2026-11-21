"""Dependency selection for API routes."""
from __future__ import annotations

from app.config import settings
from app.contracts.geo import GeoProvider


def get_geo_provider() -> GeoProvider:
    if settings.geo_provider == "real":
        from app.geo.provider import RealGeoProvider

        return RealGeoProvider()
    if settings.geo_provider == "fixtures":
        from app.fakes.fixture_geo import FixtureGeoProvider

        return FixtureGeoProvider()

    from app.fakes.fake_geo import FakeGeoProvider

    return FakeGeoProvider()
