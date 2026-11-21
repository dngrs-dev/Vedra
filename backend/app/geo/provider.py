"""Real GeoProvider. Signatures frozen at T0; Part A implements the bodies."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

from app.contracts.common import SourceResult, SourceStatus
from app.contracts.errors import InvalidParcelQuery, ParcelNotFound
from app.contracts.geo import GeoBundle, GeoRequest
from app.contracts.parcel import Parcel
from app.geo import soil, uldk

log = logging.getLogger(__name__)

# Seconds kept back from the deadline so a source can return its own partial result before being cancelled.
# Our choice; CONTRACTS.md allows the deadline + 0.5 s.
_INNER_MARGIN_S = 1.0

_NOT_YET_PL = {
    "vegetation": "Analiza zdjęć satelitarnych Sentinel-2 nie jest jeszcze dostępna w tej wersji prototypu.",
    "terrain": "Analiza ukształtowania terenu (NMT) nie jest jeszcze dostępna w tej wersji prototypu.",
    "hydro": "Dane o ciekach i rowach w otoczeniu działki nie są jeszcze dostępne w tej wersji prototypu.",
    "landcover": "Dane o pokryciu terenu (ESA WorldCover) nie są jeszcze dostępne w tej wersji prototypu.",
    "edo": "Wskaźniki Europejskiego Obserwatorium Suszy (EDO) nie są jeszcze dostępne w tej wersji prototypu.",
    "imgw": "Dane bieżące IMGW-PIB nie są jeszcze dostępne w tej wersji prototypu.",
}
_FAILED_PL = "Źródło danych nie odpowiedziało poprawnie; wynik analizy nie uwzględnia tych danych."
_TIMEOUT_PL = "Źródło danych nie odpowiedziało w wyznaczonym czasie; wynik analizy nie uwzględnia tych danych."


def _missing(note_pl: str, error: str | None = None, elapsed: float | None = None) -> SourceResult:
    return SourceResult(status=SourceStatus.MISSING, notes_pl=[note_pl], error=error, elapsed_s=elapsed)


async def _guard(name: str, make: Callable[[float], Awaitable[SourceResult]], deadline: float) -> SourceResult:
    """Runs one source with the time left until `deadline` (time.monotonic). Never raises."""
    t0 = time.monotonic()
    remaining = deadline - t0
    try:
        res = await asyncio.wait_for(make(max(remaining - _INNER_MARGIN_S, 0.1)), timeout=max(remaining, 0.05))
    except asyncio.TimeoutError:
        return _missing(_TIMEOUT_PL, f"{name}: deadline exceeded", round(time.monotonic() - t0, 3))
    except Exception as exc:  # noqa: BLE001 - contract: collect() never raises
        log.warning("geo source %s failed: %r", name, exc)
        return _missing(_FAILED_PL, f"{name}: {type(exc).__name__}: {exc}", round(time.monotonic() - t0, 3))
    if res.elapsed_s is None:
        res.elapsed_s = round(time.monotonic() - t0, 3)
    return res


def _not_yet(name: str) -> Callable[[float], Awaitable[SourceResult]]:
    async def run(_budget: float) -> SourceResult:
        return _missing(_NOT_YET_PL[name], f"{name}: not implemented yet")
    return run


class RealGeoProvider:
    async def find_parcels(self, query: str) -> list[Parcel]:
        q = uldk.parse_query(query)
        if q.kind == "id":
            return [await uldk.get_by_id(q.text)]
        if q.kind == "region_number":
            return await uldk.get_by_id_or_nr(q.text)
        parcel = await uldk.get_by_xy(q.lat, q.lon)  # type: ignore[arg-type]
        if parcel is None:
            raise ParcelNotFound(f"uldk: no parcel at {q.lat},{q.lon}")
        return [parcel]

    async def parcel_at_point(self, lat: float, lon: float) -> Parcel | None:
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):  # WGS84 bounds (RFC 7946 3.1.1)
            raise InvalidParcelQuery(uldk.INVALID_QUERY_PL)
        return await uldk.get_by_xy(lat, lon)

    async def collect(self, req: GeoRequest) -> GeoBundle:
        deadline = time.monotonic() + req.deadline_s
        parcel = req.parcel
        sources: dict[str, Callable[[float], Awaitable[SourceResult]]] = {
            "soil": lambda budget: soil.soil_info(parcel, budget),
            "vegetation": _not_yet("vegetation"),
            "terrain": _not_yet("terrain"),
            "hydro": _not_yet("hydro"),
            "landcover": _not_yet("landcover"),
            "edo": _not_yet("edo"),
            "imgw": _not_yet("imgw"),
        }
        results = await asyncio.gather(*(_guard(n, f, deadline) for n, f in sources.items()))
        return GeoBundle.model_validate({n: r.model_dump() for n, r in zip(sources, results)})

    async def render_static_map(self, parcel: Parcel, bundle: GeoBundle, width_px: int = 1200) -> bytes:
        raise NotImplementedError  # CP3 (static_map.py)
