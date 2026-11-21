"""Read a saved analysis report by its permanent identifier."""
import asyncio

from fastapi import APIRouter, HTTPException, status

from app.api.deps import StoreDependency
from app.contracts.report import Report
from app.recommendations import texts_pl as text

router = APIRouter(prefix="/api/reports")


@router.get("/{report_id}", summary=text.REPORT_SAVED_SUMMARY)
async def get_report(report_id: str, store: StoreDependency) -> Report:
    saved = await asyncio.to_thread(store.get_report, report_id)
    if saved is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, text.REPORT_NOT_FOUND)
    return saved.report
