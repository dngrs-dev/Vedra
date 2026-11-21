"""In-memory analysis jobs for the CP1 API."""
from __future__ import annotations

import asyncio
import logging
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.analytics.models import AnalysisRequest
from app.analytics.pipeline import run_analysis
from app.contracts.errors import InvalidParcelQuery, ParcelNotFound, UpstreamUnavailable
from app.contracts.geo import GeoProvider
from app.contracts.report import Report
from app.recommendations import texts_pl as text

logger = logging.getLogger(__name__)
# README.md §1 sets a 30-second cold run target for an analysis.
ANALYSIS_TIMEOUT_S = 30.0


class AnalysisStatus(BaseModel):
    analysis_id: str
    status: Literal["queued", "running", "done", "error"] = "queued"
    progress: list[str] = Field(default_factory=list)
    report: Report | None = None
    error: str | None = None


class AnalysisRunner:
    def __init__(self, timeout_s: float = ANALYSIS_TIMEOUT_S) -> None:
        self.timeout_s = timeout_s
        self._jobs: dict[str, AnalysisStatus] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def submit(self, req: AnalysisRequest, geo: GeoProvider) -> str:
        analysis_id = str(uuid4())
        job = AnalysisStatus(analysis_id=analysis_id, progress=[text.PROGRESS_QUEUED])
        self._jobs[analysis_id] = job
        task = asyncio.create_task(self._run(req, geo, job))
        self._tasks[analysis_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(analysis_id, None))
        return analysis_id

    def status(self, analysis_id: str) -> AnalysisStatus | None:
        return self._jobs.get(analysis_id)

    async def _run(self, req: AnalysisRequest, geo: GeoProvider, job: AnalysisStatus) -> None:
        job.status = "running"
        try:
            async with asyncio.timeout(self.timeout_s):
                job.report = await run_analysis(req, geo, job.progress.append)
        except InvalidParcelQuery:
            job.error = text.PARCEL_QUERY_INVALID
        except ParcelNotFound:
            job.error = text.PARCEL_NOT_FOUND
        except (UpstreamUnavailable, NotImplementedError):
            job.error = text.GEO_SERVICE_UNAVAILABLE
        except TimeoutError:
            job.error = text.ANALYSIS_TIMEOUT
        except asyncio.CancelledError:
            job.status = "error"
            job.error = text.ANALYSIS_INTERRUPTED
            raise
        except Exception:
            logger.exception("Analysis %s failed", job.analysis_id)
            job.error = text.ANALYSIS_FAILED

        if job.report is not None:
            job.progress.append(text.PROGRESS_DONE)
            job.status = "done"
        else:
            job.status = "error"

    async def close(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
