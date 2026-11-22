import asyncio
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.analytics.models import AnalysisRequest
from app.contracts.report import Report
from app.fakes.fake_geo import FakeGeoProvider
from app.jobs import runner
from app.storage.db import ReportStore

SAMPLE = Path(__file__).resolve().parents[1] / "fixtures" / "sample_report.json"


@pytest.mark.asyncio
async def test_waiting_job_stays_queued_until_an_execution_slot_opens(monkeypatch):
    report = Report.model_validate_json(SAMPLE.read_bytes())
    running = asyncio.Event()
    release = asyncio.Event()
    second_started = asyncio.Event()
    requests = []

    async def analyze(request, *_args, **_kwargs):
        requests.append(request.parcel_id)
        if len(requests) == 1:
            running.set()
            await release.wait()
        else:
            second_started.set()
        return report

    monkeypatch.setattr(runner, "run_analysis", analyze)
    engine = runner.AnalysisRunner(Mock(spec=ReportStore), concurrency=1)
    geo = FakeGeoProvider()
    # The fixture date and identification exercise queue ordering without a live provider.
    request = AnalysisRequest(parcel_id=report.parcel.parcel_id, crop_code=report.crop_code,
                              analysis_date=report.analysis_date)
    first = engine.submit(request, geo)
    second = engine.submit(request, geo)
    try:
        await asyncio.wait_for(running.wait(), timeout=runner.ANALYSIS_TIMEOUT_S)
        assert engine.status(first).status == "running"
        assert engine.status(second).status == "queued"
        assert len(requests) == 1
        release.set()
        await asyncio.wait_for(second_started.wait(), timeout=runner.ANALYSIS_TIMEOUT_S)
        assert engine.status(first).status == "done"
        assert len(requests) == 2
    finally:
        await engine.close()
