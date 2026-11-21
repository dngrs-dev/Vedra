"""Shared async HTTP client with host allowlist and retries. Frozen after T0."""
from __future__ import annotations

import asyncio
from urllib.parse import urlparse

import httpx

from app.analytics.hosts import ANALYTICS_HOSTS  # owner B
from app.contracts.errors import UpstreamUnavailable
from app.geo.hosts import GEO_HOSTS  # owner A

_client: httpx.AsyncClient | None = None


class HostNotAllowed(Exception):
    pass


def allowed_hosts() -> set[str]:
    return set(GEO_HOSTS) | set(ANALYTICS_HOSTS)


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0),
            follow_redirects=True,
            headers={"User-Agent": "Vedra/0.1 (HackNation 2026 prototype)"},
            limits=httpx.Limits(max_connections=64),
        )
    return _client


async def get(url: str, *, params: dict | None = None, timeout: float | None = None, retries: int = 2) -> httpx.Response:
    host = urlparse(url).hostname or ""
    if host not in allowed_hosts():
        raise HostNotAllowed(host)
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = await get_client().get(url, params=params, timeout=timeout)
            if resp.status_code >= 500 and attempt < retries:
                await asyncio.sleep(0.5 * 2**attempt)
                continue
            resp.raise_for_status()
            return resp
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            last_exc = exc
            if attempt < retries:
                await asyncio.sleep(0.5 * 2**attempt)
    raise UpstreamUnavailable(f"{host}: {last_exc}")


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
