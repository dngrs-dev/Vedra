"""SoilGrids 2.0 soil layers with quantiles (ISRIC REST API).

The REST API is slow (spike 2026-11-21: 163 s once, HTTP 504 after 180 s another time; see
config/geo_sources.yaml `soilgrids_rest`) and the files mirror has no water-retention layers, so:
  1. preprocessed responses for known points (data/a/soilgrids_points.json, scripts/a/prefetch_soilgrids.py),
  2. disk cache (namespace geo.soilgrids, no expiry - SoilGrids is a static product),
  3. live REST call run as a shared background task: the caller waits only for its budget; when the budget
     runs out the request keeps going and fills the cache, so the next analysis of the parcel has the data.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from app.contracts.common import Range
from app.contracts.geo import SoilLayer
from app.core import cache, http
from app.geo.aio import wait_shared
from app.geo.sources import DATA_DIR, source

PREPROCESSED_FILE = DATA_DIR / "soilgrids_points.json"
REST_TIMEOUT_S = 240.0  # background request limit; observed answer after 163 s (geo_sources.yaml)

# property name in SoilGrids -> SoilLayer field, extra divisor after d_factor (units: SoilGrids docs / unit_measure)
_FIELDS: dict[str, tuple[str, float]] = {
    "sand": ("sand_pct", 1.0),          # g/kg / d_factor 10 -> %
    "silt": ("silt_pct", 1.0),
    "clay": ("clay_pct", 1.0),
    "soc": ("soc_g_kg", 1.0),           # dg/kg / 10 -> g/kg
    "bdod": ("bulk_density_g_cm3", 1.0),  # cg/cm3 / 100 -> kg/dm3 (= g/cm3)
    "wv0033": ("theta_fc", 100.0),      # (10^-2 cm3/cm3)*10 / 10 -> vol. %; /100 -> m3/m3
    "wv1500": ("theta_wp", 100.0),
}

_inflight: dict[str, asyncio.Task] = {}


class SoilGridsResult:
    def __init__(self, layers: list[SoilLayer], fetched_at: datetime, live: bool, url: str):
        self.layers, self.fetched_at, self.live, self.url = layers, fetched_at, live, url


def _key(lat: float, lon: float) -> str:
    return cache.make_key("geo.soilgrids", lat=round(lat, 5), lon=round(lon, 5))


def _params(lat: float, lon: float) -> list[tuple[str, Any]]:
    c = source("soilgrids_rest")
    return ([("lon", round(lon, 5)), ("lat", round(lat, 5))] + [("property", p) for p in c["properties"]]
            + [("depth", d) for d in c["depths"]] + [("value", v) for v in c["values"]])


def parse_layers(payload: dict) -> list[SoilLayer]:
    """SoilGrids /properties/query JSON -> layers top to bottom. Missing values are left as None."""
    by_depth: dict[tuple[int, int], dict[str, Range]] = {}
    for layer in payload.get("properties", {}).get("layers", []):
        name = layer.get("name")
        if name not in _FIELDS:
            continue
        field_name, extra = _FIELDS[name]
        d_factor = float(layer["unit_measure"]["d_factor"]) * extra
        for d in layer.get("depths", []):
            rng = d["range"]
            vals = d.get("values", {})
            mid = vals.get("Q0.5")
            if mid is None:
                continue

            def conv(v):
                return None if v is None else round(v / d_factor, 4)

            by_depth.setdefault((int(rng["top_depth"]), int(rng["bottom_depth"])), {})[field_name] = Range(
                low=conv(vals.get("Q0.05")), mid=conv(mid), high=conv(vals.get("Q0.95")))
    return [SoilLayer(top_cm=t, bottom_cm=b, **fields) for (t, b), fields in sorted(by_depth.items())]


def _preprocessed(lat: float, lon: float) -> dict | None:
    if not PREPROCESSED_FILE.exists():
        return None
    for rec in json.loads(PREPROCESSED_FILE.read_text(encoding="utf-8")):
        if round(rec["lat"], 5) == round(lat, 5) and round(rec["lon"], 5) == round(lon, 5):
            return rec
    return None


async def _fetch_and_cache(lat: float, lon: float) -> dict:
    url = source("soilgrids_rest")["url"]
    resp = await http.get(url, params=_params(lat, lon), timeout=REST_TIMEOUT_S, retries=0)  # type: ignore[arg-type]
    rec = {"lat": round(lat, 5), "lon": round(lon, 5), "fetched_at": datetime.now(timezone.utc).isoformat(),
           "response": resp.json()}
    cache.set(_key(lat, lon), rec)
    return rec


def _start(lat: float, lon: float) -> asyncio.Task:
    key = _key(lat, lon)
    task = _inflight.get(key)
    if task is None or task.done():
        task = asyncio.get_running_loop().create_task(_fetch_and_cache(lat, lon))
        _inflight[key] = task
        task.add_done_callback(lambda t, k=key: (_inflight.pop(k, None), t.exception() if not t.cancelled() else None))
    return task


async def soil_layers(lat: float, lon: float, budget_s: float) -> SoilGridsResult | None:
    """Layers for the point, or None if not available within budget_s (the fetch continues in background).
    Raises the upstream error if the REST call failed within the budget."""
    url = source("soilgrids_rest")["url"]
    rec = _preprocessed(lat, lon)
    live = False
    if rec is None:
        rec = cache.get(_key(lat, lon))
    if rec is None:
        task = _start(lat, lon)
        try:
            rec = await wait_shared(task, timeout=budget_s)
        except asyncio.TimeoutError:
            return None
        live = True
    return SoilGridsResult(parse_layers(rec["response"]), datetime.fromisoformat(rec["fetched_at"]), live, url)


async def fetch_blocking(lat: float, lon: float) -> dict:
    """For scripts/a/prefetch_soilgrids.py: wait for the REST answer, return the raw record."""
    return await _fetch_and_cache(lat, lon)


def wod_mm(layers: list[SoilLayer], depth_cm: int = 100) -> Range | None:
    """Σ (θFC − θWP) × thickness over 0..depth_cm, in mm (θ in m3/m3, thickness in mm).

    mid = from medians. low/high = OUR CHOICE: θFC and θWP are both driven by texture and organic matter, so
    their quantiles are paired co-monotonically: Σ(θFC(Q0.05) − θWP(Q0.05)) and Σ(θFC(Q0.95) − θWP(Q0.95)),
    sorted into low/high and floored at 0. An anti-correlated envelope (FC Q0.05 − WP Q0.95) was tried in the
    live check on 2026-11-21 and gave 7..410 mm around a 230 mm median - too wide to carry information.
    Quantiles are not additive across layers, so this is an indicative band, not a 90 % interval.
    """
    mid = q05 = q95 = 0.0
    covered = 0
    have_bounds = True
    for L in layers:
        top, bottom = L.top_cm, min(L.bottom_cm, depth_cm)
        if bottom <= top or L.theta_fc is None or L.theta_wp is None:
            continue
        mm = (bottom - top) * 10.0
        mid += (L.theta_fc.mid - L.theta_wp.mid) * mm
        if None in (L.theta_fc.low, L.theta_fc.high, L.theta_wp.low, L.theta_wp.high):
            have_bounds = False
        else:
            q05 += (L.theta_fc.low - L.theta_wp.low) * mm
            q95 += (L.theta_fc.high - L.theta_wp.high) * mm
        covered += bottom - top
    if covered < depth_cm:
        return None  # incomplete profile: do not report a WOD for the full depth
    if not have_bounds:
        return Range(mid=round(mid, 1))
    low, high = sorted((max(q05, 0.0), max(q95, 0.0)))
    return Range(low=round(min(low, mid), 1), mid=round(mid, 1), high=round(max(high, mid), 1))
