"""Run the complete Part B pipeline for every geo snapshot recorded by Part A."""
from datetime import date
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.analytics import open_meteo, season
from app.analytics.models import AnalysisRequest, WeatherData
from app.analytics.pipeline import run_analysis
from app.contracts.common import SourceResult, SourceStatus
from app.contracts.geo import GeoBundle
from app.contracts.report import Report
from app.fakes.fixture_geo import FIXTURES_DIR, FixtureGeoProvider
from app.recommendations import texts_pl as text

DIRECTORY = Path(os.environ.get("VEDRA_GEO_FIXTURES", FIXTURES_DIR))
SNAPSHOTS = sorted(DIRECTORY.glob("*.json"))


@pytest.mark.skipif(not SNAPSHOTS, reason="Part A's recorded fixtures are absent from this checkout")
@pytest.mark.parametrize("snapshot", SNAPSHOTS, ids=lambda path: path.stem)
@pytest.mark.asyncio
async def test_pipeline_report_on_recorded_geo(snapshot, monkeypatch):
    recorded = json.loads(snapshot.read_bytes())
    parcel_id = recorded["parcel"]["parcel_id"]
    analysis_date = date.fromisoformat(snapshot.stem.rsplit("__", maxsplit=1)[1])
    bundle = GeoBundle.model_validate(recorded["bundle"])
    # Exercise recorded geo inputs without relying on the live weather quota in a contract test.
    weather = SourceResult[WeatherData](status=SourceStatus.MISSING, notes_pl=[text.WEATHER_ARCHIVE_UNAVAILABLE])
    monkeypatch.setattr(open_meteo, "fetch_weather", AsyncMock(return_value=weather))

    report = Report.model_validate_json((await run_analysis(
        AnalysisRequest(parcel_id=parcel_id, crop_code="spring_cereals", analysis_date=analysis_date),
        FixtureGeoProvider(DIRECTORY),
        lambda _: None,
    )).model_dump_json())

    assert report.parcel.parcel_id == parcel_id
    assert report.analysis_date == analysis_date
    assert report.assessment.kbw.explanation_pl
    if season.mode(analysis_date) == "off_season":
        assert report.assessment.kbw.verdict == "off_season"
    assert {signal.code for signal in report.assessment.signals} >= {"weather", "vegetation", "edo"}
    assert text.WEATHER_ARCHIVE_UNAVAILABLE in report.limitations_pl
    sources = {item.source_id for item in report.data_sources}
    for name in GeoBundle.model_fields:
        source = getattr(bundle, name)
        assert {item.source_id for item in source.provenance} <= sources
        assert set(source.notes_pl) <= set(report.limitations_pl)
    references = {item.id for item in report.references}
    assert all(item.why_pl and set(item.reference_ids) <= references for item in report.recommendations)
