"""Submit analyses and poll their status and reports."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel

from app.analytics.crops import load
from app.analytics.models import AnalysisRequest
from app.api.deps import GeoDependency, RunnerDependency, StoreDependency
from app.config import analysis_today, years_before
from app.contracts.geo import GeoProvider
from app.jobs.runner import AnalysisRunner, AnalysisStatus
from app.recommendations import texts_pl as text
from app.reports import pdf
from app.storage.db import ReportStore, StoredReport

router = APIRouter(prefix="/api/analyses")
# Contract guarantee in docs/CONTRACTS.md §3 and the KOWR historical-analysis requirement.
ANALYSIS_HISTORY_YEARS = 10
# docs/CONTRACTS.md §1 sets a three-second budget for maps rendered for PDFs.
MAP_TIMEOUT_S = 3.0
# Upper bound for one combined PDF; the crop list in config/crops.yaml is shorter.
MAX_COMBINED_REPORTS = 20
# Names the PDF layout in cache keys, so PDFs cached with an earlier layout are rebuilt.
PDF_LAYOUT_VERSION = 4  # 4: grouped actions with site maps and the field visit plan (merged main)
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


@router.get("/report.pdf", response_class=Response, summary=text.REPORT_COMBINED_PDF_SUMMARY)
async def get_combined_pdf(
    analysis_ids: Annotated[list[str], Query(alias="analysis_id", min_length=1, max_length=MAX_COMBINED_REPORTS)],
    runner: RunnerDependency, store: StoreDependency, geo: GeoDependency,
) -> Response:
    """One PDF with a section per analysis, e.g. one per crop selected for a parcel."""
    ids = list(dict.fromkeys(item.strip() for item in analysis_ids if item.strip()))
    if not ids:
        raise HTTPException(HTTPStatus.UNPROCESSABLE_ENTITY, text.REPORT_NOT_FOUND)
    saved = [await _saved_report(analysis_id, runner, store) for analysis_id in ids]
    reports = [item.report for item in saved]

    async def build() -> bytes:
        # Analyses of one parcel share its outline, so each parcel map is rendered once.
        by_parcel = {item.report.parcel.parcel_id: item for item in saved}
        maps = dict(zip(by_parcel, await asyncio.gather(*(_map_png(item, geo) for item in by_parcel.values()))))
        return await asyncio.to_thread(pdf.render_many, [(report, maps[report.parcel.parcel_id]) for report in reports])

    cache_key = f"combined-{PDF_LAYOUT_VERSION}:" + ",".join(report.report_id for report in reports)
    content = await _cached_pdf(store, cache_key, build)
    return _pdf_response(content, f"vedra-{reports[0].analysis_date}-{len(reports)}.pdf")


@router.get("/{analysis_id}", summary=text.ANALYSIS_STATUS_SUMMARY)
async def get_analysis(analysis_id: str, runner: RunnerDependency, store: StoreDependency) -> AnalysisStatus:
    job = runner.status(analysis_id)
    if job is not None:
        return job
    saved = await asyncio.to_thread(store.by_analysis, analysis_id)
    if saved is not None:
        return AnalysisStatus(analysis_id=analysis_id, status="done", progress=saved.progress, report=saved.report)
    raise HTTPException(status.HTTP_404_NOT_FOUND, text.ANALYSIS_NOT_FOUND)


async def _saved_report(analysis_id: str, runner: AnalysisRunner, store: ReportStore) -> StoredReport:
    saved = await asyncio.to_thread(store.by_analysis, analysis_id)
    if saved is None:
        job = runner.status(analysis_id)
        if job is not None and job.status in {"queued", "running"}:
            raise HTTPException(status.HTTP_409_CONFLICT, text.REPORT_PENDING)
        raise HTTPException(status.HTTP_404_NOT_FOUND, text.REPORT_NOT_FOUND)
    return saved


async def _map_png(saved: StoredReport, geo: GeoProvider) -> bytes | None:
    if saved.bundle is None:
        return None
    try:
        async with asyncio.timeout(MAP_TIMEOUT_S):
            return await geo.render_static_map(saved.report.parcel, saved.bundle)
    except Exception:
        logger.info("Static map unavailable for report %s", saved.report.report_id, exc_info=True)
        return None


async def _cached_pdf(store: ReportStore, cache_key: str, build: Callable[[], Awaitable[bytes]]) -> bytes:
    content = await asyncio.to_thread(store.get_pdf, cache_key)
    if content is None:
        try:
            content = await build()
        except (ImportError, OSError) as exc:
            logger.exception("PDF renderer unavailable for %s", cache_key)
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, text.REPORT_PDF_UNAVAILABLE) from exc
        await asyncio.to_thread(store.save_pdf, cache_key, content)
    return content


def _pdf_response(content: bytes, filename: str) -> Response:
    return Response(content, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/{analysis_id}/report.pdf", response_class=Response, summary=text.REPORT_PDF_SUMMARY)
async def get_analysis_pdf(
    analysis_id: str, runner: RunnerDependency, store: StoreDependency, geo: GeoDependency
) -> Response:
    saved = await _saved_report(analysis_id, runner, store)
    report = saved.report

    async def build() -> bytes:
        return await asyncio.to_thread(pdf.render, report, await _map_png(saved, geo))

    content = await _cached_pdf(store, f"report-{PDF_LAYOUT_VERSION}:{report.report_id}", build)
    return _pdf_response(content, f"vedra-{report.report_id}.pdf")
