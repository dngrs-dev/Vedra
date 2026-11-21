"""European Drought Observatory: Combined Drought Indicator class at the parcel (config/geo_sources.yaml `edo`).

EDO's public WMS has no GetFeatureInfo and its WCS returns class codes, not indicator values (spike 2026-11-21),
so only `cdi_class` (label from the CDI factsheet) and `date_used` are filled; cdi_value, sma, fapar_anomaly and
spi3 stay None (see docs/A_REQUESTS_FOR_B.md section 4).
"""
from __future__ import annotations

import asyncio
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.contracts.common import SourceResult, SourceStatus
from app.contracts.geo import EdoData
from app.core import cache, http
from app.geo.sources import provenance, source

NO_VALUES_NOTE_PL = ("Europejskie Obserwatorium Suszy (EDO) udostępnia publicznie tylko klasy wskaźnika CDI; "
                     "wartości liczbowe SMA, fAPAR i SPI nie są pobierane.")


def dekad_start(d: date) -> date:
    return d.replace(day=1 if d.day < 11 else 11 if d.day < 21 else 21)


def next_dekad(t: date) -> date:
    if t.day == 1:
        return t.replace(day=11)
    if t.day == 11:
        return t.replace(day=21)
    return (t.replace(day=28) + timedelta(days=4)).replace(day=1)


def prev_dekad(t: date) -> date:
    if t.day == 21:
        return t.replace(day=11)
    if t.day == 11:
        return t.replace(day=1)
    return (t - timedelta(days=1)).replace(day=21)


def dekad_for(analysis_date: date, first: date, last: date) -> date | None:
    """Latest dekad t with first <= t <= last whose period has ended on or before analysis_date
    (geo_sources.yaml edo.dekad_rule)."""
    t = min(dekad_start(analysis_date), dekad_start(last))
    while t >= first:
        if next_dekad(t) - timedelta(days=1) <= analysis_date:
            return t
        t = prev_dekad(t)
    return None


async def _time_extent(layer: str) -> tuple[date, date]:
    """(first, last) dekad of a layer from WMS GetCapabilities, e.g. '2012-01-01/2026-11-01/P10D'."""
    cfg = source("edo")
    key = cache.make_key("geo.edo.caps", layer=layer)
    ext = cache.get(key)
    if ext is None:
        r = await http.get(cfg["wms_url"], params=dict(SERVICE="WMS", REQUEST="GetCapabilities",
                                                        VERSION=cfg["wms_version"]), timeout=15.0)
        m = re.search(rf"<Name>{re.escape(layer)}</Name>.*?<Extent[^>]*name=\"time\"[^>]*>([^<]+)</Extent>",
                      r.text, re.S)
        if not m:
            raise ValueError(f"edo: no time extent for {layer}")
        ext = m.group(1).strip()
        cache.set(key, ext, expire_s=6 * 3600)  # new dekads appear every 10 days; refresh a few times a day
    first, last = ext.split("/")[:2]
    return date.fromisoformat(first[:10]), date.fromisoformat(last[:10])


async def _strip(layer: str, t: date, lon: float) -> tuple[bytes, datetime, bool]:
    """GeoTIFF strip 0.2 deg wide around lon (the WCS ignores the lat subset - geo_sources.yaml)."""
    cfg = source("edo")
    w = cfg["wcs"]
    lon0 = round(lon, 2)
    key = cache.make_key("geo.edo.strip.v2", layer=layer, t=t.isoformat(), lon=lon0)
    data = cache.get(key)
    if data is not None:
        return data["tiff"], datetime.fromisoformat(data["fetched_at"]), False
    params: Any = [("map", w["map_param"]), ("SERVICE", "WCS"), ("VERSION", w["version"]),
                   ("REQUEST", "GetCoverage"), ("coverageID", layer), ("CRS", "EPSG:4326"),
                   ("format", w["format"]), ("TIME", t.isoformat()),
                   ("SUBSET", f"long({lon0 - 0.1:.2f},{lon0 + 0.1:.2f})")]
    r = await http.get(cfg["wcs_url"], params=params, timeout=20.0)
    # GeoTIFF signature according to TIFF 6.0 §2. Error XML from a WCS may still be served with HTTP 200.
    if not r.content.startswith((b"II*\0", b"MM\0*")):
        raise ValueError("edo: expected a GeoTIFF coverage")
    fetched_at = datetime.now(timezone.utc)
    cache.set(key, {"tiff": r.content, "fetched_at": fetched_at.isoformat()})  # fixed published dekad
    return r.content, fetched_at, True


def sample_code(tiff: bytes, lat: float, lon: float) -> int | None:
    from rasterio.io import MemoryFile

    with MemoryFile(tiff) as mf, mf.open() as ds:
        left, bottom, right, top = ds.bounds
        if not (left <= lon <= right and bottom <= lat <= top):
            return None
        v = int(next(ds.sample([(lon, lat)]))[0])
        return None if ds.nodata is not None and v == ds.nodata else v


async def edo_signal(lat: float, lon: float, analysis_date: date) -> SourceResult[EdoData]:
    t0 = time.monotonic()
    cfg = source("edo")
    layer = cfg["cdi_coverage"]
    first, last = await _time_extent(layer)
    t = dekad_for(analysis_date, first, last)
    if t is None:
        return SourceResult[EdoData](
            status=SourceStatus.MISSING, error=f"edo: no {layer} dekad <= {analysis_date}",
            notes_pl=["Brak danych Europejskiego Obserwatorium Suszy (EDO) dla daty analizy."],
            elapsed_s=round(time.monotonic() - t0, 3))
    tiff, fetched_at, live = await _strip(layer, t, lon)
    code = await asyncio.to_thread(sample_code, tiff, lat, lon)
    label = cfg["cdi_levels"].get(code) if code is not None else None
    notes = [NO_VALUES_NOTE_PL]
    if label is None:
        notes.insert(0, "Europejskie Obserwatorium Suszy (EDO) nie podaje klasy CDI dla lokalizacji działki "
                        f"(dekada od {t.isoformat()}).")
    data = EdoData(date_used=t, cdi_class=label)
    entry = provenance("edo", cfg["wcs_url"], fetched_at=fetched_at, live=live,
                       data_period=f"dekada od {t.isoformat()}")
    if entry.attribution_pl:
        entry.attribution_pl = entry.attribution_pl.replace("[year]", str(t.year))
    return SourceResult[EdoData](status=SourceStatus.OK if label else SourceStatus.PARTIAL, data=data,
                                 provenance=[entry], notes_pl=notes, elapsed_s=round(time.monotonic() - t0, 3))
