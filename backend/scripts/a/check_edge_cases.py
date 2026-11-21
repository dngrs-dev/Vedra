"""Live CP4 edge cases: real forest / water / built-up / very large parcels and a date in 2016.

Usage (from backend/): python -m scripts.a.check_edge_cases [--deadline 22]

Parcels are found with ULDK GetParcelByXY at the points below (ids are never typed by hand) and written to
tests/a/data/edge_parcels.json; each bundle goes to tests/a/data/edge_bundles/<id>__<date>.json and is validated
offline by tests/a/test_edge_cases.py::test_edge_bundles. The points are well-known places picked so the parcel
under them is of the named kind; the WorldCover shares printed for each run show what the parcel really is.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import date

from app.contracts.geo import GeoRequest
from app.core import http
from app.geo import uldk, vegetation
from app.geo.provider import RealGeoProvider
from app.geo.sources import BACKEND

OUT = BACKEND / "tests" / "a" / "data"
POINTS = [  # (kind, place, lat, lon)
    ("forest", "Puszcza Kampinoska", 52.330, 20.550),
    ("water", "Jezioro Śniardwy (bardzo duża działka)", 53.750, 21.730),
    ("built_up", "Warszawa, Plac Defilad", 52.2318, 21.0060),
    ("built_up", "Kraków, Rynek Główny", 50.0617, 19.9373),
]
DAY = date(2023, 5, 31)
EARLY = ("040704_2.0012.63/1", date(2016, 12, 15))   # a test parcel at the start of the Sentinel-2 L2A archive


async def run(geo: RealGeoProvider, parcel, day: date, deadline: float) -> dict:
    t = time.monotonic()
    bundle = await geo.collect(GeoRequest(parcel=parcel, analysis_date=day, deadline_s=deadline))
    total = time.monotonic() - t
    path = OUT / "edge_bundles" / f"{parcel.parcel_id.replace('/', '-')}__{day.isoformat()}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"parcel": parcel.model_dump(mode="json"), "bundle": bundle.model_dump(mode="json")},
                               ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\n{parcel.parcel_id} ({parcel.area_ha} ha, {parcel.commune}) {day}: collect {total:.1f} s")
    for name, res in bundle:
        print(f"  {name:11} {res.status.value:8} {res.elapsed_s or 0:5.1f} s  {res.error or ''}"[:200])
        for n in res.notes_pl:
            print(f"      - {n}"[:240])
    if bundle.landcover.data:
        print("  landcover parcel:", bundle.landcover.data.shares_parcel)
    if bundle.soil.data:
        print("  soil:", bundle.soil.data.soil_type_code, bundle.soil.data.kbw_category,
              bundle.soil.data.category_source)
    return {"parcel_id": parcel.parcel_id, "date": day.isoformat(), "collect_s": round(total, 2),
            "status": {n: r.status.value for n, r in bundle}}


async def main(deadline: float) -> int:
    geo = RealGeoProvider()
    found = []
    for kind, place, lat, lon in POINTS:
        p = await uldk.get_by_xy(lat, lon)
        if p is None:
            print(f"no parcel at {place} ({lat}, {lon})")
            continue
        found.append({"kind": kind, "place": place, "lat": lat, "lon": lon, "parcel_id": p.parcel_id,
                      "area_ha": p.area_ha, "source": "ULDK GetParcelByXY"})
        await run(geo, p, DAY, deadline)
    (OUT / "edge_parcels.json").write_text(json.dumps(found, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    await run(geo, await uldk.get_by_id(EARLY[0]), EARLY[1], deadline)
    await http.close()
    vegetation.shutdown_background()
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--deadline", type=float, default=22.0)
    a = ap.parse_args()
    code = asyncio.run(main(a.deadline))
    sys.stdout.flush()
    os._exit(code)   # do not wait for background scene reads (see scripts/a/run_geo.py)
