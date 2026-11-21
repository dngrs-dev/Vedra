"""Preprocess SoilGrids for the test parcels -> data/a/soilgrids_points.json (+ data/a/manifest.json).

Usage (from backend/):  python -m scripts.a.prefetch_soilgrids [--attempts 3]

The SoilGrids REST API answers in minutes (or 504s), far beyond the 22 s geo budget, so the responses for
the points the provider will query (app.geo.geometry.query_point of each parcel in
tests/fixtures/parcels.json) are fetched once here and stored verbatim with their fetch time.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

for _var in ("PROJ_LIB", "GDAL_DATA"):  # see scripts/a/spike_sources.py
    os.environ.pop(_var, None)

from app.core import http  # noqa: E402
from app.geo import geometry, soilgrids, uldk  # noqa: E402
from app.geo.sources import BACKEND, DATA_DIR, source  # noqa: E402

MANIFEST = DATA_DIR / "manifest.json"


def _load(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


async def main(attempts: int) -> int:
    parcels = json.loads((BACKEND / "tests" / "fixtures" / "parcels.json").read_text(encoding="utf-8"))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    records = _load(soilgrids.PREPROCESSED_FILE, [])
    have = {(r["lat"], r["lon"]) for r in records}
    failed = 0
    for p in parcels:
        parcel = await uldk.get_by_id(p["parcel_id"])
        lat, lon = geometry.query_point(parcel)
        if (lat, lon) in have:
            print(f"  have   {parcel.parcel_id} ({lat}, {lon})")
            continue
        for attempt in range(1, attempts + 1):
            t = datetime.now(timezone.utc)
            try:
                rec = await soilgrids.fetch_blocking(lat, lon)
            except Exception as exc:  # noqa: BLE001 - retry, report
                print(f"  fail   {parcel.parcel_id} attempt {attempt}: {type(exc).__name__}: {str(exc)[:120]}")
                continue
            rec["parcel_id"] = parcel.parcel_id
            records.append(rec)
            have.add((lat, lon))
            soilgrids.PREPROCESSED_FILE.write_text(json.dumps(records, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"  ok     {parcel.parcel_id} ({lat}, {lon}) in {(datetime.now(timezone.utc) - t).total_seconds():.0f} s")
            break
        else:
            failed += 1
    manifest = _load(MANIFEST, {})
    manifest["soilgrids_points.json"] = {
        "url": source("soilgrids_rest")["url"],
        "downloaded": datetime.now(timezone.utc).date().isoformat(),
        "licence": source("soilgrids_rest")["licence"],
        "content": "raw SoilGrids 2.0 /properties/query responses for query_point() of each test parcel",
        "script": "scripts/a/prefetch_soilgrids.py",
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    await http.close()
    print(f"{len(records)} points stored, {failed} parcels failed")
    return 1 if failed else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--attempts", type=int, default=3)
    sys.exit(asyncio.run(main(ap.parse_args().attempts)))
