"""IMGW-PIB current data: nearest synop observation and hydrological drought warnings (config/geo_sources.yaml `imgw`).

Only for analysis_date == today (Europe/Warsaw): IMGW public endpoints give current values only, and Part A must
not use data observed after a historical analysis date (CONTRACTS.md section 3).
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import date, datetime, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

from pyproj import Geod

from app.contracts.common import SourceResult, SourceStatus
from app.contracts.geo import HydroWarning, ImgwData, ImgwObservation
from app.contracts.parcel import Parcel
from app.core import cache, http
from app.geo.sources import BACKEND, provenance, source

HISTORICAL_NOTE_PL = "Dane bieżące IMGW niedostępne dla daty historycznej"   # wording from PART_A_DATA_GEO.md
_GEOD = Geod(ellps="WGS84")
_OPEN_END = "9999-12-31"   # IMGW uses 9999-12-31 23:59:59 for "until further notice" (warningshydro, 2026-11-21)


def today_warsaw() -> date:
    return datetime.now(ZoneInfo("Europe/Warsaw")).date()


@lru_cache(maxsize=1)
def stations() -> dict[str, dict]:
    path = BACKEND / source("imgw")["stations_file"]
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"stations": []}
    return {s["id_stacji"]: s for s in data["stations"]}


def _num(v) -> float | None:
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def nearest_observation(synop: list[dict], lat: float, lon: float) -> ImgwObservation | None:
    best = None
    for rec in synop:
        st = stations().get(rec.get("id_stacji", ""))
        if st is None:
            continue
        _, _, dist_m = _GEOD.inv(lon, lat, st["lon"], st["lat"])
        if best is None or dist_m < best[0]:
            best = (dist_m, rec)
    if best is None:
        return None
    dist_m, rec = best
    observed = datetime.fromisoformat(f"{rec['data_pomiaru']}T{int(rec['godzina_pomiaru']):02d}:00:00").replace(
        tzinfo=timezone.utc)  # synop_time_zone: UTC (geo_sources.yaml)
    return ImgwObservation(
        station_id=rec["id_stacji"], station_name=rec["stacja"], distance_km=round(dist_m / 1000, 1),
        observed_at=observed, temperature_c=_num(rec.get("temperatura")),
        precipitation_mm=_num(rec.get("suma_opadu")), relative_humidity_pct=_num(rec.get("wilgotnosc_wzgledna")))


def _ts(text: str | None) -> datetime | None:
    """IMGW 'YYYY-MM-DD HH:MM:SS' kept as given (naive; no time zone is stated by the API)."""
    if not text or text.startswith(_OPEN_END):
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def drought_warnings(warnings: list[dict], voivodeship: str) -> list[HydroWarning]:
    cfg = source("imgw")
    want = voivodeship.strip().casefold()
    out = []
    for w in warnings:
        if w.get("zdarzenie") not in cfg["drought_phenomena"]:
            continue
        for area in w.get("obszary") or []:
            if (area.get("wojewodztwo") or "").strip().casefold() != want:
                continue
            out.append(HydroWarning(number=w.get("numer"), phenomenon=w["zdarzenie"],
                                    area_pl=area.get("opis") or area.get("wojewodztwo", ""),
                                    valid_from=_ts(w.get("data_od")), valid_to=_ts(w.get("data_do")),
                                    level=w.get("stopień")))
    return out


async def _get_json(url: str):
    key = cache.make_key("geo.imgw", url=url)
    hit = cache.get(key)
    if hit is not None:
        return hit
    data = (await http.get(url, timeout=10.0)).json()
    cache.set(key, data, expire_s=600)  # current data, refreshed hourly by IMGW; 10 min is our choice
    return data


async def imgw_context(parcel: Parcel, analysis_date: date) -> SourceResult[ImgwData]:
    t0 = time.monotonic()
    if analysis_date != today_warsaw():
        return SourceResult[ImgwData](status=SourceStatus.MISSING, notes_pl=[HISTORICAL_NOTE_PL + "."],
                                      error="imgw: historical analysis date", elapsed_s=round(time.monotonic() - t0, 3))
    cfg = source("imgw")
    synop, warnings = await asyncio.gather(_get_json(cfg["synop_url"]), _get_json(cfg["warnings_hydro_url"]),
                                           return_exceptions=True)
    notes: list[str] = []
    errors: list[str] = []
    prov = []
    obs = None
    if isinstance(synop, BaseException):
        errors.append(f"synop: {type(synop).__name__}: {synop}")
        notes.append("Bieżące obserwacje synoptyczne IMGW-PIB są chwilowo niedostępne.")
    else:
        obs = nearest_observation(synop, parcel.centroid_lat, parcel.centroid_lon)
        prov.append(provenance("imgw", cfg["synop_url"]))
    warns: list[HydroWarning] = []
    if isinstance(warnings, BaseException):
        errors.append(f"warningshydro: {type(warnings).__name__}: {warnings}")
        notes.append("Ostrzeżenia hydrologiczne IMGW-PIB są chwilowo niedostępne.")
    else:
        warns = drought_warnings(warnings, parcel.voivodeship)
        prov.append(provenance("imgw", cfg["warnings_hydro_url"]))
        notes.append(f"Ostrzeżenia przed suszą hydrologiczną IMGW-PIB dobrano według województwa działki "
                     f"({parcel.voivodeship}); ostrzeżenie może dotyczyć innej zlewni w tym województwie.")
    status = SourceStatus.OK if not errors else SourceStatus.PARTIAL if prov else SourceStatus.MISSING
    return SourceResult[ImgwData](status=status, data=ImgwData(nearest_synop=obs, drought_warnings=warns) if prov else None,
                                  provenance=prov, notes_pl=notes, error="; ".join(errors) or None,
                                  elapsed_s=round(time.monotonic() - t0, 3))
