"""FastAPI entry point for Vedra."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus

from fastapi import FastAPI, Request, Response, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import RequestResponseEndpoint

from app.api import routes_analyses, routes_meta, routes_parcels, routes_reports, routes_scenarios
from app.config import settings
from app.contracts.errors import InvalidParcelQuery, ParcelNotFound, UpstreamUnavailable
from app.core import http
from app.jobs.runner import AnalysisRunner
from app.recommendations import texts_pl as text
from app.storage.db import ReportStore


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logging.getLogger("app").setLevel(settings.log_level)
    store = ReportStore(settings.db_path)
    runner = AnalysisRunner(store, concurrency=settings.analysis_concurrency)
    app.state.report_store = store
    app.state.analysis_runner = runner
    try:
        yield
    finally:
        await runner.close()
        await http.close()


app = FastAPI(title="Vedra", description=text.API_DESCRIPTION, lifespan=lifespan)
app.include_router(routes_meta.router)
app.include_router(routes_parcels.router)
app.include_router(routes_analyses.router)
app.include_router(routes_reports.router)
app.include_router(routes_scenarios.router)
app.include_router(routes_scenarios.ai_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    # GET and POST are the public methods listed in README.md §4.
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(InvalidParcelQuery)
@app.exception_handler(ParcelNotFound)
@app.exception_handler(UpstreamUnavailable)
async def geo_error(_: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, InvalidParcelQuery):
        return JSONResponse({"detail": text.PARCEL_QUERY_INVALID}, status_code=HTTPStatus.UNPROCESSABLE_ENTITY)
    if isinstance(exc, ParcelNotFound):
        return JSONResponse({"detail": text.PARCEL_NOT_FOUND}, status_code=status.HTTP_404_NOT_FOUND)
    return JSONResponse({"detail": text.GEO_SERVICE_UNAVAILABLE}, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    fields = {error["loc"][-1] for error in exc.errors() if error["loc"]}
    if fields & {"lat", "lon"}:
        detail = text.PARCEL_POINT_INVALID
    elif "q" in fields:
        detail = text.PARCEL_QUERY_INVALID
    else:
        detail = text.API_INVALID_REQUEST
    return JSONResponse({"detail": detail}, status_code=HTTPStatus.UNPROCESSABLE_ENTITY)


@app.exception_handler(StarletteHTTPException)
async def routing_error(request: Request, exc: StarletteHTTPException) -> Response:
    if exc.status_code == status.HTTP_404_NOT_FOUND and exc.detail == "Not Found":
        exc = StarletteHTTPException(exc.status_code, detail=text.API_ROUTE_NOT_FOUND, headers=exc.headers)
    elif exc.status_code == status.HTTP_405_METHOD_NOT_ALLOWED and exc.detail == "Method Not Allowed":
        exc = StarletteHTTPException(exc.status_code, detail=text.API_METHOD_NOT_ALLOWED, headers=exc.headers)
    return await http_exception_handler(request, exc)


@app.middleware("http")
async def add_security_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
    response = await call_next(request)
    # The Fetch Standard defines the nosniff response directive for MIME type checking.
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    return response
