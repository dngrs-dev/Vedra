"""Parcel lookup in ULDK GUGiK (https://uldk.gugik.gov.pl/).

Response format (spike 2026-11-21, recorded in config/geo_sources.yaml `uldk.response_format`):
line 1 = status ("0" ok, "-1 brak wyników" none, a count for GetParcelByIdOrNr), then one record per
line, fields separated by "|" in the order of `result`. Note: ULDK's `teryt` result field returns the
full parcel id, so Parcel.teryt is derived from the id instead (see `_teryt`).

Fallback: when ULDK fails (it blocked the dev client on 2026-11-21, see config `egib_parquet.role`), lookups by id
and by point go to the national EGiB GeoParquet export (app/geo/egib_parquet.py, ~4-7 s); «obręb + number» queries
too when the obręb name occurs at most egib_parquet.MAX_OBREBY times (names resolved with the PRG WFS).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal

from app.contracts.errors import InvalidParcelQuery, ParcelNotFound, UpstreamUnavailable
from app.contracts.parcel import Parcel
from app.core import cache, http
from app.geo import geometry
from app.geo.sources import source

log = logging.getLogger(__name__)
EGIB_CACHE_S = 30 * 24 * 3600   # OUR CHOICE: parcels change rarely; the export is rebuilt daily

# Full parcel id WWPPGG_R.OOOO.[AR_NR.]NR_DZ - regex from docs/PART_A_DATA_GEO.md (uldk.parse_query)
PARCEL_ID_RE = re.compile(r"^\d{6}_\d\.\d{4}\.(?:AR_\d+\.)?[0-9A-Za-z/]+$")
POINT_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*[,;]\s*(-?\d+(?:\.\d+)?)\s*$")
# "<obręb name> <parcel number>": name must contain a letter; number starts with a digit
REGION_NR_RE = re.compile(r"^(?P<region>.*[^\W\d_].*?)\s+(?P<nr>\d[0-9A-Za-z/]*)$")

INVALID_QUERY_PL = ("Nie rozpoznano zapytania. Podaj pełny identyfikator działki (np. 141201_1.0001.6509), "
                    "nazwę obrębu i numer działki (np. Krzewina 134) albo współrzędne «szerokość, długość».")


@dataclass(frozen=True)
class ParsedQuery:
    kind: Literal["id", "region_number", "point"]
    text: str = ""
    lat: float | None = None
    lon: float | None = None


def parse_query(q: str) -> ParsedQuery:
    text = " ".join((q or "").split())
    if not text:
        raise InvalidParcelQuery(INVALID_QUERY_PL)
    if PARCEL_ID_RE.match(text):
        return ParsedQuery("id", text=text)
    m = POINT_RE.match(text)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        # WGS84 bounds (RFC 7946 3.1.1)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise InvalidParcelQuery(INVALID_QUERY_PL)
        return ParsedQuery("point", lat=lat, lon=lon)
    if REGION_NR_RE.match(text):
        return ParsedQuery("region_number", text=text)
    raise InvalidParcelQuery(INVALID_QUERY_PL)


async def _request(request: str, **params: str) -> list[list[str]]:
    """Calls ULDK, returns parsed records ([] when ULDK reports no result)."""
    cfg = source("uldk")
    query = {"request": request, "result": cfg["result_fields"], "srid": "2180", **params}
    key = cache.make_key("geo.uldk", **query)
    text = cache.get(key)
    if text is not None:
        return _parse(text, cfg)
    try:
        text = (await http.get(cfg["url"], params=query, timeout=10.0)).text
        records = _parse(text, cfg)
    except _BadAnswer:
        # A malformed answer was seen once under load (2026-11-21 profiling, not reproducible); ask once more.
        text = (await http.get(cfg["url"], params=query, timeout=10.0)).text
        records = _parse(text, cfg)
    cache.set(key, text)  # parcels change rarely; no expiry (PART_A_DATA_GEO.md: geo.uldk, no expiry)
    return records


class _BadAnswer(UpstreamUnavailable):
    """ULDK answered, but not in its documented format."""


def _parse(text: str, cfg: dict) -> list[list[str]]:
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        raise _BadAnswer("uldk: empty response")
    status = lines[0].strip()
    if status.startswith("-1"):
        return []  # "-1 brak wyników" (also returned with SQL error text for malformed ids)
    if not re.fullmatch(r"\d+", status):
        raise _BadAnswer(f"uldk: unexpected status line {status[:80]!r}")
    n_fields = len(cfg["result_fields"].split(","))
    records = [ln.split("|") for ln in lines[1:]]
    bad = [ln for ln, r in zip(lines[1:], records) if len(r) != n_fields]
    if bad:
        raise _BadAnswer(f"uldk: unexpected record format ({len(bad)} of {len(records)}): {bad[0][:160]!r}")
    return records


def _teryt(parcel_id: str) -> str:
    """'040704_2.0012.63/1' -> '040704_2' (TERYT of the commune + commune type digit)."""
    return parcel_id.split(".", 1)[0]


def to_parcel(rec: list[str]) -> Parcel:
    """Record in `result_fields` order: id, geom_wkt (EPSG:2180), teryt, voivodeship, county, commune,
    region, parcel."""
    pid, ewkt, _teryt_field, voiv, county, commune, region, number = (f.strip() for f in rec)
    srid, g2180 = geometry.parse_ewkt(ewkt)
    if srid not in (None, 2180):
        raise UpstreamUnavailable(f"uldk: unexpected SRID {srid}")
    g4326 = geometry.to_4326(g2180)
    c = g4326.centroid
    return Parcel(
        parcel_id=pid,
        teryt=_teryt(pid),
        voivodeship=voiv,
        county=county,
        commune=commune,
        region=region or pid.split(".")[1],  # obręb name; its number when ULDK has no name
        parcel_number=number or pid.rsplit(".", 1)[-1],
        area_ha=round(g2180.area / 10_000, 4),
        geometry_wgs84=g4326.__geo_interface__,
        geometry_2180_wkt=g2180.wkt,
        centroid_lat=round(c.y, 6),
        centroid_lon=round(c.x, 6),
    )


async def _egib(kind: str, key_parts: dict, lookup) -> list[str] | None:
    """Fallback record from the EGiB GeoParquet, cached (None = the export has no such parcel)."""
    key = cache.make_key("geo.egib." + kind, **key_parts)
    hit = cache.get(key)
    if hit is not None:
        return hit or None
    rec = await lookup()
    cache.set(key, rec or [], expire_s=EGIB_CACHE_S)
    return rec


async def get_by_id(parcel_id: str) -> Parcel:
    from app.geo import egib_parquet

    try:
        records = await _request("GetParcelById", id=parcel_id)
    except UpstreamUnavailable as exc:
        log.warning("uldk failed, using the EGiB GeoParquet: %s", exc)
        try:
            rec = await _egib("id", {"id": parcel_id}, lambda: egib_parquet.by_id(parcel_id))
        except Exception as fallback_exc:  # noqa: BLE001 - report the ULDK error, the fallback is secondary
            raise UpstreamUnavailable(f"{exc}; egib fallback: {fallback_exc!r}") from fallback_exc
        records = [rec] if rec else []
    if not records:
        raise ParcelNotFound(f"uldk: no parcel {parcel_id!r}")
    return to_parcel(records[0])


async def get_by_id_or_nr(text: str) -> list[Parcel]:
    """'Krzewina 134' or a full id. May return many parcels (e.g. 58 for 'Nowa Wieś 1', spike 2026-11-21).
    Fallback when ULDK fails: EGiB GeoParquet, for obręb names that occur at most egib_parquet.MAX_OBREBY times."""
    from app.geo import egib_parquet

    try:
        records = await _request("GetParcelByIdOrNr", id=text)
    except UpstreamUnavailable as exc:
        m = REGION_NR_RE.match(" ".join(text.split()))
        if not m:
            raise
        log.warning("uldk failed, using the EGiB GeoParquet: %s", exc)
        region, nr = m.group("region"), m.group("nr")
        try:
            records = await _egib("nr", {"region": region.lower(), "nr": nr},
                                  lambda: egib_parquet.by_region_number(region, nr))
        except Exception as fallback_exc:  # noqa: BLE001
            raise UpstreamUnavailable(f"{exc}; egib fallback: {fallback_exc}") from fallback_exc
        records = records or []
    if not records:
        raise ParcelNotFound(f"uldk: no parcel for {text!r}")
    return [to_parcel(r) for r in records]


async def get_by_xy(lat: float, lon: float) -> Parcel | None:
    from app.geo import egib_parquet

    xy = source("uldk")["xy_format"].format(lon=lon, lat=lat)
    try:
        records = await _request("GetParcelByXY", xy=xy)
    except UpstreamUnavailable as exc:
        log.warning("uldk failed, using the EGiB GeoParquet: %s", exc)
        x, y = geometry.lonlat_to_2180(lon, lat)
        try:
            rec = await _egib("xy", {"x": round(x, 1), "y": round(y, 1)}, lambda: egib_parquet.by_point(x, y))
        except Exception as fallback_exc:  # noqa: BLE001
            raise UpstreamUnavailable(f"{exc}; egib fallback: {fallback_exc!r}") from fallback_exc
        records = [rec] if rec else []
    return to_parcel(records[0]) if records else None
