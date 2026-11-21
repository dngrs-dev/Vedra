"""Profile RealGeoProvider.collect per source: cold (empty cache) and warm (same requests again).

Usage (from backend/):
    python -m scripts.a.profile_collect                       # all test parcels x fixture dates
    python -m scripts.a.profile_collect --no-preprocessed     # ignore data/a/** (the path of an unseen parcel)
    python -m scripts.a.profile_collect --parcels 3 --dates 2023-05-31 --out profile.json

Targets (docs/PART_A_DATA_GEO.md CP4): p95 of collect <= 22 s cold, <= 3 s warm. The cache directory is a fresh
temporary one unless CACHE_DIR is set, so the first pass is really cold. Runs are sequential, as one worker would
serve them; background work left by one run (Sentinel-2 scenes, NMT) keeps going during the next ones.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

os.environ.setdefault("CACHE_DIR", tempfile.mkdtemp(prefix="vedra-profile-cache-"))  # before app.core.cache

import numpy as np  # noqa: E402

from app.contracts.geo import GeoRequest  # noqa: E402
from app.core import http  # noqa: E402
from app.geo import dem, sentinel2, soilgrids, uldk, vegetation  # noqa: E402
from app.geo.provider import RealGeoProvider  # noqa: E402
from app.geo.sources import BACKEND  # noqa: E402

SOURCES = ("soil", "vegetation", "terrain", "hydro", "landcover", "edo", "imgw")


def disable_preprocessed() -> None:
    sentinel2._preprocessed = lambda: {}                                     # type: ignore[assignment]
    soilgrids._preprocessed = lambda lat, lon: None                          # type: ignore[assignment]
    dem.preprocessed_path = lambda parcel: Path(os.devnull) / "none.tif"     # type: ignore[assignment]


async def run_pass(label: str, requests: list[GeoRequest]) -> list[dict]:
    geo = RealGeoProvider()
    rows = []
    for req in requests:
        t = time.monotonic()
        bundle = await geo.collect(req)
        total = time.monotonic() - t
        row = {"pass": label, "parcel_id": req.parcel.parcel_id, "date": req.analysis_date.isoformat(),
               "collect_s": round(total, 3)}
        for name in SOURCES:
            res = getattr(bundle, name)
            row[name] = {"status": res.status.value, "elapsed_s": res.elapsed_s, "error": res.error,
                         "notes_pl": res.notes_pl}
        rows.append(row)
        print(f"  {label:4} {req.parcel.parcel_id:28} {req.analysis_date}  {total:5.1f} s  " + "  ".join(
            f"{n}={row[n]['status'][0]}{row[n]['elapsed_s'] or 0:.1f}" for n in SOURCES), flush=True)
        for n in SOURCES:
            if row[n]["status"] == "missing" and row[n]["error"]:
                print(f"         {n}: {row[n]['error'][:160]}", flush=True)
    return rows


def summary(rows: list[dict], label: str) -> dict:
    sel = [r for r in rows if r["pass"] == label]
    out = {}
    for key in ("collect_s", *SOURCES):
        vals = np.array([r[key] if key == "collect_s" else (r[key]["elapsed_s"] or 0.0) for r in sel])
        out[key] = {"p50": round(float(np.percentile(vals, 50)), 2), "p95": round(float(np.percentile(vals, 95)), 2),
                    "max": round(float(vals.max()), 2)}
    for name in SOURCES:
        statuses = [r[name]["status"] for r in sel]
        out[name]["status"] = {s: statuses.count(s) for s in ("ok", "partial", "missing") if s in statuses}
    return out


async def main(n: int | None, dates: list[date], deadline: float, out: Path | None, no_pre: bool) -> int:
    if no_pre:
        disable_preprocessed()
    parcels = json.loads((BACKEND / "tests" / "fixtures" / "parcels.json").read_text(encoding="utf-8"))[:n]
    resolved = [await uldk.get_by_id(p["parcel_id"]) for p in parcels]   # parcel lookup is not part of collect
    requests = [GeoRequest(parcel=p, analysis_date=d, deadline_s=deadline) for p in resolved for d in dates]
    print(f"cache {os.environ['CACHE_DIR']}; preprocessed data {'off' if no_pre else 'on'}; {len(requests)} runs")
    rows = await run_pass("cold", requests)
    rows += await run_pass("warm", requests)
    result = {"preprocessed": not no_pre, "deadline_s": deadline, "runs": rows,
              "summary": {p: summary(rows, p) for p in ("cold", "warm")}}
    for p in ("cold", "warm"):
        print(f"\n{p}: " + "  ".join(f"{k} p95={v['p95']}" for k, v in result["summary"][p].items()))
    if out:
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    await http.close()
    vegetation.shutdown_background()
    return 0


if __name__ == "__main__":
    today = datetime.now(ZoneInfo("Europe/Warsaw")).date()
    ap = argparse.ArgumentParser()
    ap.add_argument("--parcels", type=int, default=None)
    ap.add_argument("--dates", nargs="*", type=date.fromisoformat,
                    default=[today, date(2018, 7, 10), date(2023, 5, 31)])
    ap.add_argument("--deadline", type=float, default=22.0)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--no-preprocessed", action="store_true")
    a = ap.parse_args()
    code = asyncio.run(main(a.parcels, a.dates, a.deadline, a.out, a.no_preprocessed))
    sys.stdout.flush()
    os._exit(code)   # do not wait for background scene reads (see scripts/a/run_geo.py)
