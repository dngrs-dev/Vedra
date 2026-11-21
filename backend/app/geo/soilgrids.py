"""SoilGrids 2.0 soil layers with quantiles, and water retention by the Saxton & Rawls (2006) pedotransfer functions.

Texture, organic carbon and bulk density come from SoilGrids (ISRIC); lookup order:
  1. preprocessed REST answers for known points (data/a/soilgrids_points.json, scripts/a/prefetch_soilgrids.py),
  2. disk cache (geo.soilgrids = REST answer, geo.soilgrids.files = tile read; no expiry - static product),
  3. live pixel reads from the SoilGrids tiles (app/geo/soilgrids_files.py, ~2 s, identical values to REST),
  4. if the tiles fail: the REST API as a shared background task (26-163 s, see config `soilgrids_rest`); the
     caller waits only for its budget, the request keeps going and fills the cache for the next analysis.
Field capacity / wilting point: saxton_rawls() below, not SoilGrids wv0033/wv1500 (reason in config
`soilgrids_files.water_retention`).
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from app.contracts.common import Range
from app.contracts.geo import SoilLayer
from app.core import cache, http
from app.geo import soilgrids_files
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
}

# Organic matter = 1.724 x organic carbon: the conventional van Bemmelen factor (discussed in Pribyl 2010,
# Geoderma 156:75-83). Saxton & Rawls (2006) take OM in % by weight.
OM_PER_SOC = 1.724
# Range of the data Saxton & Rawls (2006) fitted the equations to (their applicability note): OM <= 8 %, clay <= 60 %.
SR_MAX_OM_PCT = 8.0
SR_MAX_CLAY_PCT = 60.0


def saxton_rawls(sand: float, clay: float, om_pct: float) -> tuple[float, float]:
    """(theta_33kPa, theta_1500kPa) in m3/m3. Saxton K.E., Rawls W.J. (2006) Soil water characteristic estimates
    by texture and organic matter for hydrologic solutions. SSSAJ 70:1569-1578, Table 1 (eq. 1 and 2).
    sand, clay: fractions 0..1 by weight; om_pct: organic matter, % by weight."""
    S, C, OM = sand, clay, om_pct
    t1500 = -0.024 * S + 0.487 * C + 0.006 * OM + 0.005 * S * OM - 0.013 * C * OM + 0.068 * S * C + 0.031
    t33 = -0.251 * S + 0.195 * C + 0.011 * OM + 0.006 * S * OM - 0.027 * C * OM + 0.452 * S * C + 0.299
    return t33 + (1.283 * t33 ** 2 - 0.374 * t33 - 0.015), t1500 + (0.14 * t1500 - 0.02)


def add_water_retention(layers: list[SoilLayer]) -> tuple[list[SoilLayer], bool]:
    """Fills theta_fc / theta_wp with Saxton & Rawls. mid = from the SoilGrids medians; low/high = OUR CHOICE:
    min/max of the equations over the Q0.05/Q0.95 combinations of sand, clay and organic matter (combinations
    with sand + clay > 100 % skipped). Returns (layers, True if any median is outside the fitted data range)."""
    outside = False
    out = []
    for L in layers:
        if None in (L.sand_pct, L.clay_pct, L.soc_g_kg):
            out.append(L)
            continue
        om = lambda soc: soc * OM_PER_SOC / 10.0  # noqa: E731 - g/kg C -> % OM
        mid = saxton_rawls(L.sand_pct.mid / 100, L.clay_pct.mid / 100, om(L.soc_g_kg.mid))
        outside |= om(L.soc_g_kg.mid) > SR_MAX_OM_PCT or L.clay_pct.mid > SR_MAX_CLAY_PCT
        combos = [mid]
        for s in (L.sand_pct.low, L.sand_pct.high):
            for c in (L.clay_pct.low, L.clay_pct.high):
                for o in (L.soc_g_kg.low, L.soc_g_kg.high):
                    if None not in (s, c, o) and s + c <= 100:
                        combos.append(saxton_rawls(s / 100, c / 100, om(o)))
        fc = [v[0] for v in combos]
        wp = [v[1] for v in combos]
        out.append(L.model_copy(update={
            "theta_fc": Range(low=round(min(fc), 4), mid=round(mid[0], 4), high=round(max(fc), 4)),
            "theta_wp": Range(low=round(min(wp), 4), mid=round(mid[1], 4), high=round(max(wp), 4)),
        }))
    return out, outside

_inflight: dict[str, asyncio.Task] = {}


class SoilGridsResult:
    def __init__(self, layers: list[SoilLayer], fetched_at: datetime, live: bool, url: str,
                 source_id: str = "soilgrids_rest", ptf_outside_range: bool = False):
        self.layers, self.fetched_at, self.live, self.url = layers, fetched_at, live, url
        self.source_id, self.ptf_outside_range = source_id, ptf_outside_range


def _key(lat: float, lon: float) -> str:
    return cache.make_key("geo.soilgrids", lat=round(lat, 5), lon=round(lon, 5))


def _files_key(lat: float, lon: float) -> str:
    return cache.make_key("geo.soilgrids.files", lat=round(lat, 5), lon=round(lon, 5))


def _files_record(lat: float, lon: float) -> dict:
    """Sync (worker thread): tile read -> REST-shaped record, cached."""
    raw = soilgrids_files.profile_raw(lat, lon, source("soilgrids_rest")["depths"])
    rec = {"lat": round(lat, 5), "lon": round(lon, 5), "fetched_at": datetime.now(timezone.utc).isoformat(),
           "response": soilgrids_files.as_rest_payload(raw)}
    cache.set(_files_key(lat, lon), rec)
    return rec


def _result(rec: dict, live: bool, url: str, source_id: str) -> SoilGridsResult:
    layers, outside = add_water_retention(parse_layers(rec["response"]))
    return SoilGridsResult(layers, datetime.fromisoformat(rec["fetched_at"]), live, url, source_id, outside)


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
    """Layers for the point, or None if not available within budget_s (a REST fetch then continues in background).
    Raises the upstream error if both the tile reads and the REST call failed within the budget."""
    t0 = asyncio.get_running_loop().time()
    rest_url = source("soilgrids_rest")["url"]
    files_url = source("soilgrids_files")["url"]
    rec = _preprocessed(lat, lon)
    if rec is not None:
        return _result(rec, False, rest_url, "soilgrids_rest")
    rec = cache.get(_key(lat, lon))
    if rec is not None:
        return _result(rec, True, rest_url, "soilgrids_rest")
    rec = cache.get(_files_key(lat, lon))
    if rec is not None:
        return _result(rec, True, files_url, "soilgrids_files")
    try:
        rec = await asyncio.wait_for(asyncio.to_thread(_files_record, lat, lon), timeout=max(budget_s, 0.1))
        return _result(rec, True, files_url, "soilgrids_files")
    except asyncio.TimeoutError:
        return None          # the thread finishes and fills the cache for the next analysis
    except Exception:  # noqa: BLE001 - tiles unreadable: REST fallback
        pass
    task = _start(lat, lon)
    try:
        rec = await wait_shared(task, timeout=budget_s - (asyncio.get_running_loop().time() - t0))
    except asyncio.TimeoutError:
        return None
    return _result(rec, True, rest_url, "soilgrids_rest")


async def fetch_blocking(lat: float, lon: float) -> dict:
    """For scripts/a/prefetch_soilgrids.py: wait for the REST answer, return the raw record."""
    return await _fetch_and_cache(lat, lon)


def wod_mm(layers: list[SoilLayer], depth_cm: int = 100) -> Range | None:
    """Σ (θFC − θWP) × thickness over 0..depth_cm, in mm (θ in m3/m3 from add_water_retention, thickness in mm).

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
