"""Submit analyses and poll their status and reports."""
from __future__ import annotations

import asyncio
import logging
from http import HTTPStatus

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel

from app.analytics.crops import load
from app.analytics.models import AnalysisRequest
from app.api.deps import GeoDependency, RunnerDependency, StoreDependency
from app.config import analysis_today, years_before
from app.jobs.runner import AnalysisStatus
from app.recommendations import texts_pl as text
from app.reports import pdf

router = APIRouter(prefix="/api/analyses")
# Contract guarantee in docs/CONTRACTS.md §3 and the KOWR historical-analysis requirement.
ANALYSIS_HISTORY_YEARS = 10
# docs/CONTRACTS.md §1 sets a three-second budget for maps rendered for PDFs.
MAP_TIMEOUT_S = 3.0
logger = logging.getLogger(__name__)


class AnalysisStarted(BaseModel):
    analysis_id: str


@router.post("", status_code=status.HTTP_202_ACCEPTED, summary=text.ANALYSIS_SUBMIT_SUMMARY)
async def submit_analysis(req: AnalysisRequest, geo: GeoDependency, runner: RunnerDependency) -> AnalysisStarted:
    today = analysis_today()
    if not years_before(today, ANALYSIS_HISTORY_YEARS) <= req.analysis_date <= today:
        raise HTTPException(HTTPStatus.UNPROCESSABLE_ENTITY, text.ANALYSIS_DATE_RANGE)
    if req.crop_code not in load():
        raise HTTPException(HTTPStatus.UNPROCESSABLE_ENTITY, text.ANALYSIS_UNKNOWN_CROP)
    parcel_id = req.parcel_id.strip()
    if not parcel_id:
        raise HTTPException(HTTPStatus.UNPROCESSABLE_ENTITY, text.PARCEL_QUERY_INVALID)

    analysis_id = runner.submit(req.model_copy(update={"parcel_id": parcel_id}), geo)
    return AnalysisStarted(analysis_id=analysis_id)


@router.get("/{analysis_id}", summary=text.ANALYSIS_STATUS_SUMMARY)
async def get_analysis(analysis_id: str, runner: RunnerDependency, store: StoreDependency) -> AnalysisStatus:
    job = runner.status(analysis_id)
    if job is not None:
        return job
    saved = await asyncio.to_thread(store.by_analysis, analysis_id)
    if saved is not None:
        return AnalysisStatus(analysis_id=analysis_id, status="done", progress=saved.progress, report=saved.report)
    raise HTTPException(status.HTTP_404_NOT_FOUND, text.ANALYSIS_NOT_FOUND)


@router.get("/{analysis_id}/report.pdf", response_class=Response, summary=text.REPORT_PDF_SUMMARY)
async def get_analysis_pdf(
    analysis_id: str, runner: RunnerDependency, store: StoreDependency, geo: GeoDependency
) -> Response:
    saved = await asyncio.to_thread(store.by_analysis, analysis_id)
    if saved is None:
        job = runner.status(analysis_id)
        if job is not None and job.status in {"queued", "running"}:
            raise HTTPException(status.HTTP_409_CONFLICT, text.REPORT_PENDING)
        raise HTTPException(status.HTTP_404_NOT_FOUND, text.REPORT_NOT_FOUND)

    report = saved.report
    content = await asyncio.to_thread(store.get_pdf, report.report_id)
    if content is None:
        map_png = None
        if saved.bundle is not None:
            try:
                async with asyncio.timeout(MAP_TIMEOUT_S):
                    map_png = await geo.render_static_map(report.parcel, saved.bundle)
            except Exception:
                logger.info("Static map unavailable for report %s", report.report_id, exc_info=True)
        try:
            content = await asyncio.to_thread(pdf.render, report, map_png)
        except (ImportError, OSError) as exc:
            logger.exception("PDF renderer unavailable for report %s", report.report_id)
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, text.REPORT_PDF_UNAVAILABLE) from exc
        await asyncio.to_thread(store.save_pdf, report.report_id, content)

    return Response(content, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="vedra-{report.report_id}.pdf"'})
