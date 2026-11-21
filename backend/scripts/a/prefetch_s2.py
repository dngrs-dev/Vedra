"""Preprocess Sentinel-2 scene statistics for the test parcels -> data/a/s2_scene_stats.json (+ manifest).

Usage (from backend/):
    python -m scripts.a.prefetch_s2                       # all parcels x fixture dates
    python -m scripts.a.prefetch_s2 --dates 2023-05-31 --parcels 3

Each clear scene costs ~4 MB of COG tiles (see config/geo_sources.yaml sentinel2_processing), so a cold
analysis can read only a fraction of the ~50-70 scenes within the 22 s budget. This script runs the same
vegetation code with a long budget and stores every scene x parcel-interior result, so the test parcels are
complete in any deployment. Values are computed exactly as at runtime (app.geo.sentinel2.scene_stats).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.contracts.geo import GeoRequest
from app.core import http
from app.geo import sentinel2, uldk, vegetation
from app.geo.sources import BACKEND, DATA_DIR, source

MANIFEST = DATA_DIR / "manifest.json"


async def main(n_parcels: int | None, dates: list[date], budget: float) -> int:
    parcels = json.loads((BACKEND / "tests" / "fixtures" / "parcels.json").read_text(encoding="utf-8"))
    if n_parcels is not None:
        parcels = parcels[:n_parcels]
    out = BACKEND / sentinel2.s2_params()["preprocessed_stats_file"]
    stored = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    for p in parcels:
        parcel = await uldk.get_by_id(p["parcel_id"])
        for day in dates:
            t = time.monotonic()
            res = await vegetation.vegetation_data(parcel, GeoRequest(parcel=parcel, analysis_date=day), budget)
            d = res.data
            print(f"  {parcel.parcel_id} {day}: {res.status.value} "
                  f"{d.scenes_processed if d else 0}/{d.scenes_considered if d else 0} scenes "
                  f"in {time.monotonic() - t:.0f} s")
            stored.update(sentinel2.computed)
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(stored, sort_keys=True) + "\n", encoding="utf-8")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    manifest["s2_scene_stats.json"] = {
        "url": f"{source('earth_search')['url']} (collections {source('earth_search')['collections']['primary']}, "
               f"{source('earth_search')['collections']['fallback']})",
        "downloaded": datetime.now(timezone.utc).date().isoformat(),
        "licence": source("earth_search")["licence"],
        "content": "per scene x parcel-interior NDVI/NDMI medians computed by app.geo.sentinel2.scene_stats "
                   "for the test parcels and fixture dates; key = scene_id|sha1(interior geometry)[:16]",
        "script": "scripts/a/prefetch_s2.py",
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    await http.close()
    vegetation.shutdown_background()
    print(f"{len(stored)} scene results stored in {out.relative_to(BACKEND)}")
    return 0


if __name__ == "__main__":
    today = datetime.now(ZoneInfo("Europe/Warsaw")).date()
    ap = argparse.ArgumentParser()
    ap.add_argument("--parcels", type=int, default=None)
    ap.add_argument("--dates", nargs="*", type=date.fromisoformat,
                    default=[today, date(2018, 7, 10), date(2023, 5, 31)])
    ap.add_argument("--budget", type=float, default=1800.0)
    a = ap.parse_args()
    sys.exit(asyncio.run(main(a.parcels, a.dates, a.budget)))
