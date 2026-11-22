"""Dependency selection for API routes."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.api.cadastral import CadastralProvider
from app.config import settings
from app.contracts.geo import GeoProvider
from app.jobs.runner import AnalysisRunner
from app.storage.db import ReportStore


def get_geo_provider() -> GeoProvider:
    if settings.geo_provider == "real":
        from app.geo.provider import RealGeoProvider

        return CadastralProvider(RealGeoProvider(), snapshot_path=settings.egib_snapshot_path)
    if settings.geo_provider == "fixtures":
        from app.fakes.fixture_geo import FixtureGeoProvider

        return FixtureGeoProvider()

    from app.fakes.fake_geo import FakeGeoProvider

    return FakeGeoProvider()


def get_analysis_runner(request: Request) -> AnalysisRunner:
    return request.app.state.analysis_runner


def get_report_store(request: Request) -> ReportStore:
    return request.app.state.report_store


GeoDependency = Annotated[GeoProvider, Depends(get_geo_provider)]
RunnerDependency = Annotated[AnalysisRunner, Depends(get_analysis_runner)]
StoreDependency = Annotated[ReportStore, Depends(get_report_store)]
