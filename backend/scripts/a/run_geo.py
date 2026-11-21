"""CLI: python -m scripts.a.run_geo <parcel query> <YYYY-MM-DD> [--deadline 22] [--json]

Prints the GeoBundle for a parcel and date with per-source status and timings. The query may be a full
parcel id, «obręb number» or «lat,lon» (first match is used).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import date

for _var in ("PROJ_LIB", "GDAL_DATA"):  # see scripts/a/spike_sources.py
    os.environ.pop(_var, None)

from app.contracts.geo import GeoRequest  # noqa: E402
from app.core import http  # noqa: E402
from app.geo.provider import RealGeoProvider  # noqa: E402


async def main(query: str, day: date, deadline: float, as_json: bool) -> int:
    geo = RealGeoProvider()
    t = time.monotonic()
    parcels = await geo.find_parcels(query)
    t_find = time.monotonic() - t
    parcel = parcels[0]
    t = time.monotonic()
    bundle = await geo.collect(GeoRequest(parcel=parcel, analysis_date=day, deadline_s=deadline))
    t_collect = time.monotonic() - t
    await http.close()
    if as_json:
        print(json.dumps({"parcel": parcel.model_dump(mode="json"), "bundle": bundle.model_dump(mode="json")},
                         ensure_ascii=False, indent=2))
        return 0
    print(f"parcel  {parcel.parcel_id}  {parcel.region} {parcel.parcel_number}, {parcel.commune}, "
          f"{parcel.voivodeship}; {parcel.area_ha} ha  (find {t_find:.2f} s, {len(parcels)} match(es))")
    print(f"collect {t_collect:.2f} s (deadline {deadline} s)")
    for name, res in bundle:
        print(f"  {name:11} {res.status.value:8} {res.elapsed_s or 0:6.2f} s  error={res.error}")
        for n in res.notes_pl:
            print(f"      - {n}")
    if bundle.soil.data:
        print("\nsoil:", json.dumps(bundle.soil.data.model_dump(mode="json", exclude={"layers"}), ensure_ascii=False))
        print(f"      layers: {len(bundle.soil.data.layers)}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("date", type=date.fromisoformat)
    ap.add_argument("--deadline", type=float, default=22.0)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    sys.exit(asyncio.run(main(a.query, a.date, a.deadline, a.json)))
