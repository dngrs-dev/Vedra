"""FastAPI entry point for Vedra."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import RequestResponseEndpoint

from app.api import routes_meta
from app.config import settings
from app.core import http
from app.recommendations.texts_pl import API_DESCRIPTION


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logging.getLogger("app").setLevel(settings.log_level)
    try:
        yield
    finally:
        await http.close()


app = FastAPI(title="Vedra", description=API_DESCRIPTION, lifespan=lifespan)
app.include_router(routes_meta.router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    # GET and POST are the public methods listed in README.md §4.
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
    response = await call_next(request)
    # The Fetch Standard defines the nosniff response directive for MIME type checking.
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    return response
