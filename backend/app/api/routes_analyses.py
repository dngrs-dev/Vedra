"""Submit analyses and poll their status and reports."""
from __future__ import annotations

from http import HTTPStatus

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.analytics.crops import load
from app.analytics.models import AnalysisRequest
from app.api.deps import GeoDependency, RunnerDependency
from app.config import analysis_today, years_before
from app.jobs.runner import AnalysisStatus
from app.recommendations import texts_pl as text

router = APIRouter(prefix="/api/analyses")
# Contract guarantee in docs/CONTRACTS.md §3 and the KOWR historical-analysis requirement.
ANALYSIS_HISTORY_YEARS = 10


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
async def get_analysis(analysis_id: str, runner: RunnerDependency) -> AnalysisStatus:
    job = runner.status(analysis_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, text.ANALYSIS_NOT_FOUND)
    return job
